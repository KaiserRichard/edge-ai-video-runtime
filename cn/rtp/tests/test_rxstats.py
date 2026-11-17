from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rtp.rxstats import SourceStats


def test_sequence_wrap_extends_highest_sequence():
    s = SourceStats(10)
    assert not s.update(65534, 0, 0)
    assert s.update(65535, 900, 10_000_000)
    assert s.update(0, 1800, 20_000_000)
    report = s.report(interval=False)
    assert report.extended_highest_seq == 65536
    assert report.expected == 2
    assert report.cumulative_lost == 0


def test_reorder_duplicate_and_five_packet_frame_loss_accounting():
    s = SourceStats(1)
    for seq in (10, 11, 13, 11, 14):
        s.update(seq, seq * 900, seq * 10_000_000)
    report = s.report(interval=False)
    assert report.expected == 4
    assert report.received == 4  # includes the reordered duplicate per RFC 3550 A.3
    assert report.cumulative_lost == 0
    lost = SourceStats(2)
    for seq in (10, 11, 13, 14, 15):
        lost.update(seq, seq * 900, seq * 10_000_000)
    report = lost.report(interval=False)
    assert report.expected == 5
    assert report.cumulative_lost == 1
    assert lost.report().fraction_lost == 51  # floor(1 * 256 / 5)


def test_probation_and_bad_sequence_restart():
    s = SourceStats(4)
    assert not s.update(100, 0, 0)
    assert s.update(101, 900, 10_000_000)
    assert not s.update(5000, 1800, 20_000_000)  # suspicious jump: set bad_seq
    assert s.update(5001, 2700, 30_000_000)  # sequential bad_seq confirms restart
    report = s.report(interval=False)
    assert report.expected == 1
    assert report.received == 1
    assert report.extended_highest_seq == 5001


def test_interarrival_jitter_hand_calculation_and_arrival_conversion():
    s = SourceStats(8)
    # At 90 kHz, arrivals at 0, 10, 30 ticks against RTP timestamps 0, 10, 20
    # give transit 0, 0, 10; hence J: 0 -> 0 -> 10/16 = 0.625 timestamp units.
    for seq, ts, arrival_ns in ((1, 0, 0), (2, 10, 111_112), (3, 20, 333_334)):
        s.update(seq, ts, arrival_ns)
    assert abs(s.jitter - 0.625) < 1e-9
    assert s.report(interval=False).jitter == 0
