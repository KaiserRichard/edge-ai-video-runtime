"""Metrics for the RTP experiment CSV contract."""

from __future__ import annotations

import json
import importlib.util
import math
import re
from pathlib import Path
from statistics import stdev

import numpy as np
import pandas as pd

try:
    from analysis.aoi import area_aoi
except ModuleNotFoundError:  # Running from rtp/ where its analysis dir shadows the root package.
    _aoi_path = Path(__file__).resolve().parents[2] / "analysis" / "aoi.py"
    _aoi_spec = importlib.util.spec_from_file_location("cn_root_aoi", _aoi_path)
    _aoi_module = importlib.util.module_from_spec(_aoi_spec)
    _aoi_spec.loader.exec_module(_aoi_module)
    area_aoi = _aoi_module.area_aoi


_CLOCK_SUFFIX = re.compile(r"_(mono|rx|sim)_ns$")
RTP_CLOCK_RATE = 90_000
_T_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
          6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
          11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
          16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
          21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
          26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def timestamp_clock(column: str) -> str:
    """Return a timestamp's declared clock domain, rejecting unnamed clocks."""
    match = _CLOCK_SUFFIX.search(column)
    if not match:
        raise ValueError(f"timestamp column {column!r} has no recognized clock suffix")
    return match.group(1)


def subtract_timestamps(frame: pd.DataFrame, end_column: str, start_column: str) -> pd.Series:
    """Subtract timestamp columns only when their names declare the same clock."""
    end_clock, start_clock = timestamp_clock(end_column), timestamp_clock(start_column)
    if end_clock != start_clock:
        raise ValueError(f"cannot subtract {end_clock}-clock {end_column} from "
                         f"{start_clock}-clock {start_column}")
    return pd.to_numeric(frame[end_column], errors="coerce") - pd.to_numeric(
        frame[start_column], errors="coerce")


def _read_csv(run_dir: Path, name: str) -> pd.DataFrame:
    path = run_dir / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _read_rtcp(run_dir: Path, preferred: str = "rtcp.csv") -> pd.DataFrame:
    """Read the contract name first, then the hardware sender RR log."""
    for name in ("rtcp.csv", preferred, "sender_rtcp.csv"):
        path = run_dir / name
        if path.exists():
            return pd.read_csv(path)
    return pd.DataFrame()


def _number(series: pd.Series, default: float = float("nan")) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else default


def _packet_loss(receiver: pd.DataFrame, rtcp: pd.DataFrame) -> float:
    if not rtcp.empty and "cum_lost" in rtcp and "ext_high_seq" in rtcp:
        lost = _number(rtcp["cum_lost"])
        high = _number(rtcp["ext_high_seq"])
        if not math.isnan(lost) and not math.isnan(high):
            if "expected" in rtcp:
                expected = _number(rtcp["expected"], 0)
            else:
                # RTCP cumulative loss is expected minus received (RFC 3550
                # §6.4.1); counting received events preserves an initial gap.
                expected = len(receiver) + int(lost)
            return max(0.0, lost / expected) if expected > 0 else 0.0
    if "expected" in rtcp and "cum_lost" in rtcp:
        expected, lost = _number(rtcp.expected), _number(rtcp.cum_lost)
        return max(0.0, lost / expected) if expected > 0 else 0.0
    return float("nan")


def _jitter_ms(receiver: pd.DataFrame) -> float:
    if receiver.empty or "jitter_ts_units" not in receiver:
        return float("nan")
    # RFC 3550 §6.4.1 reports jitter in RTP timestamp units.
    jitter = pd.to_numeric(receiver.jitter_ts_units, errors="coerce").dropna()
    return float(jitter.iloc[-1] * 1000.0 / RTP_CLOCK_RATE) if not jitter.empty else float("nan")


def _frame_metrics(frames: pd.DataFrame) -> tuple[float, float]:
    if frames.empty or "complete" not in frames:
        return float("nan"), float("nan")
    complete = frames.complete.astype(str).str.lower().isin(("true", "1", "yes"))
    frame_loss = float((~complete).mean())
    if "t_complete_rx_ns" not in frames or "t_playout_rx_ns" not in frames:
        return frame_loss, float("nan")
    # Both columns are receiver-clock timestamps by contract.
    done = subtract_timestamps(frames, "t_complete_rx_ns", "t_playout_rx_ns")
    on_time = complete & done.le(0)
    return frame_loss, float(on_time.mean())


def _latencies_ms(sender: pd.DataFrame, results: pd.DataFrame) -> np.ndarray:
    if sender.empty or results.empty:
        return np.array([], dtype=float)
    needed = {"frame_id", "t_capture_mono_ns"}
    if not needed <= set(sender) or not {"frame_id", "t_result_rx_mono_ns"} <= set(results):
        return np.array([], dtype=float)
    pairs = sender[["frame_id", "t_capture_mono_ns"]].merge(
        results[["frame_id", "t_result_rx_mono_ns"]], on="frame_id", how="inner")
    # Sender capture and result receipt are both on the sender's monotonic clock.
    latency = subtract_timestamps(pairs, "t_result_rx_mono_ns", "t_capture_mono_ns")
    return latency[latency.ge(0)].to_numpy(dtype=float) / 1_000_000.0


def _aoi_seconds(sender: pd.DataFrame, results: pd.DataFrame) -> float:
    if sender.empty or results.empty or not {"frame_id", "t_capture_mono_ns"} <= set(sender):
        return float("nan")
    if not {"frame_id", "t_capture_mono_ns"} <= set(sender) or not {
            "frame_id", "t_result_rx_mono_ns"} <= set(results):
        return float("nan")
    joined = sender[["frame_id", "t_capture_mono_ns"]].merge(
        results[["frame_id", "t_result_rx_mono_ns"]], on="frame_id", how="inner")
    pairs = [(float(row.t_capture_mono_ns) / 1e9,
              float(row.t_result_rx_mono_ns) / 1e9) for row in joined.itertuples()
             if pd.notna(row.t_capture_mono_ns) and pd.notna(row.t_result_rx_mono_ns)]
    if not pairs:
        return float("nan")
    start = min(generated for generated, _ in pairs)
    end = max(received for _, received in pairs)
    if end <= start:
        return 0.0
    # analysis/aoi.py uses the area method, with both event times on sender's clock.
    return float(area_aoi(pairs, start, end)[0])


def _goodput_bps(sender: pd.DataFrame, receiver: pd.DataFrame) -> float:
    if sender.empty or receiver.empty or "bytes" not in receiver:
        return float("nan")
    if "t_capture_mono_ns" not in sender:
        return float("nan")
    captures = pd.to_numeric(sender.t_capture_mono_ns, errors="coerce").dropna()
    if len(captures) < 2:
        return float("nan")
    duration = (captures.max() - captures.min()) / 1e9
    if duration <= 0:
        return float("nan")
    return float(pd.to_numeric(receiver.bytes, errors="coerce").fillna(0).sum() * 8 / duration)


def _step_metrics(run_dir: Path, frames: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Compute CN-T8 metrics for steps described in steps.csv or args.json."""
    steps_path = run_dir / "steps.csv"
    if steps_path.exists():
        steps = pd.read_csv(steps_path)
    else:
        args_path = run_dir / "args.json"
        try:
            raw = json.loads(args_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        step_data = raw.get("steps", [])
        steps = pd.DataFrame(step_data)
    if steps.empty or frames.empty or "t_complete_rx_ns" not in frames:
        return {}
    output = {}
    time_column = "t_complete_rx_ns"
    for i, step in steps.iterrows():
        start = step.get("start_rx_ns", step.get("start_ns"))
        end = step.get("end_rx_ns", step.get("end_ns"))
        if pd.isna(start) or pd.isna(end):
            continue
        grouping_column = "t_playout_rx_ns" if "t_playout_rx_ns" in frames else time_column
        subset = frames[pd.to_numeric(frames[grouping_column], errors="coerce").between(
            start, end, inclusive="left")]
        if subset.empty:
            continue
        complete = subset.complete.astype(str).str.lower().isin(("true", "1", "yes"))
        if "t_complete_rx_ns" in subset and "t_playout_rx_ns" in subset:
            delta = subtract_timestamps(subset, "t_complete_rx_ns", "t_playout_rx_ns")
            on_time = complete & delta.le(0)
        else:
            on_time = complete
        output[str(step.get("label", step.get("loss", i)))] = {
            "frame_loss": float((~complete).mean()),
            "on_time_ratio": float(on_time.mean()),
            "n_frames": int(len(subset)),
        }
    return output


def compute_run_metrics(run_dir: str | Path, *, rtcp_csv: str = "rtcp.csv") -> dict:
    """Load a run directory and return scalar metrics plus optional CN-T8 steps."""
    run_dir = Path(run_dir)
    sender, receiver = _read_csv(run_dir, "sender.csv"), _read_csv(run_dir, "receiver.csv")
    frames, rtcp = _read_csv(run_dir, "frames_rx.csv"), _read_rtcp(run_dir, rtcp_csv)
    results = _read_csv(run_dir, "results_tx.csv")
    frame_loss, on_time = _frame_metrics(frames)
    latencies = _latencies_ms(sender, results)
    return {
        "run_id": run_dir.name,
        "packet_loss": _packet_loss(receiver, rtcp),
        "jitter_ms": _jitter_ms(receiver),
        "frame_loss": frame_loss,
        "on_time_ratio": on_time,
        "goodput_bps": _goodput_bps(sender, receiver),
        "capture_ai_latency_p50_ms": float(np.percentile(latencies, 50)) if len(latencies) else float("nan"),
        "capture_ai_latency_p95_ms": float(np.percentile(latencies, 95)) if len(latencies) else float("nan"),
        "ai_result_avg_age_s": _aoi_seconds(sender, results),
        "steps": _step_metrics(run_dir, frames),
    }


def aggregate_runs(runs: list[dict], *, confidence: float = 0.95) -> dict[str, dict[str, float]]:
    """Aggregate scalar run metrics with Student-t confidence intervals."""
    keys = [k for k in runs[0] if k not in ("run_id", "steps")] if runs else []
    result = {}
    for key in keys:
        vals = np.asarray([r[key] for r in runs], dtype=float)
        vals = vals[np.isfinite(vals)]
        if not len(vals):
            result[key] = {"n": 0, "mean": float("nan"), "min": float("nan"),
                           "max": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
            continue
        avg = float(np.mean(vals))
        # The experiment contract uses five repetitions. This table keeps the
        # common small-sample Student-t intervals exact without adding SciPy.
        if len(vals) > 1 and confidence == 0.95:
            critical = _T_975.get(len(vals) - 1, 1.96)
            margin = critical * stdev(vals) / math.sqrt(len(vals))
        else:
            margin = float("nan")
        result[key] = {"n": int(len(vals)), "mean": avg, "min": float(np.min(vals)),
                       "max": float(np.max(vals)), "ci_low": avg - margin,
                       "ci_high": avg + margin}
    return result


def analyze_config(config_dir: str | Path) -> tuple[list[dict], dict[str, dict[str, float]]]:
    """Analyze run<k> subdirectories under one configuration."""
    config_dir = Path(config_dir)
    runs = [compute_run_metrics(p) for p in sorted(config_dir.glob("run*")) if p.is_dir()]
    return runs, aggregate_runs(runs)
