# Dashboard

From this folder, run `python -m dashboard --mode replay --replay samples/cn-loss5 --loop`.
Open http://127.0.0.1:8080/ and stop with Ctrl+C. Requires Python 3.11+ and
local socket access; runtime dependencies are standard-library only.

`python -m dashboard --mode synthetic` generates clearly labelled teaching data.
`python -m dashboard --mode replay --replay samples/os-demo.csv --loop` uses
the synthetic OS illustration. Neither is physical MCU evidence.

Live CN video demo (run the dashboard, receiver, and sender in three terminals
from the repository root; video appears in the dashboard as JPEG frames arrive):

```powershell
$env:PYTHONPATH = "$PWD\dashboard;$PWD\cn\rtp"
.\.venv\Scripts\python -m dashboard --mode live
.\.venv\Scripts\python -m rtp receiver --out-dir _ticket\output\rx --duration 12 --telemetry 127.0.0.1 --telemetry-session demo
.\.venv\Scripts\python -m rtp sender --host 127.0.0.1 --port 5004 --source synthetic --duration 8 --out-dir _ticket\output\tx --telemetry 127.0.0.1 --telemetry-session demo
```

Open http://127.0.0.1:8080/. The receiver sends at most five JPEG telemetry
events per second by default; `--telemetry-video-fps 0` disables video events.

Evidence roots are fixed paths within the repository. The resolver still rejects
traversal, encoded paths and symlink/reparse escapes. Missing sources are reported
unavailable. Canonical lessons live in `../docs/lessons-vi`; run
`python tools/prepare_lessons.py` after changing them to refresh publication hashes.

Tests: `python -m pytest tests -q` after installing development requirements.
HTTP/UDP tests require local sockets.
