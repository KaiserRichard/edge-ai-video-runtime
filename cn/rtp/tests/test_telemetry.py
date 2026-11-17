"""Telemetry regressions, using the dashboard's authoritative schema."""
import argparse
import io
import json
import os
from pathlib import Path
import queue
import socket
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.environ.get('DASHBOARD_ROOT', str(ROOT.parents[1] / 'dashboard')))
from dashboard.schema import decode, validate
from rtp.telemetry import Emitter, add_arguments, from_arguments
from rtp.sender import Sender, log_rtcp
from rtp.receiver import Receiver
from rtp.rtcp import AppAirs, ReceiverReport, ReportBlock
from tools.telemetry_e2e import run


class Sink:
    def __init__(self):
        self.events = []
    def emit(self, kind, data):
        self.events.append((kind, data))


class Log:
    def write(self, **row):
        pass


def test_cli_off_and_required_session():
    parser = argparse.ArgumentParser()
    add_arguments(parser, 5006)
    args = parser.parse_args([])
    assert from_arguments(args, parser, 'pi') is None
    for arguments in (['--telemetry', '127.0.0.1'],
                      ['--telemetry', '127.0.0.1', '--telemetry-session', 'x', '--telemetry-port', '0']):
        with pytest.raises(SystemExit):
            from_arguments(parser.parse_args(arguments), parser, 'pi')


def test_emitter_udp_and_clean_close():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        sock.settimeout(2)
        emitter = Emitter('127.0.0.1', sock.getsockname()[1], source='pi', session='test')
        payload = {'bitrate_mbps': .125}
        assert emitter.emit('sender', payload)
        payload['bitrate_mbps'] = 999
        emitter.close()
        emitter.close()
        message = decode(sock.recv(60001))
        assert message['data']['bitrate_mbps'] == .125
        assert not emitter.worker.is_alive()
        assert not emitter.emit('sender', payload)


def test_queue_full_drops_without_blocking():
    emitter = Emitter.__new__(Emitter)
    import threading
    emitter.emit_lock = threading.Lock()
    emitter.closed = False
    emitter.source, emitter.session, emitter.profile = 'pi', 'test', 'cn'
    emitter.origin = time.monotonic()
    emitter.queue = queue.Queue(maxsize=1)
    emitter.dropped = 0
    assert emitter.emit('sender', {'bitrate_mbps': 0})
    assert not emitter.emit('sender', {'bitrate_mbps': 0})
    assert emitter.dropped == 1


def test_rtcp_wire_units_empty_report_and_known_lsr():
    sink = Sink()
    report = ReportBlock(123, 17, -2, 999, 180, 65536, 0)
    log_rtcp(Log(), ReceiverReport(5, (report,)), 'rx', 0,
             sender_ssrc=123, a_units=131072, known_lsr={65536: 1}, telemetry=sink)
    assert sink.events[-1] == ('rtcp', dict(kind='RR', direction='rx', fraction_lost=17,
        cumulative_lost=-2, jitter_ms=2, rtt_ms=1000))
    log_rtcp(Log(), ReceiverReport(5, (report,)), 'rx', 0,
             sender_ssrc=123, a_units=131072, known_lsr={}, telemetry=sink)
    assert 'rtt_ms' not in sink.events[-1][1]
    log_rtcp(Log(), ReceiverReport(5), 'tx', 0, telemetry=sink)
    assert sink.events[-1][1] == dict(kind='RR', direction='tx')
    for kind, data in sink.events:
        validate(dict(v=1, profile='cn', source='pi', session='test', type=kind, time_s=0, data=data))


def test_frame_incomplete_omits_offset(tmp_path):
    sink = Sink()
    rx = Receiver(tmp_path, port=0, telemetry=sink)
    try:
        rx._frame_row(dict(frame_id=1, rtp_ts=2, status='lost', t_complete_rx_ns=None,
            t_playout_rx_ns=100, complete=0, n_expected=2, n_received=1))
        assert sink.events[-1][1] == dict(frame_id=1, rtp_ts=2, status='lost', buffer_frames=0)
    finally:
        rx.close()


def test_rate_trailing_second_and_unknown_quality():
    tx = Sender.__new__(Sender)
    from collections import deque
    tx.telemetry, tx.fps = Sink(), 30
    tx.telemetry_quality, tx.telemetry_next_ns = None, 0
    tx.telemetry_bytes = deque([(0, 100), (500_000_000, 200), (1_000_000_000, 300)])
    tx._emit_status(1_000_000_000)
    assert tx.telemetry.events[-1][1] == dict(bitrate_mbps=.004, fps=30)
    tx._emit_status(2_000_000_001)
    assert tx.telemetry.events[-1][1]['bitrate_mbps'] == 0
    tx._emit_status(2_000_000_002, decision='hold_jitter')
    assert tx.telemetry.events[-1][1]['decision'] == 'hold'


@pytest.mark.parametrize('enabled', [False, True])
def test_localhost_hub_cli(tmp_path, enabled):
    run(tmp_path, enabled)


def test_airs_matches_full_key_and_suppresses_duplicates(tmp_path):
    from rtp.sources import CapturedFrame
    class Source:
        def close(self):
            pass
    sink = Sink()
    rx = Receiver(tmp_path / 'rx', port=0)
    tx = Sender(Source(), tmp_path / 'tx', port=rx.port, bind='127.0.0.1', telemetry=sink)
    try:
        frame = CapturedFrame(7, b'fixture', time.monotonic_ns())
        tx.send_frame(frame)
        rx.receive_rtp()
        timestamp = tx.timestamp(frame.t_capture_mono_ns)
        for frame_id, rtp_ts in ((8, timestamp), (7, (timestamp+1) & 0xffffffff),
                                 (7, timestamp), (7, timestamp)):
            rx.send_result(rtp_ts, frame_id, 4, 123, 0)
        tx.receive_control()
        results = [data for kind, data in sink.events if kind == 'result']
        assert len(results) == 1 and results[0]['frame_id'] == 7
        assert results[0]['rtp_ts'] == timestamp and results[0]['latency_ms'] >= 0
    finally:
        rx.close()
        tx.close()


def test_ai_emits_float_confidence_only_for_success(tmp_path):
    from types import SimpleNamespace
    from rtp.edge_ai import EdgeAI
    sink = Sink()
    edge = EdgeAI('latest', 'synthetic', 1, lambda *args: None,
                  ai_csv=tmp_path / 'ai.csv', telemetry=sink)
    job = SimpleNamespace(frame_id=3, rtp_ts=90, t_enqueue_rx_ns=1_000_000)
    try:
        edge._write(job, status='skipped')
        edge._write(job, start=2_000_000, done=5_000_000, status='error')
        assert not sink.events
        edge._write(job, start=2_000_000, done=5_000_000, class_id=8, confidence=.42, status='ok')
        assert sink.events == [('ai', dict(frame_id=3, rtp_ts=90, policy='latest',
            queue_ms=1, inference_ms=3, class_id=8, confidence=.42))]
    finally:
        edge.close()
