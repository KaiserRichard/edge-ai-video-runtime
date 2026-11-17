"""Bounded sequence-gap estimator, separate from the sender's RFC RR stats."""
from collections import deque


class PacketStats:
    def __init__(self):
        self.highest = self.base = None
        self.seen = set()
        self.order = deque()
        self.unique = 0
        self.frame_ts = self.frame_time = None
        self.frame_jitter = 0.0

    def update(self, data, time_s):
        seq = data["seq"]
        extended = seq if self.highest is None else self.highest + ((seq - self.highest + 32768) % 65536 - 32768)
        duplicate = extended in self.seen
        reordered = self.highest is not None and extended < self.highest
        gap_start = None
        if self.highest is None:
            self.base = extended
        elif extended > self.highest + 1:
            gap_start = self.highest + 1
        if not duplicate:
            self.unique += 1
            self.seen.add(extended)
            self.order.append(extended)
            if len(self.order) > 65536:
                self.seen.discard(self.order.popleft())
        self.highest = extended if self.highest is None else max(self.highest, extended)
        self.base = min(self.base, extended)
        expected = self.highest - self.base + 1
        result = {"extended_seq": extended, "packet_status": "duplicate" if duplicate else "reordered" if reordered else "received",
                  "gap_start": gap_start, "gap_end": extended - 1 if gap_start is not None else None,
                  "sequence_lost": max(0, expected - self.unique),
                  "sequence_loss_pct": max(0, expected - self.unique) / expected * 100}
        ts = data["rtp_ts"]
        delta = None if self.frame_ts is None else (ts - self.frame_ts + 2**31) % 2**32 - 2**31
        if delta is None or delta > 0:
            if delta is not None:
                deviation_ms = abs((time_s - self.frame_time) * 1000 - delta / 90)
                self.frame_jitter += (deviation_ms - self.frame_jitter) / 16
            self.frame_ts, self.frame_time = ts, time_s
        # Arrival at hub is unsuitable for estimating network jitter; the sender
        # of live telemetry or the CSV adapter must supply receiver-clock jitter.
        return result
