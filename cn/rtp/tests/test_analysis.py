import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "analysis"))
from metrics import aggregate_runs, compute_run_metrics, subtract_timestamps
from plots import plot_scenario


def _write_run(path, captures=(0, 1_000_000_000, 2_000_000_000)):
    path.mkdir(parents=True)
    pd.DataFrame({
        "frame_id": [1, 2, 3], "rtp_ts": [0, 90000, 180000],
        "seq_first": [100, 102, 104], "seq_last": [101, 103, 104],
        "n_pkts": [2, 2, 1], "bytes": [2000, 2000, 1000], "quality": [60] * 3,
        "t_capture_mono_ns": captures, "t_send_first_mono_ns": captures,
        "t_send_last_mono_ns": captures,
    }).to_csv(path / "sender.csv", index=False)
    pd.DataFrame({
        "seq": [100, 101, 103, 104], "rtp_ts": [0, 0, 90000, 180000],
        "frame_id": [1, 1, 2, 3], "marker": [0, 1, 1, 1], "bytes": [1000] * 4,
        "t_arrival_rx_ns": [1, 2, 3, 4], "transit_ts_units": [0] * 4,
        "jitter_ts_units": [0, 0, 45, 90],
    }).to_csv(path / "receiver.csv", index=False)
    pd.DataFrame({
        "frame_id": [1, 2, 3], "rtp_ts": [0, 90000, 180000],
        "n_expected": [2, 2, 1], "n_received": [2, 2, 0],
        "complete": [True, True, False], "t_complete_rx_ns": [10_000_000, 25_000_000, None],
        "t_playout_rx_ns": [11_000_000, 24_000_000, 30_000_000],
        "status": ["ok", "late", "lost"],
    }).to_csv(path / "frames_rx.csv", index=False)
    pd.DataFrame({"t_mono_ns": [1], "dir": ["rx"], "type": ["RR"], "ssrc": [1],
                  "fraction_lost": [51], "cum_lost": [1], "ext_high_seq": [104],
                  "jitter": [90], "lsr": [0], "dlsr": [0], "rtt_ms": [0]}).to_csv(
                      path / "rtcp.csv", index=False)
    pd.DataFrame({"frame_id": [1, 2, 3], "rtp_ts": [0, 90000, 180000],
                  "t_capture_mono_ns": captures,
                  "t_result_rx_mono_ns": [100_000_000, 1_200_000_000, 2_100_000_000],
                  "class_id": [1] * 3}).to_csv(path / "results_tx.csv", index=False)


def test_metrics_known_answers(tmp_path):
    run = tmp_path / "run1"
    _write_run(run)
    values = compute_run_metrics(run)
    assert values["packet_loss"] == pytest.approx(0.2)
    assert values["jitter_ms"] == pytest.approx(1.0)
    assert values["frame_loss"] == pytest.approx(1 / 3)
    assert values["on_time_ratio"] == pytest.approx(1 / 3)
    assert values["goodput_bps"] == pytest.approx(16_000)
    assert values["capture_ai_latency_p50_ms"] == pytest.approx(100)
    assert values["capture_ai_latency_p95_ms"] == pytest.approx(190)
    assert math.isfinite(values["ai_result_avg_age_s"])


def test_metrics_accepts_sender_rtcp_filename(tmp_path):
    run = tmp_path / "run1"
    _write_run(run)
    (run / "rtcp.csv").rename(run / "sender_rtcp.csv")
    assert compute_run_metrics(run)["packet_loss"] == pytest.approx(0.2)
    assert compute_run_metrics(run, rtcp_csv="sender_rtcp.csv")["packet_loss"] == pytest.approx(0.2)


def test_metrics_prefers_contract_rtcp_when_both_names_exist(tmp_path):
    run = tmp_path / "run1"
    _write_run(run)
    pd.DataFrame({"cum_lost": [2], "ext_high_seq": [104], "expected": [20]}).to_csv(
        run / "sender_rtcp.csv", index=False)
    # rtcp.csv remains the canonical source and describes 1 lost of 5 expected.
    assert compute_run_metrics(run)["packet_loss"] == pytest.approx(0.2)
    assert compute_run_metrics(run, rtcp_csv="sender_rtcp.csv")["packet_loss"] == pytest.approx(0.2)


def test_clock_domains_must_match():
    frame = pd.DataFrame({"t_capture_mono_ns": [0], "t_start_rx_ns": [2]})
    with pytest.raises(ValueError, match="cannot subtract"):
        subtract_timestamps(frame, "t_start_rx_ns", "t_capture_mono_ns")


def test_aggregate_uses_five_run_t_interval():
    runs = [{"value": float(v)} for v in (1, 2, 3, 4, 5)]
    stats = aggregate_runs(runs)["value"]
    assert stats["mean"] == 3
    assert (stats["min"], stats["max"]) == (1, 5)
    assert stats["ci_low"] == pytest.approx(3 - 2.776 * (2.5 ** 0.5) / 5 ** 0.5)


def test_plot_scenario_from_run_csvs(tmp_path):
    scenario = tmp_path / "T2"
    for i in range(1, 6):
        _write_run(scenario / "medium" / f"run{i}")
    paths = plot_scenario(scenario)
    assert [p.suffix for p in paths] == [".png", ".pdf"]
    assert all(p.is_file() and p.stat().st_size > 0 for p in paths)
