"""Single-session RTP/RTCP receiver with a fixed receiver-clock playout buffer.

AI1 integration: set receiver.playout.callback = edge.submit, constructing edge
with send_result=receiver.send_result. Close/drain edge before receiver.close().
The callback signature is (frame_id, rtp_ts, jpeg_bytes, t_complete_rx_ns) and
must be nonblocking. Default: discard. AIRS may be sent from an AI worker thread.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import math
from pathlib import Path
import secrets
import select
import threading
import time

from .packet import RTPPacket
from .payload import decode_fragment
from .playout import CLOCK_RATE, FRAME_FIELDS, CsvLog, PlayoutBuffer, unwrap32
from .rtcp import (AppAirs, Bye, ReceiverReport, ReportBlock, SenderReport, Sdes,
                   build_compound, dlsr_from_seconds, fixed_rtcp_interval,
                   lsr_from_ntp, parse_compound)
from .rxstats import ReceiverStats
from .sender import RTCP_FIELDS, log_rtcp, open_udp_pair
from .telemetry import add_arguments, from_arguments

RECEIVER_FIELDS = "seq,rtp_ts,frame_id,marker,bytes,t_arrival_rx_ns,transit_ts_units,jitter_ts_units".split(",")


class Receiver:
    def __init__(self, out_dir, *, bind="127.0.0.1", port=5004,
                 playout_ms=100.0, late_window_ms=1000.0, rtcp_interval=1.0,
                 callback=None, ssrc=None, rtcp_filename="rtcp.csv", telemetry=None):
        self.telemetry = telemetry
        if not math.isfinite(rtcp_interval):
            raise ValueError("RTCP interval must be finite")
        self.interval_ns = round(fixed_rtcp_interval(rtcp_interval) * 1e9)
        self.ssrc = secrets.randbits(32) if ssrc is None else ssrc
        self.stats = ReceiverStats()
        self.peer = self.source_ssrc = self.last_sr = None
        self.timestamp_reference = None
        self.bye_received_ns = None
        self.packet_count = self.malformed = 0
        self.control_lock = threading.RLock()
        self.resources = ExitStack()
        try:
            self.rtp, self.rtcp = open_udp_pair(bind, port)
            self.resources.callback(self.rtp.close)
            self.resources.callback(self.rtcp.close)
            self.logs = {}
            for name, fields in (("receiver", RECEIVER_FIELDS), ("frames_rx", FRAME_FIELDS)):
                self.logs[name] = CsvLog(Path(out_dir) / (name + ".csv"), fields)
                self.resources.callback(self.logs[name].close)
            self.logs["rtcp"] = CsvLog(Path(out_dir) / rtcp_filename, RTCP_FIELDS)
            self.resources.callback(self.logs["rtcp"].close)
            self.playout = PlayoutBuffer(playout_ms, late_window_ms=late_window_ms,
                callback=callback, on_row=self._frame_row)
        except BaseException:
            self.resources.close()
            raise
        self.closed = False

    def _frame_row(self, row):
        self.logs["frames_rx"].write(**row)
        if self.telemetry is not None:
            data = dict(frame_id=row["frame_id"], rtp_ts=row["rtp_ts"], status=row["status"],
                        buffer_frames=len(self.playout.frames))
            if row["t_complete_rx_ns"] is not None:
                data["arrival_offset_ms"] = (row["t_complete_rx_ns"] - row["t_playout_rx_ns"]) / 1e6
            self.telemetry.emit("frame", data)

    @property
    def port(self):
        return self.rtp.getsockname()[1]

    def _accept_peer(self, peer, ssrc):
        if self.peer is None:
            self.peer, self.source_ssrc = peer, ssrc
        return self.peer == peer and self.source_ssrc == ssrc

    def receive_rtp(self):
        for _ in range(256):
            try:
                wire, peer = self.rtp.recvfrom(65535)
            except BlockingIOError:
                break
            now = time.monotonic_ns()
            try:
                packet = RTPPacket.parse(wire)
                fragment = decode_fragment(packet.payload)
                if packet.payload_type != 96 or not self._accept_peer(peer, packet.ssrc):
                    continue
                reference = self.timestamp_reference
                extended = packet.timestamp if reference is None else unwrap32(packet.timestamp, reference)
                self.timestamp_reference = extended if reference is None else max(reference, extended)
                # RTP1's update takes a u32 timestamp. Shift its arrival coordinate
                # by the same whole RTP epochs to keep §6.4.1/A.8 transit deltas
                # continuous across wrap; the CSV arrival stays the actual rx clock.
                epoch_ticks = extended - packet.timestamp
                arrival_ticks = now * CLOCK_RATE // 1_000_000_000 - epoch_ticks
                stats_arrival = (arrival_ticks * 1_000_000_000 + CLOCK_RATE - 1) // CLOCK_RATE
                self.stats.update(packet.ssrc, packet.seq, packet.timestamp, stats_arrival)
                stats = self.stats.sources[packet.ssrc]
                self.logs["receiver"].write(seq=packet.seq, rtp_ts=packet.timestamp,
                    frame_id=fragment.frame_id, marker=int(packet.marker), bytes=len(wire),
                    t_arrival_rx_ns=now, transit_ts_units=stats.transit, jitter_ts_units=stats.jitter)
                if self.telemetry is not None:
                    self.telemetry.emit("packet", dict(seq=packet.seq, rtp_ts=packet.timestamp,
                        frame_id=fragment.frame_id, bytes=len(wire), jitter_ms=stats.jitter / 90))
                self.packet_count += 1
                self.playout.add(packet, now)
            except ValueError:
                self.malformed += 1

    def receive_control(self):
        for _ in range(256):
            try:
                wire, peer = self.rtcp.recvfrom(65535)
            except BlockingIOError:
                break
            now = time.monotonic_ns()
            if self.peer is not None and peer != (self.peer[0], self.peer[1] + 1):
                continue
            try:
                packets = parse_compound(wire)
            except ValueError:
                self.malformed += 1
                continue
            if self.peer is None:
                first = packets[0]
                if not isinstance(first, SenderReport) or peer[1] < 2:
                    continue
                self._accept_peer((peer[0], peer[1] - 1), first.ssrc)
            with self.control_lock:
                for packet in packets:
                    log_rtcp(self.logs["rtcp"], packet, "rx", now, telemetry=self.telemetry)
                    if isinstance(packet, SenderReport) and packet.ssrc == self.source_ssrc:
                        self.last_sr = lsr_from_ntp(packet.ntp_timestamp), now
                    if isinstance(packet, Bye) and self.source_ssrc in packet.ssrcs:
                        self.bye_received_ns = now

    def _transmit_control(self, packets, now):
        if self.peer is None:
            return
        self.rtcp.sendto(build_compound(packets), (self.peer[0], self.peer[1] + 1))
        for packet in packets:
            log_rtcp(self.logs["rtcp"], packet, "tx", now, telemetry=self.telemetry)

    def send_report(self):
        with self.control_lock:
            now = time.monotonic_ns()
            blocks = ()
            if self.source_ssrc in self.stats.sources:
                report = self.stats.report(self.source_ssrc)
                lsr, dlsr = 0, 0
                if self.last_sr is not None:
                    lsr, arrival = self.last_sr
                    # RFC 3550 §6.4.1: delay since SR receipt, receiver clock only.
                    dlsr = dlsr_from_seconds((now - arrival) / 1e9)
                blocks = (ReportBlock(report.ssrc, report.fraction_lost, report.cumulative_lost,
                    report.extended_highest_seq & 0xffffffff, report.jitter, lsr, dlsr),)
            self._transmit_control([ReceiverReport(self.ssrc, blocks),
                Sdes(((self.ssrc, f"receiver-{self.ssrc:08x}"),))], now)

    def send_result(self, rtp_ts, frame_id, class_id, confidence, t_done_edge_us):
        """AI1 callable; confidence is the RTCP1 u8 wire value, not a float.

        Edge time is informational only. Sender matches (frame_id, rtp_ts) to
        its own capture time; no receiver timestamps enter latency subtraction.
        """
        with self.control_lock:
            if self.closed:
                raise RuntimeError("receiver is closed; close AI before the receiver")
            packet = AppAirs(self.ssrc, rtp_ts, frame_id, class_id, confidence,
                             t_done_edge_us & 0xffffffff)
            self._transmit_control([ReceiverReport(self.ssrc),
                Sdes(((self.ssrc, f"receiver-{self.ssrc:08x}"),)), packet], time.monotonic_ns())

    def run(self, duration=12.0, *, stop_event=None, exit_on_bye=False):
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("duration must be finite and positive")
        end = time.monotonic_ns() + round(duration * 1e9)
        next_report = time.monotonic_ns() + self.interval_ns
        while (now := time.monotonic_ns()) < end:
            if stop_event is not None and stop_event.is_set():
                break
            wake = min(end, next_report, self.playout.next_deadline_ns() or end)
            ready, _, _ = select.select([self.rtp, self.rtcp], [], [],
                max(0.0, min(0.02, (wake - now) / 1e9)))
            if self.rtp in ready:
                self.receive_rtp()
            if self.rtcp in ready:
                self.receive_control()
            now = time.monotonic_ns()
            self.playout.advance(now)
            if now >= next_report:
                self.send_report()
                next_report = now + self.interval_ns
            if exit_on_bye and self.bye_received_ns is not None:
                end = min(end, self.bye_received_ns + self.playout.delay_ns + self.playout.late_window_ns)
        self.playout.close(time.monotonic_ns())
        self.send_report()
        return self.packet_count

    def close(self):
        with self.control_lock:
            if not self.closed:
                self.playout.close(time.monotonic_ns())
                self.closed = True
                self.resources.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5004)
    parser.add_argument("--duration", type=float, default=12)
    parser.add_argument("--playout-ms", type=float, default=100)
    parser.add_argument("--late-window-ms", type=float, default=1000)
    parser.add_argument("--rtcp-interval", type=float, default=1)
    parser.add_argument("--exit-on-bye", action="store_true")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--rtcp-csv", default="rtcp.csv")
    parser.add_argument("--ai", choices=("off", "synthetic", "onnx"), default="off")
    parser.add_argument("--ai-policy", choices=("fifo", "latest"), default="latest")
    parser.add_argument("--ai-service-ms", type=float, default=0)
    parser.add_argument("--model", default="offline-bundle/mobilenetv2-12.onnx")
    parser.add_argument("--threads", type=int, default=1)
    add_arguments(parser, 5007)
    args = parser.parse_args(argv)
    receiver = edge = telemetry = None
    try:
        telemetry = from_arguments(args, parser, "receiver")
        receiver = Receiver(args.out_dir, bind=args.bind, port=args.port,
            playout_ms=args.playout_ms, late_window_ms=args.late_window_ms,
            rtcp_interval=args.rtcp_interval, rtcp_filename=args.rtcp_csv, telemetry=telemetry)
        if args.ai != "off":
            from .edge_ai import EdgeAI
            model = "synthetic" if args.ai == "synthetic" else args.model
            edge = EdgeAI(args.ai_policy, model, args.threads, receiver.send_result,
                          service_ms=args.ai_service_ms,
                          ai_csv=Path(args.out_dir) / "ai.csv", telemetry=telemetry)
            receiver.playout.callback = edge.submit
        print(f"READY RTP={receiver.port} RTCP={receiver.port + 1}", flush=True)
        count = receiver.run(args.duration, exit_on_bye=args.exit_on_bye)
        print(f"received {count} RTP packets; malformed={receiver.malformed}", flush=True)
    finally:
        if edge is not None:
            edge.close()
        if receiver is not None:
            receiver.close()
        if telemetry is not None:
            telemetry.close()


if __name__ == "__main__":
    main()
