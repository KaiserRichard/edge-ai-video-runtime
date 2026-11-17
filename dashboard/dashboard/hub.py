"""Asyncio UDP fan-out and a deliberately small read-only HTTP/WebSocket server."""
import asyncio
import base64
from collections import OrderedDict, deque
import hashlib
import json
from pathlib import Path
import struct
import time
from urllib.parse import urlsplit

from .metrics import PacketStats
from .schema import decode
from .learning import route as learning_route

STATIC = Path(__file__).with_name("static")


class Hub:
    def __init__(self, mode="live", history_size=4000, queue_size=32):
        self.mode = mode
        self.history = deque(maxlen=history_size)
        self.clients = set()
        self.queue_size = queue_size
        self.stats = {"accepted": 0, "invalid": 0, "client_drops": 0}
        self.packet_stats = OrderedDict()
        self.started = time.monotonic()
        self.index = 0
        self.latest_video = {}
        self.last_received = None
        self.status = "waiting for telemetry" if mode == "live" else "starting"

    def ingest(self, datagram):
        try:
            message = decode(datagram)
        except ValueError:
            self.stats["invalid"] += 1
            return None
        return self.publish(message)

    def publish(self, message):
        # t is always the hub's clock, shared by both profiles and all sources.
        # source time_s remains metadata, never used for cross-machine latency.
        self.index += 1
        self.last_received = time.monotonic()
        output = {**message, "id": self.index, "t": time.monotonic() - self.started,
                  "mode": self.mode, "data": dict(message["data"])}
        if message["type"] == "packet":
            key = (message["profile"], message["source"], message["session"])
            tracker = self.packet_stats.setdefault(key, PacketStats())
            self.packet_stats.move_to_end(key)
            if len(self.packet_stats) > 32:
                self.packet_stats.popitem(last=False)
            output["data"].update(tracker.update(message["data"], message["time_s"]))
        self.stats["accepted"] += 1
        if message["type"] == "video":
            self.latest_video[message["profile"]] = output
        else:
            self.history.append(output)
        for queue in tuple(self.clients):
            if queue.full():
                queue.get_nowait()
                self.stats["client_drops"] += 1
            queue.put_nowait(output)
        return output

    def subscribe(self):
        queue = asyncio.Queue(maxsize=self.queue_size)
        self.clients.add(queue)
        return queue

    def source_status(self):
        if self.mode != "live":
            return self.status
        if self.last_received is None:
            return "waiting for telemetry"
        if time.monotonic() - self.last_received > 3:
            return "telemetry stale · waiting for datagrams"
        return "receiving live telemetry"

    def snapshot(self):
        return dict(type="hello", mode=self.mode, status=self.source_status(),
                    t=time.monotonic() - self.started,
                    stats=dict(self.stats), history=list(self.history) + list(self.latest_video.values()))


class TelemetryProtocol(asyncio.DatagramProtocol):
    def __init__(self, hub):
        self.hub = hub

    def datagram_received(self, data, addr):
        self.hub.ingest(data)

    def error_received(self, exc):
        self.hub.stats["invalid"] += 1


def ws_frame(payload, opcode=1):
    size = len(payload)
    header = bytes([0x80 | opcode])
    if size < 126:
        return header + bytes([size]) + payload
    if size < 65536:
        return header + b"\x7e" + struct.pack("!H", size) + payload
    return header + b"\x7f" + struct.pack("!Q", size) + payload


async def read_ws_frame(reader):
    head = await reader.readexactly(2)
    opcode, size = head[0] & 15, head[1] & 127
    # The page sends no application data; accept only small masked control frames.
    if head[0] & 0x70 or not head[0] & 0x80 or not head[1] & 0x80 or opcode not in (8, 9, 10) or size > 125:
        raise ValueError("unsupported websocket frame")
    mask = await reader.readexactly(4)
    payload = await reader.readexactly(size)
    return opcode, bytes(value ^ mask[i % 4] for i, value in enumerate(payload))


class Server:
    def __init__(self, hub):
        self.hub = hub
        self.tasks = set()
        self.writers = set()

    async def close(self):
        for writer in tuple(self.writers):
            writer.close()
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    async def handle(self, reader, writer):
        self.tasks.add(asyncio.current_task())
        self.writers.add(writer)
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            if len(raw) > 16384:
                raise ValueError("headers too large")
            lines = raw.decode("ascii").split("\r\n")
            method, target, version = lines[0].split()
            headers = dict(line.split(":", 1) for line in lines[1:] if line)
            headers = {key.lower(): value.strip() for key, value in headers.items()}
            path = urlsplit(target).path
            if method != "GET":
                await self.respond(writer, 405, b"read-only server", "text/plain")
            elif path == "/ws":
                await self.websocket(reader, writer, headers)
            elif path == "/api/status":
                body = json.dumps({"mode": self.hub.mode, "status": self.hub.source_status(), **self.hub.stats}).encode()
                await self.respond(writer, 200, body, "application/json")
            elif path in ("/", "/app.js", "/fallback.js", "/fallback.css", "/style.css"):
                name, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                              "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                              "/fallback.js": ("fallback.js", "text/javascript; charset=utf-8"),
                              "/fallback.css": ("fallback.css", "text/css; charset=utf-8"),
                              "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                await self.respond(writer, 200, (STATIC / name).read_bytes(), mime)
            else:
                # Disk scans/hashes/Markdown must not block UDP and websocket ingestion.
                response = await asyncio.to_thread(learning_route, target)
                if response is None:
                    await self.respond(writer, 404, b"not found", "text/plain")
                else:
                    await self.respond(writer, *response)
        except (ValueError, UnicodeError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError, TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            self.tasks.discard(asyncio.current_task())
            self.writers.discard(writer)

    async def respond(self, writer, code, body, mime):
        reason = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}[code]
        writer.write((f"HTTP/1.1 {code} {reason}\r\nContent-Type: {mime}\r\nContent-Length: {len(body)}\r\nConnection: close\r\nX-Content-Type-Options: nosniff\r\n\r\n").encode() + body)
        await asyncio.wait_for(writer.drain(), 5)

    async def websocket(self, reader, writer, headers):
        key = headers.get("sec-websocket-key", "")
        try:
            valid_key = len(base64.b64decode(key, validate=True)) == 16
        except ValueError:
            valid_key = False
        origin = headers.get("origin")
        if (not valid_key or headers.get("upgrade", "").lower() != "websocket" or
            "upgrade" not in headers.get("connection", "").lower() or headers.get("sec-websocket-version") != "13" or
            (origin and urlsplit(origin).netloc != headers.get("host"))):
            await self.respond(writer, 400, b"invalid websocket handshake", "text/plain")
            return
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        writer.write((f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        queue = self.hub.subscribe()
        send_lock = asyncio.Lock()

        async def send(payload, opcode=1):
            async with send_lock:
                writer.write(ws_frame(payload, opcode))
                await asyncio.wait_for(writer.drain(), 5)

        async def consume_controls():
            while True:
                opcode, payload = await read_ws_frame(reader)
                if opcode == 8:
                    await send(payload, 8)
                    return
                if opcode == 9:
                    await send(payload, 10)

        async def transmit():
            await send(json.dumps(self.hub.snapshot(), allow_nan=False).encode())
            while True:
                await asyncio.sleep(0.1)
                batch = []
                while not queue.empty():
                    batch.append(queue.get_nowait())
                await send(json.dumps({"type": "batch", "events": batch,
                                       "t": time.monotonic() - self.hub.started,
                                       "status": self.hub.source_status(), "stats": self.hub.stats}, allow_nan=False).encode())

        tasks = [asyncio.create_task(consume_controls()), asyncio.create_task(transmit())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.hub.clients.discard(queue)
