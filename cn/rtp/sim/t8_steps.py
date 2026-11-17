"""Capture-relative CN-T8 metrics from the simulator's shared CSV contract."""
from __future__ import annotations

import argparse
from bisect import bisect_left
import csv
import json
from pathlib import Path
import statistics


def rows(run_dir: Path, name: str) -> list[dict]:
    with (run_dir / name).open() as stream:
        return list(csv.DictReader(stream))


def write_step_metrics(run_dir: Path) -> dict:
    """Write 20 s bins, using all captured frames, including wholly lost frames."""
    meta = json.loads((run_dir / "meta.json").read_text())
    if meta.get("clock") != "sim":
        raise ValueError("CN-T8 metrics require the single simulator clock")
    args = json.loads((run_dir / "args.json").read_text())
    start = int(meta["media_start_ns"])
    sent = rows(run_dir, "sender.csv")
    frames = {row["frame_id"]: row for row in rows(run_dir, "frames_rx.csv")}
    captures = [int(row["t_capture_mono_ns"]) for row in sent]
    changes = []
    evaluations = []
    for row in rows(run_dir, "rtcp.csv"):
        if row["dir"] != "local" or row["type"] != "ABR":
            continue
        when = int(row["t_mono_ns"])
        evaluations.append((when - start) / 1e9)
        following = bisect_left(captures, when)
        if 0 < following < len(sent):
            if sent[following]["quality"] != sent[following - 1]["quality"]:
                changes.append((when - start) / 1e9)
    steps = []
    for begin in range(0, int(args["simTime"]), 20):
        end = min(begin + 20, args["simTime"])
        selected = [row for row in sent
                    if begin * 1e9 <= int(row["t_capture_mono_ns"]) - start < end * 1e9]
        if not selected:
            continue
        statuses = [frames[row["frame_id"]] for row in selected]
        # sender.bytes is RTP datagram bytes, including RTP/fragment headers.
        media_bytes = [int(row["bytes"]) - 20 * int(row["n_pkts"]) - 4
                       for row in selected]
        reactions = [time - begin for time in evaluations if begin <= time < end]
        bitrate_reactions = [time - begin for time in changes if begin <= time < end]
        steps.append({
            "start_s": begin, "end_s": end, "sent_frames": len(selected),
            "frame_loss": sum(row["complete"] == "0" for row in statuses) / len(selected),
            "on_time_ratio": sum(row["status"] == "ok" for row in statuses) / len(selected),
            "mean_frame_bytes": statistics.mean(media_bytes),
            "mean_rtp_frame_bytes": statistics.mean(int(row["bytes"]) for row in selected),
            "reaction_time_s": min(reactions) if reactions else None,
            "bitrate_reaction_time_s": min(bitrate_reactions) if bitrate_reactions else None,
        })
    result = {"evidence": "SIM", "clock": "sim", "steps": steps}
    (run_dir / "t8_steps.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, nargs="+")
    args = parser.parse_args()
    for run_dir in args.run_dir:
        write_step_metrics(run_dir)


if __name__ == "__main__":
    main()
