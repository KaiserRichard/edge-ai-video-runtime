"""Reproduce SIM1b acceptance evidence; run with the repository .venv Python."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics

try:
    from .sweep import ROOT, run_command
except ImportError:
    from sweep import ROOT, run_command


def rows(run_dir: Path, name: str) -> list[dict]:
    with (run_dir / name).open() as stream:
        return list(csv.DictReader(stream))


def run_statistics(run_dir: Path) -> dict:
    sent = rows(run_dir, "sender.csv")
    received = rows(run_dir, "receiver.csv")
    frames = rows(run_dir, "frames_rx.csv")
    assert [r["frame_id"] for r in sent] == [r["frame_id"] for r in frames]
    assert all(int(s["n_pkts"]) == int(f["n_expected"]) for s, f in zip(sent, frames))
    total = sum(int(row["n_pkts"]) for row in sent)
    positions = {}
    start = 0
    for row in sent:
        positions[row["frame_id"]] = (start, int(row["seq_first"]))
        start += int(row["n_pkts"])
    arrived = set()
    for row in received:
        start, seq_first = positions[row["frame_id"]]
        arrived.add(start + ((int(row["seq"]) - seq_first) % 65536))
    assert len(arrived) == len(received)
    bursts = []
    current = 0
    for seq in range(total):
        if seq not in arrived:
            current += 1
        elif current:
            bursts.append(current)
            current = 0
    if current:
        bursts.append(current)
    return {
        "run_dir": str(run_dir),
        "sent_frames": len(sent),
        "received_frame_rows": len(frames),
        "sent_packets": total,
        "received_packets": len(received),
        "packet_loss": 1 - len(received) / total,
        "frame_loss": sum(row["complete"] == "0" for row in frames) / len(frames),
        "mean_loss_run_packets": statistics.mean(bursts) if bursts else 0,
        "max_loss_run_packets": max(bursts, default=0),
    }


def calculated_jitter(packet_sizes: list[int]) -> dict:
    """Idle ns-3 DIX CSMA: 100 Mb/s, 1 us propagation, default IFG/backoff."""
    # Each RTP datagram adds UDP(8), IPv4(20), Ethernet header/FCS(18).
    serialization = [(size + 46) * 80 for size in packet_sizes]
    # IFG = 960 ns < propagation; ns-3 takes one deterministic 1000 ns backoff.
    gaps = [duration + 1960 for duration in serialization[1:]]
    spread = sum(gaps)
    differences = [spread] + gaps
    jitter = 0.0
    last_cycle = []
    for _ in range(100):
        last_cycle = []
        for delta in differences:
            jitter += (delta - jitter) / 16
            last_cycle.append(jitter / 1e6)
    return {
        "first_transit_ns": serialization[0] + 1000,
        "intra_frame_spread_ns": spread,
        "steady_mean_jitter_ms": 2 * spread / len(packet_sizes) / 1e6,
        "steady_min_jitter_ms": min(last_cycle),
        "steady_max_jitter_ms": max(last_cycle),
        "steady_last_jitter_ms": last_cycle[-1],
    }


def baseline_check(run_dir: Path) -> dict:
    sent = rows(run_dir, "sender.csv")
    received = rows(run_dir, "receiver.csv")
    first = [r for r in received if r["frame_id"] == "0"]
    expected = calculated_jitter([int(row["bytes"]) for row in first])
    transit = int(first[0]["t_arrival_rx_ns"]) - int(sent[0]["t_send_first_mono_ns"])
    assert abs(transit - expected["first_transit_ns"]) <= 1
    steady = [float(row["jitter_ts_units"]) / 90 for row in received
              if int(row["frame_id"]) >= 30]
    mean_jitter = statistics.mean(steady)
    # A 90 kHz tick is 0.011111 ms; quantized recurrence must be within one tick.
    assert abs(mean_jitter - expected["steady_mean_jitter_ms"]) < 1 / 90
    assert abs(steady[-1] - expected["steady_last_jitter_ms"]) < 1 / 90
    return {"calculated": expected, "sim_first_transit_ns": transit,
            "sim_steady_mean_jitter_ms": mean_jitter,
            "sim_last_jitter_ms": steady[-1]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rtp-video")
    parser.add_argument("--out", type=Path, default=ROOT / "results/sim_rtp/SIM1b")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    def simulate(label, seed=1, **options):
        path = args.out / label / f"seed-{seed:02d}"
        params = {"link": "csma", "frameBytes": 12000, "fps": 30,
                  "lossP": 0.05, "simTime": 60, "seed": seed, "run": seed, **options}
        command = [str(args.binary), *(f"--{k}={v}" for k, v in params.items()),
                   f"--outDir={path}"]
        metrics = run_command(command)
        stats = run_statistics(path)
        stats["an1"] = metrics
        print(f"{label}/seed-{seed:02d}: loss={stats['packet_loss']:.6f}, "
              f"frame_loss={stats['frame_loss']:.6f}, "
              f"mean_loss_run={stats['mean_loss_run_packets']:.3f}", flush=True)
        return stats

    baseline = simulate("baseline", lossP=0, simTime=3)
    assert baseline["packet_loss"] == 0
    assert baseline["frame_loss"] == 0
    baseline["timing"] = baseline_check(Path(baseline["run_dir"]))
    table = []
    bernoulli = []
    for size in (1188, 3000, 12000, 30000):
        runs = [simulate(f"bernoulli-{size}B", seed, frameBytes=size) for seed in range(1, 6)]
        n = 1 + (max(0, size - 1188) + 1191) // 1192
        table.append({
            "frame_bytes": size, "packets_per_frame": n,
            "calculated_frame_loss": 1 - (1 - 0.05) ** n,
            "sim_frame_loss_mean": statistics.mean(r["frame_loss"] for r in runs),
            "sim_frame_loss_min": min(r["frame_loss"] for r in runs),
            "sim_frame_loss_max": max(r["frame_loss"] for r in runs),
            "runs": runs,
        })
        if size == 12000:
            bernoulli = runs
    ge = [simulate("ge-burst4", seed, geBurst=4) for seed in range(1, 6)]
    mean_loss = statistics.mean(r["packet_loss"] for r in bernoulli)
    ge_loss = statistics.mean(r["packet_loss"] for r in ge)
    assert abs(mean_loss - 0.05) <= 0.01
    assert abs(ge_loss - 0.05) <= 0.01
    bernoulli_burst = statistics.mean(r["mean_loss_run_packets"] for r in bernoulli)
    ge_burst = statistics.mean(r["mean_loss_run_packets"] for r in ge)
    assert ge_burst > 2 * bernoulli_burst
    evidence = {"evidence": "SIM", "baseline": baseline, "frame_loss_table": table,
                "bernoulli_mean_packet_loss": mean_loss, "ge_mean_packet_loss": ge_loss,
                "bernoulli_mean_loss_run": bernoulli_burst, "ge_mean_loss_run": ge_burst,
                "ge_runs": ge}
    (args.out / "validation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"PASS: Bernoulli loss={mean_loss:.6f}; GE loss={ge_loss:.6f}; "
          f"mean consecutive losses={bernoulli_burst:.3f} vs {ge_burst:.3f}")


if __name__ == "__main__":
    main()
