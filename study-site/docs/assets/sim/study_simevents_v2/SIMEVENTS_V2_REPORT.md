# CN SimEvents v2: the network as visible blocks

v2 rebuilds the CN model as [CN_simevents_v2.slx](../generated/CN_simevents_v2.slx), with its own entity dictionary [CN_simevents_v2.sldd](../generated/CN_simevents_v2.sldd). The builder is [build_cn_simevents_v2.m](build_cn_simevents_v2.m). The v1 model, scripts and report are unchanged. The SHA-256 hashes of all 29 protected files match the v1 snapshot in `study_simevents/source_hashes_after.csv`, and no file under `study_simevents/`, `+course/`, `models/`, `data/` or `output/` was modified.

In v1, the RTP packetizer, the channel draw, the receiver (reassembly, playout deadline and RTCP report) and the frame source were each one `CNSEStage` MATLAB Discrete-Event System block. **v2 contains no `CNSEStage` block and no MATLAB Discrete-Event System block at all.** The `noCNSEStageBlocks` test checks this on the saved model. Every stage is now built from native SimEvents blocks: Entity Generator, Server, Queue, Replicator, Output Switch, Terminator and Transport Delay. Short "event action" lines set entity attributes. Three Simulink Function blocks hold the receiver formulas. Each subsystem reads left to right inside coloured Simulink Area frames, numbered 1, 2, 3 in reading order.

## Results at a glance

| Check | Result |
|---|---|
| Stage A, 5 runs × 20 metrics vs v1 | **100/100 identical** (abs diff 0) |
| Stage B, 10 runs × 20 metrics vs v1 | 194/200 identical; 6 differ in the two `B_queue_*` runs, caused by a tie between simultaneous events (below) |
| Stage C, 28 runs × 20 metrics vs v1 (rerun) | 554 identical, 555 within tolerance; 5 out of tolerance in the two `C_T7_*` runs, same tie as in Stage B |
| Tie check with the service time moved by ±1 ns, v1 vs v2 | 32/32 metric rows identical (max abs diff 0) |
| Trace oracles (`cnse2_validate`, 24 checks per run) | A 120/120, B 240/240, C 672/672 |
| Regression suite (`cnse2_run_shared_tests`) | **31/31 passed**: the 29 original tests plus 2 v2 tests |
| Figures | 14 PNGs exported to [figures/](figures), each opened and checked |

## What changed, subsystem by subsystem

Each subsystem's figure shows the blocks. The block names below match the diagram.

| Subsystem | v1 | v2 (native blocks, left to right) |
|---|---|---|
| [Top level](figures/CN_simevents_v2.png) | Grouped blocks, no frames | Three area frames: the RTP media path, the RTCP return path and AIMD plus the dashboard. The AIMD size-scale wire runs from the Feedback tick into Frames. |
| [Frames](figures/CN_simevents_v2__Frames.png) | `CNSEStage` "frame" mode, with the rate signal as a DES input | **Frame clock** Entity Generator (period 1/fps). Its generate action calls **`sizeScale()`**, a Simulink Function whose Inport is wired to the AIMD scale ([inside](figures/CN_simevents_v2__Frames__sizeScale_reads_the_AIMD_wire.png)). The action takes the seeded camera size draw and sets frame, capture time and bytes. A **Capture window open?** Output Switch routes frames after the capture window to the **After capture end** Terminator. |
| [Sender Queue](figures/CN_simevents_v2__Sender_Queue.png) | Admission decided inside the frame DES | **Admission check** Server (zero time, sets `route`), then the **Sender admission** switch, with a full FIFO going to the **Sender overflow** Terminator. Then the **Frame FIFO or latest** Queue (lesson 07) and the **Sender processing** Server. |
| [RTP Packetizer](figures/CN_simevents_v2__RTP_Packetizer.png) | `CNSEStage` "packetizer": `course.Packetizer` plus `eventGenerate` | Area 1, **Count fragments**: `N = ceil(bytes/payload)`, 90 kHz timestamp `mod(round(capture·90000), 2^32)`, SSRC, and the first seq of the frame. Area 2, **Make N copies**: an Entity Replicator with the amount taken from the attribute `count`. The original goes to the **Original frame record** Terminator and the copies go to the **Fragment line** FIFO. Area 3, **Stamp RTP header**: copy *k* gets `fragment = k`, `seq + k − 1 (mod 65536)`, `size = min(payload, bytes − (k−1)·payload)` and `marker = (k == N)`. |
| [Serialization](figures/CN_simevents_v2__Serialization.png) | Service time computed in the runtime | Packet FIFO, then the **Link serializer**, whose service action is written in the block: `dt = 8*(size + 48)/linkBitRate`. |
| [Channel](figures/CN_simevents_v2__Channel.png) | One `CNSEStage` "channel" for loss and delay together | Area 1: the **Seeded loss draw** Server action calls the seeded `course.Loss` stream (seed + 200, one draw per 1480-byte IP fragment). The **Loss route** switch sends drops to the **Netem drops** Terminator. Area 2: **Seeded delay draw** (`course.Delay`, seed + 300), then the **Entity Transport Delay** with the **Guaranteed delay** constant, then the infinite **Per-packet delay remainder** Server. |
| [Receiver](figures/CN_simevents_v2__Receiver.png) | `CNSEStage` "receiver" with reassembly, deadline and RTCP in code | Area 1, **Arrival** Server: its action calls three visible Simulink Function blocks. [RFC 3550 jitter](figures/CN_simevents_v2__Receiver__RFC_3550_jitter.png) computes `J += (|D| − J)/16`. [Playout deadline](figures/CN_simevents_v2__Receiver__Playout_deadline.png) anchors on the first packet and adds the RTP time offset plus the depth. [Fragment counter](figures/CN_simevents_v2__Receiver__Fragment_counter.png) flags the fragment that completes its frame. Area 2, **Playout-deadline gate**: the **Deadline check** switch sends late fragments to the **Late fragments** Terminator. On-time fragments wait in the infinite-capacity **Playout buffer** Server until `deadline − arrival`. Area 3, **Reassembly**: at the deadline, the **Frame complete?** switch lets the completing fragment continue as the frame entity (**Frame to AI**). The other fragments of a complete frame, and all fragments of an incomplete frame, go to **Merged or incomplete**. Area 4: the **RTCP report clock (1 s)** Entity Generator produces one receiver-report entity per second. |
| [Inference](figures/CN_simevents_v2__Inference.png) | Admission set at playout inside the receiver DES | **AI admission check** Server, then the switch (overflow goes to a Terminator), then the **AI waiting frames** Queue, **Inference service** and the **AI result** Terminator. |
| [RTCP Reverse Path](figures/CN_simevents_v2__RTCP_Reverse_Path.png) | Reverse loss and delay drawn inside the receiver DES | **Seeded reverse draw** Server (`course.Loss` seed + 600, `course.Delay` seed + 700), then the **Reverse loss** switch (lost reports go to **RR drops**), then **Reverse propagation** (service time from the attribute `reverseDelay`), then **RR at sender**, whose arrival count goes to AIMD. |
| [AIMD](figures/CN_simevents_v2__AIMD.png) | Stateflow chart | Unchanged: the same chart, 1 kHz sampling and Feedback tick Unit Delay. |

### What is still code, and why

The block types that v1 implemented as `CNSEStage` are all native now. The remaining MATLAB code is either small attribute actions or helpers outside the mechanism:

| Remaining code | Where | Why it is not a native block |
|---|---|---|
| **`CNSEStage`** | **None.** | Every v1 use was replaced (the test `noCNSEStageBlocks` checks this). |
| Calls to `cnse2_runtime('lossDraw' / 'delayDraw' / 'reverseDraw' / 'frame')` | One line each in the seeded draw actions | The same seeded `course.Loss`, `course.Delay` and camera `RandStream` objects as v1. A Random Number block would produce a different random sequence, so identical seeds would no longer give identical loss counts. |
| `cnse2_runtime('receive')` and `('report')` | Arrival action, RTCP report clock | `course.ReceiverReport` keeps the RFC 3550 extended-sequence, fraction-lost and cumulative-lost counters for the 1 s report. The jitter shown in the model and on the dashboard comes from the native RFC 3550 block. The library value is only cross-checked against it. |
| `cnse2_runtime('admitSender' / 'admitAI')` | Admission check actions | FIFO admission needs the waiting count before the queue accepts the frame. Without the switch, a full queue would block the generator instead of dropping the frame. This is the same as v1. |
| `cnse2_runtime('propagation')` | Delay remainder service action | SimEvents event actions have no clock function, so the elapsed time since sending is read from the model through `get_param`. |
| `cnse2_runtime('time')` | Arrival action | Same reason: the arrival time is needed for the jitter and deadline blocks. |
| Trace calls (`packetize`, `serialized`, `release`, `result`, `feedback`, `lateFragment`, queue counters) | Various actions | Record events for validation. They do not change any entity. |
| `CNSE2Monitor` (a MATLAB System block, not a DES) | Top level, "Observations" | Same role as v1's `CNSEMonitor`: it releases one delivered receiver report per 1 ms tick to the Stateflow chart and outputs the five dashboard signals. |

## Stage A: open loop (same seeds and configs as v1)

All 100 compared values are identical. Each cell shows v1 / v2. [stage_A_compare.csv](stage_A_compare.csv) · [results](stage_A_results.csv) · [validation](stage_A_validation.csv)

| Run | Sent | Seq. loss | On time (%) | RFC jitter (ms) | P95 (ms) | AoI (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Seed 1 | 1823 / 1823 | 0.0433 / 0.0433 | 73.6 / 73.6 | 14.706 / 14.706 | 77.4 / 77.4 | 133.4 / 133.4 |
| Seed 17 | 1828 / 1828 | 0.0609 / 0.0609 | 54.6 / 54.6 | 15.050 / 15.050 | 68.2 / 68.2 | 154.9 / 154.9 |
| Seed 903 | 1823 / 1823 | 0.0420 / 0.0420 | 61.3 / 61.3 | 15.204 / 15.204 | 68.7 / 68.7 | 141.8 / 141.8 |
| All lost | 455 / 455 | 1 / 1 | 0 / 0 | n/a | n/a | n/a |
| No loss | 455 / 455 | 0 / 0 | 100 / 100 | 0.133 / 0.133 | 62.7 / 62.7 | 96.0 / 96.0 |

## Stage B: closed loop and queue policy

[stage_B_compare.csv](stage_B_compare.csv) · [results](stage_B_results.csv) · [validation](stage_B_validation.csv)

| Run | Sent | On time (%) | RFC jitter (ms) | P95 (ms) | AoI (ms) |
|---|---:|---:|---:|---:|---:|
| Loss step, fixed | 4557 / 4557 | 73.2 / 73.2 | 0.141 / 0.141 | 62.7 / 62.7 | 147.7 / 147.7 |
| Loss step, AIMD | 2730 / 2730 | 87.1 / 87.1 | 0.115 / 0.115 | 62.7 / 62.7 | 111.9 / 111.9 |
| 0.55 Mb/s, fixed | 1823 / 1823 | 0 / 0 | 22.927 / 22.927 | n/a | n/a |
| 0.55 Mb/s, AIMD | 738 / 738 | 96.6 / 96.6 | 2.541 / 2.541 | 81.4 / 81.4 | 117.0 / 117.0 |
| **Inference FIFO** | 2184 / 2184 | 100 / 100 | 0.133 / 0.133 | **483.5 / 500.2** | **500.2 / 516.9** |
| **Inference latest** | 2184 / 2184 | 100 / 100 | 0.133 / 0.133 | **116.9 / 133.5** | **133.5 / 150.2** |
| Reverse all lost | 546 / 546 | 32.4 / 32.4 | 0.159 / 0.159 | 62.7 / 62.7 | 225.6 / 225.6 |
| Reverse impaired | 369 / 369 | 50.0 / 50.0 | 0.120 / 0.120 | 62.7 / 62.7 | 158.2 / 158.2 |
| Sender FIFO | 1510 / 1510 | 0 / 0 | 2.800 / 2.800 | n/a | 6933.3 / 6933.3 |
| Sender latest | 1468 / 1468 | 66.7 / 66.7 | 2.801 / 2.801 | 112.7 / 112.7 | 140.5 / 140.5 |

All counts and loss fractions, including sent, received, results, reports, overflows, replacements and rate scale, match exactly in every run.

### Why the inference-queue runs differ (an explained tolerance failure)

The six out-of-tolerance values are P50, P95 and AoI in `B_queue_fifo` and `B_queue_latest`. The P95 and AoI values are 16.7 ms higher in v2, and P50 is 8.3–16.7 ms higher. These runs use 30 FPS, 50 ms inference and zero network jitter. A frame's playout release and an inference completion therefore fall on **the same instant**, every third frame. The doubles are bit-equal (for example, 0.15020068 s for both frame 4's release and frame 2's completion). The two events have the same time, so the outcome depends only on how SimEvents orders simultaneous events:

- **v1:** the receiver DES scheduled the frame with an explicit event priority, so the new frame reached the AI queue before the server took the next waiting frame.
- **v2:** the release is an ordinary Entity Server completion. The inference server completes first and takes the older waiting frame, so it serves a frame one period older at every coincidence.

Neither order is wrong. To confirm this is the only cause, [cnse2_tie_check.m](cnse2_tie_check.m) runs both models with the inference service time moved by −1 ns and by +1 ns, which removes the tie. In all 32 metric rows (both B queue runs and both C T7 runs, each at both shifts) v1 and v2 are **identical**, with maximum abs diff 0. [tie_check.csv](tie_check.csv). At the exact tie, v1 behaves like the +1 ns case and v2 like the −1 ns case. Every other configuration has jitter or a non-commensurate service time, so the tie never occurs.

## Stage C: measured Pi/netem conditions (rerun)

All 28 cases were rerun with seed 11, as in v1. 554 of 560 values are identical. Every count and loss fraction matches. The only differences are in `C_T7_fifo` and `C_T7_latest`, which use the same 30 FPS / 50 ms inference structure as above, and the ±1 ns check proves the tie is the cause. At the exact tie, `C_T7_fifo` P95 is 533.5 ms in v1 and 550.2 ms in v2, and `C_T7_latest` P95 is 166.9 ms in v1 and 183.5 ms in v2. All 672 trace checks passed. [stage_C_compare.csv](stage_C_compare.csv) · [results](stage_C_results.csv) · [validation](stage_C_validation.csv). The comparison against the hardware measurements is unchanged from v1 apart from these two T7 rows. It was not regenerated for v2.

## Trace oracles

[cnse2_validate.m](cnse2_validate.m) runs the 20 v1 oracle checks and adds four checks of the new native mechanisms against the `+course` reference objects. All four pass in all 43 study runs:

| New v2 check | Compared with | Tolerance |
|---|---|---|
| Replicator packetizer fields (seq, ts, frame, fragment, count, size, marker, capture) | `course.Packetizer` on the same frames | 0 |
| Native RFC 3550 MATLAB Function jitter | `course.ReceiverReport` jitter at each arrival | 1e-9 ms |
| Native fragment counter completion flag | `course.Depacketizer` | 0 |
| Frames released by the deadline gate | Frames complete on or before their deadline | 0 |

## Regression suite

[cnse2_run_shared_tests.m](cnse2_run_shared_tests.m) is a v2 copy of the v1 runner. It runs the untouched suite in a scratch copy under `study_simevents_v2/` and writes [shared_test_results.csv](shared_test_results.csv). **31/31 tests passed:**
- **29 original tests:** 13 TestLibrary, 13 TestRegression and 3 TestSimulink.
- **`reloadedModelPassesTraceOracles`:** reloads the saved v2 model from disk and runs all 24 oracle checks.
- **`noCNSEStageBlocks`.**

## Figures

[export_cn_simevents_v2.m](export_cn_simevents_v2.m) exports the top level, every subsystem, the four Simulink Function blocks and the AIMD chart: 14 PNGs in [figures/](figures). Each image was opened and inspected. The first export had three problems: the area fills printed dark (setting an area's ForegroundColor also overwrote its fill), a Constant overlapped a Terminator in Channel, and top-level lines passed through blocks. These were fixed in the builder and the figures re-exported. In the final images, labels are readable, blocks do not overlap and no line passes through a block. On the top level, a few signal lines still cross each other outside blocks.

## Reproduce

Run these in one MATLAB R2026b session from the workspace root. SimEvents, Stateflow and Communications Toolbox are required.

```matlab
addpath(pwd, fullfile(pwd,'study_simevents'), fullfile(pwd,'study_simevents_v2'), fullfile(pwd,'generated'))
build_cn_simevents_v2              % writes generated/CN_simevents_v2.slx and .sldd
run_cn_simevents_v2_study('A')     % about 35 s; writes stage_A_results/validation/compare.csv
run_cn_simevents_v2_study('B')     % about 80 s
run_cn_simevents_v2_study('C')     % about 9 min
cnse2_tie_check                    % about 5 min; v1 is simulated in memory only, nothing saved
export_cn_simevents_v2             % figures/*.png
cnse2_run_shared_tests             % 31 tests
```

The study reuses v1's `cnse_config` and `cnse_metrics` read-only, so the configurations and metric definitions are the same. Run traces are saved in `study_simevents_v2/runs/*.mat`. The simulation caches go to `study_simevents_v2/cache` and `codegen`.

## Files

| File | Role |
|---|---|
| [build_cn_simevents_v2.m](build_cn_simevents_v2.m) | Builds the model, its layout and area frames |
| [cnse2_runtime.m](cnse2_runtime.m) | Seeded streams, RTCP counters and the event trace (no scheduling) |
| [cnse2_params.m](cnse2_params.m) | Numeric parameters for event actions (`payload`, `linkBitRate`, `playoutDepth`); actions cannot read the struct `c` |
| [CNSE2Monitor.m](CNSE2Monitor.m) | 1 kHz observation and receiver-report sampler for AIMD and the dashboard |
| [cnse2_run.m](cnse2_run.m), [run_cn_simevents_v2_study.m](run_cn_simevents_v2_study.m) | Single run and study stages (same cases as v1) |
| [cnse2_validate.m](cnse2_validate.m), [cnse2_compare.m](cnse2_compare.m), [cnse2_tie_check.m](cnse2_tie_check.m) | Trace oracles, comparison with v1, tie proof |
