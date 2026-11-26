# OS + CN: product-first review (24 Nov 2026)

**Scope.** This is a review and plan only. Nothing was run, built or changed.

**Sources inspected:**
- the public staging repo `E:\Quoc_Khanh\github_release_audit\oscn_staging\repo` (latest commit 24cd6fc, 22 Nov)
- the original OS repo `D:\Quoc_Khanh\Research\OS-project\heterogeneous-edge-ai-os` (`PROJECT.md`)
- the CN working repo `E:\Quoc_Khanh\github_release_audit\work\cn_rtp` (slides and report)
- the MacBook worktree `CN-wt-ABR1`, which holds the T8 attempts

**Paths:**
- `os/…`, `cn/…`, `sim/…` and `dashboard/…` are relative to the staging repo.
- **Every command below was checked against the repository source, but none was executed.**

**Course requirements.** No official course document, rubric or deadline was found. Here is what each source says:
- **The 10–15-minute format and the lecturers' interests** come from your own description.
- **OS `PROJECT.md`:** "demonstrating fundamental operating system principles on a real heterogeneous computing platform", observed empirically. That fits a demo-centred presentation.
- **CN `HYBRID_PLAN.md`:** the OS and CN reports must not present the same claim twice.

**Two decks already exist and should be reused rather than rebuilt:**
- CN: `work/cn_rtp/slides/main.pdf` and `main_en.pdf`
- OS: `slides_course/` in the original OS repo, final preview round 14

## A. Verdict

**Product-first teaching fits both projects, but the products are not equally demonstrable.** Each project has a different strength:
- **OS** has real hardware evidence of supervisor behaviour.
- **CN** has the most complete software product and a runnable demo without hardware.

**Changes to the CN1–CN6 / OS1–OS6 roadmap:**
1. **Change the order:** follow the data path and the demos, not the textbook topics.
2. **Drop the "theory first" items:**
   - CN1 header decoding becomes a 5-minute look at one packet.
   - OS1 scheduling classes are taught only through the F4 starvation fault and the E2 campaign.
3. **Add three topics:**
   - demo operation and failure handling
   - the native SimEvents walk-through
   - the presentation itself
4. **Correct the OS framing:**
   - The strongest OS claim is the physical fault campaign (E4/F5): the supervisor's detection behaviour, measured on the real Pi and STM32.
   - The 192 vs 93 ms age result is a PTY software measurement with no MCU, so it is not that claim.
   - The 0/18 real-UART failure concerns timing comparison. It does not concern whether the system works.

## B. What is actually demonstrable

### CN: RTP/RTCP video, Pi → laptop (Đề 11)

**Product.** A Python `rtp` package:
- **The sender** captures JPEG frames from one of four sources:
  - `synthetic`
  - `jpegdir:`
  - `mjpeg-pipe`
  - `shm:`, the Pi camera through the OS project's shared-memory library
- **It packetizes** into a custom PT 96 payload with an 8-byte fragment header. This is not RFC 2435.
- **It sends RTCP SR** and optionally runs AIMD bitrate control (`--abr aimd`).
- **The receiver:**
  - computes RFC 3550 statistics
  - runs a playout buffer (`--playout-ms`, default 100)
  - sends RTCP RR
  - optionally runs AI inference: synthetic, or ONNX MobileNetV2
- **Telemetry:** both ends can send UDP telemetry to a read-only browser dashboard.

**Important.** The receiver writes CSVs and telemetry. **It does not display video.**
- The dashboard has a video panel that expects a `jpeg_b64` field.
- Neither the sender nor the receiver emits that field (checked with grep), so live mode will show "Waiting for a decoded JPEG".
- **What a lecturer can see today:** packet, frame, RTCP and AI metrics updating live. Not moving video.

**What exists today:**

| Item | Status |
|---|---|
| Runnable without hardware | [`cn/rtp/scripts/loopback_demo.sh`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/cn/rtp/scripts/loopback_demo.sh): synthetic source, 10 s at 15 fps on localhost. It checks 150 frames, all OK, and that an RR with RTT arrived. Also `dashboard --mode replay --replay samples/cn-loss5`, which replays the first 8 s of T3/loss5/run1. |
| Hardware (MEASURED) | T2 Ethernet baseline, T3 loss levels, T4 playout depth, T5 packet size and quality, T6 Wi-Fi, T7 FIFO vs latest-value (synthetic AI service time), T9 latency breakdown. All on the Pi + laptop with netem, 5 runs each, no throttling flags ([`cn/rtp/report/hw_tables.md`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/cn/rtp/report/hw_tables.md)). |
| Raw data in the staging repo | Only T2, T3 and T5 have raw run folders. The others exist as table rows only. |
| Simulation (SIMULATED) | SimEvents v1 and v2 (`sim/generated/CN_simevents_v2.slx`), with 14 native subsystem figures in `sim/study_simevents_v2/figures/`. Stage B in the v1 model compares fixed bitrate with AIMD during a 15% loss step. |
| **Adaptation (AIMD)** | **Simulation only.** The code exists (`--abr aimd`), but **CN-T8 on hardware is pending**: the T8 folder holds only two loopback runs. Present AIMD as "implemented, simulated, not validated on hardware". |
| Hardware needed for a live demo | Pi 5 + camera, laptop, Ethernet, `sudo` for netem on the Pi. Optional: the ONNX runtime and model weights. |

**Defensible results:**

| Experiment | Baseline → change | Measured result | Interpretation | Limitation |
|---|---|---|---|---|
| **T3 loss** | 0% → 1/5/10% netem loss | Frame loss 0 → 4.9 / 24.0 / 41.5%. The formula gives 5.0 / 23.0 / 41.6%. | A frame needs all of its ~5.1 packets, so loss is amplified | Independent loss only; burst loss (GE) gives 8.8% |
| **T4 playout depth** | D = 20 → 50 → 100 ms, with jitter 20 ± 20 ms | Late frames 93.5% → 14.3% → 0%; capture→AI P50 38 → 75 → 118 ms | **A trade-off, not an improvement:** delay is spent to buy continuity | One jitter profile, wired link |
| **T7 AI hand-off policy** | FIFO → latest-value | Mean AI-result age 0.623 → 0.204 s; queue wait P50 440 → 16 ms | Discarding stale frames keeps results fresh | AI service time is synthetic on hardware |
| **T5 packet size** | 1400 → 3000 B payload (IP fragmentation) | Packet loss 2.0 → 4.8% at 2% netem loss | Losing any fragment loses the whole datagram | Single configuration |
| **AIMD vs fixed bitrate** | Fixed → AIMD | **Simulated only** (SimEvents Stage B) | — | No hardware evidence (T8 pending) |

**Config drift (fix before the defence).** [`configs/CN-T3.yaml`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/cn/rtp/configs/CN-T3.yaml) lists `loss gemodel 1% 25% 25% 0.2%`, but the table records the ge5_b4 run as `gemodel 1.316% 25% 100% 0%`. Quote the table, which records what ran, and expect the question.

### OS: Pi 5 Linux + STM32F446RE FreeRTOS freshness supervisor

**Product, as a data path:**
1. **Source process (`linux/camera`)** captures frames.
2. **Inference process** runs MobileNetV2 ONNX or a synthetic workload.
3. **Bridge process** receives over Unix datagram IPC, applies a FIFO or latest-value policy, and sends over UART. Protocol v3 adds CRC-16, sequence numbers, age_at_send, heartbeat and echo messages.
4. **STM32 FreeRTOS supervisor:**
   - TIM2 timestamps and DMA UART receive
   - states INIT / FRESH / HOLD / latched FAILSAFE
   - heartbeat timeout 100 ms; age thresholds 200 ms (HOLD) and 500 ms (FAILSAFE)
   - GPIO state outputs and LEDs
   - STATE_EVENT messages reported back to the Pi

**What exists today:**

| Demo candidate | Status |
|---|---|
| Supervisor reacting to faults on real hardware | **MEASURED and recorded (12 Oct, E4/F5).** On the Pi and STM32, F1–F3 each 5/5 valid, F5 5/5 valid, F4 7/14 accepted.<br>• F1 bridge `kill -9`, F2 bridge SIGSTOP: heartbeat FAILSAFE about 100.5 ms after the last heartbeat (configured 100 ms)<br>• F3 inference SIGSTOP, F5 inference suppressed with the heartbeat still alive: HOLD about 175 ms and FAILSAFE about 475 ms after the last inference, by source age<br>• F4 FIFO-99 CPU hog: the bridge is starved, and in 6 of 7 accepted runs the board goes straight to FAILSAFE<br>**This is the core OS demo and claim.** |
| Pipeline over a PTY, no MCU | Runnable on the Pi: `bash os/scripts/pi/run_pipeline.sh` (PTY by default). It shows the processes, IPC and bridge, but not the supervisor. |
| Pipeline over real UART | `run_pipeline.sh --serial /dev/ttyAMA0 --baud 921600 --duration 60`, after flashing the matching firmware. Faults are injected with [`os/scripts/pi/fault_inject.sh`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/os/scripts/pi/fault_inject.sh). **Not run since 12 Oct. It is unknown whether the board currently holds the matching firmware**, and later firmware fixes were compiled but never flashed. |
| Supervisor logic in simulation | Stateflow [`sim/os_supervisor/os_supervisor_chart.slx`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/sim/os_supervisor/os_supervisor_chart.slx), 8 scenarios passing, with timeline PNGs in `sim/os_supervisor/output/`. **There is no exported image of the native chart**, so it has to be exported later (one MATLAB print, no simulation). It models the supervisor logic only, **not Linux scheduling**. |
| Scheduling evidence | Cyclictest (30/30 valid under rule v1; v2 re-check: only the 3 idle runs per profile stay valid). E1–E3 over PTY (45/45 under v1; 0/45 under v2, because monitor timestamps are missing). |
| Hardware needed | Pi 5, Nucleo-F446RE, 3 jumper wires (PA9/PA10/GND, 3.3 V), camera, **an adequate power supply**, ST-LINK for flashing. |

**Defensible results:**

| Experiment | Baseline → change | Result | Label |
|---|---|---|---|
| **Fault detection (E4/F5)** | Healthy → injected fault | Heartbeat detection about 100.5 ms; source-age detection: HOLD about 175 ms, FAILSAFE about 475 ms after the last inference | MEASURED (Pi + MCU timestamps, no logic analyzer in E4) |
| **Input policy (OS-T4, 30 Oct)** | FIFO → latest-value input; idle; bridge set to latest | Time-average AoI 192.0 → 92.8 ms; also under memory stress 334.7 → 223.5 ms | MEASURED, **PTY, no MCU**, 3 valid repeats (the deck asks for 5) |
| **Bridge policy under memory stress (E3)** | FIFO → latest-value bridge | Mean AoI about 6660 ms for the FIFO bridge | MEASURED over PTY; a separate experiment |
| **Real-UART timing comparison (E3 real)** | Six load × policy cells | **0/18 valid** | FLAGGED: power, clock fit, missing events |

**Why this is an OS project and not just a UART application.** The interesting behaviour comes from three OS mechanisms:
- **Scheduling and contention:** a SCHED_FIFO hog starves the bridge (F4).
- **IPC queue policy:** FIFO keeps stale work, while latest-value discards it.
- **Independent supervision by a second RTOS:** its own clock, tasks, a watchdog and a latched failsafe.

The UART is only the boundary between the two operating systems.

## C. Integrated roadmap (4 sessions, about 6.5 h of core study)

| Session | Project | Real system or diagram inspected | Important mechanism | Demo or evidence | What I must be able to explain |
|---|---|---|---|---|---|
| **1. CN end-to-end product** (1.75 h) | CN | Sender → receiver → AI → RTCP data path ([`rtp/sender.py`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/cn/rtp/rtp/sender.py), [`receiver.py`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/cn/rtp/rtp/receiver.py)); dashboard replay | Packetization into ~5 packets per frame; RFC 3550 jitter (convert 90 kHz units, the offset cancels); frame loss 1−(1−p)^n | Run [`loopback_demo.sh`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/cn/rtp/scripts/loopback_demo.sh); dashboard replay of loss5; T3 table, with the 5.106 packets-per-frame check | Draw the pipeline in 2 minutes; why 5% packet loss becomes 24% frame loss; what the dashboard shows and does not show |
| **2. CN trade-offs, plus the SimEvents model** (1.75 h) | CN | Native SimEvents v2: top level, Packetizer, Channel, Receiver (jitter, playout deadline), AIMD Stateflow | Playout deadline; FIFO vs latest-value for the AI; RTCP RR as delayed feedback; the AIMD loop | T4, T7, T5; SimEvents Stage B (fixed vs AIMD) | Playout trade-off with numbers; why AIMD is simulation-only; which results are MEASURED and which SIMULATED |
| **3. OS end-to-end product and supervisor** (1.75 h) | OS | Process and task diagram; Protocol v3 frame; Stateflow chart (export needed); E4 state-event CSVs | Age = elapsed since receipt + age_at_send + 5 ms; heartbeat vs freshness; latched FAILSAFE and rearm; Pi–MCU clock fit (assumed 200 µs pass limit) | E4/F5 detection table; Stateflow degrade-and-recover and stale-result timelines | Trace one message from camera to LED; why it was HOLD at about 175 ms rather than at 200 ms; why it is an OS project |
| **4. OS scheduling, evidence validity, plus the shared lessons** (1.25 h) | OS + CN | F4 FIFO-hog runs; OS-T4 AoI; E3 real-UART summary; CN T7 for comparison | SCHED_FIFO starvation; input-policy AoI; under-voltage invalidation; v1 vs v2 validity rules | OS-T4 192/93 (PTY); 0/18 FLAGGED, with the reasons | Valid vs functional vs flagged; one table comparing CN buffering (adds delay on purpose) with OS latest-value (discards stale data); the WBR link: stale state hurts control |

**Time outside core study:**
- **Demo rehearsal:** about 1.5 h for CN and about 2 h for OS (hardware assembly and checks).
- **Presentation rehearsal:** about 1 h for both together.
- **Experiments:** none needed for the defence. A clean real-UART timing re-run is optional, and only after the power fix.
- **Optional theory:** NTP/PTP, queueing, schedulability analysis.

**Shared concepts, taught where they occur:**
- **Clock domains:** CN jitter, the OS clock fit, WBR M13.
- **Freshness vs continuity:**
  - CN playout buffering trades delay for smoothness.
  - The OS latest-value policy and CN T7 discard stale data.
  - WBR state estimation needs fresh data in the same way.
- **Delayed feedback:** RTCP/AIMD and the WBR delay margin.
- **Validity:** throttle flags in both projects.

## D. Demo runbooks

### CN runbook

**Tier 1: guaranteed, laptop only.**

Setup (repo root, Python 3.11+, local sockets allowed):
```sh
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
```

Steps:
1. **Pipeline proof.** Run `bash cn/rtp/scripts/loopback_demo.sh`.
   - Success line: `MEASURED loopback: 150 frames, <n> packets, all frames ok; run directory: …`
   - **It proves** that the sender, receiver, playout and RTCP RR (with RTT) all work.
   - **It does not prove** anything about network performance: there is no impairment on localhost.
2. **Evidence replay.** `cd dashboard`, then `python -m dashboard --mode replay --replay samples/cn-loss5 --loop`, then open http://127.0.0.1:8080/.
   - It shows the real loss5 data from T3 run 1.
   - It is labelled as a replay, not live.

**Tier 2: live on hardware (UNTESTED here; needs the Pi, camera and Ethernet).**
1. Start the receiver on the laptop: `python -m rtp receiver --bind 0.0.0.0 --out-dir <dir> --playout-ms 100 --telemetry 127.0.0.1`.
2. Start the dashboard: `python -m dashboard --mode live`.
3. Start the sender on the Pi: `python -m rtp sender --host <laptop IP> --source shm:<name> --duration 60 --out-dir <dir> --telemetry <laptop IP>`.
   - The `shm:` source needs the OS camera service and library. If it is unavailable, use `--source synthetic`.
4. Add impairment on the Pi:
   - `sudo tc qdisc add dev eth0 root netem loss 5%`
   - Expect frame loss of about 20–25% and the RR loss to rise.
   - Remove it with `sudo tc qdisc del dev eth0 root`.
5. **Before the demo**, check the exact telemetry and dashboard flags against `python -m dashboard --help` and `python -m rtp sender --help`.

**Failure handling:**

| Symptom | Likely cause and fix |
|---|---|
| Receiver never prints `READY` | Port 5004 is busy (a stale process). Kill it with `pkill -f "rtp receiver"`. |
| No packets arrive | Wrong IP address or firewall. Check with `ping`. |
| `tc` error | No sudo, or wrong interface name. Find it with `ip link`. |
| Dashboard empty in live mode | Telemetry host or port mismatch. |
| Pi throttling | Check `vcgencmd get_throttled` before the demo; it must be 0x0. |
| Anything else | Fall back to Tier 1. |

**What not to show live:** AIMD as a working hardware feature.

### OS runbook

**Tier 1: guaranteed, no hardware.**
- Show the **E4/F5 recorded results**: the detection table and the state-event CSV for F1-r01.
- Show the **Stateflow timelines** (stale_result_failsafe_rearm, degrade_and_recover) and, once exported, the native chart.
- Explain them as "measured on 12 Oct" and "simulated logic" respectively.
- Optionally run the host tests: `make test PYTHON=python3` in `os/`. **These are software verification only.**

**Tier 2: Pi only (UNTESTED here).**
- `make -C linux all`, then `bash scripts/pi/run_pipeline.sh --duration 30`, which runs over a PTY.
- It shows the three processes and the CSV output.
- Use [`fault_inject.sh`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/os/scripts/pi/fault_inject.sh) only according to [`UART.md`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/os/scripts/pi/UART.md).

**Tier 3: Pi + STM32 live fault demo (UNTESTED; highest value, highest risk).**

Prerequisites:
1. **Power:** an adequate Pi 5 supply. The recorded rig used 5 V / 3 A, and the rail sagged to 4.66–4.92 V under load.
2. **Firmware:** the matching firmware flashed with [`scripts/stm32/flash.sh`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/os/scripts/stm32/flash.sh). Confirm which commit is on the board.
3. **Wiring:** PA9/PA10/GND.
4. **Throttle check:** `vcgencmd get_throttled` reads 0x0.

Run:
1. Start `run_pipeline.sh --serial /dev/ttyAMA0 --baud 921600 --duration 120`.
2. Expect the FRESH LED or GPIO.
3. Inject F2 (bridge SIGSTOP) → FAILSAFE about 100 ms later, and it stays **latched**. Rearm according to the firmware README.
4. Inject F5 (suppress inference while the heartbeat continues) → HOLD, then FAILSAFE.

**It proves** that the detection logic works on the real board. **It does not prove** timing performance under load: the comparison runs were invalid.

**Failure handling:**

| Symptom | Likely cause and fix |
|---|---|
| No `/dev/ttyAMA0` | Serial setup from [`bootstrap.sh`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/os/scripts/pi/bootstrap.sh) not applied, or no reboot afterwards. |
| CRC errors or no MCU_STATUS | Wiring, baud rate, or firmware version mismatch. |
| Under-voltage | `get_throttled` is not 0x0. Stop, since timing becomes untrustworthy, and fall back to Tier 1. |
| Board unavailable | Fall back to Tier 1. |

## E. Presentation outlines (about 12 min each)

**CN:**

| Time | Content | How it is shown |
|---|---|---|
| 1 min | Problem: real-time video to an edge AI over an imperfect network | Slide |
| 2 min | Architecture: sender, network (netem), receiver, playout, AI, RTCP | Slide diagram |
| 4 min | Demo: Tier 1 loopback plus the dashboard replay, or Tier 2 with live 5% loss | Live, with Tier 1 as the fallback |
| 3 min | Results: T3 loss amplification; T4 playout trade-off; T7 freshness | 3 slides |
| 1 min | SimEvents: why it exists; AIMD simulated | One native figure |
| 1 min | Limitations: T8 pending; T7 uses synthetic AI time; custom payload, not RFC 2435 | Slide |

Leave in the report: header fields, the jitter derivation, T5, T6, T9.

**Top 5 expected questions:**
1. What did you build yourselves, rather than borrow from a library?
2. Why does 5% loss give 24% frame loss?
3. How do you measure latency without synchronizing the clocks?
4. Does adaptation work on real hardware?
5. Why not RFC 2435, and why not use an existing streamer?

**OS:**

| Time | Content | How it is shown |
|---|---|---|
| 1 min | Problem: a stale AI result looks valid unless something checks its age | Slide |
| 2 min | Architecture: 3 Linux processes, a bridge policy, UART, the FreeRTOS supervisor | Slide diagram |
| 4 min | Demo: the F2 or F5 fault live on Tier 3, or the recorded E4 data plus the Stateflow timeline | Live or recorded |
| 3 min | Results: detection times (E4/F5); input-policy AoI 192 → 93 ms (PTY); F4 starvation | 2–3 slides |
| 2 min | Limitations: 0/18 real-UART timing runs invalid (power); 3 repeats, not 5; Stateflow models only the supervisor | Slide |

**Top 5 expected questions:**
1. Why is this an OS project?
2. Why use an external MCU instead of a Linux watchdog?
3. Why is FAILSAFE latched?
4. Why are all the real-UART runs invalid, and what would fix that?
5. How do you compare timestamps from two clocks?

## F. Evidence gaps that could hurt the defence

1. **CN has no video display.** "Demonstrate video transmission" currently means metrics, not a picture.
   - Minimum fix (proposal, not done): emit a small `jpeg_b64` thumbnail in the receiver's frame telemetry, about 20 lines.
   - Alternatively, show the source frames on the Pi side.
2. **CN adaptation (AIMD) exists only in simulation.** T8 has only loopback runs.
3. **The OS real-UART timing comparison is 0/18 valid**, mainly because of Pi under-voltage. The minimum fix is a proper 5 V / 5 A Pi 5 supply.
4. **Firmware state on the board is unknown**, and later fixes were never flashed. Verify the board before any live OS demo.
5. **Validity rules changed (v1 → v2).**
   - Under v2, E1–E3 drop to 0/45 and cyclictest to 3/15 per profile.
   - Quote v1 results as measured under v1, and state the v2 limitation.
6. **Three repeats against a deck gate of five** (OS-T4).
7. **There is no exported image of the native Stateflow chart.**
8. **CN-T3 config drift** between the YAML and the run that was recorded.
9. **Course requirements and deadline:** no official document was found. Get the real rubric from the lecturers or the course page.
10. **Hardware availability is unknown.** Pi 5, Nucleo, camera, power supply: the Pi was recorded as lent out on 7 Nov. **Tell me what you have.**

## G. What ChatGPT should teach first

**Start with the CN end-to-end product (session 1).** Reasons:
- **It is the only project with a demo that is guaranteed today without hardware:** the loopback test plus the evidence replay. You can practise operating it from the first session.
- **Its data path (packets, frames, buffer, feedback) is the simplest place to learn clock domains and freshness.** These are then reused directly in OS sessions 3–4.

Do OS second. Its best demo depends on the hardware and power questions in F3, F4 and F10, which need answers first. Do the paired comparison last (session 4), because it only makes sense once both systems are familiar.
