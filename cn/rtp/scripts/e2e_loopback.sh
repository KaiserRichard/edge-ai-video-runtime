#!/usr/bin/env bash
# 20 s, 15 fps RTP -> synthetic EdgeAI -> AIRS loopback with seeded 5% packet drop.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
export PYTHONPATH="$ROOT/rtp${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" - "$ROOT" "${1:-}" <<'PY'
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import subprocess
import sys

root = Path(sys.argv[1])
out = Path(sys.argv[2]) if sys.argv[2] else root / "rtp/results/e2e_loopback" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
out = out.resolve()
out.mkdir(parents=True, exist_ok=True)
rx_log = (out / "receiver.log").open("w")
rx = subprocess.Popen([sys.executable, "-m", "rtp", "receiver", "--bind", "127.0.0.1",
    "--port", "5004", "--duration", "24", "--exit-on-bye", "--out-dir", str(out),
    "--rtcp-csv", "receiver_rtcp.csv", "--ai", "synthetic", "--ai-policy", "latest",
    "--ai-service-ms", "30", "--threads", "1"],
    stdout=subprocess.PIPE, stderr=rx_log, text=True)
try:
    if not select.select([rx.stdout], [], [], 5)[0]:
        raise RuntimeError(f"receiver did not become ready; see {out / 'receiver.log'}")
    ready = rx.stdout.readline()
    rx_log.write(ready)
    rx_log.flush()
    if not ready.startswith("READY"):
        raise RuntimeError(f"receiver failed to start: {ready.strip()}; see {out / 'receiver.log'}")
    with (out / "sender.log").open("w") as tx_log:
        subprocess.run([sys.executable, "-m", "rtp", "sender", "--host", "127.0.0.1",
            "--port", "5004", "--source", "synthetic", "--duration", "20", "--fps", "15",
            "--drop-prob", "0.05", "--seed", "7", "--out-dir", str(out),
            "--rtcp-csv", "sender_rtcp.csv"], stdout=tx_log, stderr=subprocess.STDOUT,
            check=True, timeout=28)
    remaining, _ = rx.communicate(timeout=8)
    rx_log.write(remaining)
    if rx.returncode:
        raise RuntimeError(f"receiver exited {rx.returncode}; see {out / 'receiver.log'}")

    # Endpoint RTCP files share the contract schema; combine after both writers close.
    merge = "import csv,pathlib,sys; d=pathlib.Path(sys.argv[1]); rows=[]; header=None\n" \
        "for name in ('sender_rtcp.csv','receiver_rtcp.csv'):\n" \
        " p=d/name\n" \
        " if p.exists():\n" \
        "  with p.open(newline='') as f:\n" \
        "   r=csv.DictReader(f); header=header or r.fieldnames; rows.extend(r)\n" \
        "with (d/'rtcp.csv').open('w',newline='') as f:\n" \
        " w=csv.DictWriter(f,fieldnames=header); w.writeheader(); w.writerows(sorted(rows,key=lambda x:int(x['t_mono_ns'])))\n"
    subprocess.run([sys.executable, "-c", merge, str(out)], check=True)
    args = {"duration_s": 20, "fps": 15, "drop_prob": 0.05, "seed": 7,
            "ai": "synthetic", "ai_policy": "latest", "ai_service_ms": 30}
    (out / "args.json").write_text(json.dumps(args, indent=2) + "\n")
    git_hash = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
    (out / "meta.json").write_text(json.dumps({"git_hash": git_hash,
        "python": sys.version.split()[0], "seed": 7, "wall_time_s": 20,
        "evidence": "MEASURED loopback; host local monotonic clocks"}, indent=2) + "\n")

    def rows(name):
        with (out / name).open(newline="") as f:
            return list(csv.DictReader(f))
    sent, results = rows("sender.csv"), rows("results_tx.csv")
    if not results:
        raise RuntimeError(f"no AIRS results received; inspect {out / 'ai.csv'} and logs")
    if not sent:
        raise RuntimeError("sender.csv is empty")
    import importlib.util
    metrics_spec = importlib.util.spec_from_file_location(
        "rtp_metrics", root / "rtp/analysis/metrics.py")
    metrics_module = importlib.util.module_from_spec(metrics_spec)
    metrics_spec.loader.exec_module(metrics_module)
    metrics = metrics_module.compute_run_metrics(out)
    if not (metrics["capture_ai_latency_p50_ms"] >= 0 and metrics["capture_ai_latency_p95_ms"] >= 0):
        raise RuntimeError("capture-to-AI latency metrics are unavailable")
    print("MEASURED loopback summary")
    print("metric                         value")
    print(f"frames sent                    {len(sent)}")
    print(f"AIRS results received          {len(results)}")
    print(f"capture->AI latency P50        {metrics['capture_ai_latency_p50_ms']:.3f} ms")
    print(f"capture->AI latency P95        {metrics['capture_ai_latency_p95_ms']:.3f} ms")
    print(f"run directory                  {out}")
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
