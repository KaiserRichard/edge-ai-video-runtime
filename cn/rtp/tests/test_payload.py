from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rtp.packet import RTPPacket
from rtp.payload import FrameReassembler, decode_fragment, encode_fragment, fragment_jpeg


def test_fragmentation_reorder_duplicate_and_reassembly():
    jpeg = bytes(range(73))
    packets = fragment_jpeg(jpeg, 42, 24, seq_start=65534, rtp_ts=9000, ssrc=7)
    assert len(packets) > 2
    assert all(len(p.payload) <= 24 for p in packets)
    assert packets[-1].marker and not any(p.marker for p in packets[:-1])
    rx = FrameReassembler(timeout=2)
    result = None
    for p in [packets[-1], packets[0], packets[0], *packets[1:-1]]:
        result = rx.add(p, now=0.1) or result
    assert result == (42, jpeg)


def test_reports_missing_range_for_lost_packet_in_five_packet_frame():
    packets = fragment_jpeg(bytes(range(64)), 8, 24, rtp_ts=99, ssrc=3)
    assert len(packets) == 5
    rx = FrameReassembler()
    for p in packets[:2] + packets[3:]:
        rx.add(p, now=0)
    missing = rx.missing(3, 99)
    assert missing == [(packets[2].payload[4] << 16 |
                        int.from_bytes(packets[2].payload[5:7], "big"),
                        packets[3].payload[4] << 16 |
                        int.from_bytes(packets[3].payload[5:7], "big"))]


def test_expiry_drops_partial_frame():
    p = fragment_jpeg(b"abc" * 20, 2, 20, rtp_ts=11, ssrc=5)[0]
    rx = FrameReassembler(timeout=0.5)
    assert rx.add(p, now=1) is None
    assert rx.expire(1.49) == []
    assert rx.expire(1.5) == [(5, 11)]


def test_payload_header_round_trip():
    data = encode_fragment(0x12345678, 0x123456, b"jpg", first=True, total_length=23)
    frag = decode_fragment(data)
    assert (frag.frame_id, frag.frag_offset, frag.flags, frag.total_length, frag.data) == (
        0x12345678, 0x123456, 1, 23, b"jpg")
