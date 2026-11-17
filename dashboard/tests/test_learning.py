import asyncio
import hashlib
import json
from pathlib import Path
import re

import pytest

from dashboard import evidence as ev
from dashboard import learning as web
from dashboard.hub import Hub, Server


def test_publication_exact_and_every_image_resolves():
    for item in json.loads((web.CONTENT / 'publication.json').read_text(encoding='utf-8')):
        assert hashlib.sha256((web.CONTENT/item['file']).read_bytes()).hexdigest() == item['sha256']
    assert [item['id'] for item in web.lessons()] == [f'{i:02}' for i in range(1,11)]
    for key in ['index'] + [item['id'] for item in web.lessons()]:
        code, body, mime = web.route('/lessons/'+key)
        assert code == 200 and 'text/html' in mime
        rendered = body.decode()
        assert '<h1' in rendered
        assert 'src=""' not in rendered
        assert rendered.count('class="diagram"') == web.lesson_source(key).count('```mermaid')
        for asset in re.findall(r'<img[^>]+src="([^"]+)"', rendered):
            assert web.route(asset)[0] == 200
        if key != 'index':
            assert 'Câu hỏi kiểm tra' in rendered and 'Xem đáp án' in rendered


def test_markdown_escapes_untrusted_html_and_urls():
    rendered = web.markdown('<script>alert(1)</script>\n\n[x](javascript:alert)\n\n`<svg onload=x>`')
    assert '<script>' not in rendered and 'href="javascript:' not in rendered
    assert '&lt;svg' in rendered


@pytest.mark.parametrize('value', ['../secret.csv','/secret.csv','C:/secret.csv','C:\\secret.csv','\\\\host\\share','a/../../secret.csv','%2e%2e/secret.csv','%252e%252e/secret.csv','a%2fb.csv','a\\b.csv','a//b.csv','./data.csv','data.csv:secret','data.csv.','data.csv ','a\x00.csv'])
def test_evidence_rejects_traversal(tmp_path, monkeypatch, value):
    monkeypatch.setitem(ev.ROOTS, 'fixture', tmp_path)
    with pytest.raises(ev.EvidenceError):
        ev.resolve('fixture', value)


def test_evidence_symlink_and_junction(tmp_path, monkeypatch):
    monkeypatch.setitem(ev.ROOTS, 'fixture', tmp_path)
    target = tmp_path/'real.csv'; target.write_text('t,x\n0,5\n')
    link = tmp_path/'link.csv'
    try:
        link.symlink_to(target)
    except OSError:
        # Windows accounts without SeCreateSymbolicLinkPrivilege: exercise an
        # actual directory junction (also a reparse point), without admin rights.
        import subprocess
        folder = tmp_path/'real'; folder.mkdir(); (folder/'data.csv').write_text('x\n1\n')
        junction = tmp_path/'junction'
        # Explicit file handles work in restricted Windows hosts where PIPE
        # handle duplication is unavailable.
        with (tmp_path/'junction.log').open('w') as output:
            outcome = subprocess.run(['cmd','/c','mklink','/J',str(junction),str(folder)], stdin=subprocess.DEVNULL, stdout=output, stderr=output)
        assert outcome.returncode == 0, (tmp_path/'junction.log').read_text()
        with pytest.raises(ev.EvidenceError):
            ev.resolve('fixture','junction/data.csv')
    else:
        with pytest.raises(ev.EvidenceError):
            ev.resolve('fixture','link.csv')


def test_evidence_preview_pagination_plot_and_hash(tmp_path, monkeypatch):
    monkeypatch.setitem(ev.ROOTS, 'fixture', tmp_path)
    content = 'time_s,value,label\n'+''.join(f'{i},{i*2},a\n' for i in range(113))
    (tmp_path/'data.csv').write_text(content)
    preview = ev.preview('fixture','data.csv',2,'value')
    assert preview['total'] == 113 and len(preview['rows']) == 50
    assert preview['rows'][0]['value'] == '100'
    assert preview['plot'][10] == [10,20]
    assert 'label' not in preview['numeric']
    assert ev.provenance('fixture','data.csv')['sha256'] == hashlib.sha256((tmp_path/'data.csv').read_bytes()).hexdigest()
    (tmp_path/'test.log').write_text('\n'.join(str(i) for i in range(350)))
    assert ev.preview('fixture','test.log')['text'].splitlines()[0] == '150'
    with pytest.raises(ev.EvidenceError):
        ev.preview('fixture','data.csv',column='absent')


def test_widgets_measured_and_simulated_are_separate():
    for i in range(1,11):
        widget = web.widget_data(f'{i:02}')
        assert widget['kind'] != 'missing', widget
        assert widget['sources']
    assert web.widget_data('07')['kind'] == 'simulated'
    assert web.widget_data('10')['badge'] == 'MÔ PHỎNG'
    playout = web.widget_data('03')
    assert playout['experiment_d'] == pytest.approx(100, abs=.01)
    assert playout['complete'] <= playout['total']
    jitter = web.widget_data('02')
    assert jitter['calculator'][1]['jitter_ts_units'] == '2.25'
    assert sum(web.widget_data('08')['charts'][0]['ys'][0]) == 2700


def test_missing_measurement_has_reason_not_curve(monkeypatch, tmp_path):
    monkeypatch.setitem(ev.ROOTS, 'sample', tmp_path)
    data = web.widget_data('02')
    assert data['kind'] == 'missing' and data['charts'] == []
    assert data['missing'].startswith('Chưa có dữ liệu đo:')


def test_demo_data_matches_lessons_and_ten_minutes():
    steps = web.demo_steps()
    assert 6 <= len(steps) <= 8
    assert sum(s['seconds'] for s in steps) == 600
    for step in steps:
        assert web.lesson_source(step['lesson']) and step['note']
        assert step['profile'] in ('cn','os')
    assert 'chưa chạy phần cứng' in steps[3]['note']


def test_learning_http_routes_and_encoded_attacks():
    async def scenario():
        app = Server(Hub('replay'))
        listener = await asyncio.start_server(app.handle,'127.0.0.1',0)
        port = listener.sockets[0].getsockname()[1]
        try:
            for path, expected in [('/lessons',200),('/lessons/01',200),('/lessons/11',404),('/demo',200),('/evidence',200),('/api/demo',200),('/api/widgets/03',200),('/api/evidence/list',200),('/api/evidence/preview?root=sample&path=%2e%2e%2fREADME.md',404),('/api/evidence/preview?root=sample&path=%252e%252e%252fREADME.md',404),('/api/evidence/preview?root=sample&path=C%3A%5Csecret.csv',404),('/lesson-assets/../hub.py',404),('/api/evidence/preview?root=unknown&path=x.csv',404)]:
                reader, writer = await asyncio.open_connection('127.0.0.1',port)
                writer.write(f'GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n'.encode())
                response = await asyncio.wait_for(reader.read(),5)
                assert f'HTTP/1.1 {expected}'.encode() in response, (path,response[:200])
                writer.close(); await writer.wait_closed()
        finally:
            listener.close(); await listener.wait_closed(); await app.close()
    asyncio.run(scenario())
