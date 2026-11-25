# CN topic 11: RTP/RTCP video

Imported from the local CN course repo at RTP0/HWAN2; see root NOTICE.
The telemetry patch is integrated here once, with no duplicate runtime tree.
Runtime sources are `rtp/`, analysis `analysis/`, experiment configurations
`configs/`, and hardware measurements `results/`. The root coursework's earlier
offloading study is background and is not the main project.

For a one-machine synthetic source demonstration, install `requirements-dev.txt`
from the repo root, then from this folder run `bash scripts/loopback_demo.sh`.
Read that script's options first; it runs both sender and receiver and writes
outputs. It requires local UDP sockets. `python -m rtp sender --help` and
`python -m rtp receiver --help` document runtime flags. The shell script waits
for the bounded demonstration to finish; Ctrl+C stops a manual runtime.

The PT 96 payload has a project-specific 8-byte fragment header; it is not
RFC 2435. Latency must stay in a single monotonic clock domain. Optional ONNX
inference requires separately supplied runtime and model weights.
Telemetry is opt-in and observational; dashboard failure must not stop transport.

Live dashboard video demo (run these in three terminals from the repository
root; video appears in the dashboard from completed JPEG frames):

```powershell
$env:PYTHONPATH = "$PWD\dashboard;$PWD\cn\rtp"
.\.venv\Scripts\python -m dashboard --mode live
.\.venv\Scripts\python -m rtp receiver --out-dir out\rx --duration 12 --telemetry 127.0.0.1 --telemetry-session demo
.\.venv\Scripts\python -m rtp sender --host 127.0.0.1 --port 5004 --source synthetic --duration 8 --out-dir out\tx --telemetry 127.0.0.1 --telemetry-session demo
```

Open http://127.0.0.1:8080/. The receiver defaults to at most 5 video events
per second; `--telemetry-video-fps 0` disables JPEG telemetry.

Hardware: `runner/run_scenario.py` uses reviewed configs and may require netem,
SSH and privileges. Replace loopback examples explicitly for your own lab.
No lab hostname or private network setting is bundled. Read the
`report/hw_tables.md` validity notes before quoting results.

Tests: `python -m pytest tests -q`. ns-3 integration tests additionally need the
separately installed dependency in `../../third_party/README.md`.

## CN-T8 on hardware (fixed vs RTCP-driven ABR)

Configs: `configs/CN-T8-hw.yaml` (ABR, AIMD) and `configs/CN-T8-hw-fixed.yaml`
(fixed, quality 90). Edit `PI_SSH`, `LAPTOP_IP`, `interface` and the camera
source first; the files explain each placeholder. Run from the laptop, which is
also the receiver; `--output-dir` must exist as the same path on both hosts.
`tc`/`tcpdump` are run with `sudo -n` (set `privilege:`), so the Pi user needs
passwordless sudo for them.

```bash
python runner/run_scenario.py configs/CN-T8-hw.yaml --dry-run --repetitions 1 --output-dir /tmp/cn_t8
python runner/run_scenario.py configs/CN-T8-hw-fixed.yaml --output-dir /tmp/cn_t8
python runner/run_scenario.py configs/CN-T8-hw.yaml --output-dir /tmp/cn_t8
python analysis/t8.py /tmp/cn_t8/T8 --plot /tmp/cn_t8/t8.png
python analysis/hw_tables.py /tmp/cn_t8 --output /tmp/cn_t8/hw_tables.md
```

Each run writes `steps.csv` (netem schedule as offsets from sender start) and
`args.json`; logs from both hosts are copied back before the RTCP merge.
`analysis/t8.py` builds step windows separately on the sender and receiver
clocks, reports per-step on-time ratio, frame loss, goodput, frame size,
reaction time and recovery time, and prints the TEST_SCENARIOS pass/fail
verdict. The recovery threshold (90 % of first-step goodput) is an assumption
stated in the module and the table.

