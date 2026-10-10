import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from zee.core import Device,Store,TYPES
from zee.gui import Window
from zee.wan import wan_health,route_report
from zee.wan_dialog import WanDialog

def device():return Device(name='WAN fixture',host='127.0.0.1',kind=TYPES[0],wan=1,integration={'wan_verified':True,'min_download_mbps':5})

def test_router_reply_does_not_prove_internet_and_stale_is_unknown():
    d=device();now=time.time()
    assert wan_health(d,'Online',{'at':now,'internet':'Offline — external check failed'},{},now)[0]=='Offline'
    assert wan_health(d,'Online',{'at':now-1000,'internet':'Online'},{},now)[0]=='Unknown'
    assert wan_health(d,'Online',{}, {},now)[0]=='Unknown'

def test_degraded_thresholds_and_unknown_router_are_separate():
    d=device();now=time.time();row={'at':now,'internet':'Online','internet_latency_ms':2000}
    assert wan_health(d,'Online',row,{},now)[0]=='Degraded'
    row['internet_latency_ms']=100
    assert wan_health(d,'No reply',row,{},now)[0]=='Degraded'
    assert wan_health(d,'Online',row,{'at':now,'download_mbps':1},now)[0]=='Degraded'
    assert wan_health(d,'Unknown',row,{},now)[0]=='Online'

def test_loopback_readonly_route_selection():
    report=route_report('127.0.0.1','127.0.0.1')
    assert 'OS-selected local source: 127.0.0.1' in report
    assert 'No UDP data was sent' in report

def test_speed_success_does_not_clear_external_failure_and_source_edit_invalidates(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'wan.db');d=device();store.save(d);w=Window(store)
    try:
        w.notify=lambda *args:None
        w.measurements.latest[d.id]={'at':time.time(),'internet':'Offline — external check failed','metrics':{}}
        w.measurements.pending[(d.id,True)]=d;w.measurements.due[(d.id,True)]=time.monotonic()+900
        w.measurements.complete((d,True,w.engine.generation),{'at':time.time(),'download_mbps':10,'rate_kind':'Controlled download throughput'})
        assert 'External endpoint check failed' in w.telemetry_alerted[d.id]
        dialog=WanDialog(w,d);dialog.source.setText('127.0.0.1')
        assert not dialog.value().integration['wan_verified']
        dialog.accept();assert d.id not in w.measurements.latest and d.id not in w.measurements.speed_latest
    finally:w.close();store.db.close()
