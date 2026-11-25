# CN scope and current status

The local coursework changed from an earlier ns-3 inference-offloading study
to topic 11, RTP/RTCP video. The imported runtime supports custom fragmentation,
receiver sequence/jitter statistics, playout, RTCP feedback and inference handoff.
The telemetry patch adds an optional observer for the dashboard.

CN-T2 through T9 snapshots contain retained evidence where available.
CN-T8 hardware adaptation remains pending. Source packet clocks, receiver clocks
and sender-side APP round-trip age must remain separate. Do not call the custom
PT 96 fragment payload RFC 2435.

The ns-3 RTP model is optional and separately licensed. It is pinned to ns-3.44;
its Linux dependency build and integration tests were not reproduced here.
Use C++ scenarios with stock ns-3 modules; do not change dependency internals.
The old Python binding pilot was not the supported simulation path.

This page converts the useful scope/roadmap and agent-rule content into stable
documentation. Raw task records, schedules and worklogs are not bundled.
