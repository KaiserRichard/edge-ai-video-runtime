"""Version 1 UDP contract. Unknown fields are rejected to catch integration typos."""
import json
import math

MAX_DATAGRAM = 60_000
# name: (required fields, optional fields). All fields are flat JSON scalars,
# except cpu_cores and jpeg_b64. Units are part of the field names.
FIELDS = {
    "packet": ({"seq", "rtp_ts", "frame_id", "bytes", "jitter_ms"}, {"frame_jitter_ms"}),
    "frame": ({"frame_id", "rtp_ts", "status"}, {"arrival_offset_ms", "buffer_frames"}),
    "ai": ({"frame_id", "rtp_ts", "policy", "queue_ms", "inference_ms", "class_id", "confidence"}, {"label"}),
    "result": ({"frame_id", "rtp_ts", "latency_ms"}, {"capture_send_ms", "network_playout_ms", "queue_ms", "inference_ms"}),
    "rtcp": ({"kind", "direction"}, {"fraction_lost", "cumulative_lost", "jitter_ms", "rtt_ms"}),
    "sender": ({"bitrate_mbps"}, {"quality", "fps", "step", "decision", "netem", "netem_jitter_ms"}),
    "hardware": ({"temperature_c", "throttled"}, {"cpu_pct", "cpu_cores", "rssi_dbm", "tx_mbps", "kernel_drops", "netem", "netem_jitter_ms"}),
    "queue": ({"fifo_age_ms", "latest_age_ms", "fifo_queue", "latest_queue"}, {"service_ms"}),
    "os": ({"state"}, {"fifo_age_ms", "latest_age_ms", "inference_ms", "condition", "fault", "link_active"}),
    "video": ({"jpeg_b64", "frame_id", "status"}, set()),
}
ENUMS = {"status": {"ok", "late", "lost"}, "policy": {"fifo", "latest"},
         "kind": {"SR", "RR", "APP", "SDES", "BYE", "ABR"},
         "direction": {"rx", "tx", "local"}, "decision": {"up", "down", "hold"},
         "state": {"FRESH", "HOLD", "FAILSAFE"},
         "condition": {"idle-P0", "stress-P0", "idle-P1", "stress-P1"}}
STRINGS = {"label", "netem", "fault", "jpeg_b64"} | ENUMS.keys()
INTEGERS = {"seq", "rtp_ts", "frame_id", "bytes", "class_id", "fraction_lost", "cumulative_lost", "kernel_drops", "throttled", "buffer_frames", "fifo_queue", "latest_queue", "quality", "step"}
SIGNED = {"arrival_offset_ms", "rssi_dbm", "temperature_c", "cumulative_lost"}


def validate(message):
    if not isinstance(message, dict) or set(message) != {"v", "profile", "source", "session", "type", "time_s", "data"}:
        raise ValueError("expected v, profile, source, session, type, time_s, data")
    if type(message["v"]) is not int or message["v"] != 1:
        raise ValueError("unsupported schema version")
    if message["profile"] not in ("cn", "os") or message["source"] not in ("receiver", "pi", "bridge"):
        raise ValueError("invalid profile/source")
    if not isinstance(message["session"], str) or not 1 <= len(message["session"]) <= 64:
        raise ValueError("session must identify one experiment, 1..64 chars")
    timestamp = message["time_s"]
    if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("time_s must be finite and nonnegative")
    kind, data = message["type"], message["data"]
    if not isinstance(kind, str) or kind not in FIELDS or not isinstance(data, dict):
        raise ValueError("invalid event type/data")
    required, optional = FIELDS[kind]
    if not required <= data.keys() or data.keys() - required - optional:
        raise ValueError(f"invalid {kind} fields")
    for key, value in data.items():
        if key in STRINGS:
            if not isinstance(value, str) or len(value) > (55_000 if key == "jpeg_b64" else 512):
                raise ValueError(f"invalid string: {key}")
            if key in ENUMS and value not in ENUMS[key]:
                raise ValueError(f"invalid {key}")
        elif key == "cpu_cores":
            if not isinstance(value, list) or not 1 <= len(value) <= 128 or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 100 for x in value):
                raise ValueError("cpu_cores must be percentages")
        elif key == "link_active":
            if type(value) is not bool:
                raise ValueError("link_active must be boolean")
        elif type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"invalid number: {key}")
        elif key in INTEGERS and type(value) is not int:
            raise ValueError(f"{key} must be integer")
        elif key not in SIGNED and value < 0:
            raise ValueError(f"{key} must be nonnegative")
    for key, upper in {"seq": 65535, "rtp_ts": 2**32-1, "fraction_lost": 255, "confidence": 1, "cpu_pct": 100, "quality": 100}.items():
        if key in data and data[key] > upper:
            raise ValueError(f"{key} out of range")
    return message


def decode(datagram):
    if len(datagram) > MAX_DATAGRAM:
        raise ValueError("telemetry datagram too large")
    try:
        return validate(json.loads(datagram))
    except (UnicodeError, TypeError, KeyError, OverflowError) as exc:
        raise ValueError("invalid telemetry JSON") from exc


def event(kind, data, time_s=0.0, source="receiver", profile="cn", session="demo"):
    return validate(dict(v=1, profile=profile, source=source, session=session,
                         type=kind, time_s=time_s, data=data))
