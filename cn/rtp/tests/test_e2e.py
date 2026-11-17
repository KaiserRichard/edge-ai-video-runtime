"""In-memory end-to-end handoff through RTP reassembly, EdgeAI, and AIRS."""

import csv
from pathlib import Path
import sys
import time

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_loopback import MemoryNetwork

from rtp.edge_ai import EdgeAI
from rtp.receiver import Receiver
from rtp.sender import Sender
from rtp.sources import SyntheticSource


def test_sender_receiver_ai_airs_share_one_run_directory(tmp_path, monkeypatch):
    network = MemoryNetwork()
    monkeypatch.setattr("rtp.sender.open_udp_pair", network.pair)
    monkeypatch.setattr("rtp.receiver.open_udp_pair", network.pair)
    rx = Receiver(tmp_path, port=5004, playout_ms=0, late_window_ms=100)
    source = SyntheticSource(width=32, height=24)
    tx = Sender(source, tmp_path, port=rx.port, ssrc=123, seq_start=1,
                timestamp_offset=0, rtcp_filename="sender_rtcp.csv")
    ai = EdgeAI("fifo", "synthetic", 1, rx.send_result, service_ms=0,
                ai_csv=tmp_path / "ai.csv")
    rx.playout.callback = ai.submit
    try:
        tx.send_frame(source.read())
        rx.receive_rtp()
        rx.playout.advance(time.monotonic_ns() + 1_000_000)
        deadline = time.monotonic() + 1
        while not (tmp_path / "results_tx.csv").exists() or time.monotonic() < deadline:
            tx.receive_control()
            if deadline - time.monotonic() < 0:
                break
            time.sleep(0.001)
    finally:
        ai.close()
        rx.close()
        tx.close()
    with (tmp_path / "results_tx.csv").open(newline="") as f:
        results = list(csv.DictReader(f))
    with (tmp_path / "ai.csv").open(newline="") as f:
        ai_rows = list(csv.DictReader(f))
    assert len(results) == 1
    assert results[0]["frame_id"] == "0"
    assert len(ai_rows) == 1 and ai_rows[0]["status"] == "ok"
    for name in ("sender.csv", "receiver.csv", "frames_rx.csv", "results_tx.csv", "ai.csv"):
        assert (tmp_path / name).is_file()
