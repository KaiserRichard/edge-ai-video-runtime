"""Small RFC 3550 RTCP wire-format helpers (standard library only).

Times passed to the conversion helpers are integer nanoseconds. Packet classes
encode and decode individual RTCP packets; ``build_compound`` and
``parse_compound`` handle compound packets.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import struct
import time
from typing import Iterable, Sequence


class RTCPError(ValueError):
    """Malformed or unsupported RTCP data."""


VERSION = 2
PT_SR, PT_RR, PT_SDES, PT_BYE, PT_APP = 200, 201, 202, 203, 204
NTP_UNIX_EPOCH = 2_208_988_800


def _u32(value: int, name: str) -> int:
    if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{name} must be an unsigned 32-bit integer")
    return value


def _header(packet_type: int, count: int, body: bytes, padding: int = 0) -> bytes:
    if not 0 <= count <= 31:
        raise ValueError("RTCP count/subtype must be in 0..31")
    if padding:
        if not 1 <= padding <= 255:
            raise ValueError("padding must be in 1..255")
        body += b"\0" * (padding - 1) + bytes((padding,))
    packet = struct.pack("!BBH", (VERSION << 6) | (0x20 if padding else 0) | count,
                         packet_type, (len(body) + 4) // 4 - 1) + body
    if len(packet) % 4:
        raise ValueError("RTCP packet is not aligned to 32-bit words")
    return packet


def _unpack_header(data: bytes, offset: int = 0) -> tuple[int, int, bool, int, int]:
    if len(data) - offset < 4:
        raise RTCPError("truncated RTCP header")
    b0, pt, length = struct.unpack_from("!BBH", data, offset)
    if b0 >> 6 != VERSION:
        raise RTCPError("unsupported RTCP version")
    count, padding = b0 & 31, bool(b0 & 0x20)
    size = (length + 1) * 4
    if size < 4 or offset + size > len(data):
        raise RTCPError("RTCP length exceeds available data")
    end = offset + size
    if padding:
        pad_count = data[end - 1]
        if pad_count == 0 or pad_count > size - 4:
            raise RTCPError("invalid RTCP padding length")
        body_end = end - pad_count
    else:
        body_end = end
    return count, pt, padding, offset + 4, body_end


@dataclass(frozen=True)
class ReportBlock:
    ssrc: int
    fraction_lost: int
    cumulative_lost: int
    ext_high_seq: int
    jitter: int
    lsr: int
    dlsr: int

    def encode(self) -> bytes:
        _u32(self.ssrc, "ssrc")
        for n, v in (("fraction_lost", self.fraction_lost), ("ext_high_seq", self.ext_high_seq),
                     ("jitter", self.jitter), ("lsr", self.lsr), ("dlsr", self.dlsr)):
            if not 0 <= v <= 0xFFFFFFFF:
                raise ValueError(f"{n} out of range")
        if self.fraction_lost > 255:
            raise ValueError("fraction_lost must fit in 8 bits")
        if not -(1 << 23) <= self.cumulative_lost < (1 << 23):
            raise ValueError("cumulative_lost must fit signed 24-bit")
        lost = self.cumulative_lost & 0xFFFFFF
        return (struct.pack("!IB", self.ssrc, self.fraction_lost) + lost.to_bytes(3, "big") +
                struct.pack("!IIII", self.ext_high_seq, self.jitter, self.lsr, self.dlsr))

    @classmethod
    def decode(cls, data: bytes) -> "ReportBlock":
        if len(data) != 24:
            raise RTCPError("report block must be exactly 24 bytes")
        ssrc, fraction = struct.unpack_from("!IB", data)
        lost = int.from_bytes(data[5:8], "big")
        if lost & 0x800000:
            lost -= 1 << 24
        ext, jitter, lsr, dlsr = struct.unpack_from("!IIII", data, 8)
        return cls(ssrc, fraction, lost, ext, jitter, lsr, dlsr)


def _blocks(blocks: Sequence[ReportBlock]) -> bytes:
    if len(blocks) > 31:
        raise ValueError("at most 31 report blocks are allowed")
    return b"".join(x.encode() for x in blocks)


@dataclass(frozen=True)
class SenderReport:
    ssrc: int
    ntp_timestamp: int
    rtp_timestamp: int
    packet_count: int
    octet_count: int
    reports: tuple[ReportBlock, ...] = ()

    def encode(self) -> bytes:
        for n, v in (("ssrc", self.ssrc), ("rtp_timestamp", self.rtp_timestamp),
                     ("packet_count", self.packet_count), ("octet_count", self.octet_count)):
            _u32(v, n)
        if not 0 <= self.ntp_timestamp <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("ntp_timestamp must fit in 64 bits")
        return _header(PT_SR, len(self.reports), struct.pack("!IQIII", self.ssrc,
            self.ntp_timestamp, self.rtp_timestamp, self.packet_count, self.octet_count) + _blocks(self.reports))

    @classmethod
    def decode(cls, data: bytes) -> "SenderReport":
        count, pt, _, start, end = _unpack_header(data)
        if pt != PT_SR or end - start != 24 + count * 24:
            raise RTCPError("invalid SR packet length or type")
        ssrc, ntp, rtp, packets, octets = struct.unpack_from("!IQIII", data, start)
        reports = tuple(ReportBlock.decode(data[i:i+24]) for i in range(start + 24, end, 24))
        return cls(ssrc, ntp, rtp, packets, octets, reports)


@dataclass(frozen=True)
class ReceiverReport:
    ssrc: int
    reports: tuple[ReportBlock, ...] = ()

    def encode(self) -> bytes:
        _u32(self.ssrc, "ssrc")
        return _header(PT_RR, len(self.reports), struct.pack("!I", self.ssrc) + _blocks(self.reports))

    @classmethod
    def decode(cls, data: bytes) -> "ReceiverReport":
        count, pt, _, start, end = _unpack_header(data)
        if pt != PT_RR or end - start != 4 + count * 24:
            raise RTCPError("invalid RR packet length or type")
        ssrc = struct.unpack_from("!I", data, start)[0]
        reports = tuple(ReportBlock.decode(data[i:i+24]) for i in range(start + 4, end, 24))
        return cls(ssrc, reports)


@dataclass(frozen=True)
class Sdes:
    chunks: tuple[tuple[int, str], ...]

    def encode(self) -> bytes:
        if not 1 <= len(self.chunks) <= 31:
            raise ValueError("SDES requires 1..31 chunks")
        body = bytearray()
        for ssrc, cname in self.chunks:
            _u32(ssrc, "ssrc")
            value = cname.encode("utf-8")
            if not value or len(value) > 255:
                raise ValueError("CNAME must encode to 1..255 bytes")
            body += struct.pack("!I", ssrc) + bytes((1, len(value))) + value + b"\0"
            body += b"\0" * (-len(body) % 4)
        return _header(PT_SDES, len(self.chunks), bytes(body))

    @classmethod
    def decode(cls, data: bytes) -> "Sdes":
        count, pt, _, start, end = _unpack_header(data)
        if pt != PT_SDES or count == 0:
            raise RTCPError("invalid SDES type or chunk count")
        chunks = []
        pos = start
        for _ in range(count):
            if pos + 4 > end:
                raise RTCPError("truncated SDES chunk")
            ssrc = struct.unpack_from("!I", data, pos)[0]
            pos += 4
            cname = None
            while True:
                if pos >= end:
                    raise RTCPError("missing SDES end item")
                item_type = data[pos]
                pos += 1
                if item_type == 0:
                    pos += (-pos) % 4
                    break
                if pos >= end:
                    raise RTCPError("truncated SDES item length")
                size = data[pos]
                pos += 1
                if pos + size > end:
                    raise RTCPError("truncated SDES item")
                value = data[pos:pos+size]
                pos += size
                if item_type == 1:
                    try:
                        cname = value.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise RTCPError("invalid UTF-8 CNAME") from exc
            if cname is None:
                raise RTCPError("SDES chunk has no CNAME")
            chunks.append((ssrc, cname))
        if pos != end:
            raise RTCPError("unexpected bytes after SDES chunks")
        return cls(tuple(chunks))


@dataclass(frozen=True)
class Bye:
    ssrcs: tuple[int, ...]
    reason: str | None = None

    def encode(self) -> bytes:
        if not 1 <= len(self.ssrcs) <= 31:
            raise ValueError("BYE requires 1..31 SSRCs")
        body = bytearray(b"".join(struct.pack("!I", _u32(x, "ssrc")) for x in self.ssrcs))
        if self.reason is not None:
            reason = self.reason.encode("utf-8")
            if len(reason) > 255:
                raise ValueError("BYE reason must be at most 255 bytes")
            body += bytes((len(reason),)) + reason
            body += b"\0" * (-len(body) % 4)
        return _header(PT_BYE, len(self.ssrcs), bytes(body))

    @classmethod
    def decode(cls, data: bytes) -> "Bye":
        count, pt, _, start, end = _unpack_header(data)
        if pt != PT_BYE or count == 0 or end - start < count * 4:
            raise RTCPError("invalid BYE packet length or type")
        ssrcs = struct.unpack_from("!" + "I" * count, data, start)
        pos = start + count * 4
        reason = None
        if pos < end:
            size = data[pos]
            pos += 1
            if pos + size > end:
                raise RTCPError("truncated BYE reason")
            try:
                reason = data[pos:pos+size].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RTCPError("invalid UTF-8 BYE reason") from exc
            pos += size
            if any(data[pos:end]):
                raise RTCPError("nonzero BYE alignment bytes")
        return cls(tuple(ssrcs), reason)


@dataclass(frozen=True)
class AppAirs:
    ssrc: int
    rtp_ts: int
    frame_id: int
    class_id: int
    confidence: int
    t_done_edge_us: int

    def encode(self) -> bytes:
        _u32(self.ssrc, "ssrc")
        for n, v in (("rtp_ts", self.rtp_ts), ("frame_id", self.frame_id), ("t_done_edge_us", self.t_done_edge_us)):
            _u32(v, n)
        if not 0 <= self.class_id <= 0xFFFF or not 0 <= self.confidence <= 255:
            raise ValueError("class_id/confidence out of range")
        body = struct.pack("!I4sIIHBBI", self.ssrc, b"AIRS", self.rtp_ts, self.frame_id,
                           self.class_id, self.confidence, 0, self.t_done_edge_us)
        return _header(PT_APP, 0, body)

    @classmethod
    def decode(cls, data: bytes) -> "AppAirs":
        count, pt, _, start, end = _unpack_header(data)
        if pt != PT_APP or count != 0 or end - start != 24:
            raise RTCPError("invalid AIRS APP packet length, subtype, or type")
        ssrc, name, rtp_ts, frame, class_id, conf, reserved, done = struct.unpack_from("!I4sIIHBBI", data, start)
        if name != b"AIRS" or reserved != 0:
            raise RTCPError("unknown APP name or nonzero reserved byte")
        return cls(ssrc, rtp_ts, frame, class_id, conf, done)


Packet = SenderReport | ReceiverReport | Sdes | Bye | AppAirs


def parse_packet(data: bytes) -> Packet:
    _, pt, _, _, _ = _unpack_header(data)
    declared_size = (struct.unpack_from("!H", data, 2)[0] + 1) * 4
    if declared_size != len(data):
        raise RTCPError("RTCP packet length does not match supplied data")
    decoder = {PT_SR: SenderReport, PT_RR: ReceiverReport, PT_SDES: Sdes,
               PT_BYE: Bye, PT_APP: AppAirs}.get(pt)
    if decoder is None:
        raise RTCPError(f"unsupported RTCP packet type {pt}")
    return decoder.decode(data)


def build_compound(packets: Iterable[Packet], padding: int = 0) -> bytes:
    packets = tuple(packets)
    if not packets or not isinstance(packets[0], (SenderReport, ReceiverReport)):
        raise ValueError("compound RTCP must begin with SR or RR")
    encoded = [p.encode() for p in packets]
    if padding:
        # RTCP padding is on the final packet only; adjust its length field.
        raw = encoded[-1]
        count, pt, _, start, end = _unpack_header(raw)
        body = raw[start:end]
        encoded[-1] = _header(pt, count, body, padding)
    return b"".join(encoded)


def parse_compound(data: bytes) -> tuple[Packet, ...]:
    if not data or len(data) % 4:
        raise RTCPError("compound RTCP must be nonempty and 32-bit aligned")
    packets = []
    pos = 0
    while pos < len(data):
        count, pt, padding, _, _ = _unpack_header(data, pos)
        length = struct.unpack_from("!H", data, pos + 2)[0]
        size = (length + 1) * 4
        if padding and pos + size != len(data):
            raise RTCPError("only the final packet in a compound packet may be padded")
        packets.append(parse_packet(data[pos:pos+size]))
        pos += size
    if not packets or not isinstance(packets[0], (SenderReport, ReceiverReport)):
        raise RTCPError("compound RTCP must begin with SR or RR")
    return tuple(packets)


def ntp_from_monotonic(monotonic_ns: int, mapping_monotonic_ns: int,
                       mapping_wallclock_ns: int) -> int:
    """Convert monotonic ns using a supplied monotonic->Unix-wallclock mapping."""
    unix_ns = mapping_wallclock_ns + (monotonic_ns - mapping_monotonic_ns)
    sec, ns = divmod(unix_ns, 1_000_000_000)
    ntp_sec = sec + NTP_UNIX_EPOCH
    fraction = (ns << 32) // 1_000_000_000
    return ((ntp_sec & 0xFFFFFFFF) << 32) | fraction


def ntp_now_from_mapping(mapping_monotonic_ns: int, mapping_wallclock_ns: int,
                         now_monotonic_ns: int | None = None) -> int:
    return ntp_from_monotonic(time.monotonic_ns() if now_monotonic_ns is None else now_monotonic_ns,
                              mapping_monotonic_ns, mapping_wallclock_ns)


def lsr_from_ntp(ntp_timestamp: int) -> int:
    """Return the middle 32 bits of an NTP timestamp (RFC 3550 §6.4.1)."""
    if not 0 <= ntp_timestamp <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("NTP timestamp must fit in 64 bits")
    return (ntp_timestamp >> 16) & 0xFFFFFFFF


def dlsr_from_seconds(seconds: float) -> int:
    """Convert delay to 1/65536-second units (RFC 3550 §6.4.1)."""
    if seconds < 0:
        raise ValueError("delay cannot be negative")
    return min(0xFFFFFFFF, int(seconds * 65536))


def rtt_ms(a_units: int, lsr: int, dlsr: int) -> float | None:
    """Compute A−LSR−DLSR on the sender clock; return None for LSR=0."""
    if lsr == 0:
        return None
    delta = (a_units - lsr - dlsr) & 0xFFFFFFFF
    return delta * 1000.0 / 65536.0


def rtcp_interval(avg_packet_size: float, members: int, rtcp_bandwidth: float,
                  *, senders: int = 0, we_sent: bool = False,
                  initial: bool = False, random_value: float | None = None,
                  fixed_interval: float | None = None) -> float:
    """RFC 3550 §6.3.1 interval in seconds, with optional experiment override.

    Randomization uses 0.5–1.5 and compensation divides by e−1.5. The 5 s
    minimum (2.5 s for the initial interval) is scaled by the participant
    bandwidth allocation described in §6.3.1.
    """
    if fixed_interval is not None:
        if fixed_interval <= 0:
            raise ValueError("fixed_interval must be positive")
        return fixed_interval
    if avg_packet_size < 0 or members < 1 or rtcp_bandwidth <= 0 or senders < 0:
        raise ValueError("invalid RTCP interval inputs")
    if senders and senders <= members * 0.25:
        if we_sent:
            members = senders
            rtcp_bandwidth *= 0.25
        else:
            members -= senders
            rtcp_bandwidth *= 0.75
    t = avg_packet_size * members / rtcp_bandwidth
    minimum = 2.5 if initial else 5.0
    if senders and senders <= members * 0.25 and not we_sent:
        minimum *= 1 / 0.75
    t = max(minimum, t)
    r = random.uniform(0.5, 1.5) if random_value is None else random_value
    if not 0.5 <= r <= 1.5:
        raise ValueError("random_value must be in 0.5..1.5")
    return t * r / (math.e - 1.5)


def fixed_rtcp_interval(seconds: float = 1.0) -> float:
    """Fixed interval helper intended for controlled experiments."""
    return rtcp_interval(0, 1, 1, fixed_interval=seconds)
