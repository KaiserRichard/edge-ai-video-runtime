"""ABR AIMD thresholds, hysteresis and application drop schedule."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rtp.abr import AimdController
from rtp.rtcp import ReportBlock
from rtp.sender import RTCP_FIELDS, Sender, parse_drop_steps
from rtp.sources import SyntheticSource


def test_step_down_multiplies_quality_and_reduces_resolution():
    abr = AimdController(80)
    decision = abr.update(13, 100)  # 13/256 > 5% loss
    assert decision.action == "down"
    assert decision.quality == 56
    assert decision.resolution_scale == 0.9
    assert decision.clean_reports == 0


def test_step_up_after_three_clean_reports():
    abr = AimdController(60)
    decisions = [abr.update(2, 100) for _ in range(3)]  # 2/256 < 1%
    assert [decision.action for decision in decisions] == ["hold", "hold", "up"]
    assert decisions[-1].quality == 65
    assert decisions[-1].resolution_scale == 1.0


def test_quality_floor_and_ceiling():
    abr = AimdController(21)
    assert abr.update(255, 10).quality == 20
    assert abr.update(255, 11).quality == 20
    abr = AimdController(90)
    for _ in range(3):
        decision = abr.update(0, 10)
    assert decision.quality == 95
    for _ in range(3):
        decision = abr.update(0, 10)
    assert decision.quality == 95


def test_hysteresis_requires_flat_or_falling_jitter_and_three_clean_reports():
    abr = AimdController(60)
    assert abr.update(2, 100).action == "hold"
    assert abr.update(2, 101).jitter_trend == "noise"  # small rise: still counts as clean
    abr.clean_reports = 1
    rising = abr.update(2, 300)
    assert rising.action == "hold_jitter"
    assert rising.clean_reports == 0
    assert abr.update(2, 290).action == "hold"
    assert abr.update(2, 290).action == "hold"
    recovered = abr.update(2, 289)
    assert recovered.action == "up"
    assert recovered.quality == 65


def test_loss_step_resets_recovery_counter_to_guard_oscillation():
    abr = AimdController(60)
    abr.update(2, 100)
    down = abr.update(13, 101)
    assert down.quality == 42
    assert down.clean_reports == 0
    assert abr.update(2, 100).action == "hold"
    assert abr.update(2, 100).action == "hold"
    assert abr.update(2, 100).action == "up"


def test_drop_step_parser():
    assert parse_drop_steps("0:0,20:0.05,40:0.15,60:0") == (
        (0.0, 0.0), (20.0, 0.05), (40.0, 0.15), (60.0, 0.0))
    for invalid in ("", "0:0,10:1.2", "2:0,1:0", "nan:0"):
        try:
            parse_drop_steps(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid drop schedule: {invalid}")


def test_sender_applies_rr_decision_before_next_synthetic_frame():
    class Log:
        def __init__(self):
            self.rows = []

        def write(self, **row):
            self.rows.append(row)

    source = SyntheticSource(quality=75)
    sender = Sender.__new__(Sender)
    sender.telemetry = None  # __new__ bypasses the optional observer default.
    sender.source = source
    sender.controller = AimdController(75)
    sender.base_dimensions = (source.width, source.height)
    sender.ssrc = 99
    sender.logs = {"rtcp": Log()}
    report = ReportBlock(99, 13, 1, 100, 10, 0, 0)

    sender._apply_decision(report, 1234)
    next_frame = source.read()

    assert next_frame.quality == 52
    assert source.width == round(320 * 0.9)
    assert source.height == round(240 * 0.9)
    row = sender.logs["rtcp"].rows[0]
    assert set(row) == set(RTCP_FIELDS)
    assert row["dir"] == "local" and row["type"] == "ABR"
