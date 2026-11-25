"""CN-T8 analysis and runner tests on a small generated fixture."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "runner"))

import t8  # noqa: E402

STEPS = [("0pct_a", "loss 0%", 0, 20), ("5pct", "loss 5%", 20, 40),
         ("15pct", "loss 15%", 40, 60), ("0pct_b", "loss 0%", 60, 80)]
TX0, RX0 = 5_000_000_000, 900_000_000_000  # unrelated clocks on purpose


def make_run(run: Path, *, ontime_15: float, abr: bool, recover_after_s: float) -> None:
    """15 fps for 80 s; frames in the 15 % step are 'ok' with ratio ontime_15."""
    run.mkdir(parents=True)
    pd.DataFrame([{"label": l, "netem": n, "start_offset_s": a, "end_offset_s": b}
                  for l, n, a, b in STEPS]).to_csv(run / "steps.csv", index=False)
    sender, receiver, frames = [], [], []
    for i in range(80 * 15):
        t = i / 15
        quality = 75
        if abr and 20.5 <= t < 60:
            quality = 55  # reaction 0.5 s after the 5 % onset
        if abr and 40.3 <= t < 60:
            quality = 35
        size = 4000 if quality == 75 else (3000 if quality == 55 else 2000)
        if not abr:
            size = 4000
        sender.append({"frame_id": i, "bytes": size, "quality": quality if abr else 90,
                       "t_capture_mono_ns": TX0 + int(t * 1e9)})
        gp_scale = 0.3 if 60 <= t < 60 + recover_after_s else 1.0
        receiver.append({"seq": i, "bytes": int(size * gp_scale), "t_arrival_rx_ns": RX0 + int(t * 1e9)})
        status = "ok"
        if 40 <= t < 60 and (i % 100) >= ontime_15 * 100:
            status = "lost"
        frames.append({"frame_id": i, "status": status, "t_playout_rx_ns": RX0 + int((t + 0.01) * 1e9)})
    pd.DataFrame(sender).to_csv(run / "sender.csv", index=False)
    pd.DataFrame(receiver).to_csv(run / "receiver.csv", index=False)
    pd.DataFrame(frames).to_csv(run / "frames_rx.csv", index=False)


def build(root: Path, *, abr_ontime: float, fixed_ontime: float, abr_recover: float) -> Path:
    t8_root = root / "T8"
    for k in (1, 2):
        make_run(t8_root / "fixed_high_hw" / f"run{k}", ontime_15=fixed_ontime, abr=False, recover_after_s=0)
        make_run(t8_root / "abr_aimd_hw" / f"run{k}", ontime_15=abr_ontime, abr=True, recover_after_s=abr_recover)
    return t8_root


def test_per_step_reaction_recovery(tmp_path):
    root = build(tmp_path, abr_ontime=0.8, fixed_ontime=0.6, abr_recover=2)
    run = t8.run_t8(root / "abr_aimd_hw" / "run1")
    labels = [s["label"] for s in run["steps"]]
    assert labels == ["0pct_a", "5pct", "15pct", "0pct_b"]
    assert run["steps"][2]["on_time_ratio"] == pytest.approx(0.8, abs=0.02)
    assert run["steps"][0]["on_time_ratio"] == 1.0
    assert run["steps"][1]["reaction_s"] == pytest.approx(0.5, abs=0.1)
    assert run["steps"][2]["reaction_s"] == pytest.approx(0.3, abs=0.1)
    assert run["steps"][0]["reaction_s"] != run["steps"][0]["reaction_s"]  # NaN: no onset
    assert 1.5 <= run["recovery_s"] <= 2.5


def test_pass(tmp_path):
    root = build(tmp_path, abr_ontime=0.8, fixed_ontime=0.6, abr_recover=2)
    arms = t8.collect(root)
    agg = t8.aggregate_t8(arms["fixed"], arms["abr"])
    assert agg["n_fixed"] == agg["n_abr"] == 2
    assert agg["verdict"] == "PASS"


@pytest.mark.parametrize("abr_ontime,abr_recover", [(0.5, 2), (0.8, 8)])
def test_fail(tmp_path, abr_ontime, abr_recover):
    root = build(tmp_path, abr_ontime=abr_ontime, fixed_ontime=0.6, abr_recover=abr_recover)
    arms = t8.collect(root)
    assert t8.aggregate_t8(arms["fixed"], arms["abr"])["verdict"] == "FAIL"


def test_hw_tables_t8_section(tmp_path):
    import hw_tables
    build(tmp_path, abr_ontime=0.8, fixed_ontime=0.6, abr_recover=2)
    out = tmp_path / "hw.md"
    hw_tables.main([str(tmp_path), "--output", str(out)])
    text = out.read_text(encoding="utf-8")
    assert "## CN-T8" in text and "Verdict (TEST_SCENARIOS CN-T8): PASS" in text


def test_hw_tables_empty_t8(tmp_path):
    import hw_tables
    out = tmp_path / "hw.md"
    hw_tables.main([str(tmp_path), "--output", str(out)])
    assert "_No T8 runs yet_" in out.read_text(encoding="utf-8")


def test_runner_writes_steps_and_keeps_rr(tmp_path):
    import run_scenario
    config = run_scenario.load_config(ROOT / "configs" / "CN-T8-hw.yaml")
    commands = run_scenario.plan(config, output=tmp_path, repetitions=1)
    joined = "\n".join(commands)
    assert "steps.csv" in joined and "args.json" in joined
    assert "--rr-interval 1" in joined
    assert "sudo -n tc qdisc replace" in joined
    assert "scp -q" in joined
    # logs are copied back before the RTCP merge
    scp = next(i for i, c in enumerate(commands) if c.startswith("scp -q"))
    merge = next(i for i, c in enumerate(commands) if "rtcp.csv" in c and c.startswith("python3 -c"))
    assert scp < merge


def test_runner_loopback_unchanged(tmp_path):
    import run_scenario
    config = run_scenario.load_config(ROOT / "configs" / "CN-T8.yaml")
    joined = "\n".join(run_scenario.plan(config, output=tmp_path, repetitions=1))
    assert "sudo" not in joined and "scp" not in joined and "--ai off" in joined
