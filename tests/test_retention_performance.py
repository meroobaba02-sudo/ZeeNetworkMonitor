import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,sqlite3,time,threading
from pathlib import Path
import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication
from zee.core import Store,Device
from zee.engine import Engine
from zee.ping import Result
from zee.retention import Policy,cleanup,history_hours,Cleaner,trim_diagnostics
from zee.gui import Window


@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


def pump(app,until,seconds=5):
    start=time.monotonic()
    while not until() and time.monotonic()-start<seconds:
        app.processEvents();time.sleep(.003)
    app.processEvents();assert until()


def test_retention_defaults_and_legacy_customization_restart(tmp_path):
    s=Store(tmp_path/'db');assert history_hours(s)==48
    s.set_setting('retention',7);assert history_hours(s)==168
    s.set_setting('detail_hours',72);s.close()
    s=Store(tmp_path/'db');assert history_hours(s)==72;s.close()


def test_cleanup_expires_only_old_details_and_protects_important_events(tmp_path):
    s=Store(tmp_path/'db');now=time.time();old=now-100*86400
    for at in (old,now-49*3600,now-47*3600):s.record('d',Result(True,2),at)
    for kind,device in [('status','old'),('alert','resolved'),('alert','active'),('audit','owner'),('security','owner'),('licence','owner'),('status','pinned')]:s.event(device,kind,device,old)
    s.event('ordinary','status','fresh',now)
    pin=s.events(device='pinned')[0]['id'];s.pin_event(pin)
    s.set_setting('active_incident_devices',['active'])
    r=cleanup(s.path,Policy(),now=now)
    assert r['deleted']==4
    assert len(s.samples('d'))==1
    assert {r['device'] for r in s.events()}=={'active','owner','pinned','ordinary'}
    assert s.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    s.pin_event(pin);cleanup(s.path,Policy(incident_days=0),now=now)
    assert not s.events(device='pinned');assert s.events(device='active');s.close()


def test_archive_has_deleted_records_and_warning_never_deletes_fresh(tmp_path):
    s=Store(tmp_path/'db');s.record('d',Result(True,1),1);s.record('d',Result(True,1))
    r=cleanup(s.path,Policy(archive=True,disk_warning_mb=0))
    assert not r['disk_warning'];assert len(s.samples('d'))==1
    archived=Store(r['archive']);assert len(archived.samples('d'))==2;archived.close();s.close()


def test_cancelled_cleanup_keeps_data_and_bounded_pass_can_resume(tmp_path):
    s=Store(tmp_path/'db');s.record('d',Result(True,1),1)
    cancel=threading.Event();cancel.set();assert cleanup(s.path,Policy(),cancel)['cancelled']
    assert len(s.samples('d'))==1
    assert cleanup(s.path,Policy(),budget=0)['more'];assert len(s.samples('d'))==1
    assert cleanup(s.path,Policy())['deleted']==1;s.close()


def test_diagnostic_multiline_record_age(tmp_path):
    now=time.time();old=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(now-49*3600));new=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(now))
    p=tmp_path/'diagnostic.log';p.write_text(old+',000 ERROR expired\nold traceback\n'+new+',000 INFO current\ncurrent detail\n')
    trim_diagnostics(tmp_path,now-48*3600)
    assert 'expired' not in p.read_text() and 'old traceback' not in p.read_text()
    assert 'current detail' in p.read_text()


def test_background_cleanup_does_not_share_gui_connection(app,tmp_path):
    s=Store(tmp_path/'db')
    with s.db:s.db.executemany('INSERT INTO samples(device,at,success,latency,error) VALUES(?,?,?,?,?)',[('old',1,1,1,'')]*6000)
    cleaner=Cleaner();results=[]
    def done(r):
        assert QThread.currentThread()==app.thread();results.append(r)
    cleaner.finished.connect(done)
    assert cleaner.start(s.path,Policy());assert not cleaner.start(s.path,Policy())
    s.event('gui','status','GUI can write while cleanup works')
    pump(app,lambda:bool(results));assert not results[0].get('error')
    assert results[0]['deleted']==6000;assert s.events(device='gui')
    cleaner.shutdown();s.close()


def test_database_lock_reports_controlled_failure_without_removing_records(app,tmp_path):
    s=Store(tmp_path/'db');s.record('old',Result(True,1),1)
    s.db.execute('BEGIN IMMEDIATE')
    cleaner=Cleaner();results=[];cleaner.finished.connect(results.append)
    assert cleaner.start(s.path,Policy());pump(app,lambda:bool(results),seconds=2)
    assert results[0].get('error') and len(s.samples('old'))==1
    s.db.rollback();cleaner.shutdown();s.close()


def test_resource_sample_is_finite_and_process_only():
    from zee.resources import Usage
    sample=Usage().sample();assert sample['cpu_percent_one_core']>=0
    assert sample['working_set_mb'] is None or sample['working_set_mb']>0


def test_retry_backoff_and_cancelled_retry_wait(app):
    calls=[]
    def probe(d):calls.append(d.id);return Result(len(calls)>=2,3)
    engine=Engine(probe_fn=probe);engine.configure(limit=1,retries=2,retry_delay=.1,minimum_interval=60)
    d=Device(id='one',host='127.0.0.1',interval=5)
    results=[];engine.result.connect(lambda *args:results.append(args[-1]))
    assert engine.submit(d);assert not engine.submit(Device(id='two',host='127.0.0.1'))
    pump(app,lambda:bool(results));assert results[0].success and len(calls)==2
    assert engine.due[d.id]-time.monotonic()>55
    engine.probe_fn=lambda d:Result(False,error='No reply');engine.configure(retries=3,retry_delay=10)
    assert engine.submit(d);time.sleep(.02);start=time.monotonic();engine.stop()
    pump(app,lambda:not engine.pending);assert time.monotonic()-start<1
    engine.shutdown()


def test_infrastructure_error_not_retried_and_limits_clamped(app):
    calls=[];engine=Engine(probe_fn=lambda d:(calls.append(d.id) or Result(False,infrastructure_error=True)))
    engine.configure(limit=999,retries=999);assert engine.limit==16 and engine.retries==3
    engine.submit(Device(id='one',host='127.0.0.1'));pump(app,lambda:not engine.pending)
    assert calls==['one'];engine.shutdown()


def test_manual_cleanup_works_with_auto_disabled_and_pagination(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False)
    for i in range(205):s.save(Device(name=f'R{i}',host='127.0.0.1'))
    s.record('old',Result(True,1),1)
    w=Window(s)
    try:
        assert not w.cleaner.running and len(s.samples('old'))==1
        assert w.table.rowCount()==200;w.table_page(1);assert w.table.rowCount()==5
        w.prune(manual=True);pump(app,lambda:not w.cleaner.running)
        assert not s.samples('old')
        w.measurements.pending[('one',False)]=Device(id='one')
        assert not w.measurements.submit(Device(id='one',host='127.0.0.1'),speed=True)
        w.measurements.pending.clear()
    finally:w.close()


def test_refresh_cache_and_coalesced_results_keep_immediate_alarm(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('alarm_delay_seconds',0);s.set_setting('auto_cleanup',False);d=Device(name='R',host='127.0.0.1',failure_threshold=1);s.save(d)
    w=Window(s);w.buzzer.sound_fn=lambda *args:None
    try:
        renders=[];original=w.render_table;w.render_table=lambda:(renders.append(1),original())
        for _ in range(10):w.result(d.id,d,Result(False,error='No reply'))
        assert not renders and w.buzzer.playing
        w.refresh_states();assert len(renders)==1 and s.stats(d.id)['n']==10
        w.refresh_states();assert len(renders)==1
        w.store.set_setting('minimum_interval',60);w.apply_performance()
        w.latest[d.id]['at']=time.time()-60;assert w.state(d)=='No reply'
    finally:w.close()


def test_minimize_policy_default_continues_and_opt_in_resumes(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);w=Window(s);w.show();app.processEvents()
    try:
        w.engine.start();w.showMinimized();app.processEvents();assert w.engine.running
        w.showNormal();app.processEvents();s.set_setting('pause_minimized',True)
        w.showMinimized();app.processEvents();assert not w.engine.running and w._resume_minimized
        w.showNormal();app.processEvents();assert w.engine.running
    finally:w.close()
