import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from zee.core import Device,Store,Station,TYPES
from zee.dashboard import speed_statistics,dashboard_text
from zee.gui import Window
from PySide6.QtWidgets import QApplication

def test_statistics_keep_capacity_and_traffic_separate():
    text=speed_statistics([{'rate_kind':'Traffic estimate','download_mbps':2},{'rate_kind':'Controlled download','download_mbps':10},{'rate_kind':'Traffic estimate','download_mbps':4},{'download_mbps':float('nan')}])
    assert 'Traffic estimate download: 2 samples, min 2.00, avg 3.00, max 4.00' in text
    assert 'Controlled download download: 1 samples' in text
    assert 'nan' not in text

def test_ping_online_never_implies_wireless_or_internet_health():
    d=Device(kind=TYPES[1],wan=1)
    text=dashboard_text([d],{d.id:'Online'},{},{},1,{},{},time.time())
    assert 'Wireless: good 0' in text and 'WAN Internet: online 0' in text

def test_stale_metrics_not_healthy_or_active_alert():
    d=Device(kind=TYPES[1],wan=1);now=time.time()
    text=dashboard_text([d],{d.id:'Online'},{d.id:{'at':now-1000,'internet':'Online','metrics':{'signal_dbm':-50}}},{},1,{},{d.id:'bad'},now)
    assert 'Wireless: good 0' in text and 'Active device alerts 0' in text

def test_tower_filter_applied_before_event_limit(tmp_path):
    app=QApplication.instance() or QApplication([])
    store=Store(tmp_path/'test.db');tower=Station(name='Target');store.save_station(tower)
    target=Device(name='Target radio',station_id=tower.id,enabled=False);other=Device(name='Other',enabled=False);store.save(target);store.save(other)
    store.event(target.id,'alarm','target retained')
    for _ in range(1005):store.event(other.id,'alarm','other traffic')
    w=Window(store)
    try:
        w.event_tower.setCurrentIndex(w.event_tower.findData(tower.id))
        rows=w.event_rows();assert any(r['message']=='target retained' for r in rows)
        assert all(r['device'] in (target.id,tower.id) for r in rows)
        w.event_search.setText('retained');assert len(w.event_rows())==1
        assert not w.summary.isHidden()
    finally:w.close();store.db.close()
