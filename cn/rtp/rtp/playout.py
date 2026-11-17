"""Fixed receiver-clock playout and bounded JPEG reassembly.

RTP timestamp deltas use the 90 kHz media clock (RFC 3550 §5.1), not a
cross-machine wall-clock subtraction. For each SSRC the first arrival anchors
playout: t0 + (unwrapped_ts - ts0) / 90000 + delay.

One final row is emitted per observed frame. Complete by deadline -> ok;
complete after deadline within late_window -> late; still incomplete after that
window -> lost. Only ok frames reach the callback, at playout. Entirely unseen
frames and unknown packet counts require a join with sender.csv; we do not
invent their timestamps or packet counts. Duplicate packets do not add frames.
"""
from __future__ import annotations

from collections import OrderedDict
import csv
from dataclasses import dataclass, field
import math
from pathlib import Path

from .packet import RTPPacket
from .payload import FrameReassembler, decode_fragment

CLOCK_RATE = 90_000
FRAME_FIELDS = "frame_id,rtp_ts,n_expected,n_received,complete,t_complete_rx_ns,t_playout_rx_ns,status".split(",")


class CsvLog:
    def __init__(self, path, fields):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("w", newline="", buffering=1)
        self.writer = csv.DictWriter(self.file, fieldnames=fields)
        self.writer.writeheader()

    def write(self, **row):
        self.writer.writerow(row)

    def close(self):
        self.file.close()


def unwrap32(value, reference):
    """Nearest extended timestamp; consecutive observations must be <2^31 apart."""
    return reference + ((value - reference + (1 << 31)) & 0xffffffff) - (1 << 31)


@dataclass
class _Frame:
    frame_id: int
    timestamp: int
    deadline: int
    reassembler: FrameReassembler = field(default_factory=FrameReassembler)
    sequences: set = field(default_factory=set)
    first_seq: int | None = None
    last_seq: int | None = None
    jpeg: bytes | None = None
    completed: int | None = None


class PlayoutBuffer:
    def __init__(self, delay_ms=100.0, *, late_window_ms=1000.0,
                 callback=None, on_row=None, max_frames=1024):
        if (not math.isfinite(delay_ms) or not math.isfinite(late_window_ms)
                or delay_ms < 0 or late_window_ms < 0 or max_frames < 1):
            raise ValueError("playout delays must be finite/nonnegative and max_frames positive")
        self.delay_ns = round(delay_ms * 1_000_000)
        self.late_window_ns = round(late_window_ms * 1_000_000)
        self.callback = callback or (lambda frame_id, rtp_ts, jpeg, t_complete_rx_ns: None)
        self.on_row = on_row or (lambda row: None)
        self.max_frames = max_frames
        self.frames = {}
        self.anchors = {}
        self.finalized = OrderedDict()

    def add(self, packet: RTPPacket, arrival_ns: int):
        fragment = decode_fragment(packet.payload)
        key = packet.ssrc, packet.timestamp
        if key in self.finalized:
            return
        if packet.ssrc not in self.anchors:
            self.anchors[packet.ssrc] = (packet.timestamp, arrival_ns, packet.timestamp)
        ts0, t0, reference = self.anchors[packet.ssrc]
        extended = unwrap32(packet.timestamp, reference)
        self.anchors[packet.ssrc] = (ts0, t0, max(reference, extended))
        deadline = t0 + (extended - ts0) * 1_000_000_000 // CLOCK_RATE + self.delay_ns
        # Reject ancient replay after its tombstone has aged out of the bounded cache.
        if key not in self.frames and arrival_ns > deadline + self.late_window_ns:
            return
        frame = self.frames.get(key)
        if frame is None:
            if len(self.frames) >= self.max_frames:
                oldest = min(self.frames, key=lambda k: self.frames[k].deadline)
                self._finish(oldest, arrival_ns)
            frame = self.frames[key] = _Frame(fragment.frame_id, packet.timestamp, deadline)
        if frame.frame_id != fragment.frame_id:
            raise ValueError("conflicting frame_id for one RTP timestamp")
        if frame.jpeg is not None:
            return
        # Leave an expired incomplete frame lost, even if its final packet arrives now.
        if arrival_ns > deadline + self.late_window_ns:
            self._finish(key, arrival_ns)
            return
        if fragment.flags & 1:
            frame.first_seq = packet.seq
        if packet.marker:
            frame.last_seq = packet.seq
        result = frame.reassembler.add(packet, arrival_ns / 1_000_000_000)
        frame.sequences.add(packet.seq)
        if result is not None:
            _, frame.jpeg = result
            frame.completed = arrival_ns
        self.advance(arrival_ns)

    def advance(self, now_ns):
        for key, frame in list(self.frames.items()):
            if ((frame.jpeg is not None and now_ns >= frame.deadline)
                    or now_ns >= frame.deadline + self.late_window_ns):
                self._finish(key, now_ns)

    def _finish(self, key, now_ns):
        frame = self.frames.pop(key)
        complete = frame.jpeg is not None
        status = "lost" if not complete else ("ok" if frame.completed <= frame.deadline else "late")
        expected = None
        if frame.first_seq is not None and frame.last_seq is not None:
            expected = ((frame.last_seq - frame.first_seq) & 0xffff) + 1
        self.finalized[key] = None
        if len(self.finalized) > 4096:
            self.finalized.popitem(last=False)
        self.on_row(dict(frame_id=frame.frame_id, rtp_ts=frame.timestamp,
                         n_expected=expected, n_received=len(frame.sequences), complete=int(complete),
                         t_complete_rx_ns=frame.completed, t_playout_rx_ns=frame.deadline, status=status))
        if status == "ok" and now_ns >= frame.deadline:
            self.callback(frame.frame_id, frame.timestamp, frame.jpeg, frame.completed)

    def next_deadline_ns(self):
        return min((f.deadline if f.jpeg is not None else f.deadline + self.late_window_ns
                    for f in self.frames.values()), default=None)

    def close(self, now_ns):
        """Finalize observed frames at session end; never invoke a callback early."""
        for key in list(self.frames):
            self._finish(key, now_ns)
