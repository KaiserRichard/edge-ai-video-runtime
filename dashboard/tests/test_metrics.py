from dashboard.metrics import PacketStats
from dashboard.synthetic import QueueComparison, Synthetic


def packet(seq, ts=0):
    return dict(seq=seq, rtp_ts=ts)


def test_wrap_gaps_duplicates_and_late_recovery():
    stats = PacketStats()
    assert stats.update(packet(65534), 0)["sequence_lost"] == 0
    gap = stats.update(packet(1), .1)
    assert (gap["gap_start"], gap["gap_end"], gap["sequence_lost"]) == (65535, 65536, 2)
    recovered = stats.update(packet(0), .2)
    assert recovered["packet_status"] == "reordered"
    assert recovered["sequence_lost"] == 1
    assert stats.update(packet(0), .3)["packet_status"] == "duplicate"
    assert stats.update(packet(65535), .4)["sequence_lost"] == 0


def test_frame_jitter_ignores_intraframe_packets_and_handles_timestamp_wrap():
    tracker = PacketStats()
    tracker.update(packet(0, 2**32 - 3000), 1)
    tracker.update(packet(1, 2**32 - 3000), 1.01)
    assert tracker.frame_jitter == 0
    tracker.update(packet(2, 0), 1 + 1 / 30)
    assert tracker.frame_jitter < 1e-10
    tracker.update(packet(3, 3000), 1 + 2 / 30 + .016)
    assert abs(tracker.frame_jitter - 1) < 1e-8


def test_bounded_tracking_over_multiple_wraps():
    tracker = PacketStats()
    for seq in range(140000):
        result = tracker.update(packet(seq % 65536, seq % 2**32), seq / 90000)
    assert result["sequence_lost"] == 0
    assert result["extended_seq"] == 139999
    assert len(tracker.seen) <= 65536


def test_fair_fixed_service_queues():
    queues = QueueComparison(50)
    previous = 0
    for i in range(200):
        result = queues.advance(i / 10)
        assert 0 <= result["fifo_queue"] <= 8
        assert 0 <= result["latest_queue"] <= 1
        previous = result["latest_age_ms"]
    assert result["fifo_age_ms"] > result["latest_age_ms"] * 3
    assert previous < 150


def test_synthetic_is_seeded_and_covers_every_panel():
    a, b = Synthetic(11), Synthetic(11)
    kinds = set()
    states = set()
    for i in range(840):
        messages, _, _ = a.tick(i / 10)
        assert messages == b.tick(i / 10)[0]
        kinds.update(message["type"] for message in messages)
        states.update(message["data"]["state"] for message in messages if message["type"] == "os")
    assert kinds == {"packet", "frame", "ai", "result", "rtcp", "sender", "hardware", "queue", "os"}
    assert states == {"FRESH", "HOLD", "FAILSAFE"}
