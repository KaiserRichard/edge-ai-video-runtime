"""RTP2 tests, including real UDP (never skipped when bind is unavailable).

Acceptance fixed BEFORE runs: seeded p=0.10 loss must be within +/-0.03
absolute with >=1,000 attempted packets; no-drop must be exactly lossless.
The in-memory cases validate application integration separately from UDP and
are not evidence for the loopback acceptance run.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import csv
from dataclasses import replace
import io
import os
from pathlib import Path
import random
import struct
import sys
import threading
import time

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rtp.payload import fragment_jpeg
from rtp.playout import FRAME_FIELDS, PlayoutBuffer
from rtp.receiver import RECEIVER_FIELDS, Receiver
from rtp.rtcp import SenderReport, ntp_from_monotonic, parse_compound
from rtp.sender import RESULT_FIELDS, RTCP_FIELDS, SENDER_FIELDS, Sender
from rtp.sources import (JpegDirectorySource, MjpegPipeSource, ShmSource,
                         SyntheticSource, _ring_layout, open_source)


def read_csv(path, fields):
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == fields
        return list(reader)


class MemoryNetwork:
    """Test-only datagram delivery. Explicitly not an OS UDP substitute in demos."""
    def __init__(self):
        self.sockets = {}
        self.next_port = 42000

    def pair(self, host, port):
        if not port:
            port = self.next_port
            self.next_port += 2
        return self.Socket(self, port), self.Socket(self, port + 1)

    class Socket:
        def __init__(self, network, port):
            self.network = network
            self.address = ("127.0.0.1", port)
            self.queue = deque()
            network.sockets[self.address] = self

        def getsockname(self):
            return self.address

        def sendto(self, data, destination):
            peer = self.network.sockets.get(destination)
            if peer is not None:
                peer.queue.append((data, self.address))
            return len(data)

        def recvfrom(self, size):
            try:
                return self.queue.popleft()
            except IndexError:
                raise BlockingIOError from None

        def close(self):
            self.network.sockets.pop(self.address, None)

    @staticmethod
    def select(readers, writers, errors, timeout):
        end = time.monotonic() + timeout
        while True:
            ready = [s for s in readers if s.queue]
            if ready or time.monotonic() >= end:
                return ready, [], []
            time.sleep(min(0.0005, max(0, end - time.monotonic())))


@pytest.fixture
def memory_network(monkeypatch):
    network = MemoryNetwork()
    monkeypatch.setattr("rtp.sender.open_udp_pair", network.pair)
    monkeypatch.setattr("rtp.receiver.open_udp_pair", network.pair)
    monkeypatch.setattr("select.select", network.select)
    return network


@pytest.mark.parametrize("transport", ["memory", "udp"])
@pytest.mark.parametrize("drop_prob", [0.0, 0.10])
def test_loopback_loss_rtcp_airs_and_csv(tmp_path, request, transport, drop_prob):
    if transport == "memory":
        request.getfixturevalue("memory_network")
    rx = Receiver(tmp_path / "receiver", port=0, playout_ms=50,
                  late_window_ms=100, rtcp_interval=0.1)
    tx = None
    stop = threading.Event()
    delivered = []

    def callback(frame_id, rtp_ts, jpeg, completed):
        with Image.open(io.BytesIO(jpeg)) as image:
            image.load()
            assert image.size == (320, 240)
        delivered.append(frame_id)
        rx.send_result(rtp_ts, frame_id, 42, 230, time.monotonic_ns() // 1000)

    rx.playout.callback = callback
    try:
        tx = Sender(SyntheticSource(), tmp_path / "sender", port=rx.port,
            fps=60, mtu_payload=200, drop_prob=drop_prob, seed=7, rtcp_interval=0.1,
            ssrc=123, seq_start=65000, timestamp_offset=0)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(rx.run, 5, stop_event=stop)
            try:
                tx.run(1.5, drain_seconds=0.4)
            finally:
                stop.set()
                future.result(timeout=3)
    finally:
        if tx is not None:
            tx.close()
        rx.close()
    sent = read_csv(tmp_path / "sender/sender.csv", SENDER_FIELDS)
    received = read_csv(tmp_path / "receiver/receiver.csv", RECEIVER_FIELDS)
    frames = read_csv(tmp_path / "receiver/frames_rx.csv", FRAME_FIELDS)
    control = read_csv(tmp_path / "sender/rtcp.csv", RTCP_FIELDS)
    rx_control = read_csv(tmp_path / "receiver/rtcp.csv", RTCP_FIELDS)
    results = read_csv(tmp_path / "sender/results_tx.csv", RESULT_FIELDS)
    n = sum(int(row["n_pkts"]) for row in sent)
    assert n >= 1000
    loss = 1 - len(received) / n
    assert abs(loss - drop_prob) <= 0.03
    rng = random.Random(7)
    expected_received = sum(rng.random() >= drop_prob for _ in range(n))
    assert len(received) == expected_received  # no additional loopback losses
    assert len({row["frame_id"] for row in frames}) == len(frames)
    assert {row["status"] for row in frames} <= {"ok", "late", "lost"}
    if not drop_prob:
        assert loss == 0
        assert len(sent) == len(frames) == len(results)
        assert all(row["status"] == "ok" for row in frames)
    else:
        assert any(row["status"] == "lost" for row in frames)
    reports = [row for row in control if row["type"] == "RR" and row["cum_lost"]]
    assert reports and any(row["rtt_ms"] for row in reports)
    assert all(float(row["rtt_ms"]) >= 0 for row in reports if row["rtt_ms"])
    # Full-session comparison uses receiver statistics, with RFC probation edges.
    stats = rx.stats.sources[123]
    assert abs(stats.cumulative_lost / stats.expected - drop_prob) <= 0.03
    assert any(row["type"] == "SR" and row["dir"] == "rx" for row in rx_control)
    assert any(row["type"] == "RR" and int(row["dlsr"] or 0) > 0 for row in rx_control)
    assert any(row["type"] == "BYE" for row in control)
    assert {int(row["frame_id"]) for row in results} == set(delivered)
    captures = {(row["frame_id"], row["rtp_ts"]): row["t_capture_mono_ns"] for row in sent}
    for row in results:
        assert row["t_capture_mono_ns"] == captures[row["frame_id"], row["rtp_ts"]]
        assert int(row["t_result_rx_mono_ns"]) >= int(row["t_capture_mono_ns"])
        assert row["class_id"] == "42"
    for row in sent:
        assert int(row["rtp_ts"]) == (int(row["t_capture_mono_ns"]) * 90000 // 10**9) & 0xffffffff
        assert int(row["t_capture_mono_ns"]) <= int(row["t_send_first_mono_ns"]) <= int(row["t_send_last_mono_ns"])
    elapsed = (int(sent[-1]["t_capture_mono_ns"]) - int(sent[0]["t_capture_mono_ns"])) / 1e9
    assert 1.3 <= elapsed < 1.6
    print(f"transport={transport} attempted={n} received={len(received)} loss={loss:.6f}; evidence={tmp_path}")


def make_frame(frame_id=1, ts=0, seq=65534):
    return fragment_jpeg(bytes(range(64)), frame_id, 24, seq_start=seq, rtp_ts=ts, ssrc=1)


def test_playout_reorders_deduplicates_wraps_and_delivers_at_deadline():
    rows, callbacks = [], []
    buffer = PlayoutBuffer(100, on_row=rows.append, callback=lambda *args: callbacks.append(args))
    t0, ts0 = 1_000_000_000, 0xfffff000
    packets = make_frame(ts=ts0)
    for i, packet in enumerate([packets[-1], packets[0], packets[0], *packets[1:-1]]):
        buffer.add(packet, t0 + i * 1_000_000)
    assert not rows and not callbacks
    buffer.advance(t0 + 100_000_000)
    assert len(rows) == len(callbacks) == 1
    assert rows[0] == dict(frame_id=1, rtp_ts=ts0, n_expected=5, n_received=5, complete=1,
                          t_complete_rx_ns=t0 + 5_000_000, t_playout_rx_ns=t0 + 100_000_000, status="ok")
    assert callbacks[0] == (1, ts0, bytes(range(64)), t0 + 5_000_000)
    for packet in packets:
        buffer.add(packet, t0 + 110_000_000)
    next_packets = make_frame(2, (ts0 + 9000) & 0xffffffff, 3)
    for packet in next_packets:
        buffer.add(packet, t0 + 120_000_000)
    buffer.advance(t0 + 199_999_999)
    assert len(rows) == 1
    buffer.advance(t0 + 200_000_000)
    assert len(rows) == 2 and rows[-1]["t_playout_rx_ns"] == t0 + 200_000_000


def test_playout_late_lost_unknown_endpoints_and_shutdown():
    rows, callbacks = [], []
    buffer = PlayoutBuffer(10, late_window_ms=20, on_row=rows.append,
                           callback=lambda *args: callbacks.append(args))
    packets = make_frame()
    for packet in packets[:-1]:
        buffer.add(packet, 0)
    buffer.advance(10_000_000)
    assert not rows
    buffer.add(packets[-1], 15_000_000)
    assert rows[-1]["status"] == "late" and rows[-1]["complete"] == 1
    assert not callbacks
    missing_middle = make_frame(2, 9000, 10)
    for packet in missing_middle[:2] + missing_middle[3:]:
        buffer.add(packet, 100_000_000)
    buffer.advance(130_000_000)
    assert rows[-1]["status"] == "lost" and rows[-1]["n_expected"] == 5
    assert rows[-1]["n_received"] == 4 and rows[-1]["t_complete_rx_ns"] is None
    buffer.add(missing_middle[2], 140_000_000)
    assert len(rows) == 2
    for packet in make_frame(3, 18000, 20)[1:-1]:
        buffer.add(packet, 200_000_000)
    buffer.close(201_000_000)
    assert rows[-1]["status"] == "lost" and rows[-1]["n_expected"] is None
    assert not buffer.frames


def test_playout_expires_without_future_packets_and_bounds_pending_frames():
    rows = []
    buffer = PlayoutBuffer(10, late_window_ms=10, on_row=rows.append, max_frames=2)
    for frame_id in range(3):
        buffer.add(make_frame(frame_id, frame_id * 900, frame_id * 5)[0], frame_id * 1_000_000)
    assert len(buffer.frames) == 2 and len(rows) == 1
    buffer.advance(100_000_000)
    assert len(rows) == 3 and all(row["status"] == "lost" for row in rows)
    assert not buffer.frames


def test_sources_synthetic_quality_numbered_frames_and_jpegdir(tmp_path):
    source = SyntheticSource(160, 120, 40)
    a, b = source.read(), source.read()
    assert (a.frame_id, b.frame_id, a.quality) == (0, 1, 40)
    assert a.jpeg != b.jpeg and a.t_capture_mono_ns < b.t_capture_mono_ns
    with Image.open(io.BytesIO(a.jpeg)) as image:
        assert image.size == (160, 120)
        assert image.quantization != Image.open(io.BytesIO(SyntheticSource(160, 120, 90).read().jpeg)).quantization
    (tmp_path / "a.JPG").write_bytes(a.jpeg)
    (tmp_path / "b.jpeg").write_bytes(b.jpeg)
    replay = open_source("jpegdir", jpeg_dir=tmp_path)
    frames = [replay.read() for _ in range(3)]
    assert [f.jpeg for f in frames] == [a.jpeg, b.jpeg, a.jpeg]
    assert [f.frame_id for f in frames] == [0, 1, 2]
    assert all(f.quality is None for f in frames)
    source.close()
    replay.close()


def test_mjpeg_pipe_chunk_boundaries_multiple_frames_eof_and_truncation():
    a = SyntheticSource(32, 32).read().jpeg
    class Chunks(io.BytesIO):
        def read(self, size=-1):
            return super().read(7)
    source = MjpegPipeSource(Chunks(b"noise" + a + a))
    assert source.read().jpeg == a
    assert source.read().frame_id == 1
    with pytest.raises(EOFError):
        source.read()
    with pytest.raises(ValueError, match="truncated"):
        MjpegPipeSource(io.BytesIO(a[:-2])).read()
    source.close()


def test_mjpeg_real_pipe_waits_are_bounded_and_leave_input_owned_by_caller():
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd, "rb", buffering=0) as stream:
            source = MjpegPipeSource(stream)
            start = time.monotonic()
            assert source.read(timeout=0.02) is None
            assert time.monotonic() - start < 0.3
            jpeg = SyntheticSource(32, 32).read().jpeg
            os.write(write_fd, jpeg[:10])
            assert source.read(timeout=0.01) is None
            os.write(write_fd, jpeg[10:] + jpeg)
            assert source.read(timeout=0.1).jpeg == jpeg
            assert source.read(timeout=0.1).jpeg == jpeg
            source.close()
            assert not stream.closed
    finally:
        os.close(write_fd)


def test_source_validation_and_guarded_shm(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        SyntheticSource(quality=0)
    with pytest.raises(ValueError):
        JpegDirectorySource(tmp_path)
    with pytest.raises(ValueError):
        open_source("jpegdir")
    with pytest.raises(ValueError):
        open_source("unknown")
    with pytest.raises(ValueError):
        ShmSource("../bad")
    monkeypatch.delenv("HEA_CAM_READER_LIB", raising=False)
    with pytest.raises(RuntimeError, match="HEA_CAM_READER_LIB"):
        open_source("shm:camera")
    header = struct.pack("<8I32x", 0x43414548, 1, 2, 2, 4, 12, 64, 1)
    assert _ring_layout(header, 320) == (2, 2, 4, 12, 64)
    for index, bad_value in [(0, 0), (1, 2), (2, 4097), (4, 65), (5, 13), (6, 65), (7, 0)]:
        bad = bytearray(header)
        struct.pack_into("<I", bad, index * 4, bad_value)
        with pytest.raises(ValueError):
            _ring_layout(bad, 320)
    with pytest.raises(ValueError):
        _ring_layout(header, 319)


def test_sender_rejects_unknown_and_duplicate_airs(tmp_path, memory_network):
    rx = Receiver(tmp_path / "rx", port=0)
    tx = Sender(SyntheticSource(), tmp_path / "tx", port=rx.port)
    try:
        frame = tx.source.read()
        tx.send_frame(frame)
        rx.receive_rtp()
        timestamp = tx.timestamp(frame.t_capture_mono_ns)
        rx.send_result(timestamp, frame.frame_id + 1, 4, 200, 123)
        rx.send_result((timestamp + 1) & 0xffffffff, frame.frame_id, 4, 200, 123)
        rx.send_result(timestamp, frame.frame_id, 4, 200, 123)
        rx.send_result(timestamp, frame.frame_id, 4, 200, 123)
        tx.receive_control()
    finally:
        tx.close()
        rx.close()
    rows = read_csv(tmp_path / "tx/results_tx.csv", RESULT_FIELDS)
    assert len(rows) == 1 and rows[0]["frame_id"] == str(frame.frame_id)


def test_sender_report_clock_and_counts_with_total_loss(tmp_path, memory_network, monkeypatch):
    rx = Receiver(tmp_path / "rx", port=0)
    tx = Sender(SyntheticSource(), tmp_path / "tx", port=rx.port, drop_prob=1,
                ssrc=123, seq_start=65534, timestamp_offset=456)
    try:
        frame = tx.source.read()
        tx.send_frame(frame)
        assert not rx.rtp.queue
        now = frame.t_capture_mono_ns + 1_000_000_000
        monkeypatch.setattr("rtp.sender.time.monotonic_ns", lambda: now)
        tx.send_report()
        wire, _ = rx.rtcp.recvfrom(65535)
        report = parse_compound(wire)[0]
        expected = fragment_jpeg(frame.jpeg, frame.frame_id, 1200)
        assert isinstance(report, SenderReport)
        assert report.packet_count == len(expected)
        assert report.octet_count == sum(len(packet.payload) for packet in expected)
        assert report.rtp_timestamp == tx.timestamp(now)
        assert report.ntp_timestamp == ntp_from_monotonic(now, tx.mapping_mono, tx.mapping_wall)
    finally:
        rx.close()
        tx.close()


def test_receiver_wrap_jitter_malformed_and_foreign_peer(tmp_path, memory_network, monkeypatch):
    rx = Receiver(tmp_path / "rx", port=0, playout_ms=0)
    tx = Sender(SyntheticSource(), tmp_path / "tx", port=rx.port, seq_start=1)
    try:
        tx.rtp.sendto(b"invalid", tx.destination)
        rx.receive_rtp()
        assert rx.malformed == 1
        t0 = 1_000_000_000
        timestamps = [0xfffffff0, (0xfffffff0 + 9000) & 0xffffffff]
        for i, timestamp in enumerate(timestamps):
            monkeypatch.setattr("rtp.receiver.time.monotonic_ns", lambda i=i: t0 + i * 100_000_000)
            packet = fragment_jpeg(b"abc", i, 100, seq_start=i + 1, rtp_ts=timestamp, ssrc=tx.ssrc)[0]
            tx.rtp.sendto(packet.pack(), tx.destination)
            rx.receive_rtp()
        assert rx.stats.sources[tx.ssrc].jitter == 0
        alien, alien_control = memory_network.pair("127.0.0.1", 0)
        alien.sendto(packet.pack(), tx.destination)
        tx.rtp.sendto(replace(packet, payload_type=97).pack(), tx.destination)
        rx.receive_rtp()
        assert rx.packet_count == 2
        tx.rtcp.sendto(b"bad control", tx.control_destination)
        rx.receive_control()
        assert rx.malformed == 2
        alien.close()
        alien_control.close()
    finally:
        rx.close()
        tx.close()


def test_sender_pipe_eof_and_stalled_input_are_bounded(tmp_path, memory_network):
    tx = Sender(MjpegPipeSource(io.BytesIO()), tmp_path / "empty", port=5004)
    try:
        start = time.monotonic()
        assert tx.run(10, drain_seconds=0) == 0
        assert time.monotonic() - start < 0.2
    finally:
        tx.close()
    class IdleSource:
        def read(self, timeout=0):
            return None
        def close(self):
            pass
    tx = Sender(IdleSource(), tmp_path / "idle", port=5004, rtcp_interval=0.02)
    try:
        start = time.monotonic()
        assert tx.run(0.08, drain_seconds=0) == 0
        assert time.monotonic() - start < 0.3
    finally:
        tx.close()
    rows = read_csv(tmp_path / "idle/rtcp.csv", RTCP_FIELDS)
    assert sum(row["type"] == "SR" for row in rows) >= 3
