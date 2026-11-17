import struct
import sys
from pathlib import Path

import pytest

# The ticket scope creates only rtcp.py, so expose its directory for this test run.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rtp"))

from rtcp import (
    AppAirs,
    Bye,
    RTCPError,
    ReceiverReport,
    ReportBlock,
    Sdes,
    SenderReport,
    build_compound,
    dlsr_from_seconds,
    fixed_rtcp_interval,
    lsr_from_ntp,
    ntp_from_monotonic,
    parse_compound,
    parse_packet,
    rtcp_interval,
    rtt_ms,
)


def test_sr_round_trip_and_monotonic_wallclock_mapping():
    sr = SenderReport(0x12345678, 0xE123456789ABCDEF, 0xABCDEF01, 123, 456)
    assert parse_packet(sr.encode()) == sr
    # At the mapping instant the result is the Unix epoch expressed as NTP.
    assert ntp_from_monotonic(50, 50, 0) == (2_208_988_800 << 32)


def test_rr_and_report_block_round_trip_negative_cumulative_lost():
    report = ReportBlock(2, 7, -2, 0x12345678, 99, 0x87654321, 655)
    rr = ReceiverReport(1, (report,))
    wire = rr.encode()
    assert wire[13:16] == b"\xff\xff\xfe"
    assert parse_packet(wire) == rr


def test_sdes_cname_round_trip():
    packet = Sdes(((0x01020304, "camera-a@example"),))
    assert parse_packet(packet.encode()) == packet


def test_bye_round_trip_with_reason():
    packet = Bye((0x01020304, 0xAABBCCDD), "session ended")
    assert parse_packet(packet.encode()) == packet


def test_airs_app_round_trip():
    packet = AppAirs(1, 0x12345678, 99, 1000, 87, 123456)
    assert parse_packet(packet.encode()) == packet
    assert packet.encode()[8:12] == b"AIRS"


def test_compound_packet_and_32_bit_padding():
    sr = SenderReport(1, 2, 3, 4, 5)
    compound = build_compound((sr, Sdes(((1, "cname"),)), AppAirs(1, 3, 4, 5, 6, 7)), padding=4)
    assert len(compound) % 4 == 0
    assert parse_compound(compound) == (sr, Sdes(((1, "cname"),)), AppAirs(1, 3, 4, 5, 6, 7))


def test_rtt_hand_worked_example_in_1_over_65536_second_units():
    # Sender A=3.0 s, receiver reports LSR=1.25 s and DLSR=0.5 s.
    a = 3 * 65536
    lsr = int(1.25 * 65536)
    dlsr = dlsr_from_seconds(0.5)
    assert dlsr == 32768
    assert rtt_ms(a, lsr, dlsr) == pytest.approx(1250.0)
    assert lsr_from_ntp(0x123456789ABCDEF0) == 0x56789ABC


def test_interval_helpers_fixed_and_randomized():
    assert fixed_rtcp_interval() == 1.0
    assert rtcp_interval(1, 10, 100, random_value=1.0) == pytest.approx(5 / (2.718281828459045 - 1.5))


@pytest.mark.parametrize("packet", [
    SenderReport(1, 2, 3, 4, 5).encode(),
    ReceiverReport(1).encode(),
    Sdes(((1, "x"),)).encode(),
])
def test_rejects_packet_length_that_claims_more_bytes(packet):
    malformed = packet[:2] + struct.pack("!H", 0xFFFF) + packet[4:]
    with pytest.raises(RTCPError):
        parse_packet(malformed)


def test_rejects_truncated_or_malformed_compound_packet():
    with pytest.raises(RTCPError):
        parse_compound(ReceiverReport(1).encode()[:-1])
    with pytest.raises(RTCPError):
        parse_compound(Sdes(((1, "x"),)).encode())

