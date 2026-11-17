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

Hardware: `runner/run_scenario.py` uses reviewed configs and may require netem,
SSH and privileges. Replace loopback examples explicitly for your own lab.
No lab hostname or private network setting is bundled. Read the
`report/hw_tables.md` validity notes before quoting results.

Tests: `python -m pytest tests -q`. ns-3 integration tests additionally need the
separately installed dependency in `../../third_party/README.md`.
