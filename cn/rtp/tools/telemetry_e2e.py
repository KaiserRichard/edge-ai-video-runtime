"""Real localhost hub + endpoint CLI proof; all artifacts stay under output."""
import argparse
import base64
from collections import Counter
import csv
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = Path(os.environ.get('DASHBOARD_ROOT', str(ROOT.parents[1] / 'dashboard')))
# Valid 1x1 JPEG fixture; synthetic AI does not decode pixels or require Pillow.
JPEG = base64.b64decode('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAABQb/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwC/AB//2Q==')


def free_port(kind):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_until(fn, processes, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for process in processes:
            assert process.poll() is None, f'child exited early: {process.args}'
        try:
            value = fn()
            if value:
                return value
        except (OSError, ValueError):
            pass
        time.sleep(.03)
    raise AssertionError('child startup timed out')


def status(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=1) as reply:
        return json.load(reply)


def websocket_snapshot(port):
    with socket.create_connection(('127.0.0.1', port), timeout=3) as sock:
        sock.sendall((f'GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
                      'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                      'Sec-WebSocket-Key: MDEyMzQ1Njc4OWFiY2RlZg==\r\n'
                      'Sec-WebSocket-Version: 13\r\n\r\n').encode())
        stream = sock.makefile('rb')
        assert b'101 Switching' in stream.readline()
        while stream.readline() != b'\r\n':
            pass
        opcode, length = stream.read(2)
        assert opcode == 0x81
        length &= 127
        if length == 126:
            length = struct.unpack('!H', stream.read(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', stream.read(8))[0]
        return json.loads(stream.read(length))


def run(output, enabled=True):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixture = output / 'jpeg'
    fixture.mkdir(exist_ok=True)
    (fixture / 'one.jpg').write_bytes(JPEG)
    http = free_port(socket.SOCK_STREAM)
    pi_port, rx_port = free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
    while pi_port == rx_port:
        rx_port = free_port(socket.SOCK_DGRAM)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join((str(ROOT), str(DASHBOARD))))
    python = str(DASHBOARD / '.venv' / 'Scripts' / 'python.exe')
    commands = []
    children, handles = [], []

    def start(name, arguments):
        command = [python, '-B', *arguments]
        commands.append(command)
        handle = (output / f'{name}.log').open('w', encoding='utf-8')
        handles.append(handle)
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT)
        children.append(child)
        return child

    try:
        hub = start('hub', ['-m', 'dashboard', '--mode', 'live', '--host', '127.0.0.1',
            '--port', str(http), '--udp-host', '127.0.0.1', '--pi-port', str(pi_port), '--receiver-port', str(rx_port)])
        wait_until(lambda: status(http), [hub])
        session = 'cn-localhost-proof'
        telemetry = lambda port: ['--telemetry', '127.0.0.1', '--telemetry-port', str(port), '--telemetry-session', session] if enabled else []
        rx = start('receiver', [str(ROOT / 'tools' / 'localhost_endpoint.py'), 'rtp.receiver', '--port', '0', '--duration', '4', '--playout-ms', '30',
            '--late-window-ms', '100', '--rtcp-interval', '.2', '--ai', 'synthetic', '--ai-service-ms', '5',
            '--out-dir', str(output / 'receiver'), *telemetry(rx_port)])
        def ready():
            text = (output / 'receiver.log').read_text(encoding='utf-8')
            return int(text.split('READY RTP=')[1].split()[0]) if 'READY RTP=' in text else None
        rtp_port = wait_until(ready, [hub, rx])
        tx = start('sender', [str(ROOT / 'tools' / 'localhost_endpoint.py'), 'rtp.sender', '--source', 'jpegdir', '--jpeg-dir', str(fixture),
            '--host', '127.0.0.1', '--bind', '127.0.0.1', '--port', str(rtp_port), '--duration', '1.2',
            '--drain-seconds', '.5', '--fps', '30', '--mtu-payload', '100', '--rtcp-interval', '.2',
            '--out-dir', str(output / 'sender'), *telemetry(pi_port)])
        assert tx.wait(timeout=8) == 0
        assert rx.wait(timeout=8) == 0
        # Emitter.close drains its queue; allow the hub to process last datagrams.
        time.sleep(.2)
        report = status(http)
        snapshot = websocket_snapshot(http)
        events = snapshot['history']
        assert report['invalid'] == 0, report
        counts = Counter(e['type'] for e in events)
        def rows(name):
            with (output / name).open(newline='') as file:
                return list(csv.DictReader(file))
        sent = rows('sender/sender.csv')
        packets = rows('receiver/receiver.csv')
        frames = rows('receiver/frames_rx.csv')
        ai = rows('receiver/ai.csv')
        results = rows('sender/results_tx.csv')
        assert len(sent) > 10 and len(sent) == len(frames) == len(ai) == len(results)
        assert len(packets) == sum(int(r['n_pkts']) for r in sent)
        assert all(r['status'] == 'ok' for r in frames + ai)
        if enabled:
            sys.path.insert(0, str(DASHBOARD))
            from dashboard.schema import FIELDS, validate
            # The hub adds packet-estimator fields; validate the original envelope.
            for event in events:
                raw = {key: event[key] for key in ('v', 'profile', 'source', 'session', 'type', 'time_s', 'data')}
                required, optional = FIELDS[raw['type']]
                raw['data'] = {key: value for key, value in raw['data'].items() if key in required | optional}
                validate(raw)
                assert raw['session'] == session
            assert counts['packet'] == len(packets)
            assert counts['frame'] == len(frames)
            assert counts['ai'] == len(ai)
            assert counts['result'] == len(results)
            assert counts['rtcp'] > 0 and counts['sender'] > 5
            assert report['accepted'] == len(events)
            assert {e['source'] for e in events} == {'receiver', 'pi'}
            for source in ('receiver', 'pi'):
                stamps = [e['time_s'] for e in events if e['source'] == source]
                assert stamps == sorted(stamps)
        else:
            assert report['accepted'] == 0 and not events
        evidence = dict(enabled=enabled, status=report, counts=dict(counts),
                        sent_frames=len(sent), received_packets=len(packets), matched_results=len(results),
                        schema_validated=len(events), commands=commands)
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        (output / 'hub_snapshot.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        return evidence
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=4)
        for handle in handles:
            handle.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--disabled', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.output, not args.disabled), indent=2))
