import asyncio
import base64
import json
import struct

import pytest

from dashboard.hub import Hub, Server, TelemetryProtocol, read_ws_frame, ws_frame
from dashboard.schema import event


def message(seq=1):
    return event("packet", dict(seq=seq, rtp_ts=0, frame_id=1, bytes=1212, jitter_ms=.14))


def test_invalid_udp_is_counted_without_crashing():
    hub = Hub()
    assert hub.source_status() == "waiting for telemetry"
    assert hub.ingest(b"bad") is None
    assert hub.ingest(b"null") is None
    assert hub.stats["invalid"] == 2
    assert hub.ingest(json.dumps(message()).encode())["id"] == 1
    assert hub.stats["accepted"] == 1
    assert hub.source_status() == "receiving live telemetry"
    hub.last_received -= 4
    assert "stale" in hub.source_status()


def test_slow_browser_and_history_are_bounded():
    hub = Hub(history_size=4, queue_size=2)
    queue = hub.subscribe()
    for seq in range(20):
        hub.publish(message(seq))
    assert len(hub.history) == 4
    assert queue.qsize() == 2
    assert hub.stats["client_drops"] == 18
    assert queue.get_nowait()["data"]["seq"] == 18
    assert hub.history[-1]["data"]["sequence_lost"] == 0


def test_sources_and_sessions_have_independent_sequence_state():
    hub = Hub()
    hub.publish(message(100))
    msg = message(200)
    msg["session"] = "second"
    assert hub.publish(msg)["data"]["sequence_lost"] == 0
    assert hub.publish(message(102))["data"]["sequence_lost"] == 1
    for i in range(50):
        hub.publish({**message(), "session": f"session{i}"})
    assert len(hub.packet_stats) <= 32


def test_video_does_not_fill_history():
    hub = Hub()
    for frame_id in range(20):
        hub.publish(event("video", dict(frame_id=frame_id, status="ok", jpeg_b64="/9j/2Q==")))
    assert not hub.history
    assert hub.snapshot()["history"][0]["data"]["frame_id"] == 19


@pytest.mark.parametrize("size", [2, 125, 126, 65535, 65536])
def test_websocket_length_encodings(size):
    payload = b"x" * size
    frame = ws_frame(payload)
    assert frame[0] == 0x81
    assert frame.endswith(payload)
    if size < 126:
        assert frame[1] == size
    elif size < 65536:
        assert frame[1] == 126
        assert struct.unpack("!H", frame[2:4])[0] == size
    else:
        assert frame[1] == 127
        assert struct.unpack("!Q", frame[2:10])[0] == size


async def read_frame(reader):
    first, length = await reader.readexactly(2)
    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]
    return first & 15, await reader.readexactly(length)


def masked_control(opcode, payload=b""):
    mask = b"abcd"
    return bytes([128 | opcode, 128 | len(payload)]) + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload))


def test_rejects_unmasked_or_application_client_frames():
    async def scenario():
        for frame in (b"\x81\x00", b"\x89\x00", b"\x09\x80abcd"):
            reader = asyncio.StreamReader()
            reader.feed_data(frame)
            with pytest.raises(ValueError):
                await read_ws_frame(reader)
    asyncio.run(scenario())


def test_udp_to_websocket_http_ping_and_disconnect():
    async def scenario():
        hub = Hub(queue_size=32)
        app = Server(hub)
        server = await asyncio.start_server(app.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(lambda: TelemetryProtocol(hub), local_addr=("127.0.0.1", 0))
        udp_port = transport.get_extra_info("sockname")[1]
        client_transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(asyncio.DatagramProtocol, remote_addr=("127.0.0.1", udp_port))
        writer = None
        try:
            for path, code in (("/", "200 OK"), ("/app.js", "200 OK"), ("/fallback.js", "200 OK"), ("/fallback.css", "200 OK"), ("/style.css", "200 OK"), ("/../README.md", "404 Not Found"), ("/api/status", "200 OK")):
                reader, w = await asyncio.open_connection("127.0.0.1", port)
                w.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
                response = await asyncio.wait_for(reader.read(), 2)
                assert code.encode() in response.split(b"\r\n")[0]
                w.close()
                await w.wait_closed()
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /ws HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n")
            headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
            assert b"101 Switching Protocols" in headers
            assert b"s3pPLMBiTxaQ9kYGzzhZRbK+xOo=" in headers
            _, payload = await read_frame(reader)
            assert json.loads(payload)["type"] == "hello"
            client_transport.sendto(b"bad")
            client_transport.sendto(json.dumps(message(65535)).encode())
            client_transport.sendto(json.dumps(message(1)).encode())
            received = []
            for _ in range(20):
                _, payload = await asyncio.wait_for(read_frame(reader), 2)
                received.extend(json.loads(payload)["events"])
                if len(received) >= 2:
                    break
            assert [e["data"]["seq"] for e in received] == [65535, 1]
            assert received[-1]["data"]["sequence_lost"] == 1
            assert hub.stats["invalid"] == 1
            writer.write(masked_control(9, b"ping"))
            for _ in range(20):
                opcode, payload = await asyncio.wait_for(read_frame(reader), 2)
                if opcode == 10:
                    assert payload == b"ping"
                    break
            else:
                pytest.fail("no pong")
            writer.write(masked_control(8))
            for _ in range(20):
                opcode, _ = await asyncio.wait_for(read_frame(reader), 2)
                if opcode == 8:
                    break
            else:
                pytest.fail("no close acknowledgement")
            await asyncio.sleep(.02)
            assert not hub.clients
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
            client_transport.close()
            transport.close()
            server.close()
            await server.wait_closed()
            await app.close()
    asyncio.run(scenario())


def test_cross_origin_websocket_rejected():
    async def scenario():
        app = Server(Hub())
        server = await asyncio.start_server(app.handle, "127.0.0.1", 0)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
            writer.write(b"GET /ws HTTP/1.1\r\nHost: localhost\r\nOrigin: http://example.com\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n")
            assert b"400 Bad Request" in await asyncio.wait_for(reader.read(), 2)
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()
            await app.close()
    asyncio.run(scenario())
