"""Build hardware summary tables for the CN-T2/3/5/6/7/9 runs."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from metrics import compute_run_metrics, subtract_timestamps


SCENARIOS = ("T2", "T3", "T4", "T5", "T6", "T7", "T9")


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _meta(run: Path) -> dict:
    try:
        return json.loads((run / "meta.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _num(value) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _column(df: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(df[name], errors="coerce") if name in df else pd.Series(dtype=float)


def _loss_probability(config: str, netem: str) -> float:
    text = f"{config} {netem}".lower()
    if "gemodel" in text or "ge model" in text or "delay" in text:
        return float("nan")
    match = re.search(r"loss(?:\s+random)?\s+(\d+(?:\.\d+)?)\s*%", netem, re.I)
    if match:
        return float(match.group(1)) / 100.0
    match = re.search(r"loss(?:_|-)?(\d+(?:\.\d+)?)", config, re.I)
    return float(match.group(1)) / 100.0 if match else float("nan")


def _config_value(config: str, meta: dict, key: str) -> float:
    if key in meta:
        return _num(meta[key])
    match = re.search(rf"(?:^|[^a-z]){re.escape(key)}[_=-]?(\d+)", config, re.I)
    return _num(match.group(1)) if match else float("nan")


def _fmt(v: float, digits: int = 3) -> str:
    return f"{v:.{digits}f}" if math.isfinite(v) else ""


def _percentile(series: pd.Series, pct: float) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(np.percentile(values, pct)) if len(values) else float("nan")


def _clock_delta_ms(df: pd.DataFrame, end: str, start: str) -> pd.Series:
    if end not in df or start not in df:
        return pd.Series(dtype=float)
    return subtract_timestamps(df, end, start).dropna() / 1_000_000.0


def _rr_loss(run: Path) -> float:
    m = compute_run_metrics(run)
    return m["packet_loss"]


def _sequence_loss(sender: pd.DataFrame, receiver: pd.DataFrame) -> float:
    sent = _column(sender, "n_pkts").fillna(0).sum()
    received = receiver["seq"].nunique() if "seq" in receiver else 0
    return 1 - received / sent if sent > 0 else float("nan")


def _throttle(run: Path, when: str) -> str:
    path = run / f"throttled_{when}.txt"
    return " ".join(path.read_text().split()) if path.exists() else ""


def _run_metrics(run: Path, scenario: str, config: str) -> dict:
    sender, receiver = _read(run / "sender.csv"), _read(run / "receiver.csv")
    frames, results, ai = (_read(run / name) for name in
                           ("frames_rx.csv", "results_tx.csv", "ai.csv"))
    meta = _meta(run)
    netem = str(meta.get("netem", ""))
    if not netem and (run / "qdisc.txt").exists():
        netem = " ".join((run / "qdisc.txt").read_text().split())
    sent_frames = len(sender) if len(sender) else len(frames)
    status = frames.get("status", pd.Series(dtype=str)).astype(str).str.lower()
    frame_loss = float(status.eq("lost").sum() / sent_frames) if sent_frames else float("nan")
    late = float(status.eq("late").sum() / sent_frames) if sent_frames else float("nan")
    on_time = float(status.eq("ok").sum() / sent_frames) if sent_frames else float("nan")
    captures = _column(sender, "t_capture_mono_ns").dropna()
    duration = (captures.max() - captures.min()) / 1e9 if len(captures) > 1 else float("nan")
    sent_bytes = _column(sender, "bytes").fillna(0).sum()
    packets_per_frame = _column(sender, "n_pkts").mean() if "n_pkts" in sender else float("nan")
    p = _loss_probability(config, netem)
    expected = 1 - (1 - p) ** packets_per_frame if math.isfinite(p) and math.isfinite(packets_per_frame) else float("nan")
    base = compute_run_metrics(run)
    row = {
        "scenario": scenario, "config": config, "run": run.name, "netem": netem,
        "packet_loss_rr": _rr_loss(run), "packet_loss_seq": _sequence_loss(sender, receiver),
        "packets_per_frame": _num(packets_per_frame), "frame_loss": frame_loss,
        "expected_frame_loss": expected, "on_time": on_time, "late": late,
        "jitter_ms": base["jitter_ms"], "latency_p50": base["capture_ai_latency_p50_ms"],
        "latency_p95": base["capture_ai_latency_p95_ms"],
        "ai_rate": len(results) / duration if duration > 0 else float("nan"),
        "throttle_before": _throttle(run, "before"), "throttle_after": _throttle(run, "after"),
        "meta": meta, "sender": sender, "receiver": receiver, "frames": frames,
        "results": results, "ai": ai,
    }
    if scenario == "T5":
        payload = _config_value(config, meta, "mtu_payload")
        if not math.isfinite(payload):
            payload = _config_value(config, meta, "payload")
        # sender.bytes is the encoded frame length. With fixed payload size, all
        # but each frame's final RTP packet carry a full payload.
        oversized = 0
        if math.isfinite(payload):
            for size in _column(sender, "bytes").dropna():
                full, remainder = divmod(int(size), int(payload))
                oversized += full if payload + 48 > 1500 else 0
                oversized += int(remainder + 48 > 1500)
        ip_fragments = (int(math.ceil((payload + 28) / 1480))
                        if math.isfinite(payload) and payload + 48 > 1500 else float("nan"))
        quality = _num(meta.get("quality", _column(sender, "quality").mean() if "quality" in sender else float("nan")))
        if not math.isfinite(quality):
            qmatch = re.search(r"q(\d+)", config, re.I)
            quality = _num(qmatch.group(1)) if qmatch else float("nan")
        row.update({
            "quality": quality,
            "mtu_payload": payload,
            "jpeg_bytes": _column(sender, "bytes").mean() if "bytes" in sender else float("nan"),
            "bitrate_mbps": sent_bytes * 8 / duration / 1e6 if duration > 0 else float("nan"),
            "oversized_datagrams": oversized if math.isfinite(payload) else float("nan"),
            "ip_fragments_per_datagram": ip_fragments,
            "expected_datagram_loss": 1 - (1 - p) ** ip_fragments if math.isfinite(p) and math.isfinite(ip_fragments) else float("nan"),
        })
    elif scenario == "T6":
        iw = _parse_iw(run / "iw_link.log")
        row.update(iw)
    elif scenario == "T7":
        queue_wait = _clock_delta_ms(ai, "t_start_rx_ns", "t_enqueue_rx_ns")
        row.update({
            "age_s": base["ai_result_avg_age_s"],
            "results_s": row["ai_rate"],
            "frames_skipped": int(ai.status.astype(str).str.lower().eq("skipped").sum()) if "status" in ai else 0,
            "queue_wait_p50": _percentile(queue_wait, 50),
            "queue_wait_p95": _percentile(queue_wait, 95),
            "queue_growth_ms_per_s": _trend_per_second(ai, queue_wait),
        })
    elif scenario == "T9":
        paired = sender[[c for c in ("frame_id", "t_capture_mono_ns", "t_send_first_mono_ns") if c in sender]].merge(
            results[[c for c in ("frame_id", "t_result_rx_mono_ns") if c in results]], on="frame_id", how="inner") if not sender.empty and not results.empty else pd.DataFrame()
        pi_first = _clock_delta_ms(paired, "t_send_first_mono_ns", "t_capture_mono_ns")
        pi_second = _clock_delta_ms(paired, "t_result_rx_mono_ns", "t_send_first_mono_ns")
        edge_wait = _clock_delta_ms(frames, "t_playout_rx_ns", "t_complete_rx_ns")
        edge_queue = _clock_delta_ms(ai, "t_start_rx_ns", "t_enqueue_rx_ns")
        edge_infer = _clock_delta_ms(ai, "t_done_rx_ns", "t_start_rx_ns")
        totals = pi_first.reset_index(drop=True).add(pi_second.reset_index(drop=True), fill_value=np.nan)
        total = _clock_delta_ms(paired, "t_result_rx_mono_ns", "t_capture_mono_ns")
        diff = (total.reset_index(drop=True) - totals.reset_index(drop=True)).abs()
        row.update({
            "pi_capture_send_p50": _percentile(pi_first, 50), "pi_capture_send_p95": _percentile(pi_first, 95),
            "pi_send_result_p50": _percentile(pi_second, 50), "pi_send_result_p95": _percentile(pi_second, 95),
            "pi_total_p50": _percentile(total, 50), "pi_total_p95": _percentile(total, 95),
            "pi_sum_max_error_ms": float(diff.max()) if len(diff.dropna()) else float("nan"),
            "edge_playout_wait_p50": _percentile(edge_wait, 50), "edge_playout_wait_p95": _percentile(edge_wait, 95),
            "edge_queue_wait_p50": _percentile(edge_queue, 50), "edge_queue_wait_p95": _percentile(edge_queue, 95),
            "edge_inference_p50": _percentile(edge_infer, 50), "edge_inference_p95": _percentile(edge_infer, 95),
        })
    return row


def _trend_per_second(ai: pd.DataFrame, wait_ms: pd.Series) -> float:
    if len(ai) < 2 or len(wait_ms) != len(ai) or "t_enqueue_rx_ns" not in ai:
        return float("nan")
    time = _column(ai, "t_enqueue_rx_ns").to_numpy(dtype=float) / 1e9
    values = wait_ms.to_numpy(dtype=float)
    good = np.isfinite(time) & np.isfinite(values)
    if good.sum() < 2 or np.ptp(time[good]) <= 0:
        return float("nan")
    return float(np.polyfit(time[good], values[good], 1)[0])


def _parse_iw(path: Path) -> dict:
    output = {"rssi_mean": float("nan"), "rssi_min": float("nan"), "tx_bitrate": "", "frequency": "", "channel": ""}
    if not path.exists():
        return output
    text = path.read_text(errors="replace")
    signals = [_num(x) for x in re.findall(r"signal:\s*(-?\d+(?:\.\d+)?)\s*dBm", text)]
    signals = [x for x in signals if math.isfinite(x)]
    output["rssi_mean"] = float(np.mean(signals)) if signals else float("nan")
    output["rssi_min"] = min(signals) if signals else float("nan")
    rates = re.findall(r"tx bitrate:\s*([^\r\n]+)", text)
    freqs = re.findall(r"freq:\s*(\d+)", text)
    output["tx_bitrate"] = rates[-1].strip() if rates else ""
    output["frequency"] = freqs[-1] if freqs else ""
    if freqs:
        f = int(freqs[-1])
        output["channel"] = str((f - 2407) // 5 if f < 2500 else (f - 5000) // 5)
    return output


def _collect(results_root: Path) -> tuple[dict[str, list[dict]], dict[str, list[str]]]:
    rows = {s: [] for s in SCENARIOS}
    smoke = {s: [] for s in SCENARIOS}
    for scenario in SCENARIOS:
        folder = results_root / scenario
        if not folder.exists():
            continue
        for config_dir in sorted(p for p in folder.iterdir() if p.is_dir()):
            if config_dir.name.startswith("smoke"):
                smoke[scenario].append(config_dir.name)
                continue
            for run in sorted(p for p in config_dir.glob("run* ".strip()) if p.is_dir()):
                rows[scenario].append(_run_metrics(run, scenario, config_dir.name))
    return rows, smoke


def _aggregate(rows: list[dict], columns: list[str]) -> list[dict]:
    output = []
    for config in sorted({r["config"] for r in rows}):
        group = [r for r in rows if r["config"] == config]
        entry = {"config": config, "runs": len(group)}
        for key in columns:
            vals = [_num(r.get(key)) for r in group]
            vals = [v for v in vals if math.isfinite(v)]
            entry[key] = float(np.mean(vals)) if vals else float("nan")
        entry["netem"] = "; ".join(sorted({r["netem"] for r in group if r["netem"]}))
        output.append(entry)
    return output


def _table(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |")


def build_report(results_root: Path, output_path: Path) -> None:
    all_rows, smoke = _collect(results_root)
    lines = ["# Hardware results tables (CN-T2/T3/T4/T5/T6/T7/T9)", "",
             "Packet loss is reported both from the sender's latest RR (`cum_lost / expected`) and from unique received RTP sequence numbers divided by sender packet count. Frame loss and on-time ratio use frames as denominator. Latency and queue/inference intervals are calculated only within their named clock. Empty cells mean unavailable or inapplicable.", ""]
    headers = ["Config", "Runs", "Configured netem", "RR loss", "Sequence loss", "Packets/frame", "Frame loss", "CALCULATED 1−(1−p)^n̄", "On-time", "Late", "Jitter (ms)", "Capture→AI P50 (ms)", "Capture→AI P95 (ms)", "AI results/s", "Throttled before", "Throttled after"]
    lines.extend(["## CN-T2 and CN-T3", ""])
    for scenario in ("T2", "T3", "T4"):
        lines.extend([f"### CN-{scenario}", ""])
        table_rows = []
        for row in _aggregate(all_rows[scenario], ["packet_loss_rr", "packet_loss_seq", "packets_per_frame", "frame_loss", "expected_frame_loss", "on_time", "late", "jitter_ms", "latency_p50", "latency_p95", "ai_rate"]):
            original = [r for r in all_rows[scenario] if r["config"] == row["config"]]
            table_rows.append([row["config"], str(row["runs"]), row["netem"], _fmt(row["packet_loss_rr"]), _fmt(row["packet_loss_seq"]), _fmt(row["packets_per_frame"]), _fmt(row["frame_loss"]), _fmt(row["expected_frame_loss"]), _fmt(row["on_time"]), _fmt(row["late"]), _fmt(row["jitter_ms"], 2), _fmt(row["latency_p50"], 2), _fmt(row["latency_p95"], 2), _fmt(row["ai_rate"], 2), "; ".join(sorted({x["throttle_before"] for x in original if x["throttle_before"]})), "; ".join(sorted({x["throttle_after"] for x in original if x["throttle_after"]}))])
        if not table_rows:
            table_rows = [["_No eligible runs_", "0"] + [""] * (len(headers) - 2)]
        _table(lines, headers, table_rows)
        lines.append("")
    lines.extend(["## CN-T5 — bitrate and packet size", "", "For 2 % independent loss, the calculated frame loss is `1 − (1 − p)^n`, using each run's mean packets/frame. IP datagram length is estimated as `mtu_payload + 48 B` (IPv4, UDP, RTP, and shared payload header). For a 3000 B payload, the estimated IP fragmentation count is `ceil((mtu_payload + 28) / 1480) = 3`. Netem drops per IP fragment, so an RTP datagram is lost if any fragment is lost; calculated datagram loss is `1 − (1 − p)^3`.", ""])
    t5_headers = ["Config", "Runs", "Quality", "MTU payload (B)", "Mean JPEG bytes/frame", "Measured sender bitrate (Mb/s)", "Packets/frame", "RR loss", "Sequence loss", "Frame loss", "CALCULATED frame loss at 2 %", "IP datagrams >1500 B", "CALCULATED loss/datagram (3000 B)"]
    t5_rows = []
    for agg in _aggregate(all_rows["T5"], ["quality", "mtu_payload", "jpeg_bytes", "bitrate_mbps", "packets_per_frame", "packet_loss_rr", "packet_loss_seq", "frame_loss", "expected_frame_loss", "oversized_datagrams", "expected_datagram_loss"]):
        vals = [r for r in all_rows["T5"] if r["config"] == agg["config"]]
        t5_rows.append([agg["config"], str(agg["runs"]), _fmt(agg["quality"], 0), _fmt(agg["mtu_payload"], 0), _fmt(agg["jpeg_bytes"], 1), _fmt(agg["bitrate_mbps"], 3), _fmt(agg["packets_per_frame"]), _fmt(agg["packet_loss_rr"]), _fmt(agg["packet_loss_seq"]), _fmt(agg["frame_loss"]), _fmt(agg["expected_frame_loss"]), _fmt(agg["oversized_datagrams"], 0), _fmt(agg["expected_datagram_loss"])])
    if not t5_rows:
        t5_rows = [["_No eligible runs_", "0"] + [""] * (len(t5_headers) - 2)]
    _table(lines, t5_headers, t5_rows)
    lines.append("")
    lines.extend(["## CN-T6 — Wi-Fi link", ""])
    t6_headers = ["Config", "Runs", "RR loss", "Sequence loss", "Jitter (ms)", "On-time", "Capture→AI P50/P95 (ms)", "RSSI mean/min (dBm)", "Tx bitrate", "Frequency (MHz)", "Channel"]
    t6_rows = []
    for agg in _aggregate(all_rows["T6"], ["packet_loss_rr", "packet_loss_seq", "jitter_ms", "on_time", "latency_p50", "latency_p95", "rssi_mean", "rssi_min"]):
        sample = next(r for r in all_rows["T6"] if r["config"] == agg["config"])
        t6_rows.append([agg["config"], str(agg["runs"]), _fmt(agg["packet_loss_rr"]), _fmt(agg["packet_loss_seq"]), _fmt(agg["jitter_ms"], 2), _fmt(agg["on_time"]), f"{_fmt(agg['latency_p50'],2)} / {_fmt(agg['latency_p95'],2)}", f"{_fmt(agg['rssi_mean'],1)} / {_fmt(agg['rssi_min'],1)}", str(sample.get("tx_bitrate", "")), str(sample.get("frequency", "")), str(sample.get("channel", ""))])
    _table(lines, t6_headers, t6_rows or [["_No runs yet_"] + [""] * (len(t6_headers) - 1)])
    lines.append("")
    lines.extend(["## CN-T7 — FIFO vs latest", "", "AI-result age is time-average AoI on the Pi clock, computed from capture and result-receipt pairs in `sender.csv` / `results_tx.csv`. Queue growth is the linear trend in enqueue-to-start wait against enqueue time on the edge clock.", ""])
    t7_headers = ["Config / policy", "Runs", "Mean AI-result age (s)", "Results/s", "Frames skipped", "Queue wait P50/P95 (ms)", "FIFO queue growth (ms/s)", "Capture→AI P50/P95 (ms)"]
    t7_rows = []
    for agg in _aggregate(all_rows["T7"], ["age_s", "results_s", "frames_skipped", "queue_wait_p50", "queue_wait_p95", "queue_growth_ms_per_s", "latency_p50", "latency_p95"]):
        t7_rows.append([agg["config"], str(agg["runs"]), _fmt(agg["age_s"], 3), _fmt(agg["results_s"], 2), _fmt(agg["frames_skipped"], 0), f"{_fmt(agg['queue_wait_p50'],2)} / {_fmt(agg['queue_wait_p95'],2)}", _fmt(agg["queue_growth_ms_per_s"], 2), f"{_fmt(agg['latency_p50'],2)} / {_fmt(agg['latency_p95'],2)}"])
    _table(lines, t7_headers, t7_rows or [["_No runs yet_"] + [""] * (len(t7_headers) - 1)])
    lines.append("")
    lines.extend(["## CN-T9 — per-frame latency breakdown", "", "Pi-clock components are capture→first send and first send→result receipt; Pi-clock total is capture→result receipt. Edge-clock components are playout wait, AI queue wait, and inference. Each cell is mean of per-run P50/P95 values. Pi-clock component sum is checked against total per paired frame; the reported maximum absolute error should be ≤1 ms.", ""])
    t9_headers = ["Config", "Runs", "Pi capture→send P50/P95 (ms)", "Pi send→result P50/P95 (ms)", "Pi total P50/P95 (ms)", "Max Pi sum error (ms)", "Edge playout wait P50/P95 (ms)", "Edge queue wait P50/P95 (ms)", "Edge inference P50/P95 (ms)"]
    t9_rows = []
    keys = ["pi_capture_send_p50", "pi_capture_send_p95", "pi_send_result_p50", "pi_send_result_p95", "pi_total_p50", "pi_total_p95", "pi_sum_max_error_ms", "edge_playout_wait_p50", "edge_playout_wait_p95", "edge_queue_wait_p50", "edge_queue_wait_p95", "edge_inference_p50", "edge_inference_p95"]
    for agg in _aggregate(all_rows["T9"], keys):
        t9_rows.append([agg["config"], str(agg["runs"]), f"{_fmt(agg['pi_capture_send_p50'],2)} / {_fmt(agg['pi_capture_send_p95'],2)}", f"{_fmt(agg['pi_send_result_p50'],2)} / {_fmt(agg['pi_send_result_p95'],2)}", f"{_fmt(agg['pi_total_p50'],2)} / {_fmt(agg['pi_total_p95'],2)}", _fmt(agg["pi_sum_max_error_ms"], 3), f"{_fmt(agg['edge_playout_wait_p50'],2)} / {_fmt(agg['edge_playout_wait_p95'],2)}", f"{_fmt(agg['edge_queue_wait_p50'],2)} / {_fmt(agg['edge_queue_wait_p95'],2)}", f"{_fmt(agg['edge_inference_p50'],2)} / {_fmt(agg['edge_inference_p95'],2)}"])
    _table(lines, t9_headers, t9_rows or [["_No runs yet_"] + [""] * (len(t9_headers) - 1)])
    smoke_items = [f"CN-{s}: {', '.join(names)}" for s, names in smoke.items() if names]
    lines.extend(["", "Footnote: smoke configurations excluded from all tables: " + ("; ".join(smoke_items) if smoke_items else "none found") + "."])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")


def main(argv=None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: hw_tables.py RESULTS_ROOT")
    project = Path(__file__).resolve().parents[2]
    build_report(Path(args[0]), project / "rtp" / "report" / "hw_tables.md")


if __name__ == "__main__":
    main()
