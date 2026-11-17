"""Optional standalone side-channel helper to COPY into a sender/receiver repo.

This file has only standard-library imports. It is not installed or patched into
either experiment repository by this dashboard. emit() never waits for UDP or
JSON encoding. A bounded worker queue drops telemetry under load.
"""
import json
import queue
import socket
import threading
import time


class Emitter:
    def __init__(self, host, port, *, source, session, profile="cn", capacity=512):
        self.destination = (socket.gethostbyname(host), port)
        self.source, self.session, self.profile = source, session, profile
        self.origin = time.monotonic()
        self.queue = queue.Queue(maxsize=capacity)
        self.dropped = 0
        self.closed = False
        self.emit_lock = threading.Lock()
        self.stop = threading.Event()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.worker = threading.Thread(target=self._run, name="telemetry", daemon=True)
        self.worker.start()

    def emit(self, kind, data, time_s=None):
        with self.emit_lock:
            if self.closed:
                return False
            message = dict(v=1, profile=self.profile, source=self.source, session=self.session,
                           type=kind, time_s=time.monotonic() - self.origin if time_s is None else time_s,
                           data=dict(data))
            try:
                self.queue.put_nowait(message)
                return True
            except queue.Full:
                self.dropped += 1
                return False

    def _run(self):
        while not self.stop.is_set() or not self.queue.empty():
            try:
                message = self.queue.get(timeout=.05)
            except queue.Empty:
                continue
            try:
                wire = json.dumps(message, allow_nan=False, separators=(",", ":")).encode()
                if len(wire) > 60_000:
                    self.dropped += 1
                else:
                    self.socket.sendto(wire, self.destination)
            except (OSError, ValueError, TypeError):
                self.dropped += 1

    def close(self):
        if not self.closed:
            self.closed = True
            self.stop.set()
            self.worker.join(timeout=2)
            self.socket.close()


def add_arguments(parser, port):
    """No socket or worker unless --telemetry is supplied."""
    parser.add_argument("--telemetry", metavar="HOST", help="enable optional UDP JSON observer")
    parser.add_argument("--telemetry-port", type=int, default=port)
    parser.add_argument("--telemetry-session", help="same experiment ID on both endpoints; change each run")


def from_arguments(args, parser, source):
    if args.telemetry is None:
        return None
    if not args.telemetry_session or not 1 <= len(args.telemetry_session) <= 64:
        parser.error("--telemetry requires --telemetry-session (1..64 characters)")
    if not 1 <= args.telemetry_port <= 65535:
        parser.error("--telemetry-port must be in 1..65535")
    return Emitter(args.telemetry, args.telemetry_port, source=source,
                   session=args.telemetry_session)
