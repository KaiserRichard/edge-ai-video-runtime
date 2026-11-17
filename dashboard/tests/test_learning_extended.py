"""Source-backed calculations and full HTTP handlers without requiring a socket."""
import asyncio
import hashlib
from html import unescape
import json
import re
from urllib.parse import urlencode

import pytest

from dashboard import evidence as ev, learning as web
from dashboard.hub import Hub, Server
from dashboard.paths import input_path
from dashboard.replay import load_replay, play


def test_wsl_paths_and_publication_match_read_only_originals():
    import os
    translated = input_path(r"C:\example\lessons\vi")
    assert str(translated).startswith("/mnt/c/") if os.name != "nt" else translated.drive == "C:"
    for record in json.loads((web.CONTENT / "publication.json").read_text(encoding="utf-8")):
        original = ev.REPOSITORY / record["source"]
        assert original.is_file()
        assert hashlib.sha256(original.read_bytes()).hexdigest() == record["sha256"]


def test_each_answer_has_its_own_closed_disclosure_and_source_answer():
    for lesson in web.lessons():
        source = web.lesson_source(lesson["id"])
        rendered = web.lesson_page(lesson["id"]).decode()
        assert rendered.count('<details class="answers">') == 3
        assert '<details class="answers" open' not in rendered
        answer_block = source.split("<details><summary>Đáp án</summary>")[1].split("</details>")[0]
        for line in answer_block.splitlines():
            match = re.match(r"\d+\. (.*)", line)
            if match:
                assert web.inline(match[1]) in rendered


def test_jitter_recurrence_and_rr_preserve_logged_values():
    jitter = web.widget_data("02")["calculator"]
    assert [r["seq"] for r in jitter[:3]] == ["31318", "31319", "31320"]
    for old, new in zip(jitter, jitter[1:]):
        j = float(old["jitter_ts_units"])
        delta = abs(int(new["transit_ts_units"]) - int(old["transit_ts_units"]))
        assert j + (delta-j)/16 == pytest.approx(float(new["jitter_ts_units"]), abs=.00001)
    rr = web.widget_data("04")
    rows = [r for r in web.csv_rows(ev.resolve("cn-t3", "loss5/run1/receiver_rtcp.csv"))
            if r["type"] == "RR" and r["fraction_lost"]]
    assert rr["charts"][0]["ys"][0] == [100*int(r["fraction_lost"])/256 for r in rows]
    assert rr["charts"][1]["ys"][0] == [int(r["cum_lost"]) for r in rows]


def test_playout_is_only_observed_complete_frames_and_monotonic():
    data = web.widget_data("03")
    rows = web.csv_rows(ev.resolve("sample", "frames_rx.csv"))
    assert data["complete"] == len([r for r in rows if r["complete"] == "1" and r["t_complete_rx_ns"]])
    late = [sum(offset > d for offset in data["offsets"]) for d in range(251)]
    assert late == sorted(late, reverse=True)
    assert 99.99 < data["experiment_d"] < 100.01
    assert "T4" in data["note"] and "INFERRED" in data["note"]


def test_netem_bars_and_bitrate_points_from_named_table():
    netem = web.widget_data("05")
    assert set(netem["categories"]) == {"ge5_b4", "loss0", "loss1", "loss5", "loss10"}
    index = netem["categories"].index("loss5")
    assert netem["charts"][0]["ys"][0][index] == pytest.approx(5.2)
    assert netem["charts"][0]["ys"][1][index] == pytest.approx(24)
    abr = web.widget_data("06")
    assert abr["charts"][0]["x"] == [30,60,90]
    assert abr["charts"][0]["ys"] == [[.679,.694,1.266]]
    assert "MÔ PHỎNG" in abr["missing"]


def test_supervisor_transitions_and_images_are_saved_simulation_not_hardware():
    data = web.widget_data("10")
    assert data["kind"] == "simulated"
    assert data["report"]["complete"]
    assert all(item["passed"] for item in data["report"]["results"])
    for key in ("scenario", "degrade"):
        actual = []
        previous = None
        for row in data["traces"][key]:
            if row["state"] != previous:
                actual.append((row["time_ms"], row["state"]))
                previous = row["state"]
        assert actual == list(zip(data[key]["transition_ms"], data[key]["state_sequence"]))
    for ref in data["images"]:
        assert web.route("/api/evidence/raw?"+urlencode(ref))[0] == 200
        assert ev.preview(ref["root"],ref["path"])["badge"] == "MÔ PHỎNG"


def test_evidence_links_are_bidirectional_and_resolve():
    for lesson in web.lessons():
        body = web.lesson_page(lesson["id"]).decode()
        for ref in web.source_items(lesson["id"]):
            ev.resolve(ref["root"],ref["path"])
            assert lesson["id"] in ev.used_in(ref["root"],ref["path"])
            assert web.evidence_url(ref) in unescape(body)


@pytest.mark.parametrize("path", [
    "/api/evidence/preview?root=sample&path=%2e%2e%2fREADME.md",
    "/api/evidence/preview?root=sample&path=%252e%252e%252fREADME.md",
    "/api/evidence/preview?root=sample&path=%255c%255chost%255cfile.csv",
    "/api/evidence/raw?root=sample&path=%2fetc%2fpasswd",
    "/api/evidence/provenance?root=sample&path=C%3A%2Fsecret.csv",
    "/lesson-assets/%2e%2e/hub.py",
    "/lesson-assets/%252e%252e/hub.py",
    "/api/widgets/index",
    "/api/widgets/11",
])
def test_encoded_attacks_through_route_decoder(path):
    assert web.route(path)[0] == 404


def test_directory_symlink_and_symlink_root_are_rejected(tmp_path,monkeypatch):
    folder = tmp_path/"actual";folder.mkdir();(folder/"data.csv").write_text("t,value\n0,1")
    link = tmp_path/"linked"
    # The companion existing test checks actual Windows junctions where required.
    try:
        link.symlink_to(folder,target_is_directory=True)
    except OSError:
        pytest.skip("OS denies creating directory symlinks; existing junction test covers Windows")
    monkeypatch.setitem(ev.ROOTS,"fixture",tmp_path)
    with pytest.raises(ev.EvidenceError):ev.resolve("fixture","linked/data.csv")
    monkeypatch.setitem(ev.ROOTS,"fixture",link)
    with pytest.raises(ev.EvidenceError):ev.resolve("fixture","data.csv")


def test_plot_can_use_row_number_and_finds_sparse_numeric_columns(tmp_path,monkeypatch):
    monkeypatch.setitem(ev.ROOTS,"fixture",tmp_path)
    (tmp_path/"data.csv").write_text("time_s,value\n"+"".join(f"{i*5},{i if i>100 else ''}\n" for i in range(120)))
    preview = ev.preview("fixture","data.csv",column="value",time_column="__row__")
    assert "value" in preview["numeric"]
    assert preview["plot"][0] == [101,101]


class MemoryWriter:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self,data): self.data.extend(data)
    async def drain(self): pass
    def close(self): self.closed = True
    async def wait_closed(self): pass


def test_full_http_handler_read_only_routes_in_memory():
    async def scenario():
        server = Server(Hub("replay"))
        cases = [
            ("/",200),("/learning.js",200),("/panels.js",200),("/learning.css",200),
            ("/lessons",200),("/demo",200),("/evidence",200),("/api/demo",200),
            ("/api/status",200),("/api/evidence/preview?root=sample&path=receiver.csv&column=seq",200),
            ("/api/evidence/provenance?root=sample&path=receiver.csv",200),
            ("/lessons/11",404),("/not-a-page",404),
            ("/api/evidence/preview?root=sample&path=%252e%252e%252fREADME.md",404),
        ] + [(f"/lessons/{i:02}",200) for i in range(1,11)] + [(f"/api/widgets/{i:02}",200) for i in range(1,11)]
        for path, expected in cases:
            reader = asyncio.StreamReader()
            reader.feed_data(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
            reader.feed_eof()
            writer = MemoryWriter()
            await server.handle(reader,writer)
            head,body = bytes(writer.data).split(b"\r\n\r\n",1)
            assert head.startswith(f"HTTP/1.1 {expected}".encode()),(path,head)
            assert f"Content-Length: {len(body)}".encode() in head
            assert writer.closed
        reader = asyncio.StreamReader();reader.feed_data(b"POST /lessons HTTP/1.1\r\nHost: localhost\r\n\r\n");reader.feed_eof()
        writer = MemoryWriter();await server.handle(reader,writer)
        assert bytes(writer.data).startswith(b"HTTP/1.1 405")
        await server.close()
    # Some restricted runners deny the selector's cross-thread socket wakeup.
    # A timer lets the real to_thread results be collected without that socket.
    loop = asyncio.new_event_loop()
    def tick():
        loop.call_later(.01, tick)
    loop.call_soon(tick)
    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()


def test_real_replay_runs_to_completion_in_memory():
    async def scenario():
        hub=Hub("replay")
        events=load_replay(ev.PROJECT/"samples/cn-loss5")
        await play(hub,events,speed=10000,loop=False)
        assert hub.status == "replay complete"
        assert hub.stats["accepted"] > 500
        assert any(e["type"]=="packet" for e in hub.history)
        assert not hub.stats["invalid"]
    asyncio.run(scenario())
