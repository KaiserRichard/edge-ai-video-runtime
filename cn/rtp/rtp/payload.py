"""JPEG-over-RTP payload helpers for the project 8-byte payload header.

The format is project-specific (not RFC 2435): frame id u32, JPEG byte offset
u24, flags u8; the first fragment prepends the full JPEG length as u32.
"""

from dataclasses import dataclass, field
import struct
from typing import Dict, Iterable, Optional, Tuple

from .packet import RTPPacket

PAYLOAD_HEADER_SIZE = 8
FLAG_FIRST = 1


@dataclass(frozen=True)
class Fragment:
    frame_id: int
    frag_offset: int
    flags: int
    total_length: Optional[int]
    data: bytes


def encode_fragment(frame_id: int, frag_offset: int, data: bytes, *, first: bool = False,
                    total_length: Optional[int] = None) -> bytes:
    if not 0 <= frame_id <= 0xffffffff or not 0 <= frag_offset <= 0xffffff:
        raise ValueError("frame_id or fragment offset out of range")
    prefix = b""
    if first:
        if total_length is None or not 0 <= total_length <= 0xffffffff:
            raise ValueError("first fragment requires a u32 total_length")
        prefix = struct.pack("!I", total_length)
    elif total_length is not None:
        raise ValueError("total_length is carried only by the first fragment")
    return struct.pack("!I", frame_id) + frag_offset.to_bytes(3, "big") + bytes([FLAG_FIRST if first else 0]) + prefix + bytes(data)


def decode_fragment(payload: bytes) -> Fragment:
    if len(payload) < PAYLOAD_HEADER_SIZE:
        raise ValueError("payload shorter than project header")
    frame_id = struct.unpack_from("!I", payload)[0]
    offset = int.from_bytes(payload[4:7], "big")
    flags = payload[7]
    first = bool(flags & FLAG_FIRST)
    if first:
        if len(payload) < PAYLOAD_HEADER_SIZE + 4:
            raise ValueError("first fragment missing total-length prefix")
        total = struct.unpack_from("!I", payload, PAYLOAD_HEADER_SIZE)[0]
        data = payload[PAYLOAD_HEADER_SIZE + 4:]
    else:
        total, data = None, payload[PAYLOAD_HEADER_SIZE:]
    return Fragment(frame_id, offset, flags, total, data)


def fragment_jpeg(jpeg: bytes, frame_id: int, mtu_payload: int, *, seq_start: int = 0,
                  rtp_ts: int = 0, ssrc: int = 0, payload_type: int = 96) -> list[RTPPacket]:
    """Split a JPEG into RTP packets whose RTP payload is <= mtu_payload bytes."""
    jpeg = bytes(jpeg)
    if mtu_payload <= PAYLOAD_HEADER_SIZE + 4:
        raise ValueError("mtu_payload must leave room for header, first length, and JPEG data")
    if len(jpeg) > 0xffffffff or len(jpeg) > 0x1000000:
        raise ValueError("JPEG length exceeds payload format range")
    packets = []
    offset = 0
    while offset < len(jpeg) or not packets:
        first = offset == 0
        room = mtu_payload - PAYLOAD_HEADER_SIZE - (4 if first else 0)
        chunk = jpeg[offset:offset + room]
        payload = encode_fragment(frame_id, offset, chunk, first=first,
                                  total_length=len(jpeg) if first else None)
        last = offset + len(chunk) == len(jpeg)
        packets.append(RTPPacket(payload, (seq_start + len(packets)) & 0xffff,
                                 rtp_ts & 0xffffffff, ssrc & 0xffffffff,
                                 payload_type, last))
        offset += len(chunk)
    return packets


@dataclass
class _Frame:
    started: float
    fragments: Dict[int, bytes] = field(default_factory=dict)
    total_length: Optional[int] = None
    marker_end: Optional[int] = None


class FrameReassembler:
    """Reassemble fragments by (SSRC, RTP timestamp), tolerating reordering/duplicates."""
    def __init__(self, timeout: float = 1.0):
        if timeout < 0:
            raise ValueError("timeout must be nonnegative")
        self.timeout = timeout
        self._frames: Dict[Tuple[int, int], _Frame] = {}

    def add(self, packet: RTPPacket, now: float = 0.0) -> Optional[Tuple[int, bytes]]:
        frag = decode_fragment(packet.payload)
        key = (packet.ssrc, packet.timestamp)
        frame = self._frames.setdefault(key, _Frame(now))
        if frag.total_length is not None:
            if frame.total_length is not None and frame.total_length != frag.total_length:
                raise ValueError("conflicting total frame lengths")
            frame.total_length = frag.total_length
        previous = frame.fragments.get(frag.frag_offset)
        if previous is not None and previous != frag.data:
            raise ValueError("conflicting duplicate fragment")
        frame.fragments[frag.frag_offset] = frag.data
        if packet.marker:
            frame.marker_end = frag.frag_offset + len(frag.data)
        total = frame.total_length
        if total is None or frame.marker_end is None or total != frame.marker_end:
            return None
        pos, chunks = 0, []
        for start, data in sorted(frame.fragments.items()):
            if start != pos:
                return None
            chunks.append(data)
            pos += len(data)
        if pos != total:
            return None
        result = b"".join(chunks)
        del self._frames[key]
        return frag.frame_id, result

    def missing(self, ssrc: int, rtp_ts: int) -> list[Tuple[int, int]]:
        """Return missing JPEG byte ranges once the final extent is known."""
        frame = self._frames.get((ssrc, rtp_ts))
        if frame is None:
            return []
        end = frame.total_length if frame.total_length is not None else frame.marker_end
        if end is None:
            return []
        missing, cursor = [], 0
        for start, data in sorted(frame.fragments.items()):
            if start > cursor:
                missing.append((cursor, start))
            cursor = max(cursor, start + len(data))
        if cursor < end:
            missing.append((cursor, end))
        return missing

    def expire(self, now: float) -> list[Tuple[int, int]]:
        """Drop frames at/after timeout; return their (SSRC, RTP timestamp) keys."""
        expired = [key for key, frame in self._frames.items() if now - frame.started >= self.timeout]
        for key in expired:
            del self._frames[key]
        return expired

    def drop_expired(self, now: float) -> list[Tuple[int, int]]:
        return self.expire(now)


Reassembler = FrameReassembler
