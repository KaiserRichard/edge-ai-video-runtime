# ns-3 RTP sweep tables

Inputs: `/opt/edge-runtime/.worktrees/CN-wt-RPTCN3/results/sim_rtp`, `/opt/edge-runtime/.worktrees/CN-wt-RPTCN3/results/sim_rtp_v3`. Only run directories with `summary.json` are included.
SIM values are means [min–max] across finished runs; incomplete runs are omitted.
`n` is packets per frame: the first packet carries $1200-8-4=1188$ frame bytes
(1200-byte RTP payload less the 8-byte fragment header and 4-byte first-fragment
length prefix); each later packet carries $1200-8=1192$ bytes. Thus for frame size $F$:
$n=1+\lceil\max(0,F-1188)/1192\rceil$. CALCULATED frame loss is $1-(1-p)^n$.

## CN-T3

| Configuration | n (packets/frame) | Packet loss (SIM) | Frame loss (SIM) | Frame loss (CALCULATED) | On-time (SIM) | Jitter ms (SIM) | Goodput Mb/s (SIM) |
|---|---:|---:|---:|---:|---:|---:|---:|
| gilbert-elliott-5pct-burst4 | 11 | 5.130% [4.722%–5.449%] | 17.033% [16.000%–17.944%] | 43.120% | 82.967% [82.056%–84.000%] | 0.1506 [0.1452–0.171] | 2.785 [2.775–2.797] |
| random-loss-0 | 11 | 0.000% [0.000%–0.000%] | 0.000% [0.000%–0.000%] | 0.000% | 100.000% [100.000%–100.000%] | 0.1452 [0.1452–0.1452] | 2.935 [2.935–2.935] |
| random-loss-0.01 | 11 | 1.059% [0.970%–1.182%] | 11.167% [10.222%–12.611%] | 10.466% | 88.833% [87.389%–89.778%] | 0.148 [0.1452–0.154] | 2.904 [2.902–2.907] |
| random-loss-0.05 | 11 | 5.036% [4.919%–5.212%] | 43.567% [42.722%–45.056%] | 43.120% | 56.433% [54.944%–57.278%] | 0.1579 [0.1458–0.1742] | 2.788 [2.784–2.79] |
| random-loss-0.1 | 11 | 10.082% [9.970%–10.237%] | 68.678% [67.722%–69.556%] | 68.619% | 31.322% [30.444%–32.278%] | 0.1695 [0.1525–0.1846] | 2.639 [2.634–2.644] |

Run paths by configuration:
- **gilbert-elliott-5pct-burst4:** `CN-T3/gilbert-elliott-5pct-burst4/seed-01`, `CN-T3/gilbert-elliott-5pct-burst4/seed-02`, `CN-T3/gilbert-elliott-5pct-burst4/seed-03`, `CN-T3/gilbert-elliott-5pct-burst4/seed-04`, `CN-T3/gilbert-elliott-5pct-burst4/seed-05`
- **random-loss-0:** `CN-T3/random-loss-0/seed-01`, `CN-T3/random-loss-0/seed-02`, `CN-T3/random-loss-0/seed-03`, `CN-T3/random-loss-0/seed-04`, `CN-T3/random-loss-0/seed-05`
- **random-loss-0.01:** `CN-T3/random-loss-0.01/seed-01`, `CN-T3/random-loss-0.01/seed-02`, `CN-T3/random-loss-0.01/seed-03`, `CN-T3/random-loss-0.01/seed-04`, `CN-T3/random-loss-0.01/seed-05`
- **random-loss-0.05:** `CN-T3/random-loss-0.05/seed-01`, `CN-T3/random-loss-0.05/seed-02`, `CN-T3/random-loss-0.05/seed-03`, `CN-T3/random-loss-0.05/seed-04`, `CN-T3/random-loss-0.05/seed-05`
- **random-loss-0.1:** `CN-T3/random-loss-0.1/seed-01`, `CN-T3/random-loss-0.1/seed-02`, `CN-T3/random-loss-0.1/seed-03`, `CN-T3/random-loss-0.1/seed-04`, `CN-T3/random-loss-0.1/seed-05`

## CN-T5

| Configuration | n (packets/frame) | Packet loss (SIM) | Frame loss (SIM) | Frame loss (CALCULATED) | On-time (SIM) | Jitter ms (SIM) | Goodput Mb/s (SIM) |
|---|---:|---:|---:|---:|---:|---:|---:|
| frame-16000B | 14 | 2.000% [1.865%–2.115%] | 24.689% [22.944%–26.389%] | 24.636% | 75.311% [73.611%–77.056%] | 0.1512 [0.1505–0.1534] | 3.832 [3.827–3.838] |
| frame-3000B | 3 | 2.011% [1.852%–2.167%] | 5.911% [5.444%–6.278%] | 5.881% | 94.089% [93.722%–94.556%] | 0.1017 [0.09904–0.1053] | 0.7211 [0.7203–0.7214] |
| frame-8000B | 7 | 2.033% [1.913%–2.246%] | 13.400% [12.944%–14.722%] | 13.187% | 86.600% [85.278%–87.056%] | 0.1595 [0.1551–0.1646] | 1.916 [1.912–1.918] |

Run paths by configuration:
- **frame-16000B:** `CN-T5/frame-16000B/seed-01`, `CN-T5/frame-16000B/seed-02`, `CN-T5/frame-16000B/seed-03`, `CN-T5/frame-16000B/seed-04`, `CN-T5/frame-16000B/seed-05`
- **frame-3000B:** `CN-T5/frame-3000B/seed-01`, `CN-T5/frame-3000B/seed-02`, `CN-T5/frame-3000B/seed-03`, `CN-T5/frame-3000B/seed-04`, `CN-T5/frame-3000B/seed-05`
- **frame-8000B:** `CN-T5/frame-8000B/seed-01`, `CN-T5/frame-8000B/seed-02`, `CN-T5/frame-8000B/seed-03`, `CN-T5/frame-8000B/seed-04`, `CN-T5/frame-8000B/seed-05`

## CN-T4 — first-arrival playout (SIM; CALCULATED reference)

Source: latest supplied root containing CN-T4. Each cell is mean [min–max] over five seeds.
Calculated late fraction conditions on each run's first-arrival anchor and predicts independent later frames.

| Distribution | J ms | D ms | Late fraction (CALCULATED) | Late fraction (SIM) | On-time fraction (SIM) |
|---|---:|---:|---:|---:|---:|
| normal | 20 | 20 | 0.9993 [0.9985–0.9996] | 0.9994 [0.9989–1.0000] | 0.0006 [0.0000–0.0011] |
| normal | 20 | 50 | 0.5182 [0.4355–0.5471] | 0.5232 [0.4383–0.5722] | 0.4768 [0.4278–0.5617] |
| normal | 20 | 100 | 0.0003 [0.0002–0.0004] | 0.0002 [0.0000–0.0006] | 0.9998 [0.9994–1.0000] |
| normal | 20 | 200 | 0.0000 [0.0000–0.0000] | 0.0000 [0.0000–0.0000] | 1.0000 [1.0000–1.0000] |
| uniform | 5 | 20 | 0.0000 [0.0000–0.0000] | 0.0000 [0.0000–0.0000] | 1.0000 [1.0000–1.0000] |
| uniform | 5 | 50 | 0.0000 [0.0000–0.0000] | 0.0000 [0.0000–0.0000] | 1.0000 [1.0000–1.0000] |
| uniform | 5 | 100 | 0.0000 [0.0000–0.0000] | 0.0000 [0.0000–0.0000] | 1.0000 [1.0000–1.0000] |
| uniform | 5 | 200 | 0.0000 [0.0000–0.0000] | 0.0000 [0.0000–0.0000] | 1.0000 [1.0000–1.0000] |

## CN-T8 — staged loss and ABR (SIM)

Source: latest supplied root containing CN-T8. Cells are mean [min–max] across five seeds; reaction is time from step start to first local ABR evaluation.

| Step (s) | Loss p | Mode | Frame loss | On-time | Mean frame bytes | Reaction s |
|---|---:|---|---:|---:|---:|---:|
| 0–20 | 0 | fixed | 0.000% [0.000%–0.000%] | 100.000% [100.000%–100.000%] | 12000.00 [12000.00–12000.00] | — |
| 0–20 | 0 | abr | 0.000% [0.000%–0.000%] | 100.000% [100.000%–100.000%] | 11688.47 [11688.47–11688.47] | 0.8041 [0.8010–0.8070] |
| 20–40 | 0.05 | fixed | 44.767% [42.500%–47.000%] | 55.233% [53.000%–57.500%] | 12000.00 [12000.00–12000.00] | — |
| 20–40 | 0.05 | abr | 22.300% [20.500%–23.667%] | 77.700% [76.333%–79.500%] | 5009.48 [4156.07–6202.82] | 0.8000 [0.8000–0.8000] |
| 40–60 | 0.15 | fixed | 82.167% [79.667%–85.333%] | 17.833% [14.667%–20.333%] | 12000.00 [12000.00–12000.00] | — |
| 40–60 | 0.15 | abr | 38.633% [36.333%–41.167%] | 61.367% [58.833%–63.667%] | 2666.00 [2666.00–2666.00] | 0.8000 [0.8000–0.8000] |
| 60–80 | 0 | fixed | 0.000% [0.000%–0.000%] | 100.000% [100.000%–100.000%] | 12000.00 [12000.00–12000.00] | — |
| 60–80 | 0 | abr | 0.000% [0.000%–0.000%] | 100.000% [100.000%–100.000%] | 4399.63 [4399.63–4399.63] | 0.8000 [0.8000–0.8000] |
