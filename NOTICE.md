# Provenance and licence scope

This repository extends [heterogeneous-edge-ai-os](https://github.com/KaiserRichard/heterogeneous-edge-ai-os).
The original OS project remains separate and unchanged. Its team built the Linux
camera/inference/IPC/UART pipeline, scheduling and queue experiments, protocol,
STM32/FreeRTOS supervisor, and retained OS measurements.

The OS code/results import is `feat/os-t3-t4-camera` at
`730b9a173e854e8e9f5551c4fb6970d88404b944`. The report is imported separately
from `docs/os-midterm-report-v2` at `9bc6677de838b8a84d0ac4483226a0d9d8109774`;
that report branch does not contain the selected code branch as an ancestor.

CN RTP/RTCP code comes from the local, not previously published CN course repo:
`work/RTP0` at `66e48bd51e28b353aeb8780e676b36a0235a4b4e`.
Its `work/HWAN2` ancestor `c0210d2618d2936ad38ee2f2d960d2b93ff73bea`
has the same Git tree. Hardware CSVs additionally come from the HWAN2 file
snapshot; those ignored files are not claimed to be stored in the named commit.
The separate dashboard, integrated CN telemetry patch, Stateflow supervisor,
shared MATLAB models and Vietnamese lessons are new file-snapshot additions,
imported on 17 November 2026. Snapshot hashes record their actual origin.

The new history records the local import and preparation; it is not the original
development history. Claude and Codex assisted development and preparation.
See [AI assistance](docs/AI_ASSISTANCE.md), [credits](CREDITS.md), and the
[public source manifest](docs/provenance/files.csv). The complete private
source-location map stays outside this repository.

The root MIT licence applies to independent team-owned code and documentation
for which no other notice is present. Contributor consent remains an owner
release task. It does not relabel third-party or derived files.

* `cn/sim/rtp/`: ns-3-dependent simulation, GPL-2.0 compatible scope;
  [component notice](cn/sim/rtp/LICENSE), [GPL text](third_party/licenses/GPL-2.0.txt).
* `os/stm32/firmware/`: the firmware build uses a GPL-2.0 reference project.
  Preserve reference/per-file terms and treat a combined derivative firmware as
  GPL-2.0 until the owner completes dependency review. The FreeRTOS kernel itself
  has MIT terms. No compiled firmware or third-party reference source is bundled.
* `docs/os-report/report_vi/wiring_src/wiring_diagram/parts/`: existing
  copyright and CC-BY-SA-3.0 declarations remain in `PARTS_CREDITS.md` and
  `LICENSE`. The wiring drawings retain CC-BY-SA-3.0; do not relabel them MIT.
* University logos, lecture slides, model weights, bulk browser bundles and
  unused reference projects are not included.

Privacy derivatives replace personal machine paths, machine identity and private
network settings. Numeric measurement fields, failed runs and validity rules are
retained. Hashes distinguish original snapshots from public derivatives.
