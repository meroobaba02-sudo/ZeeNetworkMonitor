"""Synthetic scheduler/UI/cleanup measurements; not a real-device benchmark."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,json,time,tempfile,threading,platform
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from zee.core import Store,Device
from zee.gui import Window
from zee.ping import Result
from zee.resources import Usage,memory_mb


def run(count,app):
    base=Path(tempfile.mkdtemp(prefix='zee-benchmark-'));store=Store(base/'monitor.sqlite3')
    store.set_setting('auto_cleanup',False)
    for i in range(count):store.save(Device(id=str(i),name=f'Fixture {i}',host='127.0.0.1',interval=30))
    with store.db:
        store.db.executemany('INSERT INTO samples(device,at,success,latency,error) VALUES(?,?,?,?,?)',[(str(i),time.time()-600+j,1,2,'') for i in range(count) for j in range(100)])
        store.db.executemany('INSERT INTO samples(device,at,success,latency,error) VALUES(?,?,?,?,?)',[('expired',1,1,2,'')]*25000)
    usage=Usage();started=time.monotonic();w=Window(store);w.buzzer.sound_fn=lambda *args:None;w.show();app.processEvents()
    startup=time.monotonic()-started;lock=threading.Lock();active=0;peak=0;completed=[]
    def fake(device):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active)
        # A quarter of targets simulate a slower unsuccessful response.
        slow=int(device.id)%4==0;time.sleep(.02 if slow else .003)
        with lock:active-=1
        return Result(not slow,None if slow else 3,error='Synthetic no reply' if slow else '')
    w.engine.probe_fn=fake;w.engine.result.connect(lambda *args:completed.append(args[0]))
    ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start(20)
    started=time.monotonic();w.ping_all();deadline=started+30
    while (len(completed)<count or w.cleaner.running) and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert len(completed)==count
    check_seconds=time.monotonic()-started
    clean_start=time.monotonic();w.prune(manual=True)
    while w.cleaner.running and time.monotonic()-clean_start<30:app.processEvents();time.sleep(.002)
    assert not w.cleaner.running
    result=store.setting('last_cleanup',{})
    assert result.get('deleted')==25000,result
    cleanup_wall=time.monotonic()-clean_start
    w.refresh_states();metrics=usage.sample();rss=memory_mb();timer.stop()
    gaps=[b-a for a,b in zip(ticks,ticks[1:])]
    start=time.monotonic();w.close();close_seconds=time.monotonic()-start;app.processEvents()
    return {'devices':count,'history_rows_per_device':100,'expired_rows':25000,'window_start_seconds':round(startup,3),'all_checks_seconds':round(check_seconds,3),'peak_ping_workers':peak,'cleanup_wall_seconds':round(cleanup_wall,3),'cleanup_worker_seconds':result.get('seconds'),'max_heartbeat_gap_ms':round(max(gaps,default=0)*1000,1),'heartbeat_samples':len(ticks),'close_seconds':round(close_seconds,3),'working_set_mb':round(rss,1) if rss is not None else None,**metrics}


if __name__=='__main__':
    app=QApplication([]);output=Path(sys.argv[1] if len(sys.argv)>1 else 'benchmark_phase3.json')
    report={'kind':'synthetic; no physical network requests','platform':platform.platform(),'python':platform.python_version(),'cpu_count':os.cpu_count(),'cpu_basis':'100 percent = one CPU core; whole startup/check/cleanup scenario','scope':'working-set readings are process-wide and cumulative across scenarios; heartbeat samples cover checks and cleanup, not synchronous startup','rows':[run(n,app) for n in (10,50,100,250)],'limitations':'Cloud/CI machine, not the customer old i5 Windows 10. Short simulated delays do not model real DNS, radio, TLS or maximum network timeouts.'}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
