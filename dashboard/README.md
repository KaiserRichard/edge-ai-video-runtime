# Dashboard

From this folder, run `python -m dashboard --mode replay --replay samples/cn-loss5 --loop`.
Open http://127.0.0.1:8080/ and stop with Ctrl+C. Requires Python 3.11+ and
local socket access; runtime dependencies are standard-library only.

`python -m dashboard --mode synthetic` generates clearly labelled teaching data.
`python -m dashboard --mode replay --replay samples/os-demo.csv --loop` uses
the synthetic OS illustration. Neither is physical MCU evidence.

Evidence roots are fixed paths within the repository. The resolver still rejects
traversal, encoded paths and symlink/reparse escapes. Missing sources are reported
unavailable. Canonical lessons live in `../docs/lessons-vi`; run
`python tools/prepare_lessons.py` after changing them to refresh publication hashes.

Tests: `python -m pytest tests -q` after installing development requirements.
HTTP/UDP tests require local sockets.
