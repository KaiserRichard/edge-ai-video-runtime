import json

import pytest

from dashboard.schema import MAX_DATAGRAM, decode, event


def packet():
    return event("packet", dict(seq=65535, rtp_ts=4294967295, frame_id=7, bytes=1212, jitter_ms=.14))


def test_roundtrip():
    msg = packet()
    assert decode(json.dumps(msg).encode()) == msg


@pytest.mark.parametrize("wire", [b"null", b"[]", b"{", b"\xff", b"{}", b"x" * (MAX_DATAGRAM + 1)], ids=["null", "array", "truncated", "utf8", "empty", "oversized"])
def test_malformed_datagrams(wire):
    with pytest.raises(ValueError):
        decode(wire)


@pytest.mark.parametrize("key,value", [("seq", 65536), ("seq", -1), ("seq", True), ("seq", 1.5), ("jitter_ms", float("nan")), ("bytes", -1), ("rtp_ts", float("inf"))])
def test_bad_packet_values(key, value):
    msg = packet()
    msg["data"][key] = value
    with pytest.raises(ValueError):
        decode(json.dumps(msg).encode())


@pytest.mark.parametrize("key,value", [("v", 2), ("v", True), ("time_s", -1), ("time_s", float("nan")), ("profile", "other"), ("source", "other"), ("type", "other"), ("session", "")])
def test_bad_envelopes(key, value):
    msg = packet()
    msg[key] = value
    with pytest.raises(ValueError):
        decode(json.dumps(msg).encode())


def test_contract_catches_typos_and_omissions():
    msg = packet()
    msg["data"]["jiter_ms"] = 1
    with pytest.raises(ValueError):
        decode(json.dumps(msg).encode())
    del msg["data"]["jiter_ms"]
    del msg["data"]["jitter_ms"]
    with pytest.raises(ValueError):
        decode(json.dumps(msg).encode())


def test_hardware_and_os_contracts():
    assert event("hardware", dict(temperature_c=55, throttled=0, cpu_cores=[0, 100]), source="pi")["data"]["throttled"] == 0
    assert event("os", dict(state="FAILSAFE", link_active=False, fault="bridge stopped"), source="bridge", profile="os")
    with pytest.raises(ValueError):
        event("hardware", dict(temperature_c=55, throttled=0, cpu_cores=[101]))
    with pytest.raises(ValueError):
        event("os", dict(state="BAD"))


def test_zero_and_negative_offsets_are_preserved():
    assert event("frame", dict(frame_id=0, rtp_ts=0, status="ok", arrival_offset_ms=-10))["data"]["arrival_offset_ms"] == -10
    assert event("rtcp", dict(kind="RR", direction="tx", fraction_lost=0, cumulative_lost=-1))
