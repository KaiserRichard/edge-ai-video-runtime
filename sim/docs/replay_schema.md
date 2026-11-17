# Replay CSV contract

First column `t` is seconds from one recording's origin, finite and nondecreasing. Rows may leave unrelated fields empty (NaN). Values from different machines must already be mapped to a justified common time base; the app does not fit clocks. Native OS bridge CSV is supported without conversion. Simulation input is a MAT file containing the `result` returned by `run_coursework`.

| Panel | Optional canonical columns |
|---|---|
| Video / class | `image_file` relative to CSV, `ai_label`, `ai_confidence` (0..1), `frame_bad` (0/1); latest supplied image/label at or before replay time, retaining each across unrelated blank rows |
| Sequence | `seq`, `packet_status` (0 received, 1 missing, 2 reorder) |
| Loss | `kernel_loss`, `sequence_loss`, `rr_loss`, fractions 0..1 |
| Jitter | `jitter_ms`, `frame_jitter_ms`, `configured_jitter_ms` |
| Playout | `playout_occupancy`, `deadline_slack_ms` (negative = late) |
| Deadlines | `ontime_rolling`, `ontime_cumulative`, fractions 0..1 |
| Latency | `latency_ms`, `capture_send_ms`, `network_playout_ms`, `queue_ms`, `inference_ms` |
| RTCP | `rtcp_type`, 200 SR / 201 RR / 204 APP |
| Rate | `bitrate_mbps`, `quality`, `fps` |
| Policy | `aoi_fifo_ms`, `aoi_latest_ms`, `queue_fifo`, `queue_latest` |
| Hardware | `temperature_c`, `throttled` numeric mask, `rssi_dbm`, `tx_mbps` |
| Supervisor | `state` 0/1/2/3, `reason` numeric |
| Contention | `cpu0`, `cpu1`, `cpu2`, `cpu3` percent, `rss_mib` |
| UART | `uart_bytes`, `crc_errors` |
| Faults | `fault_active` 0/1 |

Unknown fields remain unavailable, not zero. Columns sharing a panel can have different units; each series is explicitly named in the legend. The app is a teaching/replay view rather than the planned full live web frontend: no Wireshark packet decode, continuous video decode, RTCP hover-detail inspector or remote kill buttons.

CSV files must have at least one row. Native bridge send times must be finite, nondecreasing and no earlier than their input times. Simulation AoI uses exactly the configured warm-up and stop times; if the observer is uninitialized at warm-up, the AoI panel is unavailable, matching the NaN metric. Native bridge AoI covers the initialized interval from first to last send, at the bridge endpoint.

Native stage logs in simulation MAT recordings:

- Camera: `[tick, frame, capture, bytes, size_scale]`.
- RTP: `[tick, seq, timestamp, frame, fragment, count, bytes, marker, capture]`.
- Netem: `[send_tick, seq, frame, loss_drop, queue_drop, arrival, queued_bytes]`.
- Receiver log: `[arrival, seq, frame, duplicate, reordered, packet_J_ms, frame_J_ms]`.
- Receiver frames: `[frame, capture, deadline, complete_time, deadline_checked, on_time]`.
- Receiver aux: `[report_time, pulse, fraction_256, jitter_ticks, cumulative_lost, highest_extended, LSR, DLSR]`.
- Inference: `[finish, frame, capture, service, wait, enqueue, start]`; aux `[tick, queue_length, drops, busy]`.
- UART log: `[arrival, frame, capture, age_at_send, send_tick, capture_to_receive]`; aux `[tick, heartbeat_silence, estimated_source_age, fault_active]`.
- State: `[tick, state, reason]`; rate: `[tick, size_scale]`.

All time-bearing fields are seconds except explicitly named jitter fields or RTP clock ticks. `Inf` completion means incomplete; zero-padded block packets use frame id 0 for no event. Frame ids in actual traffic start at 1.
