import csv
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rtp.edge_ai import EdgeAI


def _rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_latest_replaces_waiting_frames_and_emits_results(tmp_path):
    path = tmp_path / "ai.csv"
    results = []
    edge = EdgeAI(
        "latest", "synthetic", 1,
        lambda *result: results.append(result),
        service_ms=60, ai_csv=path,
    )
    try:
        for frame_id in range(8):
            edge.submit(frame_id, frame_id * 3000, b"jpeg", time.monotonic_ns())
    finally:
        edge.close()

    rows = _rows(path)
    assert edge.skipped >= 6
    assert edge.max_waiting <= 1
    assert edge.completed + edge.skipped == 8
    assert len(results) == edge.completed
    assert sum(row["status"] == "skipped" for row in rows) == edge.skipped
    assert all(row["status"] in {"ok", "skipped"} for row in rows)
    assert all(result[3] == 255 for result in results)


def test_fifo_grows_to_capacity_then_skips_new_frames(tmp_path):
    edge = EdgeAI(
        "fifo", "synthetic", 1, lambda *_: None,
        service_ms=80, queue_size=3, ai_csv=tmp_path / "ai.csv",
    )
    try:
        for frame_id in range(12):
            edge.submit(frame_id, frame_id * 3000, b"jpeg", time.monotonic_ns())
        assert edge.max_waiting == 3
    finally:
        edge.close()
    assert edge.skipped >= 8
    assert edge.completed + edge.skipped == 12
    assert edge.max_waiting == 3


def test_invalid_policy_and_closed_submit(tmp_path):
    try:
        EdgeAI("random", "synthetic", 1, lambda *_: None,
               ai_csv=tmp_path / "invalid.csv")
    except ValueError as exc:
        assert "policy" in str(exc)
    else:
        raise AssertionError("invalid queue policy was accepted")

    edge = EdgeAI("fifo", "synthetic", 1, lambda *_: None,
                  ai_csv=tmp_path / "closed.csv")
    edge.close()
    try:
        edge.submit(1, 0, b"jpeg", time.monotonic_ns())
    except RuntimeError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("submit after close was accepted")
