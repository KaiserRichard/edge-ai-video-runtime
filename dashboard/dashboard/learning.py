"""Vietnamese learning pages, native Markdown and measured widget adapters."""
import csv
from functools import lru_cache
import hashlib
import html
import json
import math
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit

from . import evidence as ev

CONTENT = Path(__file__).with_name("content")
VI = CONTENT / "vi"
STATIC = Path(__file__).with_name("static")


def lessons():
    index = (VI / "INDEX.md").read_text(encoding="utf-8")
    names = re.findall(r'\[(\d{2}_[^\]]+\.md)\]\(', index)
    return [dict(id=name[:2], file=name, title=(VI/name).read_text(encoding="utf-8").splitlines()[0].lstrip("# "), course="CN" if int(name[:2]) < 8 else "OS") for name in names]


def lesson_source(key):
    if key == "index":
        return (VI / "INDEX.md").read_text(encoding="utf-8")
    item = next((item for item in lessons() if item["id"] == key), None)
    if not item:
        raise ev.EvidenceError("unknown lesson")
    return (VI / item["file"]).read_text(encoding="utf-8")


def evidence_url(ref):
    return "/evidence?" + urlencode(ref)


def source_ref(value):
    # Only link exact, existing allow-listed files. Unknown source stays visible text.
    paths = []
    value = value.strip().replace("\\", "/")
    if value.startswith("cn/rtp/"):
        paths = [ev.CN / value[len("cn/rtp/"):]]
    elif value.startswith("os/"):
        paths = [ev.OS / value[3:]]
    elif value.startswith("CN/"):
        paths = [ev.CN / value[3:]]
    elif value.startswith("OS/"):
        paths = [ev.OS / value[3:]]
    elif re.match(r"^[DE]:/", value):
        paths = [ev.input_path(value)]
    elif value in ("hw_tables.md", "sim_tables.md"):
        paths = [ev.CN / "report" / value]
    for path in paths:
        ref = ev.identify(path)
        if ref:
            try:
                ev.resolve(ref["root"], ref["path"])
                return ref
            except ev.EvidenceError:
                pass
    return None


def safe_link(value, image=False):
    value = html.unescape(value)
    if image:
        # Both ../img originals and vi/img figures remain byte-identical copies.
        relative = ("img/" + value[7:]) if value.startswith("../img/") else "vi/" + value
        path = CONTENT / relative
        if ".." in Path(relative).parts or not path.is_file():
            return ""
        return "/lesson-assets/" + relative
    if value == "INDEX.md":
        return "/lessons/index"
    if re.match(r"\d{2}_.*\.md$", value):
        return "/lessons/" + value[:2]
    if value.startswith(("https://", "http://", "#")):
        return value
    return "#"


def inline(value):
    tokens = []
    def hold(markup):
        tokens.append(markup)
        return f"\x01{len(tokens)-1}\x02"
    def code(match):
        raw = match.group(1)
        content = "<code>" + html.escape(raw) + "</code>"
        ref = source_ref(raw)
        return hold(f'<a href="{html.escape(evidence_url(ref), quote=True)}">{content}</a>' if ref else content)
    value = re.sub(r"`([^`]+)`", code, value)
    value = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', lambda m: hold(f'<img src="{html.escape(safe_link(m[2], True), quote=True)}" alt="{html.escape(m[1], quote=True)}" loading="eager">'), value)
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: hold(f'<a href="{html.escape(safe_link(m[2]), quote=True)}">{html.escape(m[1])}</a>'), value)
    value = html.escape(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", value)
    value = value.replace("&lt;br/&gt;", "<br>").replace("&lt;br&gt;", "<br>")
    return re.sub(r"\x01(\d+)\x02", lambda m: tokens[int(m[1])], value)


@lru_cache(maxsize=1)
def diagram_cache():
    return json.loads((CONTENT / "mermaid_cache.json").read_text(encoding="utf-8"))


def markdown(source):
    """Small deterministic server renderer for the supplied Markdown dialect.

    Raw HTML is limited to the lesson's details/summary blocks. Arbitrary HTML,
    javascript links and scripts are escaped. Mermaid uses exact-source SVG cache.
    """
    lines = source.splitlines()
    output, i, heading = [], 0, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("<!--"):
            while "-->" not in lines[i] and i+1 < len(lines):
                i += 1
            i += 1
            continue
        if line.startswith("```"):
            language, body = line[3:].strip(), []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i]); i += 1
            code = "\n".join(body)
            if language == "mermaid":
                svg = diagram_cache().get(hashlib.sha256(code.strip().encode()).hexdigest())
                if svg:
                    output.append('<figure class="diagram">' + svg + '</figure>')
                else:
                    output.append('<pre class="mermaid">' + html.escape(code) + '</pre>')
                output.append('<details class="diagram-source"><summary>Mã Mermaid</summary><pre>' + html.escape(code) + '</pre></details>')
            else:
                output.append('<pre><code class="language-' + html.escape(language, quote=True) + '">' + html.escape(code) + '</code></pre>')
            i += 1
            continue
        match = re.match(r"^(#{1,6})\s+(.*)", line)
        if match:
            heading += 1
            level = len(match[1])
            output.append(f'<h{level} id="section-{heading}">{inline(match[2])}</h{level}>')
            i += 1
            continue
        if line.startswith("<details><summary>"):
            title = re.search(r"<summary>(.*?)</summary>", line)[1]
            i += 1; body = []
            while i < len(lines) and "</details>" not in lines[i]:
                body.append(lines[i]); i += 1
            answer_text = "\n".join(body).strip()
            answers = [a for a in re.split(r"(?m)^(?=\d+\. )", answer_text) if a.strip()]
            output.append('<div class="original-summary">' + html.escape(title) + '</div>')
            for number, answer in enumerate(answers, 1):
                output.append('<details class="answers"><summary>Xem đáp án · Câu ' + str(number) +
                              '</summary>' + markdown(answer) + '</details>')
            i += 1
            continue
        if line.startswith("|") and i+1 < len(lines) and re.match(r"\|[\s:|-]+\|", lines[i+1]):
            header = [cell.strip() for cell in line.strip("|").split("|")]
            output.append('<div class="table-scroll"><table><thead><tr>' + ''.join('<th>'+inline(c)+'</th>' for c in header) + '</tr></thead><tbody>')
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                output.append('<tr>' + ''.join('<td>'+inline(c.strip())+'</td>' for c in lines[i].strip("|").split("|")) + '</tr>'); i += 1
            output.append('</tbody></table></div>')
            continue
        if line.startswith(">"):
            block = []
            while i < len(lines) and lines[i].startswith(">"):
                block.append(lines[i].lstrip("> ")); i += 1
            output.append('<blockquote>' + markdown("\n".join(block)) + '</blockquote>')
            continue
        if re.match(r"^(?:[-*] |\d+\. )", line):
            ordered = bool(re.match(r"\d+\.", line))
            tag = "ol" if ordered else "ul"
            start = f' start="{int(line.split(".")[0])}"' if ordered else ""
            output.append('<' + tag + start + '>')
            while i < len(lines) and re.match(r"^(?:[-*] |\d+\. )", lines[i]):
                output.append('<li>'+inline(re.sub(r"^(?:[-*] |\d+\. )", "", lines[i]))+'</li>'); i += 1
            output.append('</'+tag+'>')
            continue
        if line.strip() == "---":
            output.append("<hr>"); i += 1; continue
        paragraph = [line]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(?:#|```|\||>|<details|[-*] |\d+\. |<!--)", lines[i]):
            paragraph.append(lines[i]); i += 1
        output.append('<p>' + inline("\n".join(paragraph)) + '</p>')
    return "\n".join(output)


def source_items(key):
    refs = []
    manifest = json.loads((VI / "img/evidence_manifest.json").read_text(encoding="utf-8"))
    for fig in manifest["figures"]:
        if f'{fig["lesson"]:02}' == key:
            for value in fig["sources"]:
                ref = ev.identify(value)
                if ref and ref not in refs:
                    try:
                        ev.resolve(ref["root"], ref["path"])
                    except ev.EvidenceError:
                        # Figure manifests can name directories and JSON field
                        # descriptions. Only actual files belong in this table.
                        continue
                    refs.append(ref)
    for value in re.findall(r"`([^`]+)`", lesson_source(key)):
        ref = source_ref(value)
        if ref and ref not in refs:
            refs.append(ref)
    if key in ("01", "02", "03", "04"):
        for name in (["receiver.csv", "frames_rx.csv"] if key == "03" else ["receiver_rtcp.csv"] if key == "04" else ["receiver.csv"]):
            ref = dict(root="sample", path=name)
            if ref not in refs:
                refs.insert(0, ref)
    return refs


def shell(title, body, active="lessons"):
    template = (STATIC / "learning.html").read_text(encoding="utf-8")
    return template.replace("{{TITLE}}", html.escape(title)).replace("{{ACTIVE}}", active).replace("{{BODY}}", body).encode()


def sidebar(key):
    result = ['<aside class="lesson-sidebar"><a class="sidebar-home" href="/lessons">LỘ TRÌNH HỌC</a><div class="study-progress" id="study-progress">Tiến độ của bạn</div>']
    for group in ("CN", "OS"):
        result.append('<div class="sidebar-group">'+group+' <span>'+('Mạng máy tính' if group == 'CN' else 'Hệ điều hành')+'</span></div>')
        for item in lessons():
            if item["course"] != group:
                continue
            label = item["title"].split("—", 1)[-1].strip()
            result.append(f'<div class="lesson-nav {"active" if key == item["id"] else ""}"><a href="/lessons/{item["id"]}"><b>{item["id"]}</b><span>{html.escape(label)}</span></a><input type="checkbox" data-done="{item["id"]}" aria-label="Đã học bài {item["id"]}" title="Đã học"></div>')
    return ''.join(result) + '<a class="sidebar-foot" href="/demo">▷ Tập demo 10 phút</a></aside>'


def widget_markup(key, full=False):
    return f'<section class="learning-widget panel {"full-widget" if full else ""}" data-widget="{key}" id="widget-{key}"><div class="eyebrow">THỬ TRỰC TIẾP · BÀI {key}</div><p>Đang đọc dữ liệu nguồn…</p></section>'


def lesson_page(key=None):
    if key is None:
        cards = ''.join(f'<a class="lesson-card" href="/lessons/{item["id"]}"><span class="eyebrow">{item["course"]} / BÀI {item["id"]}</span><h2>{html.escape(item["title"].split("—",1)[-1].strip())}</h2><span class="card-link">Mở bài học ↗</span></a>' for item in lessons())
        return shell("Bài giảng", '<div class="learning-layout">'+sidebar(None)+'<main class="learning-main"><div class="eyebrow">HỌC TỪ HỆ THỐNG THẬT</div><h1>Từ gói tin đến<br>một kết quả còn tươi.</h1><p class="lead">Mười bài học tiếng Việt. Hai đồ án. Cùng một luồng dữ liệu từ Raspberry Pi đến laptop và STM32.</p><div class="learning-path"><span>01–07 / RTP & RTCP</span><span>→</span><span>08–10 / Edge-AI Runtime</span></div><div class="lesson-grid">'+cards+'</div><a href="/lessons/index">Đọc INDEX gốc và các giới hạn bằng chứng →</a></main></div>')
    source = lesson_source(key)
    rendered = markdown(source)
    if key != "index":
        # Place the widget beside the concept, before simulation and evidence sections.
        marker = re.search(r'<h2[^>]*>4\.', rendered)
        at = marker.start() if marker else len(rendered)
        rendered = rendered[:at] + widget_markup(key) + rendered[at:]
        refs = source_items(key)
        links = ''.join('<li><a href="'+html.escape(evidence_url(ref), quote=True)+'">'+html.escape(ref["root"]+'/'+ref["path"])+'</a></li>' for ref in refs)
        evidence_table = '<aside class="source-index"><h2>Measured evidence · Liên kết nguồn</h2><p>Nguồn mô phỏng được ghi nhãn riêng trong bài. Mở tệp để xem đường dẫn và tính SHA-256.</p><ul>'+links+'</ul></aside>'
        marker = rendered.find('<h2 id="section-7">')
        # Evidence links belong directly after the existing measured evidence table.
        marker = re.search(r'<h2[^>]*>6\.', rendered)
        at = marker.start() if marker else len(rendered)
        rendered = rendered[:at] + evidence_table + rendered[at:]
        if '<details class="answers">' not in rendered:
            rendered += '<h2>Câu hỏi kiểm tra</h2><details class="answers"><summary>Xem đáp án</summary><p>Hỏi nhóm / hỏi thầy</p></details>'
        number = int(key)
        rendered += '<nav class="lesson-pagination">'+(f'<a href="/lessons/{number-1:02}">← Bài trước</a>' if number>1 else '<a href="/lessons">← Lộ trình</a>')+(f'<a href="/lessons/{number+1:02}">Bài tiếp →</a>' if number<10 else '<a href="/demo">Tập demo →</a>')+'</nav>'
    return shell(source.splitlines()[0].lstrip("# "), '<div class="learning-layout">'+sidebar(key)+'<main class="learning-main prose"><div class="breadcrumb"><a href="/lessons">Bài giảng</a> / '+html.escape(key)+'</div>'+rendered+'</main><aside class="page-toc"><div class="eyebrow">TRONG BÀI NÀY</div><div id="toc"></div><p>Đọc → thử → đối chiếu nguồn</p></aside></div>')


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def measured_source(path):
    ref = ev.identify(path)
    return dict(source=str(path), **(ref or {"path": str(path)}))


def widget_data(key):
    if not re.fullmatch(r"0[1-9]|10", key):
        raise ev.EvidenceError("unknown widget")
    lesson_source(key)  # Validate ID before reading anything.
    result = dict(id=key, kind="measured", badge="ĐO THẬT", sources=[], charts=[])
    try:
        sample = ev.ROOTS["sample"]
        if key in ("01", "02", "03"):
            packet_path = ev.resolve("sample", "receiver.csv")
            rows = csv_rows(packet_path)
            result["sources"].append(measured_source(packet_path))
            first = rows[0]
            t0 = int(first["t_arrival_rx_ns"])
            if key == "01":
                rtcp_path = ev.resolve("sample", "sender_rtcp.csv")
                result["sources"].extend([measured_source(rtcp_path), measured_source(VI / "01_CN_rtp_header.md")])
                result.update(header={k:first[k] for k in ("seq", "rtp_ts", "marker", "bytes")},
                              ssrc=next(r["ssrc"] for r in csv_rows(rtcp_path) if r["type"] == "SR"),
                              duration=(int(rows[-1]["t_arrival_rx_ns"])-t0)/1e9,
                              packets=[[(int(r["t_arrival_rx_ns"])-t0)/1e9, int(r["seq"])] for r in rows])
            elif key == "02":
                result["charts"] = [dict(labels=["Jitter (ms)"], x=[(int(r["t_arrival_rx_ns"])-t0)/1e9 for r in rows], ys=[[float(r["jitter_ts_units"])/90 for r in rows]], xunit="s", yunit="ms")]
                result["calculator"] = [{k:r[k] for k in ("seq", "transit_ts_units", "jitter_ts_units")} for r in rows[:7]]
            else:
                frame_path = ev.resolve("sample", "frames_rx.csv")
                frames = csv_rows(frame_path)
                result["sources"].append(measured_source(frame_path))
                offsets, used = [], []
                for row in frames:
                    media_ms = ((int(row["rtp_ts"])-int(first["rtp_ts"])) % 2**32)/90
                    if row["complete"] == "1" and row["t_complete_rx_ns"]:
                        offsets.append((int(row["t_complete_rx_ns"])-t0)/1e6-media_ms)
                    if row["t_playout_rx_ns"]:
                        used.append((int(row["t_playout_rx_ns"])-t0)/1e6-media_ms)
                used.sort()
                result.update(offsets=offsets, total=len(frames), complete=len(offsets), experiment_d=round(used[len(used)//2], 3),
                              note="INFERRED: tính lại deadline trên arrival CSV T3 loss5; mẫu số chỉ gồm frame hoàn chỉnh đã quan sát. Không tái tạo thí nghiệm jitter T4; không suy ra capture→AI từ hai đồng hồ.")
        elif key == "04":
            path = ev.resolve("cn-t3", "loss5/run1/receiver_rtcp.csv")
            rows = [r for r in csv_rows(path) if r["type"] == "RR" and r["fraction_lost"]]
            t0 = int(rows[0]["t_mono_ns"])
            result["sources"] = [measured_source(path)]
            result["charts"] = [dict(labels=["Fraction lost (%)", "netem loss 5%"], x=[(int(r["t_mono_ns"])-t0)/1e9 for r in rows], ys=[[100*float(r["fraction_lost"])/256 for r in rows], [5]*len(rows)], xunit="s", yunit="%"), dict(labels=["Cumulative lost (packets)"], x=[(int(r["t_mono_ns"])-t0)/1e9 for r in rows], ys=[[int(r["cum_lost"]) for r in rows]], xunit="s", yunit="packets")]
            result["note"] = "netem loss 5%: cấu hình T3/loss5, hw_tables.md. Fraction và cumulative có phạm vi khác nhau."
            result["sources"].append(measured_source(ev.resolve("cn-report", "hw_tables.md")))
        elif key in ("05", "06"):
            path = ev.resolve("cn-report", "hw_tables.md")
            source = path.read_text(encoding="utf-8")
            result["sources"] = [measured_source(path)]
            if key == "05":
                section = source.split("### CN-T3")[1].split("### CN-T4")[0]
                table = [[c.strip() for c in l.strip("|").split("|")] for l in section.splitlines() if re.match(r"\| (?:loss\d|ge5)", l)]
                result["categories"] = [r[0] for r in table]
                result["table"] = [["Condition", "Netem (cấu hình)", "Mất gói (đo, %)", "Mất frame (đo, %)"]] + [[r[0],r[2],f"{100*float(r[4]):.1f}",f"{100*float(r[6]):.1f}"] for r in table]
                result["charts"] = [dict(labels=["Mất gói (%)", "Mất frame (%)"], x=list(range(len(table))), ys=[[100*float(r[4]) for r in table],[100*float(r[6]) for r in table]], hist=True, xunit="condition", yunit="%")]
            else:
                table = [[c.strip() for c in l.strip("|").split("|")] for l in source.splitlines() if re.match(r"\| q(?:30|60|90) \|", l)]
                result.update(kind="mixed", badge="ĐO THẬT + MÔ PHỎNG")
                result["charts"] = [dict(labels=["Bitrate đo (Mb/s)"], x=[int(r[2]) for r in table], ys=[[float(r[5]) for r in table]], hist=True, xunit="quality", yunit="Mb/s")]
                result["simulation"] = json.loads((CONTENT/"widget_spec.json").read_text(encoding="utf-8"))["abr"]
                result["missing"] = "Chưa có dữ liệu đo CN-T8: chưa chạy ABR trên phần cứng. Timeline quality bên dưới là MÔ PHỎNG theo quy tắc trong Bài 06."
        elif key == "07":
            result.update(kind="simulated", badge="MÔ PHỎNG", config=json.loads((CONTENT/"widget_spec.json").read_text(encoding="utf-8"))["queue"],
                          sources=[measured_source(VI/"07_CN_fifo_vs_latest_value.md")], missing="Chưa có dữ liệu đo dạng chuỗi T7: CSV gốc chưa tìm thấy; bảng tổng hợp trong bài vẫn là nguồn đo. Mô hình dùng cùng đầu vào và cùng service time, FIFO có giới hạn.")
        elif key == "08":
            base = ev.ROOTS["os-study"] / "2026-10-30_os_t3_contention"
            ys, labels, sources = [], [], []
            for profile in ("P0", "P1"):
                for load in ("B0_idle", "B2_memrate_c23"):
                    counts = [0]*75
                    for rep in range(1, 4):
                        parent = base / f"E2_{profile}_{load}_latest_r{rep}/pipeline"
                        ref = ev.identify(parent/"summary.json")
                        summary_path = ev.resolve(ref["root"], ref["path"])
                        summary = json.loads(summary_path.read_text(encoding="utf-8"))
                        if summary.get("validity") != "OK" or summary.get("excluded"):
                            continue
                        ref = ev.identify(parent/"infer.csv")
                        path = ev.resolve(ref["root"], ref["path"])
                        sources.extend([measured_source(path), measured_source(summary_path)])
                        for row in csv_rows(path):
                            if row["status"] == "sent":
                                value = (int(row["t_done_ns"])-int(row["t_input_ns"]))/1e6
                                counts[min(74, max(0, int(value/10)))] += 1
                    if sum(counts):
                        labels.append(profile+" / "+load); ys.append(counts)
            if not ys:
                raise ev.EvidenceError("không có run E2 hợp lệ")
            result.update(sources=sources, charts=[dict(labels=labels, x=[i*10+5 for i in range(75)], ys=ys, hist=True, xunit="service ms", yunit="count")], note="Service = (t_done_ns − t_input_ns)/1e6, gồm cả chờ đầu vào; gộp r1–r3 hợp lệ, pty, không phải UART/MCU. Bin cuối ≥740 ms.")
        elif key == "09":
            path = ev.resolve("os-study", "2026-10-30_os_t4_policy/summary/E3B_per_condition.csv")
            rows = [r for r in csv_rows(path) if r["stressor"] == "B0_idle"]
            result.update(sources=[measured_source(path)], cases=[dict(policy=r["input_policy"], latency=float(r["delivery_p50_ms"]), interval=float(r["initialized_seconds"])*1000/float(r["rx_received"]), measured=float(r["aoi_time_average_ms"])) for r in rows], note="INFERRED: L + Y/2 chỉ là xấp xỉ cho giao đều; L ở đây là delivery P50, AoI đo là trung bình theo thời gian. pty; giữ các giới hạn trong bài.")
        elif key == "10":
            path = ev.resolve("supervisor", "missed_heartbeat_recovery_result.json")
            degrade = ev.resolve("supervisor", "degrade_and_recover_result.json")
            result.update(kind="simulated", badge="MÔ PHỎNG", sources=[measured_source(path), measured_source(degrade)], scenario=json.loads(path.read_text(encoding="utf-8")), degrade=json.loads(degrade.read_text(encoding="utf-8"))),
            result["images"] = [dict(root="supervisor", path=name) for name in ("healthy_timeline.png", "missed_heartbeat_recovery_timeline.png", "degrade_and_recover_timeline.png")]
            result["report"] = json.loads(ev.resolve("supervisor", "test_results.json").read_text(encoding="utf-8"))
            result["traces"] = {}
            for name, filename in (("scenario", "missed_heartbeat_recovery.csv"), ("degrade", "degrade_and_recover.csv")):
                trace_path = ev.resolve("supervisor", filename)
                result["traces"][name] = [{key:float(row[key]) for key in ("time_ms", "state", "reason", "heartbeat_age_ms", "source_age_ms")} for row in csv_rows(trace_path)]
                result["sources"].append(measured_source(trace_path))
            result["sources"].append(measured_source(ev.resolve("supervisor", "test_results.json")))
            result["note"] = "Stateflow đã chạy: không phải đo chân LED. Animation dùng transition_ms/state_sequence trong JSON và một điểm heartbeat vắng từ CSV trước FAULT; không điều khiển MCU."
        result["sources"].append(dict(path=str(CONTENT/"widget_spec.json"), url="/lesson-assets/widget_spec.json")) if key in ("06", "07") else None
    except (OSError, ValueError, KeyError, IndexError, StopIteration) as error:
        result.update(kind="missing", badge="CHƯA CÓ DỮ LIỆU ĐO", missing="Chưa có dữ liệu đo: " + str(error), charts=[])
    return result


def demo_steps():
    # Seven grouped segments plus the final limitations; timing sums to 600 s.
    definitions = [
        ("Luồng dữ liệu & RTP",105,"01","packets","Pi gửi video bằng RTP qua UDP sang laptop. Đây là replay log phần cứng thật, loss 5%. Sequence number cho biết khoảng trống; timestamp là đồng hồ media."),
        ("RTCP RR & loss",60,"04","rtcp","RR đầu ghi fraction_lost = 13: 13/256 ≈ 5.1%. Netem đặt loss 5%; hai mẫu số và khoảng đo cần được phân biệt."),
        ("Jitter & playout",120,"03","playout","J làm mượt mỗi gói với hệ số 1/16. Thử slider D trên arrival T3; bảng T4 trong bài mới là số đo jitter experiment: 93.5% muộn tại D=20 và 0% tại D=100."),
        ("Bitrate adaptation",60,"06","bitrate","CN-T8 chưa chạy phần cứng. Timeline quality là MÔ PHỎNG; bitrate q30/60/90 là số đo trong hw_tables.md."),
        ("FIFO, latest & AoI",105,"07","queues","Hai hàng đợi cùng đầu vào và cùng service time. Đây là MÔ PHỎNG; số đo tổng hợp T7 là 0.623 s với FIFO và 0.204 s với latest. Xem tiếp Bài 09: chọn queue trước khâu inference."),
        ("Scheduling & contention",45,"08","histogram","Histogram lấy từ t_done − t_input của E2 hợp lệ, gồm cả chờ đầu vào, liên kết pty. Memory stress làm service chậm khoảng sáu lần; nguyên nhân memory bus là INFERRED."),
        ("Supervisor: còn sống, còn tươi",60,"10","states","Heartbeat và tuổi kết quả được kiểm tra riêng. FAILSAFE chốt đến khi rearm. Animation và PNG là Stateflow; bảng trong bài là trạng thái MCU đo thật, chưa phải thời gian chân LED."),
        ("Giới hạn & kết luận",45,"09","aoi","ABR chưa có hardware run. OS ít lần lặp, một số run bị FLAGGED do under-voltage. Thời gian chân LED là UNKNOWN. Công thức AoI L + Y/2 là INFERRED. Các dòng FIGURE PENDING thuộc nội dung gốc; PNG Stateflow được bổ sung riêng."),
    ]
    return [dict(id=i+1, title=t, seconds=s, lesson=l, panel=p, profile="os" if int(l)>=8 else "cn", mode="simulated" if l in ("07","10") else "mixed" if l == "06" else "replay", note=n) for i,(t,s,l,p,n) in enumerate(definitions)]


def route(target):
    """Return (status, body, content type), or None for the original hub routes."""
    from urllib.parse import parse_qs, unquote
    parsed = urlsplit(target)
    path = parsed.path
    query = parse_qs(parsed.query, keep_blank_values=True)
    q = lambda name, default=None: query.get(name, [default])[0]
    try:
        if path == "/lessons":
            return 200, lesson_page(), "text/html; charset=utf-8"
        if path.startswith("/lessons/"):
            return 200, lesson_page(path[9:]), "text/html; charset=utf-8"
        if path in ("/evidence", "/demo"):
            active = path[1:]
            title = "Bằng chứng" if active == "evidence" else "Demo cho thầy"
            body = '<main class="workspace-page"><div class="eyebrow">'+("ĐỐI CHIẾU TỪ NGUỒN" if active=="evidence" else "10 PHÚT · 8 BƯỚC")+'</div><h1>'+title+'</h1><div id="'+active+'-app" aria-live="polite">Đang đọc dữ liệu…</div></main>'
            return 200, shell(title, body, active), "text/html; charset=utf-8"
        if path.startswith("/lesson-assets/"):
            relative = path[len("/lesson-assets/"):]
            if unquote(relative) != relative or "\\" in relative or ":" in relative or any(p in ("", ".", "..") for p in relative.split("/")):
                raise ev.EvidenceError("invalid asset")
            asset = CONTENT/relative
            if not asset.resolve().is_relative_to(CONTENT.resolve()) or not asset.is_file() or asset.suffix not in (".svg", ".png", ".json"):
                raise ev.EvidenceError("unknown asset")
            return 200, asset.read_bytes(), {".svg":"image/svg+xml", ".png":"image/png", ".json":"application/json"}[asset.suffix]
        if path in ("/learning.css", "/learning.js", "/panels.js"):
            return 200, (STATIC/path[1:]).read_bytes(), "text/css; charset=utf-8" if path.endswith(".css") else "text/javascript; charset=utf-8"
        result = None
        if path == "/api/lessons":
            result = lessons()
        elif path.startswith("/api/widgets/"):
            result = widget_data(path.rsplit("/",1)[1])
        elif path == "/api/demo":
            result = dict(source=str(VI/"INDEX.md"), steps=demo_steps())
        elif path == "/api/evidence/list":
            result = ev.listing(q("root"), q("path", ""), int(q("page", "1")))
        elif path in ("/api/evidence/preview", "/api/evidence/provenance", "/api/evidence/raw"):
            root, relative = q("root"), q("path", "")
            if path.endswith("/preview"):
                result = ev.preview(root, relative, int(q("page","1")), q("column"), q("time"))
            elif path.endswith("/provenance"):
                result = ev.provenance(root, relative)
            else:
                file = ev.resolve(root, relative)
                # Raw endpoint is only for inline images; text/CSV use bounded previews.
                if file.suffix.lower() not in (".png", ".svg", ".jpg", ".jpeg") or file.stat().st_size > 20*1024*1024:
                    raise ev.EvidenceError("raw access is for images up to 20 MB")
                return 200, file.read_bytes(), ev.mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        if result is not None:
            return 200, json.dumps(result, ensure_ascii=False, allow_nan=False).encode(), "application/json; charset=utf-8"
        return None
    except (ev.EvidenceError, ValueError, OSError) as error:
        return 404, json.dumps(dict(error=str(error)), ensure_ascii=False).encode(), "application/json; charset=utf-8"
