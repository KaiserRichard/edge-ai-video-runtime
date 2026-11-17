"""Per-SSRC RTP receiver statistics from RFC 3550 Appendix A.1/A.3 and A.8."""

from dataclasses import dataclass

RTP_CLOCK_RATE = 90_000
RTP_SEQ_MOD = 1 << 16
MAX_DROPOUT = 3000
MAX_MISORDER = 100
MIN_SEQUENTIAL = 2


@dataclass(frozen=True)
class ReceptionReport:
    ssrc: int
    fraction_lost: int
    cumulative_lost: int
    extended_highest_seq: int
    jitter: int
    expected: int
    received: int


class SourceStats:
    """Sequence validation and RFC 3550 jitter state for one RTP source."""
    def __init__(self, ssrc: int = 0, clock_rate: int = RTP_CLOCK_RATE):
        if clock_rate <= 0:
            raise ValueError("clock_rate must be positive")
        self.ssrc = ssrc
        self.clock_rate = clock_rate
        self.probation = MIN_SEQUENTIAL
        self.max_seq = 0
        self.base_seq = 0
        self.bad_seq = RTP_SEQ_MOD + 1
        self.cycles = 0
        self.received = 0
        self.jitter = 0.0
        self.transit = None
        self._expected_prior = 0
        self._received_prior = 0

    def _init_seq(self, seq: int) -> None:
        self.base_seq = seq
        self.max_seq = seq
        self.bad_seq = RTP_SEQ_MOD + 1
        self.cycles = 0
        self.received = 0
        self._expected_prior = 0
        self._received_prior = 0

    def _update_seq(self, seq: int) -> bool:
        if self.probation:
            if seq == ((self.max_seq + 1) & 0xffff):
                self.max_seq = seq
                self.probation -= 1
                if self.probation == 0:
                    self._init_seq(seq)
                    self.received += 1
                    return True
            else:
                self.probation = MIN_SEQUENTIAL - 1
                self.max_seq = seq
            return False

        delta = (seq - self.max_seq) & 0xffff
        if delta < MAX_DROPOUT:
            if seq < self.max_seq:
                self.cycles += RTP_SEQ_MOD
            self.max_seq = seq
        elif delta <= RTP_SEQ_MOD - MAX_MISORDER:
            if seq == self.bad_seq:
                self._init_seq(seq)
            else:
                self.bad_seq = (seq + 1) & 0xffff
                return False
        # Else packet is reordered/duplicate within the accepted window.
        self.received += 1
        return True

    @property
    def extended_highest_seq(self) -> int:
        return self.cycles + self.max_seq

    @property
    def expected(self) -> int:
        return self.extended_highest_seq - self.base_seq + 1 if self.received else 0

    @property
    def cumulative_lost(self) -> int:
        return max(-(1 << 23), min((1 << 23) - 1, self.expected - self.received))

    def update(self, seq: int, rtp_ts: int, arrival_ns: int) -> bool:
        """Observe a packet; return whether sequence validation accepted it."""
        if not 0 <= seq <= 0xffff or not 0 <= rtp_ts <= 0xffffffff:
            raise ValueError("seq or RTP timestamp out of range")
        accepted = self._update_seq(seq)
        arrival_ts = (arrival_ns * self.clock_rate) // 1_000_000_000
        transit = arrival_ts - rtp_ts
        if self.transit is not None:
            difference = abs(transit - self.transit)
            # RFC 3550 section 6.4.1 and Appendix A.8: J += (|D| - J) / 16.
            self.jitter += (difference - self.jitter) / 16.0
        self.transit = transit
        return accepted

    def report(self, *, interval: bool = True) -> ReceptionReport:
        expected = self.expected
        lost = self.cumulative_lost
        fraction = 0
        if interval:
            expected_interval = expected - self._expected_prior
            received_interval = self.received - self._received_prior
            lost_interval = expected_interval - received_interval
            if expected_interval > 0 and lost_interval > 0:
                fraction = min(255, (lost_interval << 8) // expected_interval)
            self._expected_prior = expected
            self._received_prior = self.received
        return ReceptionReport(self.ssrc, fraction, lost, self.extended_highest_seq,
                               int(self.jitter), expected, self.received)

    def snapshot(self, *, interval: bool = True) -> ReceptionReport:
        return self.report(interval=interval)


class ReceiverStats:
    """Container for independent per-SSRC statistics."""
    def __init__(self, clock_rate: int = RTP_CLOCK_RATE):
        self.clock_rate = clock_rate
        self.sources = {}

    def update(self, ssrc: int, seq: int, rtp_ts: int, arrival_ns: int) -> bool:
        source = self.sources.setdefault(ssrc, SourceStats(ssrc, self.clock_rate))
        return source.update(seq, rtp_ts, arrival_ns)

    def report(self, ssrc: int, *, interval: bool = True) -> ReceptionReport:
        return self.sources[ssrc].report(interval=interval)
