"""Small RTCP receiver-report AIMD controller for JPEG senders.

Loss thresholds follow the ABR design. A rising jitter report pauses additive
recovery; three low-loss reports with flat or falling jitter are required.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    quality: int
    action: str
    clean_reports: int
    jitter_trend: str
    resolution_scale: float


class AimdController:
    """AIMD JPEG quality controller with a conservative resolution companion."""

    def __init__(self, quality: int, *, floor: int = 20, ceiling: int = 95,
                 resolution_scale: float = 1.0):
        if not 1 <= floor <= quality <= ceiling <= 95:
            raise ValueError("quality must be between floor and ceiling, within 1..95")
        if not 0.5 <= resolution_scale <= 1.0:
            raise ValueError("resolution_scale must be in 0.5..1.0")
        self.quality = quality
        self.floor, self.ceiling = floor, ceiling
        self.resolution_scale = resolution_scale
        self.clean_reports = 0
        self.last_jitter: int | None = None

    def update(self, fraction_lost: int, jitter: int) -> Decision:
        if not 0 <= fraction_lost <= 255 or jitter < 0:
            raise ValueError("invalid RR loss fraction or jitter")
        # A rise counts only if it is clear of RR-to-RR noise: >= 1.5x and >= 1 ms (90 ticks).
        trend = ("initial" if self.last_jitter is None else
                 "rising" if (jitter >= 1.5 * self.last_jitter and
                              jitter - self.last_jitter >= 90) else
                 "noise" if jitter > self.last_jitter else
                 "falling" if jitter < self.last_jitter else "flat")
        self.last_jitter = jitter
        old_quality = self.quality
        old_scale = self.resolution_scale

        if fraction_lost > 0.05 * 256:
            self.clean_reports = 0
            self.quality = max(self.floor, int(self.quality * 0.7))
            self.resolution_scale = max(0.5, round(self.resolution_scale * 0.9, 3))
            action = "down" if self.quality < old_quality or self.resolution_scale < old_scale else "hold"
        elif fraction_lost < 0.01 * 256:
            if trend == "rising":
                self.clean_reports = 0
                action = "hold_jitter"
            else:
                self.clean_reports += 1
                if self.clean_reports >= 3:
                    self.quality = min(self.ceiling, self.quality + 5)
                    self.resolution_scale = min(1.0, round(self.resolution_scale + 0.05, 3))
                    self.clean_reports = 0
                    action = "up" if (self.quality > old_quality or
                                      self.resolution_scale > old_scale) else "hold"
                else:
                    action = "hold"
        else:
            self.clean_reports = 0
            action = "hold"

        return Decision(self.quality, action, self.clean_reports, trend,
                        self.resolution_scale)
