# Engineering rules extracted from source process notes

Use one clock domain for latency; never subtract Pi and laptop monotonic clocks.
Keep packet loss, frame loss, lateness and freshness denominators explicit.
Use the freshest delivered capture for time-average age of information.

Bound queues. Latest-value replacement replaces waiting work; it cannot cancel
an inference already executing. Keep the heartbeat path independent of result
freshness. FAILSAFE stays latched until explicit healthy rearm; returning traffic
alone does not reset it. Preserve session/generation validation and CRC handling.

Label evidence MEASURED, SIMULATED, CALCULATED, SYNTHETIC, SOURCE or UNKNOWN.
Keep failed runs, exclusion reasons, sample counts, thermal flags and provenance.
Do not replace measurements with synthetic examples or treat pending work as done.

Keep dashboard telemetry optional and nonblocking. Expose only fixed repository
evidence roots. Reject traversal and symlink escapes. Documentation should use
relative paths and explain missing optional evidence.

These stable rules summarize useful OS/CN agent instructions, camera/protocol
tickets, dashboard design notes and simulation task notes. Raw agent scheduling,
personal paths and private coordination records are intentionally excluded.
