# CN SimEvents study

This study uses the connected [CN_simevents model](../generated/CN_simevents.slx) and its [entity dictionary](../generated/CN_simevents.sldd). The media path uses native SimEvents generators, switches, queues, servers and terminators. MATLAB discrete-event blocks adapt the existing `+course` RTP, loss, delay, reassembly, deadline and receiver-report functions to individual entities. The Stateflow AIMD chart is sampled at 1 kHz and its delayed output feeds the frame-sizing block. The hardware comparison uses measured summary values and seeded runs configured from the Pi/netem conditions.

## Reproduce

From the workspace root in MATLAB R2026b, use the following commands. Run all commands in a single session. SimEvents 26.2 and Communications Toolbox 26.2 were confirmed with `ver('slde')` and `ver('comm')`. Stateflow was licensed and the chart executed. Wireless Network Toolbox is unnecessary.

```matlab
addpath(pwd, fullfile(pwd,'study_simevents'), fullfile(pwd,'generated'))
build_cn_simevents
run_cn_simevents_study('A')
run_cn_simevents_study('B')
run_cn_simevents_study('C')
export_cn_simevents_study
cnse_run_shared_tests
```

Open the saved model and double-click **Dashboard** to inspect the five live axes. The axes show target payload bitrate in Mb/s, cumulative channel loss fraction, packet RFC 3550 jitter in ms, complete frames waiting for playout, and the age of the freshest completed AI result in ms. Each run also saves its configuration and entity traces in the corresponding MAT file. The stage validation CSVs contain numerical errors and tolerances.

## Study map

| Diagram | What to follow |
|---|---|
| [Connected model](figures/CN_simevents.png) | RTP from left to right, entity RTCP return below the receiver, and the AIMD size-scale signal back to the camera. |
| [Frames](figures/CN_simevents__Frames.png) | Pi frame cadence and the rate input that scales payload bytes. |
| [Sender Queue](figures/CN_simevents__Sender_Queue.png) | Lesson 07. Bounded FIFO rejects new work at capacity. Latest-value holds one waiting frame and replaces it on arrival. Active service continues. |
| [RTP Packetizer](figures/CN_simevents__RTP_Packetizer.png) | Packets carry sequence, 90 kHz timestamp, payload size, SSRC, frame ID, fragment index, count, marker and capture time. |
| [Serialization](figures/CN_simevents__Serialization.png) | Packet FIFO and link service of `8 × (payload bytes + 48) / link bits per second`. |
| [Channel](figures/CN_simevents__Channel.png) | The seeded draw routes dropped packets to a terminator. Entity Transport Delay handles the guaranteed component, and an infinite-capacity Entity Server applies each surviving packet's remaining delay. |
| [Receiver](figures/CN_simevents__Receiver.png) | Lesson 03. Accept out-of-order fragments, reassemble by frame, and release only complete frames at their playout deadline. Generate one receiver report per second. |
| [Inference](figures/CN_simevents__Inference.png) | Native AI waiting queue and service. The result sink timestamps completion for latency and age. |
| [RTCP Reverse Path](figures/CN_simevents__RTCP_Reverse_Path.png) | Independent loss and propagation. The count of delivered reports controls the sampled report input to AIMD. |
| [AIMD chart](figures/CN_simevents__AIMD.png) | A report above 2% interval loss scales frame bytes by 0.8. Three reports at or below 0.5% add 0.05. The scale is bounded from 0.15 to 1.5. |
| [Stage B dashboard](figures/Stage_B_Dashboard.png) | Fixed and adaptive traces. Dashed lines mark the 15% forward-loss window. The occupancy panel uses a trailing 1 s mean of the live frame count. |

The wireless example informed the loss switch and terminator layout. The Ethernet example informed the packet assembly, FIFO and serialization layout. [MathWorks wireless example](https://www.mathworks.com/help/stateflow/ug/message-communication-with-packet-loss.html) · [MathWorks Ethernet example](https://www.mathworks.com/help/simevents/ug/model-an-ethernet-communication-network-with-csmacd-protocol.html)

Entity Transport Delay integrates a shared transport speed, so the model uses it for the guaranteed component of propagation and a parallel server for the individual remainder. The split lets packets overtake one another when the configured delay draws permit it. [MathWorks Entity Transport Delay](https://www.mathworks.com/help/simevents/ref/entitytransportdelay.html)

## Stage A · Open-loop RTP and RTCP

The first three runs use 5% independent loss, 20 ms base delay, 20 ms normal jitter and a 50 ms playout depth. The sender stays at scale 1.0 and the receiver keeps emitting RTCP reports.

| Run | Sequence loss (%) | On time (%) | RFC jitter (ms) | Result P95 (ms) | AoI (ms) |
|---|---:|---:|---:|---:|---:|
| Seed 1 | 4.33 | 73.6 | 14.706 | 77.4 | 133.4 |
| Seed 17 | 6.09 | 54.6 | 15.050 | 68.2 | 154.9 |
| Seed 903 | 4.20 | 61.3 | 15.204 | 68.7 | 141.8 |
| All packets dropped | 100.00 | 0.0 | Unavailable | Unavailable | Unavailable |
| No configured loss | 0.00 | 100.0 | 0.133 | 62.7 | 96.0 |

The loss extremes delivered zero and 455 packets respectively. AoI is unavailable when no result has reached the observer by warm-up. The packet jitter recurrence and receiver report fields were replayed on the actual arrival order, including out-of-order fragments. All 100 checks passed. [Stage A results](stage_A_results.csv) · [Stage A validation](stage_A_validation.csv)

## Stage B · Closed-loop AIMD and queue policy

The paired loss-step runs use 0%, 15% and 0% configured loss with changes at 15 and 35 s. At the end of the 50 s active window the adaptive scale had recovered from 0.15 to 0.35. The lower byte scale reduced packet count and the number of fragments needed to complete a frame. The configured loss probability stayed the same for both runs.

| Run | Sent packets | On time (%) | Result P95 (ms) | AoI (ms) | Minimum scale |
|---|---:|---:|---:|---:|---:|
| Loss step, fixed | 4557 | 73.2 | 62.7 | 147.7 | 1.00 |
| Loss step, AIMD | 2730 | 87.1 | 62.7 | 111.9 | 0.15 |
| 0.55 Mb/s link, fixed | 1823 | 0.0 | Unavailable | Unavailable | 1.00 |
| 0.55 Mb/s link, AIMD | 738 | 96.6 | 81.4 | 117.0 | 0.15 |
| Inference queue, FIFO | 2184 | 100.0 | 483.5 | 500.2 | 1.00 |
| Inference queue, latest | 2184 | 100.0 | 116.9 | 133.5 | 1.00 |
| All reverse reports lost | 546 | 32.4 | 62.7 | 225.6 | 1.00 |
| Delayed and lossy reverse reports | 369 | 50.0 | 62.7 | 158.2 | 0.51 |
| Sender queue, FIFO | 1510 | 0.0 | Unavailable | 6933.3 | 1.00 |
| Sender queue, latest | 1468 | 66.7 | 112.7 | 140.5 | 1.00 |

- The fixed sender overloaded the 0.55 Mb/s serializer and produced no on-time results. AIMD restored on-time playout for 96.6% of frames in the 10–20 s observation window.
- With 30 FPS input and 50 ms inference service, FIFO rejected 112 frames and latest-value replaced 119 waiting frames. Mean AoI fell from 500.2 to 133.5 ms. Under 50 ms sender service, FIFO again rejected 112 frames and latest-value replaced 119. The FIFO observer held its last early result through warm-up, so its mean age exceeded 6 s and its latency percentile was unavailable.
- Dropping every reverse report left the sender scale at 1.0. With 25% configured reverse loss, 50 ms reverse base delay and 20 ms reverse jitter, five reports reached the sender over the run and drain. The rate reached 0.512 during active capture.
- All 200 checks passed, including Stateflow rate decisions against `course.aimd` on the delivered report sequence. [Stage B results](stage_B_results.csv) · [Stage B validation](stage_B_validation.csv)

## Stage C · Measured Pi/netem conditions

The study ran 28 cases from `course.cnConfigs`, using seed 11, 65 s of capture, a 5 s warm-up and a 2 s drain. The comparison CSV contains 127 measurements across 26 configurations. It takes 70 values from the measured-target CSV and 57 additional values, including P95s, from the hardware table snapshot. The two T8 controller cases are simulations of the configured loss waveform. The CSV records the source, signed simulated-minus-measured error, and relative error where the measurement is nonzero. [Measured comparison](stage_C_measured_comparison.csv) · [Hardware target CSV](../data/cn_targets.csv) · [Hardware tables](../data/source/cn_hw_tables.md)

| Condition | Metric | Measured | Simulated |
|---|---|---:|---:|
| Ethernet baseline | Capture-to-result P95 | 72.20 ms | 62.70 ms |
| Bursty loss | Sequence loss | 5.30% | 5.43% |
| 5% independent loss | Frame loss | 24.00% | 21.91% |
| 20 ms normal jitter, D = 100 ms | RFC jitter | 16.24 ms | 16.19 ms |
| 20 ms normal jitter, D = 20 ms | Late frame share | 93.50% | 91.10% |
| 20 ms normal jitter, D = 20 ms | Capture-to-result P95 | 42.65 ms | 38.82 ms |
| 5 ms uniform jitter, D = 50 ms | RFC jitter | 2.33 ms | 2.68 ms |
| 3000 B payload, 2% per IP fragment | Sequence loss | 4.80% | 5.02% |
| T7 FIFO | Capture-to-result P95 | 621.20 ms | 533.53 ms |
| T7 latest | Capture-to-result P95 | 191.67 ms | 166.87 ms |
| T7 FIFO | Mean AI-result AoI | 623.00 ms | 550.23 ms |
| T7 latest | Mean AI-result AoI | 204.00 ms | 183.67 ms |
| Wi-Fi sensitivity | RFC jitter | 0.29 ms | 18.83 ms |
| Wi-Fi sensitivity | Capture-to-result P95 | 144.72 ms | 83.82 ms |

At a 20 ms playout depth, the normal-jitter run achieved a 38.82 ms P95 among returned results, but its time-average age rose to 642.5 ms as most frames missed playout. Increasing depth to 100 ms brought age to 152.2 ms and eliminated late frames in this run. For T7, latest-value reduced AoI by 66.6% in simulation and 67.3% in the measurements. All 560 Stage C oracle checks passed. [Stage C results](stage_C_results.csv) · [Stage C validation](stage_C_validation.csv)

## Trace validation

Across the 43 study runs, all 860 checks passed. A saved-model reload with the bus absent from the base workspace also passed 20 checks. Changing diagram layout preserved the smoke run's transmission, reception, report, feedback, rate and result streams exactly.

| Quantity | Same-trace check | Largest absolute difference |
|---|---|---:|
| RFC jitter | `course.RFCJitter` and `course.ReceiverReport` replayed in arrival order | 0 ms |
| RFC jitter | Independent 90 kHz transit-difference recurrence with gain 1/16 | 3.55e-15 ms |
| RTCP interval fraction and cumulative loss | Receiver-report fields from `course.ReceiverReport` | 0 |
| Forward loss | Regenerated seeded `course.Loss` decisions, including IP fragments | 0 packets |
| Reported sequence loss | Unique received fragments matched to transmissions | 4.86e-17 |
| AI-result AoI | Independent integral of observation time minus freshest delivered capture, compared with `course.aoi` | 3.89e-12 ms |
| Reverse delivery | Delivered report times and fields from the seeded reverse loss and delay | 0 s |
| Forward delivery | Native arrival compared with the seeded propagation time | 1.001 ms |
| AIMD | `course.aimd` on delivered reports, checking scale and feedback timing | 0 scale, 2.000 ms |

The AoI integral uses exact event times and requires an initialized observer at the start of the analysis window. The File Exchange reference concerns steady-state AoI distributions for specific stochastic queues. The validation here integrates the recorded event trace, including loss bursts, deadlines and the chosen queues. [Queuing Models of Age of Information](https://www.mathworks.com/matlabcentral/fileexchange/74923-queuing-models-of-age-of-information)

## Shared regression suite

All 26 original library and regression tests passed, along with the 3 existing Simulink integration tests. The Simulink test setup rebuilds shared models, so the suite ran against identical test sources in a temporary workspace copy. The SHA-256 comparison covered 29 protected files, including the original `generated/CN_shared.slx`, all test sources, the shared model builders and the `+course` reference implementations. Every hash matched the handover snapshot. I opened and inspected all 11 final PNGs in the study map. [Test results](shared_test_results.csv) · Hashes before (hash list kept locally because it contains local paths) · Hashes after (hash list kept locally because it contains local paths)

## Limits

- The workspace contains hardware summaries. Replaying the original RTP arrivals and Pi result timestamps would require the per-run captures. Each simulated condition uses one seed, and published measurements generally aggregate five runs.
- Simulation timestamps AI results at local inference completion. The hardware result timestamp can include return to the Pi. Fixed service times and deadline release also suppress the latency tail seen in the hardware. The Wi-Fi case uses an assumed delay law, which substantially overpredicts jitter and underpredicts P95.
- The model uses one SSRC and RTP metadata with simplified IP fragmentation loss. RTCP implements receiver reports through `course.ReceiverReport`, whose sender-report timing fields are placeholders. The packet FIFO is unbounded. The bottleneck example therefore exercises serialization backlog.
- The continuous transport block uses a 1 µs positive floor and a 1 ms maximum solver step. The measured largest per-packet timing difference from its seeded draw was 1.001 ms, within the 1.01 ms validation tolerance. Jitter, loss and age parity use each simulation's actual event trace.

CN_SIMEVENTS_OK
