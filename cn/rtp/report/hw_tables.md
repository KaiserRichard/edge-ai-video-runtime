# Hardware results tables (CN-T2/T3/T4/T5/T6/T7/T9)

Packet loss is reported both from the sender's latest RR (`cum_lost / expected`) and from unique received RTP sequence numbers divided by sender packet count. Frame loss and on-time ratio use frames as denominator. Latency and queue/inference intervals are calculated only within their named clock. Empty cells mean unavailable or inapplicable.

## CN-T2 and CN-T3

### CN-T2

| Config | Runs | Configured netem | RR loss | Sequence loss | Packets/frame | Frame loss | CALCULATED 1−(1−p)^n̄ | On-time | Late | Jitter (ms) | Capture→AI P50 (ms) | Capture→AI P95 (ms) | AI results/s | Throttled before | Throttled after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eth_q75_640x480_15fps | 5 | none | 0.000 | 0.000 | 6.080 | 0.000 |  | 1.000 | 0.000 | 0.14 | 66.62 | 72.20 | 15.01 | throttled=0x0 |  |

### CN-T3

| Config | Runs | Configured netem | RR loss | Sequence loss | Packets/frame | Frame loss | CALCULATED 1−(1−p)^n̄ | On-time | Late | Jitter (ms) | Capture→AI P50 (ms) | Capture→AI P95 (ms) | AI results/s | Throttled before | Throttled after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ge5_b4 | 5 | loss gemodel 1.316% 25% 100% 0% | 0.053 | 0.053 | 5.121 | 0.088 |  | 0.895 | 0.000 | 0.20 | 116.57 | 119.99 | 13.45 | throttled=0x0 | throttled=0x0 |
| loss0 | 5 | qdisc fq_codel 0: root refcnt 2 limit 10240p flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn drop_batch 64 | 0.000 | 0.000 | 5.607 | 0.000 | 0.000 | 0.999 | 0.001 | 0.15 | 116.03 | 121.31 | 15.00 | throttled=0x0 | throttled=0x0 |
| loss1 | 5 | loss 1% | 0.010 | 0.010 | 5.096 | 0.049 | 0.050 | 0.951 | 0.000 | 0.18 | 115.83 | 121.02 | 14.29 | throttled=0x0 | throttled=0x0 |
| loss10 | 5 | loss 10% | 0.100 | 0.100 | 5.107 | 0.415 | 0.416 | 0.585 | 0.000 | 0.23 | 116.51 | 120.02 | 8.78 | throttled=0x0 | throttled=0x0 |
| loss5 | 5 | loss 5% | 0.052 | 0.052 | 5.106 | 0.240 | 0.230 | 0.760 | 0.000 | 0.22 | 116.69 | 119.81 | 11.42 | throttled=0x0 | throttled=0x0 |

### CN-T4

| Config | Runs | Configured netem | RR loss | Sequence loss | Packets/frame | Frame loss | CALCULATED 1−(1−p)^n̄ | On-time | Late | Jitter (ms) | Capture→AI P50 (ms) | Capture→AI P95 (ms) | AI results/s | Throttled before | Throttled after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d20j20n_D100 | 5 | delay 20ms 20ms distribution normal | 0.000 | 0.000 | 5.000 | 0.000 |  | 1.000 | 0.000 | 16.24 | 117.68 | 122.14 | 15.01 | throttled=0x0 | throttled=0x0 |
| d20j20n_D20 | 5 | delay 20ms 20ms distribution normal | 0.000 | 0.000 | 5.000 | 0.000 |  | 0.065 | 0.935 | 15.42 | 37.91 | 42.65 | 0.97 | throttled=0x0 | throttled=0x0 |
| d20j20n_D200 | 5 | delay 20ms 20ms distribution normal | 0.000 | 0.000 | 5.000 | 0.000 |  | 1.000 | 0.000 | 15.31 | 216.61 | 221.17 | 15.02 | throttled=0x0 | throttled=0x0 |
| d20j20n_D50 | 5 | delay 20ms 20ms distribution normal | 0.000 | 0.000 | 5.000 | 0.000 |  | 0.857 | 0.143 | 16.89 | 75.32 | 80.15 | 12.88 | throttled=0x0 | throttled=0x0 |
| d20j5_D100 | 5 | delay 20ms 5ms | 0.000 | 0.000 | 5.000 | 0.000 |  | 1.000 | 0.000 | 2.69 | 131.60 | 135.21 | 15.01 | throttled=0x0 | throttled=0x0 |
| d20j5_D20 | 5 | delay 20ms 5ms | 0.000 | 0.000 | 5.105 | 0.000 |  | 1.000 | 0.000 | 2.66 | 52.47 | 56.24 | 15.01 | throttled=0x0 | throttled=0x0 |
| d20j5_D200 | 5 | delay 20ms 5ms | 0.000 | 0.000 | 5.000 | 0.000 |  | 1.000 | 0.000 | 2.49 | 232.11 | 233.53 | 15.02 | throttled=0x0 | throttled=0x0 |
| d20j5_D50 | 5 | delay 20ms 5ms | 0.000 | 0.000 | 5.077 | 0.000 |  | 1.000 | 0.000 | 2.33 | 82.76 | 87.90 | 15.01 | throttled=0x0 | throttled=0x0 |

## CN-T5 — bitrate and packet size

For 2 % independent loss, the calculated frame loss is `1 − (1 − p)^n`, using each run's mean packets/frame. IP datagram length is estimated as `mtu_payload + 48 B` (IPv4, UDP, RTP, and shared payload header). For a 3000 B payload, the estimated IP fragmentation count is `ceil((mtu_payload + 28) / 1480) = 3`. Netem drops per IP fragment, so an RTP datagram is lost if any fragment is lost; calculated datagram loss is `1 − (1 − p)^3`.

| Config | Runs | Quality | MTU payload (B) | Mean JPEG bytes/frame | Measured sender bitrate (Mb/s) | Packets/frame | RR loss | Sequence loss | Frame loss | CALCULATED frame loss at 2 % | IP datagrams >1500 B | CALCULATED loss/datagram (3000 B) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| payload1200_loss2 | 5 | 75 | 1200 | 6071.0 | 0.729 | 5.232 | 0.019 | 0.020 | 0.098 | 0.100 | 0 |  |
| payload1400_loss2 | 5 | 75 | 1400 | 5945.1 | 0.714 | 5.002 | 0.020 | 0.020 | 0.097 | 0.096 | 0 |  |
| payload3000_frag_loss2 | 5 | 75 | 3000 | 5860.9 | 0.704 | 2.318 | 0.048 | 0.048 | 0.107 | 0.046 | 1935 | 0.059 |
| payload500_loss2 | 5 | 75 | 500 | 6131.2 | 0.737 | 12.307 | 0.019 | 0.019 | 0.212 | 0.220 | 0 |  |
| q30 | 5 | 30 | 1200 | 5650.4 | 0.679 | 5.003 | 0.000 | 0.000 | 0.000 |  | 0 |  |
| q60 | 5 | 60 | 1200 | 5777.2 | 0.694 | 5.024 | 0.000 | 0.000 | 0.000 |  | 0 |  |
| q90 | 5 | 90 | 1200 | 10537.4 | 1.266 | 9.211 | 0.000 | 0.000 | 0.000 |  | 0 |  |

## CN-T6 — Wi-Fi link

| Config | Runs | RR loss | Sequence loss | Jitter (ms) | On-time | Capture→AI P50/P95 (ms) | RSSI mean/min (dBm) | Tx bitrate | Frequency (MHz) | Channel |
|---|---|---|---|---|---|---|---|---|---|---|
| wifi_D50 | 5 | 0.000 | 0.000 | 0.29 | 0.966 | 102.24 / 144.72 | -72.3 / -74.2 | 175.5 MBit/s | 5300 | 60 |

## CN-T7 — FIFO vs latest

AI-result age is time-average AoI on the Pi clock, computed from capture and result-receipt pairs in `sender.csv` / `results_tx.csv`. Queue growth is the linear trend in enqueue-to-start wait against enqueue time on the edge clock.

| Config / policy | Runs | Mean AI-result age (s) | Results/s | Frames skipped | Queue wait P50/P95 (ms) | FIFO queue growth (ms/s) | Capture→AI P50/P95 (ms) |
|---|---|---|---|---|---|---|---|
| fifo | 5 | 0.623 | 17.63 | 802 | 440.20 / 461.57 |  | 599.90 / 621.20 |
| latest | 5 | 0.204 | 17.52 | 809 | 16.48 / 31.53 |  | 175.47 / 191.67 |

## CN-T9 — per-frame latency breakdown

Pi-clock components are capture→first send and first send→result receipt; Pi-clock total is capture→result receipt. Edge-clock components are playout wait, AI queue wait, and inference. Each cell is mean of per-run P50/P95 values. Pi-clock component sum is checked against total per paired frame; the reported maximum absolute error should be ≤1 ms.

| Config | Runs | Pi capture→send P50/P95 (ms) | Pi send→result P50/P95 (ms) | Pi total P50/P95 (ms) | Max Pi sum error (ms) | Edge playout wait P50/P95 (ms) | Edge queue wait P50/P95 (ms) | Edge inference P50/P95 (ms) |
|---|---|---|---|---|---|---|---|---|
| loss5_D50 | 5 | 0.07 / 0.09 | 67.93 / 73.58 | 68.01 / 73.66 | 0.000 | 50.16 / 50.42 | 0.12 / 0.14 | 12.52 / 13.08 |
| noloss_D50 | 5 | 0.07 / 0.09 | 67.84 / 72.95 | 67.91 / 73.03 | 0.000 | 50.26 / 50.54 | 0.12 / 0.13 | 12.51 / 12.93 |

Footnote: smoke configurations excluded from all tables: CN-T3: smoke_loss5; CN-T5: smoke_frag3000.
