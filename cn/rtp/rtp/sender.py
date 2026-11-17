"""Paced JPEG/RTP sender; run with PYTHONPATH=rtp python -m rtp.sender.

CSV bytes count complete RTP datagrams (including RTP/payload headers). n_pkts
and send times include seeded simulated drops, i.e. attempts before the loss
injector. SR counters count those same packets and RTP payload octets, as if the
injector were a lossy network. Existing JPEG sources leave quality empty.
"""
from __future__ import annotations

import argparse
import errno
from collections import OrderedDict, deque
from contextlib import ExitStack
import io
import math
from pathlib import Path
import random
import secrets
import select
import socket
import time

from .payload import fragment_jpeg
from .playout import CLOCK_RATE, CsvLog
from .abr import AimdController
from .rtcp import (AppAirs, Bye, ReceiverReport, SenderReport, Sdes, build_compound,
                   fixed_rtcp_interval, lsr_from_ntp, ntp_from_monotonic,
                   parse_compound, rtt_ms)
from .sources import open_source
from .telemetry import add_arguments, from_arguments

SENDER_FIELDS = "frame_id,rtp_ts,seq_first,seq_last,n_pkts,bytes,quality,t_capture_mono_ns,t_send_first_mono_ns,t_send_last_mono_ns".split(",")
RESULT_FIELDS = "frame_id,rtp_ts,t_capture_mono_ns,t_result_rx_mono_ns,class_id".split(",")
RTCP_FIELDS = "t_mono_ns,dir,type,ssrc,fraction_lost,cum_lost,ext_high_seq,jitter,lsr,dlsr,rtt_ms".split(",")


def open_udp_pair(host, port):
    """RFC 3550 §11: RTCP port = even RTP port + 1; port 0 allocates a pair."""
    if port and (port < 1024 or port > 65534 or port % 2):
        raise ValueError("RTP port must be even and in 1024..65534, or 0")
    for _ in range(128):
        rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtcp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            rtp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
            rtp.bind((host, port))
            actual = rtp.getsockname()[1]
            if actual % 2 or actual == 65535:
                rtp.close()
                rtcp.close()
                continue
            rtcp.bind((host, actual + 1))
            rtp.setblocking(False)
            rtcp.setblocking(False)
            return rtp, rtcp
        except OSError as exc:
            rtp.close()
            rtcp.close()
            if port or exc.errno != errno.EADDRINUSE:
                raise
    raise OSError("unable to allocate an adjacent even RTP/RTCP UDP pair")


def log_rtcp(log, packet, direction, now_ns, *, sender_ssrc=None, a_units=None, known_lsr=None,
             telemetry=None):
    """One CSV event per report block; leave nonapplicable fields empty."""
    kind = {SenderReport: "SR", ReceiverReport: "RR", AppAirs: "APP", Bye: "BYE", Sdes: "SDES"}[type(packet)]
    if isinstance(packet, Sdes):
        ssrcs = [ssrc for ssrc, _ in packet.chunks]
    elif isinstance(packet, Bye):
        ssrcs = packet.ssrcs
    else:
        ssrcs = [packet.ssrc]
    reports = getattr(packet, "reports", ())
    if reports:
        for report in reports:
            rtt = None
            if (a_units is not None and report.ssrc == sender_ssrc
                    and report.lsr and (known_lsr is None or report.lsr in known_lsr)):
                # RFC 3550 §6.4.1: A - LSR - DLSR, all in 1/65536 s.
                rtt = rtt_ms(a_units, report.lsr, report.dlsr)
            log.write(t_mono_ns=now_ns, dir=direction, type=kind, ssrc=report.ssrc,
                      fraction_lost=report.fraction_lost, cum_lost=report.cumulative_lost,
                      ext_high_seq=report.ext_high_seq, jitter=report.jitter,
                      lsr=report.lsr, dlsr=report.dlsr, rtt_ms=rtt)
            if telemetry is not None:
                data = dict(kind=kind, direction=direction, fraction_lost=report.fraction_lost,
                            cumulative_lost=report.cumulative_lost, jitter_ms=report.jitter / 90)
                if rtt is not None:
                    data["rtt_ms"] = rtt
                telemetry.emit("rtcp", data)
    else:
        for ssrc in ssrcs:
            log.write(t_mono_ns=now_ns, dir=direction, type=kind, ssrc=ssrc)
        if telemetry is not None:
            telemetry.emit("rtcp", dict(kind=kind, direction=direction))


def parse_drop_steps(value):
    """Parse comma-separated application drop schedule entries (time_s:prob)."""
    try:
        steps = tuple((float(pair.split(":", 1)[0]), float(pair.split(":", 1)[1]))
                      for pair in value.split(","))
    except (ValueError, IndexError) as exc:
        raise ValueError(f"invalid --drop-steps: {exc}") from exc
    if (not steps or any(not math.isfinite(t) or not math.isfinite(p) or t < 0 or
                         not 0 <= p <= 1 for t, p in steps) or
            any(steps[i][0] >= steps[i + 1][0] for i in range(len(steps) - 1))):
        raise ValueError("drop steps need increasing finite times and probabilities in 0..1")
    return steps


class Sender:
    def __init__(self, source, out_dir, *, host="127.0.0.1", port=5004,
                 bind="0.0.0.0", local_port=0, fps=15.0, mtu_payload=1200,
                 rtcp_interval=1.0, drop_prob=0.0, seed=1, ssrc=None,
                 seq_start=None, timestamp_offset=None, rtcp_filename="rtcp.csv",
                 abr="fixed", drop_steps=None, telemetry=None):
        self.telemetry = telemetry
        self.telemetry_bytes = deque()
        self.telemetry_next_ns = 0
        self.telemetry_quality = None
        if not math.isfinite(fps) or not 0 < fps <= 1000:
            raise ValueError("fps must be finite and in (0,1000]")
        if not 0 <= drop_prob <= 1 or not 13 <= mtu_payload <= 65507 - 12:
            raise ValueError("invalid drop probability or RTP payload MTU")
        if not 1024 <= port <= 65534 or port % 2:
            raise ValueError("destination RTP port must be even and in 1024..65534")
        if not math.isfinite(rtcp_interval):
            raise ValueError("RTCP interval must be finite")
        self.interval_ns = round(fixed_rtcp_interval(rtcp_interval) * 1e9)
        self.source, self.fps, self.mtu_payload = source, fps, mtu_payload
        if abr not in ("fixed", "aimd"):
            raise ValueError("abr must be fixed or aimd")
        self.abr = abr
        initial_quality = getattr(source, "quality", 75)
        self.controller = AimdController(initial_quality) if abr == "aimd" else None
        # SyntheticSource re-encodes each frame at mutable dimensions. SHM's
        # dimensions also size its native pixel buffer, so do not resize it here.
        self.base_dimensions = ((getattr(source, "width", None), getattr(source, "height", None))
                                if hasattr(source, "draw_module") else (None, None))
        self.source_scales_resolution = self.base_dimensions[0] is not None
        self.drop_steps = tuple(drop_steps or ())
        if any(not math.isfinite(t) or not math.isfinite(p) or t < 0 or p < 0 or p > 1
               for t, p in self.drop_steps):
            raise ValueError("drop steps require nonnegative times and probabilities in 0..1")
        if any(self.drop_steps[i][0] >= self.drop_steps[i + 1][0]
               for i in range(len(self.drop_steps) - 1)):
            raise ValueError("drop step times must be strictly increasing")
        self.destination = (socket.gethostbyname(host), port)
        self.control_destination = (self.destination[0], port + 1)
        self.drop_prob, self.rng = drop_prob, random.Random(seed)
        self.ssrc = secrets.randbits(32) if ssrc is None else ssrc
        self.seq = secrets.randbits(16) if seq_start is None else seq_start
        self.timestamp_offset = secrets.randbits(32) if timestamp_offset is None else timestamp_offset
        self.resources = ExitStack()
        try:
            self.rtp, self.rtcp = open_udp_pair(bind, local_port)
            self.resources.callback(self.rtp.close)
            self.resources.callback(self.rtcp.close)
            self.logs = {}
            for name, fields in (("sender", SENDER_FIELDS), ("results_tx", RESULT_FIELDS)):
                self.logs[name] = CsvLog(Path(out_dir) / (name + ".csv"), fields)
                self.resources.callback(self.logs[name].close)
            self.logs["rtcp"] = CsvLog(Path(out_dir) / rtcp_filename, RTCP_FIELDS)
            self.resources.callback(self.logs["rtcp"].close)
        except BaseException:
            self.resources.close()
            raise
        self.resources.callback(source.close)
        self.mapping_mono = time.monotonic_ns()
        self.mapping_wall = time.time_ns()
        self.packet_count = self.octet_count = self.frames_sent = 0
        self.captures = OrderedDict()
        self.sent_reports = OrderedDict()
        self.result_keys = set()
        self.run_start_ns = None

    def _apply_decision(self, report, now_ns):
        """Apply RR adaptation to source settings before its next capture."""
        decision = self.controller.update(report.fraction_lost, report.jitter)
        if hasattr(self.source, "quality"):
            self.source.quality = decision.quality
        base_width, base_height = self.base_dimensions
        if base_width is not None and base_height is not None:
            self.source.width = max(1, round(base_width * decision.resolution_scale))
            self.source.height = max(1, round(base_height * decision.resolution_scale))
        self.logs["rtcp"].write(t_mono_ns=now_ns, dir="local", type="ABR", ssrc=self.ssrc,
            fraction_lost=report.fraction_lost, jitter=report.jitter,
            rtt_ms=None, lsr=None, dlsr=None, cum_lost=None, ext_high_seq=None)
        if self.telemetry is not None:
            self.telemetry.emit("rtcp", dict(kind="ABR", direction="local",
                fraction_lost=report.fraction_lost, jitter_ms=report.jitter / 90))
            self.telemetry_quality = getattr(self.source, "quality", decision.quality)
            self._emit_status(now_ns, decision=decision.action)

    def _emit_status(self, now_ns, decision=None):
        if self.telemetry is None:
            return
        while self.telemetry_bytes and self.telemetry_bytes[0][0] <= now_ns - 1_000_000_000:
            self.telemetry_bytes.popleft()
        if decision is None and now_ns < self.telemetry_next_ns:
            return
        data = dict(bitrate_mbps=sum(n for _, n in self.telemetry_bytes) * 8 / 1e6,
                    fps=self.fps)
        if self.telemetry_quality is not None:
            data["quality"] = self.telemetry_quality
        if decision is not None:
            data["decision"] = decision if decision in ("up", "down") else "hold"
        self.telemetry.emit("sender", data)
        self.telemetry_next_ns = now_ns + 100_000_000

    def _drop_probability(self, now_ns):
        if not self.drop_steps:
            return self.drop_prob
        elapsed_s = (now_ns - (self.run_start_ns or now_ns)) / 1e9
        probability = self.drop_steps[0][1]
        for at_s, value in self.drop_steps:
            if elapsed_s < at_s:
                break
            probability = value
        return probability

    def timestamp(self, capture_ns):
        # RFC 3550 §5.1: media sampling instant, in 90 kHz units, random offset.
        return (capture_ns * CLOCK_RATE // 1_000_000_000 + self.timestamp_offset) & 0xffffffff

    def send_frame(self, frame):
        timestamp = self.timestamp(frame.t_capture_mono_ns)
        jpeg = frame.jpeg
        quality = frame.quality
        if self.controller is not None and not self.source_scales_resolution:
            # Re-encode replay/pipe/camera JPEGs because those sources do not
            # expose dynamic dimensions to their capture path.
            from PIL import Image
            with Image.open(io.BytesIO(jpeg)) as image:
                scale = self.controller.resolution_scale
                if scale != 1.0:
                    size = (max(1, round(image.width * scale)),
                            max(1, round(image.height * scale)))
                    image = image.resize(size)
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=self.controller.quality)
                jpeg = output.getvalue()
            quality = self.controller.quality
        packets = fragment_jpeg(jpeg, frame.frame_id, self.mtu_payload,
                                seq_start=self.seq, rtp_ts=timestamp, ssrc=self.ssrc)
        first_ns = None
        byte_count = 0
        for packet in packets:
            wire = packet.pack()
            now = time.monotonic_ns()
            if first_ns is None:
                first_ns = now
            if self.rng.random() >= self._drop_probability(now):
                self.rtp.sendto(wire, self.destination)
                if self.telemetry is not None:
                    self.telemetry_bytes.append((now, len(wire)))
            self.packet_count += 1
            self.octet_count += len(packet.payload)
            byte_count += len(wire)
        self.seq = (packets[-1].seq + 1) & 0xffff
        key = frame.frame_id, timestamp
        self.captures[key] = frame.t_capture_mono_ns
        # Bound capture/result bookkeeping for long camera streams.
        if len(self.captures) > 65536:
            old, _ = self.captures.popitem(last=False)
            self.result_keys.discard(old)
        self.logs["sender"].write(frame_id=frame.frame_id, rtp_ts=timestamp,
            seq_first=packets[0].seq, seq_last=packets[-1].seq, n_pkts=len(packets),
            bytes=byte_count, quality=quality, t_capture_mono_ns=frame.t_capture_mono_ns,
            t_send_first_mono_ns=first_ns, t_send_last_mono_ns=now)
        self.frames_sent += 1
        self.telemetry_quality = quality
        self._emit_status(now)

    def send_report(self, *, bye=False):
        now = time.monotonic_ns()
        ntp = ntp_from_monotonic(now, self.mapping_mono, self.mapping_wall)
        report = SenderReport(self.ssrc, ntp, self.timestamp(now),
                              self.packet_count & 0xffffffff, self.octet_count & 0xffffffff)
        packets = [report, Sdes(((self.ssrc, f"sender-{self.ssrc:08x}"),))]
        if bye:
            packets.append(Bye((self.ssrc,), "end of stream"))
        self.rtcp.sendto(build_compound(packets), self.control_destination)
        self.sent_reports[lsr_from_ntp(ntp)] = now
        if len(self.sent_reports) > 4096:
            self.sent_reports.popitem(last=False)
        for packet in packets:
            log_rtcp(self.logs["rtcp"], packet, "tx", now, telemetry=self.telemetry)

    def receive_control(self):
        # Bound a batch so incoming control cannot starve pacing/shutdown.
        for _ in range(256):
            try:
                data, peer = self.rtcp.recvfrom(65535)
            except BlockingIOError:
                break
            now = time.monotonic_ns()
            if peer != self.control_destination:
                continue
            try:
                packets = parse_compound(data)
            except ValueError:
                continue
            a = lsr_from_ntp(ntp_from_monotonic(now, self.mapping_mono, self.mapping_wall))
            for packet in packets:
                log_rtcp(self.logs["rtcp"], packet, "rx", now, sender_ssrc=self.ssrc,
                         a_units=a, known_lsr=self.sent_reports, telemetry=self.telemetry)
                if isinstance(packet, AppAirs):
                    key = packet.frame_id, packet.rtp_ts
                    if key in self.captures and key not in self.result_keys:
                        self.result_keys.add(key)
                        self.logs["results_tx"].write(frame_id=packet.frame_id, rtp_ts=packet.rtp_ts,
                            t_capture_mono_ns=self.captures[key], t_result_rx_mono_ns=now,
                            class_id=packet.class_id)
                        if self.telemetry is not None:
                            self.telemetry.emit("result", dict(frame_id=packet.frame_id,
                                rtp_ts=packet.rtp_ts, latency_ms=(now - self.captures[key]) / 1e6))
                elif isinstance(packet, ReceiverReport) and self.controller is not None:
                    for report in packet.reports:
                        if report.ssrc == self.ssrc:
                            self._apply_decision(report, now)

    def run(self, duration=10.0, *, drain_seconds=1.2):
        if not math.isfinite(duration) or duration <= 0 or not math.isfinite(drain_seconds) or drain_seconds < 0:
            raise ValueError("duration must be positive and drain_seconds nonnegative, both finite")
        start = time.monotonic_ns()
        self.run_start_ns = start
        capture_end = start + round(duration * 1e9)
        end = capture_end + round(drain_seconds * 1e9)
        next_capture = next_report = start
        period = round(1e9 / self.fps)
        while (now := time.monotonic_ns()) < end:
            self.receive_control()
            now = time.monotonic_ns()
            self._emit_status(now)
            if now < capture_end and now >= next_capture:
                try:
                    frame = self.source.read(timeout=min(0.01, (capture_end - now) / 1e9))
                except EOFError:
                    capture_end = now
                    end = now + round(drain_seconds * 1e9)
                    frame = None
                if frame is not None:
                    self.send_frame(frame)
                    next_capture += period
                    # Skip missed releases instead of bursting accumulated camera frames.
                    after = time.monotonic_ns()
                    if next_capture < after:
                        next_capture += ((after - next_capture) // period + 1) * period
                else:
                    next_capture = time.monotonic_ns() + 1_000_000
            now = time.monotonic_ns()
            if now >= next_report:
                self.send_report()
                next_report = now + self.interval_ns
            wake = min(end, next_report, next_capture if now < capture_end else end)
            select.select([self.rtcp], [], [], max(0.0, min(0.02, (wake - now) / 1e9)))
        self.send_report(bye=True)
        self.receive_control()
        return self.frames_sent

    def close(self):
        self.resources.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5004)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--local-port", type=int, default=0)
    parser.add_argument("--source", default="synthetic")
    parser.add_argument("--jpeg-dir")
    parser.add_argument("--shm-library")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--quality", type=int, default=75)
    parser.add_argument("--fps", type=float, default=15)
    parser.add_argument("--duration", type=float, default=10)
    parser.add_argument("--drain-seconds", type=float, default=1.2)
    parser.add_argument("--mtu-payload", type=int, default=1200)
    parser.add_argument("--rtcp-interval", type=float, default=1)
    parser.add_argument("--drop-prob", type=float, default=0)
    parser.add_argument("--drop-steps", help='time_s:prob pairs, e.g. "0:0,20:0.05"')
    parser.add_argument("--abr", choices=("fixed", "aimd"), default="fixed")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--rtcp-csv", default="rtcp.csv")
    add_arguments(parser, 5006)
    args = parser.parse_args(argv)
    source = open_source(args.source, quality=args.quality, width=args.width, height=args.height,
                         jpeg_dir=args.jpeg_dir, shm_library=args.shm_library)
    drop_steps = None
    if args.drop_steps is not None:
        try:
            drop_steps = parse_drop_steps(args.drop_steps)
        except ValueError as exc:
            parser.error(f"invalid --drop-steps: {exc}")
    sender = telemetry = None
    try:
        telemetry = from_arguments(args, parser, "pi")
        sender = Sender(source, args.out_dir, host=args.host, port=args.port,
            bind=args.bind, local_port=args.local_port, fps=args.fps, mtu_payload=args.mtu_payload,
            rtcp_interval=args.rtcp_interval, drop_prob=args.drop_prob, seed=args.seed,
            rtcp_filename=args.rtcp_csv, abr=args.abr, drop_steps=drop_steps, telemetry=telemetry)
        count = sender.run(args.duration, drain_seconds=args.drain_seconds)
        print(f"sent {count} frames, {sender.packet_count} RTP packet attempts", flush=True)
    finally:
        if sender is not None:
            sender.close()
        else:
            source.close()
        if telemetry is not None:
            telemetry.close()


if __name__ == "__main__":
    main()
