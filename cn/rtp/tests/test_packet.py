import struct
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rtp.packet import RTPPacket, pack_packet, parse_packet


def test_round_trip_all_header_fields_and_csrc_marker():
    original = RTPPacket(b"payload", seq=65535, timestamp=0x12345678,
                         ssrc=0x90abcdef, payload_type=111, marker=True,
                         padding=False, csrc=(1, 0x10203040),
                         extension_profile=0xBEDE, extension_data=b"abcd")
    parsed = parse_packet(pack_packet(original))
    assert parsed == original


def test_parse_skips_extension_and_padding():
    p = RTPPacket(b"x", 2, 3, 4, padding=True, extension_profile=7,
                  extension_data=b"\x01\x02\x03\x04")
    wire = pack_packet(p)
    assert parse_packet(wire) == p


@pytest.mark.parametrize("wire", [b"", b"\x80" * 11, b"\x40" + b"\0" * 11])
def test_short_or_wrong_version_rejected(wire):
    with pytest.raises(ValueError):
        parse_packet(wire)


def test_truncated_csrc_extension_and_bad_padding_rejected():
    with pytest.raises(ValueError, match="CSRC"):
        parse_packet(struct.pack("!BBHII", 0x81, 0, 1, 2, 3))
    with pytest.raises(ValueError, match="extension"):
        parse_packet(struct.pack("!BBHII", 0x90, 0, 1, 2, 3))
    with pytest.raises(ValueError, match="padding"):
        parse_packet(struct.pack("!BBHII", 0xa0, 0, 1, 2, 3) + b"\0")
