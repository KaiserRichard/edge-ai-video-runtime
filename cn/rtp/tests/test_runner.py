from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))

import run_scenario
import tshark_check
from netem import netem_remove, netem_replace


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("config_path", sorted((ROOT / "configs").glob("CN-T*.yaml")))
def test_every_scenario_has_complete_dry_run_command_plan(config_path, capsys):
    config = run_scenario.load_config(config_path)
    commands = run_scenario.plan(config, output=Path("/tmp/net1-dry-run"))
    run_scenario.execute(config, commands, output=Path("/tmp/net1-dry-run"), dry_run=True)
    output = capsys.readouterr().out
    assert "tcpdump -i any -s 128" in output
    assert "git_hash" in output or "git" in output
    assert "trap cleanup EXIT INT TERM" in output
    assert "vcgencmd" in output and "iw" in output
    assert "python -m rtp.sender" in output
    assert "python -m rtp.receiver" in output
    assert "python -m rtp.ai" in output
    assert "meta.json" in output


def test_netem_command_validation():
    assert netem_replace("wlan0", "loss 5%") == "tc qdisc replace dev wlan0 root netem loss 5%"
    assert "qdisc del dev wlan0 root" in netem_remove("wlan0")
    with pytest.raises(ValueError):
        netem_replace("eth0", "loss 1%; rm -rf /")


def test_tshark_check_validates_cn_t1(monkeypatch, tmp_path):
    calls = []

    def fake_fields(tshark, pcap, decode, display_filter, fields):
        calls.append(display_filter)
        if display_filter == "rtp":
            return [["10", "0", "0", "123"], ["11", "0", "1", "123"],
                    ["12", "6000", "1", "123"]]
        if display_filter == "rtcp":
            return [["200"], ["201"]]
        return []

    monkeypatch.setattr(tshark_check.shutil, "which", lambda _: "/usr/bin/tshark")
    monkeypatch.setattr(tshark_check, "_fields", fake_fields)
    report = tshark_check.check_pcap(tmp_path / "demo.pcap")
    assert report["passed"]
    assert report["rtp_packets"] == 3
    assert report["rtcp_packets"] == 2
    assert calls == ["rtp", "rtcp", "_ws.malformed"]


def test_tshark_check_detects_invalid_marker_and_sequence(monkeypatch, tmp_path):
    values = iter([
        [["1", "0", "1", "8"], ["3", "0", "0", "8"]],
        [["200"]],
        [],
    ])
    monkeypatch.setattr(tshark_check.shutil, "which", lambda _: "/usr/bin/tshark")
    monkeypatch.setattr(tshark_check, "_fields", lambda *args: next(values))
    report = tshark_check.check_pcap(tmp_path / "demo.pcap")
    assert not report["passed"]
    assert not report["checks"]["sequence_contiguous"]
    assert not report["checks"]["marker_last_only"]
