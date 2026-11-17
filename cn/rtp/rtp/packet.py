"""RTP v2 packet encoding and decoding; fixed header per RFC 3550 section 5.1."""

from dataclasses import dataclass
import struct
from typing import Tuple


@dataclass(frozen=True)
class RTPPacket:
    payload: bytes
    seq: int
    timestamp: int
    ssrc: int
    payload_type: int = 96
    marker: bool = False
    padding: bool = False
    csrc: Tuple[int, ...] = ()
    extension_profile: int | None = None
    extension_data: bytes = b""

    def pack(self) -> bytes:
        return pack_packet(self)

    @classmethod
    def parse(cls, data: bytes) -> "RTPPacket":
        return parse_packet(data)


def pack_packet(packet: RTPPacket) -> bytes:
    if not 0 <= packet.payload_type <= 127:
        raise ValueError("payload_type must fit in 7 bits")
    if not 0 <= packet.seq <= 0xffff:
        raise ValueError("seq must fit in 16 bits")
    for name, value in (("timestamp", packet.timestamp), ("ssrc", packet.ssrc)):
        if not 0 <= value <= 0xffffffff:
            raise ValueError(f"{name} must fit in 32 bits")
    if len(packet.csrc) > 15:
        raise ValueError("at most 15 CSRC identifiers are allowed")
    extension = packet.extension_profile is not None
    if not extension and packet.extension_data:
        raise ValueError("extension_data requires extension_profile")
    ext = b""
    if extension:
        if not 0 <= packet.extension_profile <= 0xffff:
            raise ValueError("extension_profile must fit in 16 bits")
        extdata = bytes(packet.extension_data)
        extdata += b"\0" * (-len(extdata) % 4)
        ext = struct.pack("!HH", packet.extension_profile, len(extdata) // 4) + extdata
    first = (2 << 6) | (int(packet.padding) << 5) | (int(extension) << 4) | len(packet.csrc)
    second = (int(packet.marker) << 7) | packet.payload_type
    header = struct.pack("!BBHII", first, second, packet.seq, packet.timestamp, packet.ssrc)
    header += b"".join(struct.pack("!I", c) for c in packet.csrc)
    body = header + ext + bytes(packet.payload)
    if packet.padding:
        pad_len = (-(len(body) + 1)) % 4 + 1
        body += b"\0" * (pad_len - 1) + bytes([pad_len])
    return body


def parse_packet(data: bytes) -> RTPPacket:
    data = bytes(data)
    if len(data) < 12:
        raise ValueError("RTP packet shorter than fixed 12-byte header")
    first, second, seq, timestamp, ssrc = struct.unpack_from("!BBHII", data)
    version, padding, has_extension, cc = first >> 6, bool(first & 0x20), bool(first & 0x10), first & 0x0f
    if version != 2:
        raise ValueError(f"unsupported RTP version {version}")
    offset = 12 + 4 * cc
    if len(data) < offset:
        raise ValueError("truncated CSRC list")
    csrc = struct.unpack_from(f"!{cc}I", data, 12) if cc else ()
    extension_profile = None
    extension_data = b""
    if has_extension:
        if len(data) < offset + 4:
            raise ValueError("truncated RTP header extension header")
        extension_profile, words = struct.unpack_from("!HH", data, offset)
        offset += 4
        ext_len = words * 4
        if len(data) < offset + ext_len:
            raise ValueError("truncated RTP header extension data")
        extension_data = data[offset:offset + ext_len]
        offset += ext_len
    end = len(data)
    if padding:
        if end <= offset:
            raise ValueError("RTP padding flag set without padding bytes")
        pad_len = data[-1]
        if pad_len == 0 or pad_len > end - offset:
            raise ValueError("invalid RTP padding length")
        end -= pad_len
    return RTPPacket(data[offset:end], seq, timestamp, ssrc, second & 0x7f,
                     bool(second & 0x80), padding, tuple(csrc), extension_profile, extension_data)
