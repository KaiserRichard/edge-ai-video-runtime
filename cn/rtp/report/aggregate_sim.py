#!/usr/bin/env python3
"""Aggregate completed ns-3 RTP runs into a Markdown table.

Usage: python rtp/report/aggregate_sim.py RESULTS_DIRECTORY [RESULTS_DIRECTORY ...] [--output PATH]
Only run directories containing summary.json are included. Metrics are means and
min–max across available runs; frame-loss predictions use each run's args.json.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

METRICS = ("packet_loss", "frame_loss", "on_time_ratio", "jitter_ms", "goodput_bps")


def load_runs(root: Path) -> pd.DataFrame:
    rows = []
    for summary_path in sorted(root.rglob("summary.json")):
        run_dir = summary_path.parent
        try:
            summary = json.loads(summary_path.read_text())
            args_path = run_dir / "args.json"
            args = json.loads(args_path.read_text()) if args_path.exists() else {}
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Skipping unreadable {summary_path}: {exc}")
            continue
        # The ns-3 sweep layout is scenario/config/seed-N. Keep the full path
        # so hand-organized scenario directories remain distinguishable.
        rel = run_dir.relative_to(root)
        parts = rel.parts
        scenario = parts[0] if len(parts) > 1 else "unspecified"
        config = "/".join(parts[1:-1]) if len(parts) > 2 else run_dir.name
        loss = args.get("lossP", args.get("loss_p"))
        frame_bytes = args.get("frameBytes", args.get("frame_bytes"))
        # SIM1b payload capacity: 1200-byte RTP payload less the 8-byte project
        # header and first-fragment four-byte length prefix; later fragments
        # carry 1192 JPEG bytes.
        n_packets = None
        predicted = None
        if loss is not None and frame_bytes is not None:
            frame_bytes = int(frame_bytes)
            first_capacity = 1188
            later_capacity = 1192
            n_packets = 1 + max(0, (max(0, frame_bytes - first_capacity)
                                    + later_capacity - 1) // later_capacity)
            predicted = 1 - (1 - float(loss)) ** n_packets
        row = {
            "scenario": scenario,
            "config": config,
            "run": run_dir.name,
            "run_path": rel.as_posix(),
            "n_packets_per_frame": n_packets,
            "calculated_frame_loss": predicted,
        }
        row.update({key: summary.get(key) for key in METRICS})
        rows.append(row)
    return pd.DataFrame(rows)


def fmt(value: object, percent: bool = False) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    number = float(value)
    return f"{number * 100:.3f}%" if percent else f"{number:.4g}"


def summary(group: pd.DataFrame, metric: str, percent: bool = False,
            scale: float = 1.0) -> str:
    values = pd.to_numeric(group[metric], errors="coerce").dropna() / scale
    if values.empty:
        return "UNKNOWN"
    return f"{fmt(values.mean(), percent)} [{fmt(values.min(), percent)}–{fmt(values.max(), percent)}]"


def cdf_delay(x_ms: float, dist: str, delay_ms: float, jitter_ms: float) -> float:
    if dist == "uniform":
        return min(1.0, max(0.0, (x_ms - delay_ms + jitter_ms) / (2 * jitter_ms)))
    if x_ms < 0:
        return 0.0
    return 0.5 * (1 + math.erf((x_ms - delay_ms) / (jitter_ms * math.sqrt(2))))


def calculated_late(run_dir: Path, args: dict) -> float | None:
    """Conditional independent-frame prediction used in the SIM3 summary."""
    receiver_path = run_dir / "receiver.csv"
    try:
        receiver = pd.read_csv(receiver_path)
    except (OSError, pd.errors.ParserError):
        return None
    if receiver.empty:
        return None
    anchor = receiver.loc[receiver["t_arrival_rx_ns"].idxmin()]
    # Capture timestamp zero is 18000 at simulator time 0.2 s; RTP clock is 90 kHz.
    capture_s = 0.2 + (int(anchor["rtp_ts"]) - 18000) / 90000
    arrival_ms = (int(anchor["t_arrival_rx_ns"]) / 1e6 - capture_s * 1000)
    jitter = float(args["jitterMs"])
    dist = str(args["jitterDist"])
    delay = float(args["delayMs"])
    deadline_ms = arrival_ms + float(args["playoutMs"])
    transits_ms = [0.101640 + i * 0.102600 for i in range(10)] + [1.039000]
    timely_probability = math.prod(
        cdf_delay(deadline_ms - transit, dist, delay, jitter) for transit in transits_ms
    )
    return 1.0 - timely_probability


def load_t4(roots: list[Path]) -> pd.DataFrame:
    rows = []
    # Later roots supersede earlier roots for CN-T4 (sim_rtp_v3 follows sim_rtp).
    selected = next((root for root in reversed(roots) if (root / "CN-T4").exists()), None)
    if selected is None:
        return pd.DataFrame()
    for summary_path in sorted((selected / "CN-T4").rglob("summary.json")):
        run_dir = summary_path.parent
        try:
            summary_data = json.loads(summary_path.read_text())
            args = json.loads((run_dir / "args.json").read_text())
            frames = pd.read_csv(run_dir / "frames_rx.csv")
        except (OSError, json.JSONDecodeError, pd.errors.ParserError):
            continue
        total = len(frames)
        if not total:
            continue
        rows.append({
            "dist": args.get("jitterDist", "UNKNOWN"),
            "jitter": float(args.get("jitterMs", math.nan)),
            "playout": float(args.get("playoutMs", math.nan)),
            "late": float((frames["status"] == "late").sum()) / total,
            "on_time": summary_data.get("on_time_ratio"),
            "calculated_late": calculated_late(run_dir, args),
        })
    return pd.DataFrame(rows)


def load_t8(roots: list[Path]) -> pd.DataFrame:
    rows = []
    selected = next((root for root in reversed(roots) if (root / "CN-T8").exists()), None)
    if selected is None:
        return pd.DataFrame()
    for steps_path in sorted((selected / "CN-T8").rglob("t8_steps.json")):
        run_dir = steps_path.parent
        mode = run_dir.parent.name
        try:
            steps = json.loads(steps_path.read_text()).get("steps", [])
        except (OSError, json.JSONDecodeError):
            continue
        for step in steps:
            rows.append({"mode": mode, **step})
    return pd.DataFrame(rows)


def render_t4(frame: pd.DataFrame) -> list[str]:
    lines = ["## CN-T4 — first-arrival playout (SIM; CALCULATED reference)", "",
             "Source: latest supplied root containing CN-T4. Each cell is mean [min–max] over five seeds.",
             "Calculated late fraction conditions on each run's first-arrival anchor and predicts independent later frames.", "",
             "| Distribution | J ms | D ms | Late fraction (CALCULATED) | Late fraction (SIM) | On-time fraction (SIM) |",
             "|---|---:|---:|---:|---:|---:|"]
    if frame.empty:
        return lines + ["No CN-T4 run data found.", ""]
    for key, group in frame.groupby(["dist", "jitter", "playout"], sort=True):
        calc = mean_range(group, "calculated_late", 4)
        lines.append("| " + " | ".join([
            str(key[0]), f"{key[1]:g}", f"{key[2]:g}", calc,
            mean_range(group, "late", 4), mean_range(group, "on_time", 4),
        ]) + " |")
    return lines + [""]


def render_t8(frame: pd.DataFrame) -> list[str]:
    lines = ["## CN-T8 — staged loss and ABR (SIM)", "",
             "Source: latest supplied root containing CN-T8. Cells are mean [min–max] across five seeds; reaction is time from step start to first local ABR evaluation.", "",
             "| Step (s) | Loss p | Mode | Frame loss | On-time | Mean frame bytes | Reaction s |",
             "|---|---:|---|---:|---:|---:|---:|"]
    if frame.empty:
        return lines + ["No CN-T8 step data found.", ""]
    for (start, end), step_group in frame.groupby(["start_s", "end_s"], sort=True):
        for mode in ("fixed", "abr"):
            group = step_group[step_group["mode"] == mode]
            if group.empty:
                continue
            loss = [0, 0.05, 0.15, 0][int(start // 20)]
            lines.append("| " + " | ".join([
                f"{start:g}–{end:g}", f"{loss:g}", mode,
                summary(group, "frame_loss", percent=True),
                summary(group, "on_time_ratio", percent=True),
                mean_range(group, "mean_frame_bytes", 2),
                mean_range(group, "reaction_time_s", 4),
            ]) + " |")
    return lines + [""]


def mean_range(group: pd.DataFrame, metric: str, decimals: int) -> str:
    values = pd.to_numeric(group[metric], errors="coerce").dropna()
    if values.empty:
        return "—"
    return f"{values.mean():.{decimals}f} [{values.min():.{decimals}f}–{values.max():.{decimals}f}]"


def render(roots: list[Path]) -> str:
    # Original CN-T3/CN-T5 results are retained from the first root. Corrected
    # CN-T4/CN-T8 tables are rendered separately from the latest matching root.
    frames = [load_runs(root) for root in roots]
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not frame.empty:
        frame = frame[frame["scenario"].isin({"CN-T3", "CN-T5"})]
    lines = [
        "# ns-3 RTP sweep tables",
        "",
        "Inputs: " + ", ".join(f"`{root}`" for root in roots) + ". Only run directories with `summary.json` are included.",
        "SIM values are means [min–max] across finished runs; incomplete runs are omitted.",
        "`n` is packets per frame: the first packet carries $1200-8-4=1188$ frame bytes",
        "(1200-byte RTP payload less the 8-byte fragment header and 4-byte first-fragment",
        "length prefix); each later packet carries $1200-8=1192$ bytes. Thus for frame size $F$:",
        "$n=1+\\lceil\\max(0,F-1188)/1192\\rceil$. CALCULATED frame loss is $1-(1-p)^n$.",
        "",
    ]
    if frame.empty:
        lines += ["No finished run directories with readable `summary.json` were found.", ""]
        return "\n".join(lines)
    # Keep original CN-T3/CN-T5 results if accidentally duplicated in later roots.
    if len(roots) > 1:
        frame = frame.drop_duplicates(["scenario", "config", "run"], keep="first")
    for scenario, scenario_group in frame.groupby("scenario", sort=True, dropna=False):
        lines += [f"## {scenario}", "",
                  "| Configuration | n (packets/frame) | Packet loss (SIM) | Frame loss (SIM) | Frame loss (CALCULATED) | On-time (SIM) | Jitter ms (SIM) | Goodput Mb/s (SIM) |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for config, group in scenario_group.groupby("config", sort=True, dropna=False):
            ns = pd.to_numeric(group["n_packets_per_frame"], errors="coerce").dropna()
            n_packets = str(int(ns.iloc[0])) if not ns.empty and ns.nunique() == 1 else "UNKNOWN"
            preds = pd.to_numeric(group["calculated_frame_loss"], errors="coerce").dropna()
            calc = f"{fmt(preds.mean(), True)}" if not preds.empty else "UNKNOWN"
            lines.append("| " + " | ".join([
                str(config), n_packets,
                summary(group, "packet_loss", percent=True),
                summary(group, "frame_loss", percent=True), calc,
                summary(group, "on_time_ratio", percent=True),
                summary(group, "jitter_ms"),
                summary(group, "goodput_bps", scale=1_000_000),
            ]) + " |")
        lines += ["", "Run paths by configuration:"]
        for config, group in scenario_group.groupby("config", sort=True, dropna=False):
            paths = ", ".join(f"`{path}`" for path in group["run_path"])
            lines.append(f"- **{config}:** {paths}")
        lines.append("")
    lines += render_t4(load_t4(roots))
    lines += render_t8(load_t8(roots))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_directories", nargs="+", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name("sim_tables.md"))
    args = parser.parse_args()
    roots = [root.expanduser().resolve() for root in args.results_directories]
    output = render(roots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
