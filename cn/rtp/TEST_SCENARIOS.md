# CN test scenarios (RTP/RTCP video for edge AI)

English working draft (owner review). The Vietnamese table for the submitted report is produced
from this file. Refines the seed list CN-T1..T10 from the 2026-10-29 handoff.

Rules for every scenario:
- Topology from [ROADMAP.md](ROADMAP.md): Pi A sender with camera, edge receiver, netem on Pi A
  egress. Run IDs: `rtp/results/<scenario>/<config>/run<k>/`.
- Each configuration: 5 runs × 60 s after 5 s warm-up; report mean and min–max (or 95 % CI
  over the 5 runs). Pass criteria are fixed before the runs.
- Each run directory holds: `args.json`, `meta.json` (git hash, kernel, netem line, seed or
  repetition index, `vcgencmd get_throttled` before/after, `iw` link info on Wi-Fi),
  `sender.csv`, `receiver.csv`, `ai.csv`, `rtcp.csv`, `capture.pcap` (tcpdump on the receiver,
  snaplen 128), `summary.json`.
- Latency is measured only on Pi A's clock (capture -> AI result back). Receiver-side numbers
  (jitter, playout) use only the receiver clock.
- Metrics definitions: packet loss = RFC 3550 cumulative lost / expected; interarrival jitter
  J = RFC 3550 §6.4.1 (in ms; packets of one frame share a timestamp, so J includes the
  intra-frame spread — reported, not hidden); frame loss = frames with any packet missing at
  playout time; on-time frame ratio = frames complete before their playout deadline / frames sent.

| ID | Purpose | Setup | Steps | Metric | Pass criterion | Evidence |
|---|---|---|---|---|---|---|
| CN-T1 | RTP is on the wire as specified | Ethernet, no netem, 640x480 @ 15 fps | 1) run 60 s with pcap; 2) `tshark -d udp.port==5004,rtp -d udp.port==5005,rtcp` field export | seq +1 per packet (mod 2^16), timestamp step = 90000/fps per frame, marker bit only on the last packet of a frame, SSRC constant, RTCP SR/RR parse | 0 decode errors; all four properties hold for 100 % of packets | `rtp/results/T1/…/capture.pcap`, `t1_check.json` |
| CN-T2 | Ethernet baseline | Ethernet, no netem, medium bitrate, playout D = 50 ms | 5 runs | packet loss, jitter, frame loss, on-time ratio, capture->AI latency P50/P95, goodput | loss = 0; on-time ratio ≥ 99 %; latency P95 recorded as the reference for later scenarios | `rtp/results/T2/` |
| CN-T3 | Effect of random and burst loss | netem `loss` 0/1/5/10 %, plus Gilbert-Elliott (`loss gemodel`) with mean burst ≈ 4 packets at 5 % average | 5 runs per level | packet loss measured vs configured, frame loss, on-time ratio, AI results per second | measured packet loss within ±1 percentage point of configured (sanity); frame loss grows with packets per frame as predicted by 1−(1−p)^n (CALCULATED) — mismatch beyond the run spread is reported | `rtp/results/T3/` |
| CN-T4 | Playout buffer depth vs delay jitter | netem `delay 20ms 5ms` and `delay 20ms 20ms distribution normal`; D = 20/50/100/200 ms | 5 runs per (jitter, D) | late-frame fraction, end-to-end latency P95, RFC 3550 jitter | late fraction decreases monotonically with D; the chosen D gives late < 1 % at 20 ms ± 5 ms | `rtp/results/T4/` |
| CN-T5 | Bitrate level and packet size | JPEG quality 30/60/90 (≈ low/medium/high bitrate, measured), payload size 500/1200/1400 B, one run at 3000 B with IP fragmentation | 5 runs each; 2 % loss for the packet-size part | goodput, packets per frame, frame loss, IP fragments in pcap | frame loss with 3000 B fragmented payload ≥ frame loss at 1400 B (fragment loss kills the datagram); bitrate per level measured and reported | `rtp/results/T5/` |
| CN-T6 | Ethernet vs Wi-Fi 5 | same as CN-T2 on Wi-Fi (Pi A on Wi-Fi, edge wired to the router); fixed positions | 5 runs each link; log `iw dev wlan0 link` every second | loss, jitter, on-time ratio, latency P95, RSSI, tx bitrate, channel | none fixed (descriptive comparison); every Wi-Fi run has an RSSI log | `rtp/results/T6/` |
| CN-T7 | FIFO vs latest-value hand-off to the AI | AI stage slower than the frame rate (e.g. 30 fps camera, 4-thread off) | 5 runs per policy | AI-result age (Pi A clock), on-time AI results, queue length, frames skipped | latest-value gives lower time-average AI-result age than FIFO in all runs; FIFO queue grows | `rtp/results/T7/` |
| CN-T8 | RTCP-driven adaptive bitrate vs fixed | netem loss steps 0 % → 5 % → 15 % → 0 % (20 s each), RR interval 1 s | 5 runs fixed-high, 5 runs ABR | on-time ratio per step, frame loss, bitrate trace, reaction time (step -> bitrate change) | ABR on-time ratio ≥ fixed in the 15 % step and goodput recovers within 5 s after the return to 0 %; otherwise reported as FAIL | `rtp/results/T8/` |
| CN-T9 | Capture-to-AI-result latency breakdown | Ethernet, no netem; then 5 % loss | 5 runs each | per frame on Pi A clock: capture -> send, send -> result (RTT incl. network, playout, inference); receiver-side playout wait and inference time on the edge clock (reported separately, never subtracted across clocks) | total P95 and each part reported; parts on the same clock sum to the total within 1 ms | `rtp/results/T9/` |
| CN-T10 (optional) | Why RTP needs SRTP: spoofed packet injection | attacker process on the LAN sends RTP with the right SSRC and higher seq | 5 runs; then compare SRTP overhead (bytes, CPU) if implemented | corrupted frames shown / accepted packets; SRTP overhead per packet | demo shows unauthenticated RTP accepts spoofed packets; only on the team's own isolated network | `rtp/results/T10/` |
