from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sim.sweep import build_commands


def test_cn_t3_commands_cover_five_runs_and_loss_grid(tmp_path):
    commands = build_commands(Path("build/rtp-video"), tmp_path, "CN-T3")
    assert len(commands) == 25
    assert commands[0][1:4] == ["--link=csma", "--fps=30", "--frameBytes=12000"]
    assert "--lossP=0.05" in commands[10]
    assert "--geBurst=4" in commands[20]
    assert "--run=5" in commands[4]
    assert commands[0][-2] == f"--outDir={tmp_path / 'CN-T3/random-loss-0/seed-01'}"


def test_cn_t8_fixed_and_abr_grids(tmp_path):
    commands = build_commands(Path("build/rtp-video"), tmp_path, "CN-T8")
    assert len(commands) == 10
    assert "--abr=false" in commands[0]
    assert "--abr=true" in commands[5]
    assert all("--lossSteps=0:0,20:0.05,40:0.15,60:0" in cmd for cmd in commands)
    assert all("--simTime=80" in cmd for cmd in commands)


import csv
import json
import subprocess

import pytest

from sim.sweep import ROOT, analyze_run
from sim.validate import baseline_check, run_statistics


@pytest.fixture(scope="module")
def simulator(tmp_path_factory):
    binary = tmp_path_factory.mktemp("sim1b-build") / "rtp-video"
    subprocess.run([str(ROOT / "scripts/build_sim_rtp.sh"), str(binary)], check=True)
    return binary


def simulate(binary, path, **options):
    params = {"simTime": 0.2, "frameBytes": 12000, "fps": 30, **options}
    subprocess.run([str(binary), *(f"--{k}={v}" for k, v in params.items()),
                    f"--outDir={path}"], check=True)
    return run_statistics(path)


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def test_csma_serialization_jitter_and_an1(simulator, tmp_path):
    stats = simulate(simulator, tmp_path, simTime=3)
    assert stats["sent_frames"] == stats["received_frame_rows"] == 90
    assert stats["sent_packets"] == stats["received_packets"] == 990
    timing = baseline_check(tmp_path)
    assert timing["sim_first_transit_ns"] == 101640
    sender = read_csv(tmp_path / "sender.csv")
    receiver = read_csv(tmp_path / "receiver.csv")
    assert sum(int(r["bytes"]) for r in sender) == sum(int(r["bytes"]) for r in receiver)
    assert all(int(r["rtp_ts"]) == int(r["t_capture_mono_ns"]) * 90 // 1000000
               for r in sender)
    metrics = analyze_run(tmp_path)
    assert metrics["packet_loss"] == 0
    assert metrics["on_time_ratio"] == 1
    assert metrics["capture_ai_latency_p50_ms"] is None
    assert json.loads((tmp_path / "meta.json").read_text())["clock"] == "sim"
    assert json.loads((tmp_path / "summary.json").read_text()) == metrics


@pytest.mark.parametrize("ge_burst", [0, 4])
def test_total_loss_keeps_every_frame(simulator, tmp_path, ge_burst):
    stats = simulate(simulator, tmp_path, lossP=1, geBurst=ge_burst)
    assert stats["packet_loss"] == stats["frame_loss"] == 1
    assert stats["sent_frames"] == stats["received_frame_rows"] == 6
    frames = read_csv(tmp_path / "frames_rx.csv")
    assert all(r["status"] == "lost" and r["n_received"] == "0" for r in frames)
    assert all(r["t_complete_rx_ns"] == "" for r in frames)


def test_missing_markers_first_fragments_and_reproducibility(simulator, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    stats = simulate(simulator, first, lossP=0.5, simTime=2)
    simulate(simulator, second, lossP=0.5, simTime=2)
    assert stats["sent_frames"] == stats["received_frame_rows"] == 60
    for name in ("sender.csv", "receiver.csv", "frames_rx.csv", "rtcp.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    received = read_csv(first / "receiver.csv")
    marker_frames = {r["frame_id"] for r in received if r["marker"] == "1"}
    frames = read_csv(first / "frames_rx.csv")
    assert any(r["frame_id"] not in marker_frames for r in frames)
    assert all(r["status"] == "lost" for r in frames if r["frame_id"] not in marker_frames)
    received_seqs = {(r["frame_id"], int(r["seq"])) for r in received}
    missing_first = {r["frame_id"] for r in read_csv(first / "sender.csv")
                     if (r["frame_id"], int(r["seq_first"])) not in received_seqs}
    assert missing_first
    assert all(r["status"] == "lost" for r in frames if r["frame_id"] in missing_first)


def test_reordering_completes_after_marker_and_classifies_late(simulator, tmp_path):
    stats = simulate(simulator, tmp_path, simTime=2, delayMs=20, jitterMs=60, playoutMs=50)
    assert stats["packet_loss"] == stats["frame_loss"] == 0
    received = read_csv(tmp_path / "receiver.csv")
    frames = read_csv(tmp_path / "frames_rx.csv")
    last_arrival = {}
    marker_arrival = {}
    for row in received:
        last_arrival[row["frame_id"]] = int(row["t_arrival_rx_ns"])
        if row["marker"] == "1":
            marker_arrival[row["frame_id"]] = int(row["t_arrival_rx_ns"])
    assert any(last_arrival[f] > marker_arrival[f] for f in last_arrival)
    assert all(int(r["t_complete_rx_ns"]) == last_arrival[r["frame_id"]] for r in frames)
    assert any(r["status"] == "late" for r in frames)
    assert all((r["status"] == "late") ==
               (int(r["t_complete_rx_ns"]) > int(r["t_playout_rx_ns"])) for r in frames)


def test_rr_sequence_wrap_and_final_report(simulator, tmp_path):
    stats = simulate(simulator, tmp_path, simTime=13, fps=500)
    assert stats["sent_packets"] == stats["received_packets"] == 71500
    rr = read_csv(tmp_path / "rtcp.csv")[-1]
    assert int(rr["ext_high_seq"]) == 71499
    assert int(rr["cum_lost"]) == 0
    assert rr["dir"] == "tx"
    assert analyze_run(tmp_path)["packet_loss"] == 0


@pytest.mark.parametrize("options,code,message", [
    ({"playoutAnchor": "invalid"}, 2, "Invalid simulation parameter"),
    ({"jitterDist": "invalid"}, 2, "Invalid simulation parameter"),
    ({"delayMs": -1}, 2, "Invalid simulation parameter"),
    ({"lossP": 1.1}, 2, "Invalid simulation parameter"),
    ({"frameJitter": 1}, 2, "Invalid simulation parameter"),
    ({"lossP": 0.9, "geBurst": 4}, 2, "Invalid simulation parameter"),
    ({"lossSteps": "1:0"}, 2, "Invalid simulation parameter"),
    ({"lossSteps": "0:0,1:1.1"}, 2, "Invalid simulation parameter"),
    ({"lossSteps": "0:0,1:0,1:1"}, 2, "Invalid simulation parameter"),
    ({"lossSteps": "0:0,"}, 2, "Invalid simulation parameter"),
    ({"lossSteps": "0:0,1:0junk"}, 2, "Invalid simulation parameter"),
    ({"lossSteps": "0:0", "geBurst": 4}, 2, "Invalid simulation parameter"),
    ({"fps": "nan"}, 1, "Invalid command-line argument: --fps=nan"),
])
def test_invalid_parameters_are_rejected(simulator, tmp_path, options, code, message):
    result = subprocess.run([str(simulator), *(f"--{k}={v}" for k, v in options.items()),
                             f"--outDir={tmp_path}"], capture_output=True, text=True)
    assert result.returncode == code
    assert message in result.stderr


from sim.t8_steps import write_step_metrics


def test_loss_steps_follow_capture_origin_and_do_not_drop_rtcp(simulator, tmp_path):
    simulate(simulator, tmp_path, simTime=4, lossSteps="0:0,1:1,2:0")
    frames = read_csv(tmp_path / "frames_rx.csv")
    assert len(frames) == 120
    assert all(row["status"] == ("lost" if 30 <= i < 60 else "ok")
               for i, row in enumerate(frames))
    rr = read_csv(tmp_path / "rtcp.csv")
    assert len([row for row in rr if row["type"] == "RR"]) >= 4


def test_abr_hysteresis_size_floor_recovery_and_step_metrics(simulator, tmp_path):
    simulate(simulator, tmp_path, simTime=80, abr="true",
             lossSteps="0:0,20:0.05,40:0.15,60:0")
    sent = read_csv(tmp_path / "sender.csv")
    reports = read_csv(tmp_path / "rtcp.csv")
    abr = [row for row in reports if row["type"] == "ABR"]
    rr = [row for row in reports if row["type"] == "RR"]
    # Every RR delivered before shutdown gets one local evaluation, never impaired.
    assert len(abr) == len(rr) - 1
    quality, clean, previous_jitter = 75, 0, None
    decisions = []
    for row in abr:
        fraction = int(row["fraction_lost"]) / 256
        jitter = int(row["jitter"])
        rising = (previous_jitter is not None and jitter >= 1.5 * previous_jitter
                  and jitter - previous_jitter >= 90)
        previous_jitter = jitter
        if fraction > 0.05:
            quality, clean = max(20, int(quality * 0.7)), 0
        elif fraction < 0.01 and not rising:
            clean += 1
            if clean == 3:
                quality, clean = min(95, quality + 5), 0
        else:
            clean = 0
        decisions.append((int(row["t_mono_ns"]), quality))
    index = 0
    quality = 75
    for row in sent:
        capture = int(row["t_capture_mono_ns"])
        while index < len(decisions) and decisions[index][0] <= capture:
            quality = decisions[index][1]
            index += 1
        assert int(row["quality"]) == quality
        media_bytes = int(row["bytes"]) - 20 * int(row["n_pkts"]) - 4
        assert media_bytes == int(12000 * (quality / 90))
    assert min(int(row["quality"]) for row in sent) == 20
    assert int(sent[-1]["quality"]) > 20
    metrics = write_step_metrics(tmp_path)
    assert [step["sent_frames"] for step in metrics["steps"]] == [600] * 4
    assert metrics["steps"][0]["on_time_ratio"] == 1
    assert 10000 < metrics["steps"][0]["mean_frame_bytes"] < 12667
    assert 0 < metrics["steps"][0]["reaction_time_s"] < 1
    assert 2 < metrics["steps"][0]["bitrate_reaction_time_s"] < 4
    assert 0 < metrics["steps"][1]["bitrate_reaction_time_s"] < 2
    assert 0 < metrics["steps"][2]["reaction_time_s"] < 2
    assert 2 < metrics["steps"][3]["bitrate_reaction_time_s"] < 4
    assert json.loads((tmp_path / "t8_steps.json").read_text()) == metrics


def test_cn_t4_grid_matches_netem_scenarios(tmp_path):
    commands = build_commands(Path("build/rtp-video"), tmp_path, "CN-T4")
    assert len(commands) == 40
    assert all("--playoutAnchor=first" in cmd for cmd in commands)
    assert sum("--jitterDist=uniform" in cmd and "--jitterMs=5" in cmd
               for cmd in commands) == 20
    assert sum("--jitterDist=normal" in cmd and "--jitterMs=20" in cmd
               for cmd in commands) == 20


@pytest.mark.parametrize("anchor", ["first", "capture"])
def test_playout_anchor_with_fixed_delay(simulator, tmp_path, anchor):
    simulate(simulator, tmp_path, delayMs=20, playoutMs=20, playoutAnchor=anchor)
    frames = read_csv(tmp_path / "frames_rx.csv")
    assert all(row["status"] == ("ok" if anchor == "first" else "late") for row in frames)
    received = read_csv(tmp_path / "receiver.csv")
    if anchor == "first":
        t0, ts0 = int(received[0]["t_arrival_rx_ns"]), int(received[0]["rtp_ts"])
        assert all(int(row["t_playout_rx_ns"]) ==
                   t0 + (int(row["rtp_ts"]) - ts0) * 10**9 // 90000 + 20_000_000
                   for row in frames)


@pytest.mark.parametrize("dist", ["uniform", "normal"])
def test_symmetric_jitter_clips_and_reorders(simulator, tmp_path, dist):
    simulate(simulator, tmp_path, simTime=2, delayMs=20, jitterMs=20, jitterDist=dist)
    sent = {r["frame_id"]: int(r["t_capture_mono_ns"])
            for r in read_csv(tmp_path / "sender.csv")}
    received = read_csv(tmp_path / "receiver.csv")
    transits = [int(r["t_arrival_rx_ns"]) - sent[r["frame_id"]] for r in received]
    assert min(transits) < 20_000_000 < max(transits)
    assert any(int(a["seq"]) > int(b["seq"]) for a, b in zip(received, received[1:]))
    clips = json.loads((tmp_path / "meta.json").read_text())["delay_clip_count"]
    assert (clips > 0) == (dist == "normal")
    if dist == "uniform":
        assert max(transits) < 41_100_000


def test_first_anchor_extends_wrapped_timestamps(simulator, tmp_path):
    simulate(simulator, tmp_path, simTime=130000, fps=0.0001, frameBytes=100)
    received = read_csv(tmp_path / "receiver.csv")
    frames = read_csv(tmp_path / "frames_rx.csv")
    assert any(int(a["rtp_ts"]) > int(b["rtp_ts"])
               for a, b in zip(received, received[1:]))
    t0 = int(received[0]["t_arrival_rx_ns"])
    assert all(int(row["t_playout_rx_ns"]) == t0 + i * 10_000 * 10**9 + 50_000_000
               for i, row in enumerate(frames))


def test_abr_clear_jitter_rise_pauses_but_noise_allows_recovery(simulator, tmp_path):
    simulate(simulator, tmp_path, simTime=16, fps=1, abr="true",
             delayMs=20, jitterMs=20, jitterDist="normal")
    reports = [r for r in read_csv(tmp_path / "rtcp.csv") if r["type"] == "ABR"]
    # Seed 1: 255 -> 564 is a clear rise; 564 -> 681 -> 788 -> 882 is noise.
    assert [int(r["jitter"]) for r in reports[:5]] == [255, 564, 681, 788, 882]
    qualities = [int(r["quality"]) for r in read_csv(tmp_path / "sender.csv")]
    assert qualities == [75] * 5 + [80] * 3 + [85] * 3 + [90] * 3 + [95] * 2
