#!/usr/bin/env bash
# Ten seconds of 15 fps media, plus bounded RTCP/playout drain. No external tools.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
export PYTHONPATH="$ROOT/rtp${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" - "$ROOT" "${1:-}" <<'PY'
import csv
from datetime import datetime, timezone
from pathlib import Path
import select
import subprocess
import sys

root = Path(sys.argv[1])
out = Path(sys.argv[2]) if sys.argv[2] else root / "rtp/results/loopback" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
out = out.resolve()
out.mkdir(parents=True, exist_ok=True)
rx_log = (out / "receiver.log").open("w")
rx = subprocess.Popen([sys.executable, "-m", "rtp", "receiver", "--bind", "127.0.0.1",
    "--port", "5004", "--duration", "16", "--exit-on-bye", "--out-dir", str(out),
    "--rtcp-csv", "receiver_rtcp.csv"],
    stdout=subprocess.PIPE, stderr=rx_log, text=True)
try:
    if not select.select([rx.stdout], [], [], 5)[0]:
        raise RuntimeError("receiver did not become ready within 5 s")
    ready = rx.stdout.readline()
    rx_log.write(ready)
    rx_log.flush()
    if not ready.startswith("READY"):
        raise RuntimeError(f"receiver failed to start; see {out / 'receiver.log'}")
    with (out / "sender.log").open("w") as tx_log:
        subprocess.run([sys.executable, "-m", "rtp", "sender", "--host", "127.0.0.1",
            "--port", "5004", "--source", "synthetic", "--duration", "10", "--fps", "15",
            "--out-dir", str(out), "--rtcp-csv", "sender_rtcp.csv"], stdout=tx_log, stderr=subprocess.STDOUT,
            check=True, timeout=20)
    remaining, _ = rx.communicate(timeout=6)
    rx_log.write(remaining)
    if rx.returncode:
        raise RuntimeError(f"receiver exited {rx.returncode}")
    merge = "import csv,pathlib,sys; d=pathlib.Path(sys.argv[1]); rows=[]; header=None\n" \
        "for name in ('sender_rtcp.csv','receiver_rtcp.csv'):\n" \
        " p=d/name\n" \
        " if p.exists():\n" \
        "  with p.open(newline='') as f:\n" \
        "   r=csv.DictReader(f); header=header or r.fieldnames; rows.extend(r)\n" \
        "with (d/'rtcp.csv').open('w',newline='') as f:\n" \
        " w=csv.DictWriter(f,fieldnames=header); w.writeheader(); w.writerows(sorted(rows,key=lambda x:int(x['t_mono_ns'])))\n"
    subprocess.run([sys.executable, "-c", merge, str(out)], check=True)
    def rows(path):
        with path.open(newline="") as f:
            return list(csv.DictReader(f))
    sent = rows(out / "sender.csv")
    packets = rows(out / "receiver.csv")
    frames = rows(out / "frames_rx.csv")
    control = rows(out / "sender_rtcp.csv")
    expected = sum(int(row["n_pkts"]) for row in sent)
    if len(sent) != 150 or len(packets) != expected or len(frames) != 150:
        raise RuntimeError(f"unexpected counts: sent={len(sent)}, packets={len(packets)}/{expected}, frames={len(frames)}")
    if any(row["status"] != "ok" for row in frames):
        raise RuntimeError("loopback has late/lost frames")
    if not any(row["dir"] == "rx" and row["type"] == "RR" and row["rtt_ms"] for row in control):
        raise RuntimeError("no RR with sender-clock RTT received")
    print(f"MEASURED loopback: {len(sent)} frames, {len(packets)} packets, all frames ok; run directory: {out}")
finally:
    if rx.poll() is None:
        rx.terminate()
        try:
            rx.wait(timeout=3)
        except subprocess.TimeoutExpired:
            rx.kill()
            rx.wait()
    if rx.stdout is not None:
        rx.stdout.close()
    rx_log.close()
PY
