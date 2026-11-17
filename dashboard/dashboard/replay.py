"""Adapters for the actual RTP hardware/simulator CSVs and an OS CSV contract.

Only one directory/run is loaded, never a recursive union of experiments.
Pi-clock durations and receiver-clock durations are calculated independently.
"""
import asyncio
from collections import defaultdict
import csv
import math
from pathlib import Path
import warnings

from .metrics import PacketStats
from .schema import event


def number(row, key, default=None):
    value = row.get(key)
    if value in (None, ""):
        if default is None:
            raise ValueError(f"missing {key}")
        return default
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite {key}")
    return result


def integer(row, key, default=None):
    value = number(row, key, default)
    if value != int(value):
        raise ValueError(f"non-integer {key}")
    return int(value)


def optional(row, key, target=None, scale=1):
    return {} if row.get(key) in (None, "") else {target or key: number(row, key) * scale}


def identify(headers):
    keys = set(headers)
    if {"seq", "t_arrival_rx_ns", "jitter_ts_units"} <= keys:
        return "packet"
    if {"n_received", "t_playout_rx_ns", "status"} <= keys:
        return "frame"
    if {"t_capture_mono_ns", "t_send_first_mono_ns", "bytes"} <= keys:
        return "sender"
    if {"t_capture_mono_ns", "t_result_rx_mono_ns"} <= keys:
        return "result"
    if {"t_enqueue_rx_ns", "t_done_rx_ns", "policy"} <= keys:
        return "ai"
    if {"t_mono_ns", "dir", "type"} <= keys:
        return "rtcp"
    if {"time_s", "state"} <= keys:
        return "os"
    raise ValueError("unrecognized CSV header")


def load_replay(path):
    path = Path(path)
    files = [path] if path.is_file() else sorted(path.glob("*.csv"))
    if not files:
        raise ValueError(f"no CSV files in {path}")
    groups = defaultdict(list)
    for file in files:
        with file.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            try:
                kind = identify(reader.fieldnames or [])
            except ValueError as exc:
                warnings.warn(f"{file.name}: {exc}", stacklevel=2)
                continue
            # rtcp.csv can be either endpoint: filename is only a fallback.
            for line, row in enumerate(reader, 2):
                row["_file"], row["_line"] = file.name, line
                if kind == "rtcp":
                    row["_source"] = "pi" if "sender" in file.name else "receiver"
                groups[kind].append(row)

    def safe_time(row, field):
        try:
            return number(row, field)
        except ValueError:
            return math.inf

    rx_times = [safe_time(r, field) for kind, field in (("packet", "t_arrival_rx_ns"), ("frame", "t_playout_rx_ns"), ("ai", "t_enqueue_rx_ns")) for r in groups[kind]]
    rx_times += [safe_time(r, "t_mono_ns") for r in groups["rtcp"] if r["_source"] == "receiver"]
    pi_times = [safe_time(r, field) for kind, field in (("sender", "t_send_first_mono_ns"), ("result", "t_capture_mono_ns")) for r in groups[kind]]
    pi_times += [safe_time(r, "t_mono_ns") for r in groups["rtcp"] if r["_source"] == "pi"]
    rx_origin, pi_origin = min(rx_times, default=0), min(pi_times, default=0)
    if not math.isfinite(rx_origin):
        rx_origin = 0
    if not math.isfinite(pi_origin):
        pi_origin = 0
    # Match first received packet to the corresponding sender frame only for
    # visual alignment. Propagation time is NOT estimated by this anchor.
    packets = sorted(groups["packet"], key=lambda r: safe_time(r, "t_arrival_rx_ns"))
    sends = {(r.get("frame_id"), r.get("rtp_ts")): r for r in groups["sender"]}
    for packet in packets:
        sender = sends.get((packet.get("frame_id"), packet.get("rtp_ts")))
        if sender and math.isfinite(safe_time(sender, "t_send_first_mono_ns")) and math.isfinite(safe_time(packet, "t_arrival_rx_ns")):
            pi_origin = number(sender, "t_send_first_mono_ns") - (number(packet, "t_arrival_rx_ns") - rx_origin)
            break

    events = []
    tracker = PacketStats()
    sender_window = []
    ai_rows = {(r.get("frame_id"), r.get("rtp_ts")): r for r in groups["ai"] if r.get("status") == "ok"}
    for kind in ("packet", "frame", "ai", "sender", "result", "rtcp", "os"):
        rows = packets if kind == "packet" else groups[kind]
        if kind == "sender":
            rows = sorted(rows, key=lambda r: safe_time(r, "t_send_first_mono_ns"))
        for row in rows:
            try:
                data, source, profile = {}, "receiver", "cn"
                if kind in ("packet", "frame", "ai", "result"):
                    data = {key: integer(row, key) for key in ("frame_id", "rtp_ts")}
                if kind == "packet":
                    at = (number(row, "t_arrival_rx_ns") - rx_origin) / 1e9
                    data.update(seq=integer(row, "seq"), bytes=integer(row, "bytes"), jitter_ms=number(row, "jitter_ts_units") / 90)
                    tracker.update(data, number(row, "t_arrival_rx_ns") / 1e9)
                    data["frame_jitter_ms"] = tracker.frame_jitter
                elif kind == "frame":
                    deadline = number(row, "t_playout_rx_ns")
                    # Lost rows are finalized after a late window not logged in
                    # this CSV. Replay uses the deadline as the display time.
                    at = (max(deadline, number(row, "t_complete_rx_ns", deadline)) - rx_origin) / 1e9
                    data["status"] = row["status"]
                    if row.get("t_complete_rx_ns"):
                        data["arrival_offset_ms"] = (number(row, "t_complete_rx_ns") - deadline) / 1e6
                elif kind == "ai":
                    if row.get("status") != "ok":
                        continue
                    done = number(row, "t_done_rx_ns")
                    at = (done - rx_origin) / 1e9
                    data.update(policy=row["policy"], queue_ms=(number(row, "t_start_rx_ns") - number(row, "t_enqueue_rx_ns")) / 1e6,
                                inference_ms=(done - number(row, "t_start_rx_ns")) / 1e6,
                                class_id=integer(row, "class_id"), confidence=number(row, "confidence"))
                elif kind == "sender":
                    source = "pi"
                    now = number(row, "t_send_last_mono_ns")
                    at = (now - pi_origin) / 1e9
                    sender_window.append((now, number(row, "bytes")))
                    sender_window = [(t, b) for t, b in sender_window if t > now - 1e9]
                    # One-second trailing RTP datagram bitrate; partial startup
                    # window stays a one-second rate, never a divide-by-zero spike.
                    data["bitrate_mbps"] = sum(b for _, b in sender_window) * 8 / 1e6
                    if row.get("quality"):
                        data["quality"] = integer(row, "quality")
                elif kind == "result":
                    source = "pi"
                    at = (number(row, "t_result_rx_mono_ns") - pi_origin) / 1e9
                    total = (number(row, "t_result_rx_mono_ns") - number(row, "t_capture_mono_ns")) / 1e6
                    data["latency_ms"] = total
                    key = (row.get("frame_id"), row.get("rtp_ts"))
                    sender, ai = sends.get(key), ai_rows.get(key)
                    if sender:
                        data["capture_send_ms"] = (number(sender, "t_send_last_mono_ns") - number(row, "t_capture_mono_ns")) / 1e6
                    if ai:
                        data["queue_ms"] = (number(ai, "t_start_rx_ns") - number(ai, "t_enqueue_rx_ns")) / 1e6
                        data["inference_ms"] = (number(ai, "t_done_rx_ns") - number(ai, "t_start_rx_ns")) / 1e6
                    if all(k in data for k in ("capture_send_ms", "queue_ms", "inference_ms")):
                        residual = total - data["capture_send_ms"] - data["queue_ms"] - data["inference_ms"]
                        if residual >= 0:
                            data["network_playout_ms"] = residual
                elif kind == "rtcp":
                    source = row["_source"]
                    at = (number(row, "t_mono_ns") - (pi_origin if source == "pi" else rx_origin)) / 1e9
                    data.update(kind=row["type"], direction=row["dir"])
                    for old, new in (("fraction_lost", "fraction_lost"), ("cum_lost", "cumulative_lost")):
                        if row.get(old):
                            data[new] = integer(row, old)
                    data.update(optional(row, "jitter", "jitter_ms", 1 / 90))
                    data.update(optional(row, "rtt_ms"))
                else:
                    source, profile = "bridge", "os"
                    at = number(row, "time_s")
                    data["state"] = row["state"]
                    for key in ("fifo_age_ms", "latest_age_ms", "inference_ms"):
                        data.update(optional(row, key))
                    for key in ("fault", "condition"):
                        if row.get(key):
                            data[key] = row[key]
                    hw = {}
                    if row.get("temperature_c") and row.get("throttled"):
                        hw.update(temperature_c=number(row, "temperature_c"), throttled=int(row["throttled"], 0))
                        if row.get("cpu_cores"):
                            hw["cpu_cores"] = [float(value) for value in row["cpu_cores"].split(";")]
                        events.append(event("hardware", hw, max(0, at), source="pi", profile="os", session=path.stem))
                events.append(event(kind, data, max(0.0, at), source=source, profile=profile, session=path.stem[:64]))
            except (ValueError, KeyError, TypeError) as exc:
                warnings.warn(f"{row['_file']}:{row['_line']}: skipped {exc}", stacklevel=2)
    if not events:
        raise ValueError("CSV input contains no usable telemetry events")
    events.sort(key=lambda e: e["time_s"])
    origin = events[0]["time_s"]
    for message in events:
        message["time_s"] -= origin
    return events


async def play(hub, events, speed=1.0, loop=False):
    if not math.isfinite(speed) or speed <= 0:
        raise ValueError("replay speed must be positive and finite")
    iteration = 0
    while True:
        start = asyncio.get_running_loop().time()
        hub.status = f"replaying {len(events)} events at {speed:g}x"
        for message in events:
            await asyncio.sleep(max(0, message["time_s"] / speed - (asyncio.get_running_loop().time() - start)))
            hub.publish({**message, "session": f"{message['session'][:48]}-{iteration}"})
        if not loop:
            hub.status = "replay complete"
            return
        iteration += 1
        await asyncio.sleep(0.1)
