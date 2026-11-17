import pytest

from dashboard import evidence as ev


def test_nanosecond_plot_uses_elapsed_seconds_and_preserves_raw_table(tmp_path, monkeypatch):
    monkeypatch.setitem(ev.ROOTS, 'fixture', tmp_path)
    (tmp_path/'arrival.csv').write_text('t_arrival_ns,jitter\n1211741650252307,2\n1211741750252307,3\n')
    data = ev.preview('fixture', 'arrival.csv', column='jitter')
    assert data['plot'][0] == [0, 2]
    assert data['plot'][1] == pytest.approx([.1, 3])
    assert data['rows'][0]['t_arrival_ns'] == '1211741650252307'
    assert data['plot_xunit'] == 's (elapsed)'
    assert 'cùng một đồng hồ' in data['time_note']


def test_non_time_numeric_column_is_not_relabelled_seconds(tmp_path, monkeypatch):
    monkeypatch.setitem(ev.ROOTS, 'fixture', tmp_path)
    (tmp_path/'quality.csv').write_text('quality,bitrate\n30,.679\n90,1.266\n')
    data = ev.preview('fixture', 'quality.csv', column='bitrate', time_column='quality')
    assert data['plot'] == [[30,.679],[90,1.266]]
    assert data['time_origin'] is None
    assert data['plot_xunit'] == 'quality'
