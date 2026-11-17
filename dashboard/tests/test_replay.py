import asyncio
import csv
import math

import pytest

from dashboard.hub import Hub
from dashboard.replay import identify, load_replay, play


def write(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields.split(","))
        writer.writeheader()
        writer.writerows(rows)


def make_run(path):
    # Deliberately unrelated receiver and Pi clock epochs; total must be 80 ms.
    write(path / "receiver.csv", "seq,rtp_ts,frame_id,marker,bytes,t_arrival_rx_ns,transit_ts_units,jitter_ts_units", [
        dict(seq=65535, rtp_ts=3000, frame_id=1, marker=1, bytes=1212, t_arrival_rx_ns=9_000_000_000_000, transit_ts_units=0, jitter_ts_units=90),
        dict(seq=1, rtp_ts=6000, frame_id=2, marker=1, bytes=1212, t_arrival_rx_ns=9_000_033_333_333, transit_ts_units=0, jitter_ts_units=180)])
    write(path / "frames_rx.csv", "frame_id,rtp_ts,n_expected,n_received,complete,t_complete_rx_ns,t_playout_rx_ns,status", [
        dict(frame_id=1, rtp_ts=3000, n_expected=1, n_received=1, complete=1, t_complete_rx_ns=9_000_001_000_000, t_playout_rx_ns=9_000_050_000_000, status="ok")])
    write(path / "sender.csv", "frame_id,rtp_ts,seq_first,seq_last,n_pkts,bytes,quality,t_capture_mono_ns,t_send_first_mono_ns,t_send_last_mono_ns", [
        dict(frame_id=1, rtp_ts=3000, seq_first=65535, seq_last=65535, n_pkts=1, bytes=1212, quality="", t_capture_mono_ns=1_000_000_000, t_send_first_mono_ns=1_001_000_000, t_send_last_mono_ns=1_004_000_000)])
    write(path / "results_tx.csv", "frame_id,rtp_ts,t_capture_mono_ns,t_result_rx_mono_ns,class_id", [
        dict(frame_id=1, rtp_ts=3000, t_capture_mono_ns=1_000_000_000, t_result_rx_mono_ns=1_080_000_000, class_id=281)])
    write(path / "ai.csv", "frame_id,rtp_ts,policy,t_enqueue_rx_ns,t_start_rx_ns,t_done_rx_ns,class_id,confidence,status", [
        dict(frame_id=1, rtp_ts=3000, policy="latest", t_enqueue_rx_ns=9_000_050_000_000, t_start_rx_ns=9_000_051_000_000, t_done_rx_ns=9_000_063_000_000, class_id=281, confidence=.8, status="ok"),
        dict(frame_id=2, rtp_ts=6000, policy="latest", t_enqueue_rx_ns=9_000_100_000_000, t_start_rx_ns="", t_done_rx_ns="", class_id="", confidence="", status="skipped")])
    write(path / "receiver_rtcp.csv", "t_mono_ns,dir,type,ssrc,fraction_lost,cum_lost,ext_high_seq,jitter,lsr,dlsr,rtt_ms", [
        dict(t_mono_ns=9_001_000_000_000, dir="tx", type="RR", ssrc=123, fraction_lost=13, cum_lost=1, ext_high_seq=65537, jitter=90, lsr=0, dlsr=0, rtt_ms="")])


def test_real_headers_clock_domains_and_units(tmp_path):
    make_run(tmp_path)
    events = load_replay(tmp_path)
    assert all(a["time_s"] <= b["time_s"] for a, b in zip(events, events[1:]))
    assert events[-1]["time_s"] < 2  # not a ~9000-second clock jump
    result = next(e["data"] for e in events if e["type"] == "result")
    assert result["latency_ms"] == 80
    assert result["capture_send_ms"] == 4
    assert result["queue_ms"] == 1
    assert result["inference_ms"] == 12
    assert result["network_playout_ms"] == 63
    packet = next(e["data"] for e in events if e["type"] == "packet")
    assert packet["jitter_ms"] == 1
    frame = next(e["data"] for e in events if e["type"] == "frame")
    assert frame["arrival_offset_ms"] == -49
    assert "buffer_frames" not in frame
    assert len([e for e in events if e["type"] == "ai"]) == 1
    sender = next(e["data"] for e in events if e["type"] == "sender")
    assert "quality" not in sender
    rr = next(e["data"] for e in events if e["type"] == "rtcp")
    assert rr["fraction_lost"] == 13
    assert rr["jitter_ms"] == 1
    assert "rtt_ms" not in rr


def test_bad_rows_skipped_with_location(tmp_path):
    make_run(tmp_path)
    with (tmp_path / "receiver.csv").open("a") as f:
        f.write("not-a-seq,0,0,1,100,9001000000000,0,0\n")
    with pytest.warns(UserWarning, match="receiver.csv:4"):
        assert load_replay(tmp_path)


def test_os_replay_contract(tmp_path):
    write(tmp_path / "os.csv", "time_s,state,fifo_age_ms,latest_age_ms,inference_ms,condition,fault,temperature_c,throttled,cpu_cores", [
        dict(time_s=10, state="FAILSAFE", fifo_age_ms=400, latest_age_ms=90, inference_ms=82, condition="stress-P1", fault="bridge stopped", temperature_c=61, throttled="0x0", cpu_cores="10;20;30;40")])
    events = load_replay(tmp_path)
    assert {e["profile"] for e in events} == {"os"}
    assert next(e["data"] for e in events if e["type"] == "hardware")["cpu_cores"] == [10, 20, 30, 40]
    assert events[0]["time_s"] == 0


def test_unknown_or_empty_inputs_fail(tmp_path):
    with pytest.raises(ValueError, match="no CSV"):
        load_replay(tmp_path)
    (tmp_path / "bad.csv").write_text("unknown\nfoo\n")
    with pytest.warns(UserWarning), pytest.raises(ValueError, match="no usable"):
        load_replay(tmp_path)
    with pytest.raises(ValueError):
        identify(["a"])


def test_replay_finishes_and_preserves_order(tmp_path):
    make_run(tmp_path)
    hub = Hub("replay")
    asyncio.run(play(hub, load_replay(tmp_path), speed=10000))
    assert hub.status == "replay complete"
    assert hub.stats["accepted"] == len(hub.history)
    assert [e["id"] for e in hub.history] == list(range(1, len(hub.history) + 1))
    with pytest.raises(ValueError):
        asyncio.run(play(hub, [], math.nan))


def test_packaged_real_sample():
    events = load_replay("samples/cn-loss5")
    kinds = {e["type"] for e in events}
    assert {"packet", "frame", "ai", "result", "sender", "rtcp"} <= kinds
    assert all(e["time_s"] >= 0 for e in events)
