import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
import pytest
from zee.core import Store,Device
from zee.engine import Engine
from zee.ping import Result
from zee.gui import Window,DeviceDialog

@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


def pump(app,until,timeout=4):
    start=time.monotonic()
    while not until() and time.monotonic()-start<timeout:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert until()


def test_workers_no_overlap_main_thread(app):
    import threading
    active=set();overlaps=[];seen=[];lock=threading.Lock()
    def fake(d):
        with lock:
            if d.id in active: overlaps.append(d.id)
            active.add(d.id)
        time.sleep(.03)
        with lock: active.remove(d.id)
        return Result(True,2)
    e=Engine(probe_fn=fake)
    d=Device(id='one',name='One',host='127.0.0.1')
    def receive(*args):
        assert QThread.currentThread()==app.thread()
        seen.append(args)
    e.result.connect(receive)
    assert e.submit(d)
    assert not e.submit(d)
    pump(app,lambda:len(seen)==1)
    assert not overlaps and not e.pending
    e.shutdown()


def test_dashboard_queue_alerts_and_obsolete_results(app,tmp_path):
    s=Store(tmp_path/'db')
    for i in range(12): s.save(Device(name=f'Device {i}',host='127.0.0.1',failure_threshold=2))
    w=Window(s)
    w.engine.probe_fn=lambda d:Result(True,4)
    w.ping_all()
    pump(app,lambda:len(w.latest)==12 and not w.engine.pending and not w.requested)
    assert len(s.db.execute('SELECT * FROM samples').fetchall())==12
    d=w.devices[0]
    w.notifications.setChecked(False)
    w.result(d.id,d,Result(False,error='No reply'))
    w.result(d.id,d,Result(False,error='No reply'))
    w.result(d.id,d,Result(False,error='No reply'))
    assert len(s.events(d.id,search='No reply',limit=100))>=1
    assert len([r for r in s.events(d.id) if r['kind']=='alert'])==1
    w.result(d.id,d,Result(True,3))
    assert len([r for r in s.events(d.id) if r['kind']=='alert'])==2
    count=s.stats(d.id)['n']
    changed=Device(**{**d.__dict__,'host':'127.0.0.2'})
    s.save(changed); w.reload()
    w.result(d.id,d,Result(True,3))
    assert s.stats(d.id)['n']==count
    w.search.setText('Device 1')
    assert w.table.rowCount()==3
    w.tabs.setCurrentIndex(2)
    w.topology.grab()
    w.close()


def test_editor_roundtrip(app):
    d=Device(id='x',name='Rocket',host='192.168.1.20',location='Lahore',kind='Rocket M5 / wireless radio')
    editor=DeviceDialog([d],d)
    assert editor.device()==d
    editor.close()


def test_stop_and_graceful_shutdown(app):
    calls=[]
    def fake(d):
        calls.append(d.id);time.sleep(.03);return Result(True,1)
    e=Engine(probe_fn=fake)
    e.devices=[Device(id='x',host='127.0.0.1',interval=1)]
    e.start();e.stop()
    pump(app,lambda:not e.pending)
    for _ in range(3):e.tick()
    assert calls==['x']
    e.shutdown()


def test_errors_not_counted_as_outage_and_stale_state(app,tmp_path):
    s=Store(tmp_path/'db')
    d=Device(name='Radio',host='127.0.0.1');s.save(d)
    w=Window(s)
    w.result(d.id,d,Result(False,error='ping missing',infrastructure_error=True))
    assert w.state(d)=='Probe error' and s.stats(d.id)['n']==0
    w.result(d.id,d,Result(True,200))
    assert w.state(d)=='Warning'
    w.latest[d.id]['at']=time.time()-100
    assert w.state(d)=='Unknown'
    w.requested.add(d.id)
    d.enabled=False;s.save(d);w.reload()
    assert d.id not in w.requested
    w.close()


def test_restart_does_not_show_old_state_as_fresh(app,tmp_path):
    s=Store(tmp_path/'db')
    d=Device(name='Old',host='127.0.0.1');s.save(d)
    s.record(d.id,Result(True,2))
    w=Window(s)
    assert w.state(d)=='Unknown'
    assert w.latest[d.id]['latency']==2
    w.close()
