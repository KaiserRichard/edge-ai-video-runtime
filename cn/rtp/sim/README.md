# ns-3 RTP link (SIM1 / SIM1b / SIM2 / SIM3)

Build with `scripts/build_sim_rtp.sh` (ns-3 **3.44**, existing libraries only,
`-Wall -Wextra -Werror`). Run from the repository root:

```sh
build/rtp-video --link=csma --frameBytes=12000 --fps=30 --lossP=0.05 \
  --simTime=60 --seed=1 --run=1 --outDir=results/sim_rtp/manual
.venv/bin/python rtp/sim/validate.py
.venv/bin/python rtp/sim/sweep.py CN-T3
```

`validate.py` runs the SIM1b baseline, Bernoulli frame-size grid and
Gilbert–Elliott comparison. It checks packet loss, complete frame accounting,
first-packet timing, calculated jitter and burst length. Evidence is written
to `results/sim_rtp/SIM1b/validation.json` and individual run directories.
Every run is also passed to unchanged AN1 `compute_run_metrics`, producing
`summary.json`. No AI results are simulated; their metrics are JSON `null`.

## Model and time

DESIGN: CSMA is a two-node 100 Mb/s DIX Ethernet channel with 1 µs propagation.
Wi-Fi is an 802.11ac ad-hoc pair, 5 GHz/80 MHz, IdealWifiManager, separated
by `--distance` metres. It is not an AP-to-wired-edge topology.

DESIGN: RTP/RTCP use UDP ports 5004/5005, PT 96 and a 90 kHz RTP clock.
The 1200-byte RTP payload includes the shared 8-byte fragment header and,
on the first fragment only, a 4-byte JPEG length. RTP's 12-byte header is
additional. Marker indicates the last fragment. Payload bytes are synthetic;
JPEG encoding, inference and JPEG trace-file replay are not implemented.

DESIGN: `--frameBytes` is fixed by default. `--frameJitter=0.1` restores
SIM1's optional uniform ±10% size variation, on its own RNG stream.
`--simTime` now means media duration: first capture at simulator time 0.2 s,
then captures in `[0.2, 0.2 + simTime)`. A non-RTP warm-up at 0.1 s resolves
ARP. Capture times are scheduled from the initial capture, avoiding cumulative
period rounding. A drain of at least 1 s, extended for configured delay/playout,
precedes shutdown; it is excluded from media duration.

DESIGN: all logged timestamps come from `Simulator::Now()` in nanoseconds.
Shared CSV column names/order remain unchanged (`*_mono_ns`, `*_rx_ns`).
`meta.json` explicitly maps both suffixes to the **sim** clock; these are
not hardware clock measurements. `args.json` records model inputs. The sweep
and validator add git revision, dirty-worktree flag, command and wall time.

## Loss and playout

DESIGN: one `RateErrorModel` decision per received RTP UDP datagram; never
ARP, warm-up or RTCP. With `--geBurst=B`, a two-state ErrorModel replaces it.
Injection is after UDP reception on both links and before added delivery delay.
It does not model bit errors, IP-fragment loss or Wi-Fi MAC retransmissions.
Underlying link/queue drops still contribute to measured loss under overload.
Explicit RNG streams separate loss, frame sizes and receiver delay.

CALCULATED: GE emits loss in the bad state and success in the good state.
With bad-to-good probability `b=1/B`, use good-to-bad `a=p*b/(1-p)`:
stationary loss is `a/(a+b)=p`, mean consecutive losses is `B`. Start in the
stationary distribution. Infeasible transition probabilities are rejected;
`p=0` and `p=1` give exact no-loss and all-loss endpoints.

DESIGN: `--jitterDist=uniform|normal` defaults to uniform. Extra delay is
`max(0, delayMs + X)` milliseconds, with uniform `X ~ U(-jitterMs,+jitterMs)`
or normal `X ~ N(0,jitterMs²)` (J is the standard deviation). `jitterMs=0`
is deterministic. `meta.json.delay_clip_count` counts sampled negative totals
clipped to zero, after loss injection. The delay RNG uses stream 30.
This is extra receive-side processing delay,
not channel propagation. Independent packet delays may reorder packets.
Completion requires the first fragment, marker and contiguous JPEG byte ranges;
a marker arriving early does not finalize the frame. Arrival/completion times
refer to delivery after this additional delay.

DESIGN: after the run, join receiver observations with the sender's frame
manifest to write **every** sent frame, including entirely unobserved frames.
This is simulation-only offline accounting, not information delivered over RTP.
The manifest never affects loss, reception, jitter or RTCP feedback.
`n_expected` comes from the manifest; `n_received` counts unique fragment offsets.
Completion time is empty for incomplete frames. `--playoutAnchor=first|capture`
defaults to first, matching hardware RTP2: the first delivered RTP packet anchors
`playout = t0 + floor((extended_ts - ts0) * 1e9 / 90000) + D` in nanoseconds.
`t0` is its arrival after impairment, and `ts0` its RTP timestamp, even when
that packet is a reordered fragment or from a later frame. Timestamps unwrap
around the highest extended observation; consecutive observations must be less
than 2³¹ ticks apart. Capture mode retains `capture + D`. Complete by deadline
is `ok`, complete after it is `late`, incomplete at shutdown is `lost`.
Unobserved frames have an empty first-anchor deadline; the manifest supplies
counts only. No artificial completion times are created. There is no AI
playout callback or bounded late-window eviction here: accounting completes
at shutdown. Hardware RTP2's default late window is 1 s.

DESIGN: drain is at least 1 s and otherwise delay + J + D + 100 ms for uniform,
or delay + 12J + D + 100 ms for normal. A normal distribution is unbounded;
this finite drain does not guarantee delivery of arbitrarily extreme draws.

DESIGN: RR is sent every second and once at receiver shutdown, uses extended
highest sequence (including wrap), and logs direction `tx`. This controlled
single-source session starts at sequence zero; it does not implement RTP source
probation/restarts/collision handling. A report cannot know a lost trailing
packet or an entirely unobserved stream. For exact simulation packet loss use
`1 - len(receiver.csv)/sum(sender.n_pkts)`; AN1 uses the final receiver RR.
No SR/SDES or RTT is simulated; LSR/DLSR are zero and RTT is empty.

## Calculated baseline, replacing SIM1's jitter threshold

CALCULATED for a full packet: RTP datagram `12 + 1200 = 1212 B`, plus UDP 8 B,
IPv4 20 B, Ethernet header/FCS 18 B. Serialization is
`1258 * 8 / 100e6 = 100.640 µs`; first-packet transit including propagation is
**101.640 µs**. This follows ns-3's CSMA model, which does not charge a preamble.

CALCULATED: the default interframe gap is 0.960 µs, shorter than channel
propagation 1 µs. ns-3's next send therefore takes one 1 µs backoff slot:
full-packet arrival spacing is **102.600 µs**. With a fixed 12000 B frame,
there are 11 packets: ten full datagrams and a final 104 B RTP datagram.
The last gap is `150*8/100e6 + 0.960 µs + 1 µs = 13.960 µs`.
Intra-frame arrival spread is `9*102.600 + 13.960 = 937.360 µs`.

CALCULATED: all packets in a frame share one RTP timestamp. In steady state,
RFC 3550 §6.4.1/A.8 `J += (abs(D) - J)/16` sees nine full-packet gaps, the
last short gap and one frame-boundary transit reset of that spread. Its cycle
mean is `2*937.360/11 = 170.429 µs` (**0.170429 ms**), with periodic range
0.145531–0.195020 ms. The validator allows one 90 kHz tick (0.011111 ms) for
integer timestamp quantization. This replaces the incorrect `<0.1 ms` check.

SOURCE: local ns-3.44 `src/csma/model/csma-net-device.cc` (DIX headers, IFG,
TransmitStart), `csma-channel.cc` (propagation) and `backoff.cc` (slot defaults).
SIM evidence and measured comparisons are in `logs/SIM1b-summary.md`.

## Sweep limitations

DESIGN: CN-T4 uses (uniform, J=5 ms) and (normal, J=20 ms), delay 20 ms,
D=20/50/100/200 ms, five seeds each, and explicit first anchoring. This matches
the requested netem delay distributions; independent packet scheduling permits
reordering as with netem without rate. The normal model uses an ideal Gaussian,
not netem's finite distribution table. CN-T3 and fixed-mode traffic are unchanged.
CN-T5 varies frame size only, not packet payload size/IP fragmentation.

## SIM2: CN-T8 loss steps and ABR

DESIGN: `--lossSteps="0:0,20:0.05,40:0.15,60:0"` overrides `--lossP` with
Bernoulli probabilities on half-open intervals measured from first capture
(simulator time 0.2 s). Steps must start at zero, increase strictly and have
finite probabilities in [0,1]. The last probability persists. Steps and GE
are mutually exclusive. The existing per-RTP-datagram injection point and
loss RNG stream are reused; ARP, warm-up and RTCP remain outside injection.
The step applies at reception before additional delivery delay, so a datagram
crossing a step boundary uses the probability at its injection time.

DESIGN: `--abr=true` starts at quality 75. On each received RR, compare its
quantized `fraction_lost / 256` with strict thresholds: >0.05 multiplies quality
by 0.7, truncates to integer and clamps at 20; <0.01 for three consecutive
RRs adds 5, clamped at 95. After every increase, restart the three-RR counter.
Any RR with loss >=0.01 resets that counter. The hardware ABR1 jitter guard
also resets it on low-loss reports if jitter is both >=1.5 times the previous
report and at least 90 ticks higher. Smaller rises count as clean. The initial
report has no rising trend. Loss decrease takes precedence over jitter.
RRs remain every 1 s on the receiver's simulator schedule, plus shutdown RR.
The sender stays alive during drain; decisions then cannot affect ended media.

ASSUMED: synthetic JPEG bytes = `max(1, floor(frameBytes * quality / 90))`.
This linear model makes `frameBytes` the quality-90 reference, with no fixed
JPEG overhead or resolution adaptation. Optional frame jitter multiplies this
base before truncation. SIM3 aligns the quality controller and jitter guard
with `work/ABR1:rtp/rtp/abr.py`; hardware's companion resolution adaptation
is not modeled. This is not a measured encoder rate/quality curve and
does not establish visual quality or AI accuracy. Fixed mode preserves the
original bytes and historical quality tag 75; that tag does not scale traffic.

DESIGN: every RR evaluation, including holds and saturation, writes a
`dir=local,type=ABR` row in `rtcp.csv` at the sender's receive time. The shared
column order is unchanged; numeric fields retain the triggering RR values,
LSR/DLSR remain zero and RTT empty. `sender.csv` records the resulting quality
and actual RTP datagram bytes for each frame. No feedback column is repurposed
to store quality. All CSV timestamps use the same simulator clock.

```sh
.venv/bin/python rtp/sim/sweep.py CN-T8
.venv/bin/python rtp/sim/t8_steps.py results/sim_rtp/CN-T8/abr/seed-01
```

DESIGN: CN-T8 runs fixed and ABR, each for 80 s with five seeds, writing the
usual AN1 summary plus `t8_steps.json` per run. Bins are capture-relative
[0,20), [20,40), [40,60), [60,80). Frame loss means incomplete at shutdown;
on-time ratio counts `ok` / all captured frames, so late frames are excluded.
Mean frame bytes excludes RTP/fragment headers (subtract `20*n_pkts + 4`
from sender bytes); `mean_rtp_frame_bytes` also reports bytes with headers.
`reaction_time_s` is step start to the first local ABR evaluation within that
step (including hold decisions), as requested by SIM2. Additionally,
`bitrate_reaction_time_s` counts only evaluations that change quality observed
in the next captured frame. Holds, saturation and drain-only decisions are
excluded from this second metric. No evaluation/change is JSON `null`, including
fixed mode. The initial interval now includes additive recovery from quality 75; a later
loss step may have no change if quality has already reached the floor.
These two metrics distinguish receiving feedback from changing traffic.

DESIGN: acceptance follows CN-T8: compare on-time ratio during 15% loss and
check goodput recovery within 5 s after return to zero. A first upward quality
change alone is not full goodput recovery. Under this controller a fall to
quality 20 requires fifteen +5 increases to reach 95: at least 45 clean RRs
(CALCULATED). The 20 s recovery step may therefore fail that criterion.


## SIM3 calculated CN-T4 late fraction

CALCULATED: condition on the first delivered packet's capture-relative arrival
`a` (ms). For another frame, let packet i's deterministic link transit be `b_i`
and its added delay be `Y_i`. Ignoring at most one 90 kHz tick of timestamp
rounding, completion is `max_i(b_i + Y_i)` and deadline is `a + D`.
Independent packet delays therefore give

`P(late | a) = 1 - product_i F_Y(a + D - b_i)`.

For uniform delay 20 ± 5 ms, `F_Y(x) = clamp((x - 15)/10, 0, 1)`.
The anchor is the *first arrival*, not necessarily the first sent packet;
its selection changes the distribution of `a`. An unconditional estimate must
average this formula over that selected anchor, not substitute mean delay.
The formula applies to subsequent independent frames; the anchoring frame's
packet delays are conditioned on the first arrival.

CALCULATED worked example: with 12000 B and the default CSMA link, 11 packets
have `b_i` between 0.101640 and 1.039000 ms. If the first delivered packet
arrives at `a=16 ms`, D=20 gives a deadline at capture +36 ms. Every CDF term
is 1 because `36 - 1.039 > 25`, so expected late fraction is **0**.
Even the earliest possible anchor, `a=15.101640`, gives a deadline at
35.101640 ms versus latest completion 26.039000 ms. Thus every seed, including
the anchoring frame, has exactly zero expected late frames at D=20; larger
D also give zero. By contrast, at D=5 and `a=16`, the product terms are about
0.496–0.590, so the late fraction exceeds 99%: the anchor matters in general.
For clipped normal delay, `F_Y(x)=0` for x<0 and `Phi((x-20)/20)` for x>=0;
the point mass at zero is `Phi(-1)` (about 15.87%, CALCULATED).

SIM: the SIM3 comparison and all five-seed ranges are in
`logs/SIM3-summary.md`, from `results/sim_rtp_v3/CN-T4/`. The uniform sweep
agrees with the zero late fraction derived above (all five seeds at every D).
SIM normal mean late fractions are 0.999444 at D=20, 0.523222 at D=50,
0.000222 at D=100 and 0 at D=200 ms. Run both corrected grids with:

```sh
.venv/bin/python rtp/sim/sweep.py CN-T4 CN-T8 --out results/sim_rtp_v3
```
