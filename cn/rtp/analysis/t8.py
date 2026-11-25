"""CN-T8 hardware analysis: fixed vs ABR under netem loss steps.

Layout: ``<results>/T8/<config>/run<k>/`` with ``steps.csv`` (written by
``runner/run_scenario.py``), ``sender.csv``, ``receiver.csv`` and ``frames_rx.csv``.
A config directory name containing ``abr`` or ``aimd`` is the ABR arm; one
containing ``fixed`` is the baseline.

Clock rule: no timestamp from one host is compared with a timestamp from the
other. Step windows are built separately on each clock from the step *offsets*:

* sender clock (``*_mono_ns``): anchor = first ``t_capture_mono_ns``;
* receiver clock (``*_rx_ns``): anchor = first ``t_arrival_rx_ns``.

ASSUMED: each host's anchor marks the same instant as the netem schedule's
offset 0. The receiver anchor is late by the one-way delay plus sender
start-up (tens of ms on a LAN), small against 20 s steps.

Metrics per step: on-time ratio (frames whose status is ``ok``, divided by
frames played out in the window), frame loss, goodput (receiver bytes / step
length) and mean sent frame bytes. Reaction time is the time from the onset of
a step with more loss than the previous step to the first change in sender
``quality`` (falling back to a >20 % change in frame bytes); sender clock only.
Recovery time is measured in the final step: the start of the first 1 s window
whose receiver goodput reaches ``RECOVERY_FRACTION`` of the first step's
goodput; receiver clock only.

ASSUMED: ``RECOVERY_FRACTION = 0.9``. TEST_SCENARIOS.md does not define
"recovers", so the threshold is stated here and in the table.

PASS (TEST_SCENARIOS.md, CN-T8): mean ABR on-time ratio >= mean fixed on-time
ratio in the 15 % step AND mean ABR recovery time <= 5 s.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

RECOVERY_FRACTION = 0.9
RECOVERY_LIMIT_S = 5.0
WINDOW_S = 1.0


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(df[name], errors="coerce") if name in df else pd.Series(dtype=float)


def read_steps(run: Path) -> pd.DataFrame:
    steps = _read(run / "steps.csv")
    if steps.empty or not {"start_offset_s", "end_offset_s"} <= set(steps):
        return pd.DataFrame()
    if "label" not in steps:
        steps["label"] = steps.get("netem", pd.Series(range(len(steps)))).astype(str)
    return steps


def loss_of(netem: str) -> float:
    import re
    match = re.search(r"loss(?:\s+random)?\s+(\d+(?:\.\d+)?)\s*%", str(netem), re.I)
    return float(match.group(1)) / 100.0 if match else 0.0


def _reaction(sender: pd.DataFrame, onset_ns: float, end_ns: float) -> float:
    t = _col(sender, "t_capture_mono_ns")
    before = sender[t < onset_ns]
    after = sender[(t >= onset_ns) & (t < end_ns)]
    if before.empty or after.empty:
        return float("nan")
    q_before = _col(before, "quality").dropna()
    q_after = _col(after, "quality")
    if len(q_before) and q_after.notna().any():
        changed = after[q_after.ne(q_before.iloc[-1]) & q_after.notna()]
    else:
        ref = _col(before, "bytes").tail(15).mean()
        if not ref or math.isnan(ref):
            return float("nan")
        changed = after[(_col(after, "bytes") - ref).abs() > 0.2 * ref]
    if changed.empty:
        return float("nan")
    return float((_col(changed, "t_capture_mono_ns").iloc[0] - onset_ns) / 1e9)


def run_t8(run: Path) -> dict:
    """Per-step metrics, reaction and recovery for one run directory."""
    steps = read_steps(run)
    sender, receiver = _read(run / "sender.csv"), _read(run / "receiver.csv")
    frames = _read(run / "frames_rx.csv")
    out = {"run": run.name, "steps": [], "recovery_s": float("nan")}
    if steps.empty or sender.empty or receiver.empty:
        return out
    tx0 = _col(sender, "t_capture_mono_ns").min()
    rx0 = _col(receiver, "t_arrival_rx_ns").min()
    arrivals, rbytes = _col(receiver, "t_arrival_rx_ns"), _col(receiver, "bytes").fillna(0)
    playout = _col(frames, "t_playout_rx_ns")
    status = frames.get("status", pd.Series(dtype=str)).astype(str).str.lower()
    tcap, sbytes = _col(sender, "t_capture_mono_ns"), _col(sender, "bytes")
    prev_loss = None
    for _, step in steps.iterrows():
        a, b = float(step.start_offset_s), float(step.end_offset_s)
        rx_a, rx_b = rx0 + a * 1e9, rx0 + b * 1e9
        tx_a, tx_b = tx0 + a * 1e9, tx0 + b * 1e9
        in_rx = arrivals.ge(rx_a) & arrivals.lt(rx_b)
        in_play = playout.ge(rx_a) & playout.lt(rx_b)
        n = int(in_play.sum())
        loss = loss_of(step.get("netem", ""))
        reaction = float("nan")
        if prev_loss is not None and loss > prev_loss:
            reaction = _reaction(sender, tx_a, tx_b)
        prev_loss = loss
        out["steps"].append({
            "label": str(step.label), "loss": loss,
            "on_time_ratio": float(status[in_play].eq("ok").mean()) if n else float("nan"),
            "frame_loss": float(status[in_play].eq("lost").mean()) if n else float("nan"),
            "goodput_bps": float(rbytes[in_rx].sum() * 8 / (b - a)) if b > a else float("nan"),
            "mean_frame_bytes": float(sbytes[tcap.ge(tx_a) & tcap.lt(tx_b)].mean()),
            "reaction_s": reaction, "n_frames": n,
        })
    if len(out["steps"]) >= 2:
        base = out["steps"][0]["goodput_bps"]
        last = steps.iloc[-1]
        a, b = float(last.start_offset_s), float(last.end_offset_s)
        t = a
        while t + WINDOW_S <= b + 1e-9 and math.isfinite(base) and base > 0:
            w = arrivals.ge(rx0 + t * 1e9) & arrivals.lt(rx0 + (t + WINDOW_S) * 1e9)
            if rbytes[w].sum() * 8 / WINDOW_S >= RECOVERY_FRACTION * base:
                out["recovery_s"] = t - a
                break
            t += 0.25
    return out


def _arm(config: str) -> str | None:
    name = config.lower()
    if "abr" in name or "aimd" in name:
        return "abr"
    if "fixed" in name:
        return "fixed"
    return None


def collect(t8_root: Path) -> dict[str, list[dict]]:
    arms: dict[str, list[dict]] = {"fixed": [], "abr": []}
    for cfg in sorted(p for p in t8_root.iterdir() if p.is_dir()) if t8_root.is_dir() else []:
        arm = _arm(cfg.name)
        if arm is None or "smoke" in cfg.name.lower():
            continue
        for run in sorted(p for p in cfg.glob("run*") if p.is_dir()):
            result = run_t8(run)
            if result["steps"]:
                result["config"] = cfg.name
                arms[arm].append(result)
    return arms


def _mean(values) -> float:
    vals = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return float(np.mean(vals)) if vals else float("nan")


def aggregate_t8(fixed_runs: list[dict], abr_runs: list[dict]) -> dict:
    """Per-step means for each arm and the TEST_SCENARIOS pass/fail verdict."""
    def per_step(runs):
        if not runs:
            return []
        n = min(len(r["steps"]) for r in runs)
        rows = []
        for i in range(n):
            col = [r["steps"][i] for r in runs]
            row = {"label": col[0]["label"], "loss": col[0]["loss"], "runs": len(runs)}
            for key in ("on_time_ratio", "frame_loss", "goodput_bps", "mean_frame_bytes", "reaction_s"):
                vals = [c[key] for c in col if math.isfinite(c[key])]
                row[key] = _mean(vals)
                row[key + "_min"] = float(min(vals)) if vals else float("nan")
                row[key + "_max"] = float(max(vals)) if vals else float("nan")
            rows.append(row)
        return rows
    fixed, abr = per_step(fixed_runs), per_step(abr_runs)
    result = {"fixed": fixed, "abr": abr,
              "fixed_recovery_s": _mean(r["recovery_s"] for r in fixed_runs),
              "abr_recovery_s": _mean(r["recovery_s"] for r in abr_runs),
              "abr_recovered_runs": sum(1 for r in abr_runs if math.isfinite(r["recovery_s"])
                                        and r["recovery_s"] <= RECOVERY_LIMIT_S),
              "n_fixed": len(fixed_runs), "n_abr": len(abr_runs)}
    hi_f = max(fixed, key=lambda r: r["loss"], default=None)
    hi_a = max(abr, key=lambda r: r["loss"], default=None)
    if hi_f is None or hi_a is None:
        result.update(verdict="NO DATA", on_time_ok=None, recovery_ok=None)
        return result
    on_time_ok = hi_a["on_time_ratio"] >= hi_f["on_time_ratio"]
    rec = result["abr_recovery_s"]
    recovery_ok = math.isfinite(rec) and rec <= RECOVERY_LIMIT_S
    result.update(on_time_ok=bool(on_time_ok), recovery_ok=bool(recovery_ok),
                  peak_loss=hi_a["loss"],
                  verdict="PASS" if on_time_ok and recovery_ok else "FAIL")
    return result


def _f(v, d=3):
    return f"{v:.{d}f}" if isinstance(v, (int, float)) and math.isfinite(v) else ""


def report_lines(t8_root: Path) -> list[str]:
    arms = collect(t8_root)
    agg = aggregate_t8(arms["fixed"], arms["abr"])
    lines = ["## CN-T8 — RTCP-driven ABR vs fixed bitrate", "",
             f"Runs: fixed {agg['n_fixed']}, ABR {agg['n_abr']}. Step windows are built on each host's own clock from the step offsets in `steps.csv` (see `analysis/t8.py`). Recovery = first 1 s window in the final step with receiver goodput ≥ {RECOVERY_FRACTION:.0%} of the first step's goodput (ASSUMED threshold). Cells are means; ranges are min–max over runs.", ""]
    headers = ["Step", "Arm", "Runs", "On-time", "On-time range", "Frame loss", "Goodput (Mb/s)", "Mean frame bytes", "Reaction (s)"]
    rows = []
    for arm in ("fixed", "abr"):
        for r in agg[arm]:
            rows.append([r["label"], arm, str(r["runs"]), _f(r["on_time_ratio"]),
                         f"{_f(r['on_time_ratio_min'])}–{_f(r['on_time_ratio_max'])}",
                         _f(r["frame_loss"]), _f(r["goodput_bps"] / 1e6 if math.isfinite(r["goodput_bps"]) else float('nan')),
                         _f(r["mean_frame_bytes"], 0), _f(r["reaction_s"], 2)])
    if not rows:
        rows = [["_No T8 runs yet_"] + [""] * (len(headers) - 1)]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    lines.extend("| " + " | ".join(r) + " |" for r in rows)
    lines.extend(["", f"Recovery after return to 0 %: fixed {_f(agg['fixed_recovery_s'], 2)} s, ABR {_f(agg['abr_recovery_s'], 2)} s ({agg['abr_recovered_runs']}/{agg['n_abr']} ABR runs ≤ {RECOVERY_LIMIT_S:.0f} s).",
                  "", f"**Verdict (TEST_SCENARIOS CN-T8): {agg['verdict']}** — ABR on-time ≥ fixed at peak loss: {agg.get('on_time_ok')}; ABR recovery ≤ {RECOVERY_LIMIT_S:.0f} s: {agg.get('recovery_ok')}.", ""])
    return lines


def plot_t8(t8_root: Path, output: Path) -> Path | None:
    """Per-step on-time bars and goodput-vs-time for one run of each arm."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    arms = collect(t8_root)
    agg = aggregate_t8(arms["fixed"], arms["abr"])
    if not agg["fixed"] and not agg["abr"]:
        return None
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    width = 0.38
    for k, arm in enumerate(("fixed", "abr")):
        rows = agg[arm]
        x = np.arange(len(rows)) + (k - 0.5) * width
        ax1.bar(x, [r["on_time_ratio"] for r in rows], width, label=arm)
        ax1.set_xticks(np.arange(len(rows)), [r["label"] for r in rows])
    ax1.set_ylabel("On-time frame ratio"); ax1.set_ylim(0, 1.05); ax1.legend()
    ax1.set_title("Per-step on-time ratio (mean over runs)")
    for arm in ("fixed", "abr"):
        if not arms[arm]:
            continue
        run_dir = t8_root / arms[arm][0]["config"] / arms[arm][0]["run"]
        rec = _read(run_dir / "receiver.csv")
        t = _col(rec, "t_arrival_rx_ns")
        if t.empty:
            continue
        sec = ((t - t.min()) // 1e9).astype(int)
        gp = _col(rec, "bytes").fillna(0).groupby(sec).sum() * 8 / 1e6
        ax2.plot(gp.index, gp.values, label=f"{arm} ({arms[arm][0]['run']})")
    steps = read_steps(t8_root / (arms["abr"] or arms["fixed"])[0]["config"] / (arms["abr"] or arms["fixed"])[0]["run"])
    if not steps.empty:
        last = float(steps.iloc[-1].start_offset_s)
        for edge in steps.start_offset_s.iloc[1:]:
            ax2.axvline(float(edge), color="grey", lw=0.8, ls=":")
        ax2.axvline(last + RECOVERY_LIMIT_S, color="red", lw=1, ls="--", label="+5 s recovery gate")
    ax2.set_xlabel("Receiver time since first packet (s)"); ax2.set_ylabel("Goodput (Mb/s)")
    ax2.set_title("Goodput, 1 s bins"); ax2.legend()
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)
    return output


def main(argv=None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("t8_root", type=Path, help="results/T8 directory")
    parser.add_argument("--plot", type=Path, help="write the T8 figure here")
    args = parser.parse_args(argv)
    print("\n".join(report_lines(args.t8_root)))
    if args.plot:
        print("figure:", plot_t8(args.t8_root, args.plot))


if __name__ == "__main__":
    main()
