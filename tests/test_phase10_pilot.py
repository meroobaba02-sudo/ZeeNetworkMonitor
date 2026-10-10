"""Synthetic fixtures verify pilot tooling, never certify a physical network."""
import json,time,copy
from types import SimpleNamespace
from pathlib import Path
import pytest
from zee.pilot import PilotSession,SCENARIOS,SAMPLE_LIMIT,validate_document,snapshot,atomic_json
from zee.core import Store,Device


def test_new_pilot_has_no_fake_pass_or_release_approval(tmp_path):
    session=PilotSession(tmp_path)
    assert all(x['status']=='Not performed' for x in session.document['results'].values())
    review=session.review();assert not review['ready_for_owner_review'] and not review['commercial_release_approved'] and len(review['blockers'])>len(SCENARIOS)


def test_saved_results_restart_and_interrupted_capture_preserved(tmp_path):
    session=PilotSession(tmp_path);session.record('endpoint',status='Pass',note='Controlled fixture evidence',detection_s=15,false_positive=0,false_negative=0)
    session.document['capture'].update(state='Recording',started=time.time());session.save()
    reopened=PilotSession(tmp_path)
    assert reopened.document['results']['endpoint']['detection_s']==15 and reopened.document['capture']['state']=='Interrupted'
    old_id=reopened.document['session'];reopened.reset()
    assert (tmp_path/('pilot-archive-'+old_id+'.json')).is_file() and reopened.document['session']!=old_id


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,True,'5'])
def test_bad_delay_cannot_replace_saved_evidence(tmp_path,value):
    session=PilotSession(tmp_path);session.save();before=session.path.read_bytes()
    with pytest.raises(ValueError):session.record('endpoint',status='Pass',note='Measured fixture result',detection_s=value)
    assert session.path.read_bytes()==before and session.document['results']['endpoint']['status']=='Not performed'


def test_pass_needs_evidence_and_fault_delays_are_review_blockers(tmp_path):
    session=PilotSession(tmp_path)
    with pytest.raises(ValueError):session.record('endpoint',status='Pass',note='')
    session.record('endpoint',status='Pass',note='Measured fixture result',false_positive=0,false_negative=0)
    assert any('detection delay' in x for x in session.review()['blockers'])


def test_all_checked_tests_still_need_measured_run_and_owner_review(tmp_path):
    session=PilotSession(tmp_path)
    for key,_ in SCENARIOS:session.record(key,status='Pass',note='Explicit synthetic unit fixture',detection_s=1,recovery_s=2,false_positive=0,false_negative=0)
    assert not session.review()['ready_for_owner_review']
    # Fixture only: even complete inputs can never authorize a commercial release.
    doc=session.document;doc['platform']['system']='Windows';doc['capture'].update(state='Stopped',started=time.time(),duration_s=14400,monitoring_s=14400,observed_samples=480,total_samples=480,samples=[{'at':time.time(),'cpu_percent_one_core':1,'working_set_mb':100,'database_bytes':1000,'log_bytes':100,'monitored_devices':1,'fresh_ping_devices':1,'monitoring_active':True}])
    assert session.review()['ready_for_owner_review'] and not session.review()['commercial_release_approved']
    session.record('gateway',status='Fail');assert not session.review()['ready_for_owner_review']
    session.record('gateway',status='Pass',false_negative=1);assert not session.review()['ready_for_owner_review']


def test_export_omits_notes_by_default_and_rejects_injected_private_fields(tmp_path):
    session=PilotSession(tmp_path);session.record('install',status='Blocked',note='SECRET operator note')
    encoded=json.dumps(session.report());assert 'SECRET' not in encoded and 'SECRET' in json.dumps(session.report(True))
    candidate=copy.deepcopy(session.document);candidate['capture']['private_key']='SECRET'
    with pytest.raises(ValueError):validate_document(candidate)
    candidate=copy.deepcopy(session.document);candidate['capture']['samples']=[{}]*(SAMPLE_LIMIT+1)
    with pytest.raises(ValueError):validate_document(candidate)


def test_invalid_pilot_file_is_not_overwritten(tmp_path):
    path=tmp_path/'pilot-evidence.json';path.write_text('{broken')
    with pytest.raises(ValueError):PilotSession(tmp_path)
    assert path.read_text()=='{broken'


def test_snapshot_redacts_identifiers_and_stale_metrics_and_distinguishes_speed():
    now=time.time();device=Device(id='secret-device-id',name='private-name',host='192.168.72.9',wan=1)
    latest={device.id:{'at':now,'metrics':{'signal_dbm':-65,'password':'SECRET'},'download_mbps':2,'upload_mbps':1,'service':'SECRET'}}
    speeds={device.id:{'at':now,'download_mbps':6,'rate_kind':'Controlled download throughput'}}
    window=SimpleNamespace(monitor_devices=lambda:[device],latest={device.id:{'at':now}},measurements=SimpleNamespace(latest=latest,speed_latest=speeds),engine=SimpleNamespace(running=True),state=lambda d:'Online')
    rows,counts,truncated=snapshot(window,now)
    encoded=json.dumps(rows);assert all(x not in encoded for x in ('private-name','192.168.72.9','secret-device-id','SECRET'))
    assert rows[0]['download_mbps']==2 and rows[0]['download_test_mbps']==6 and counts['fresh_ping_devices']==1 and not truncated
    rows,counts,_=snapshot(window,now+10000);assert not rows[0]['metrics'] and rows[0]['download_test_mbps'] is None and rows[0]['ping_state']=='Unknown' and not counts['fresh_ping_devices']


def test_snapshot_is_bounded_without_inventing_coverage():
    devices=[Device(id=str(i),name='Fixture',host='127.0.0.1') for i in range(250)]
    w=SimpleNamespace(monitor_devices=lambda:devices,latest={},measurements=SimpleNamespace(latest={},speed_latest={}),engine=SimpleNamespace(running=False),state=lambda d:'Online')
    rows,counts,truncated=snapshot(w);assert len(rows)==200 and counts['monitored_devices']==250 and truncated and counts['fresh_ping_devices']==0


def test_failed_atomic_save_cannot_overwrite_previous_report(tmp_path,monkeypatch):
    session=PilotSession(tmp_path);session.save();before=session.path.read_bytes();replace=Path.replace
    def fail(path,target):
        if path.name=='pilot-evidence.json.new':raise OSError('Disk fixture failure')
        return replace(path,target)
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(OSError):session.record('endpoint',status='Blocked',note='Cannot access device')
    assert session.path.read_bytes()==before and not (tmp_path/'pilot-evidence.json.new').exists()


def test_gui_pilot_capture_fault_recovery_and_reopen(tmp_path):
    from PySide6.QtWidgets import QApplication,QPushButton
    from zee.gui import Window
    from zee.ping import Result
    from zee.pilot_dialog import PilotDialog
    app=QApplication.instance() or QApplication([]);s=Store(tmp_path/'monitor.sqlite3');d=Device(name='Synthetic fault fixture',host='127.0.0.1',alerts=False);s.save(d);w=Window(s)
    try:
        dialog=PilotDialog(w);assert not dialog.include_notes.isChecked()
        assert any(b.text()=='Export support / pilot report' for b in dialog.findChildren(QPushButton))
        w.result(d.id,d,Result(False,error='Synthetic injected no reply'));w.engine.running=True
        dialog.capture.start();assert dialog.capture.running and dialog.session.document['capture']['devices'][0]['ping_state']=='No reply'
        w.result(d.id,d,Result(True,2));dialog.capture.collect()
        assert dialog.session.document['capture']['devices'][0]['ping_state']=='Online'
        dialog.close();assert dialog.capture.running # Closing the panel does not stop recording.
        reopened=PilotDialog(w);assert reopened.capture is dialog.capture;reopened.capture.stop();assert reopened.session.document['capture']['state']=='Stopped'
        assert not reopened.session.review()['commercial_release_approved'];reopened.close()
    finally:w.close();s.close()

def test_old_version_evidence_cannot_approve_new_release(tmp_path):
    session=PilotSession(tmp_path);session.document['version']='0.1.0'
    assert any('another app version' in item for item in session.review()['blockers'])

def test_stopped_monitoring_cannot_start_capture(tmp_path):
    from PySide6.QtWidgets import QApplication
    from zee.gui import Window
    from zee.pilot_dialog import PilotCapture
    app=QApplication.instance() or QApplication([]);s=Store(tmp_path/'monitor.sqlite3');w=Window(s)
    try:
        capture=PilotCapture(w)
        with pytest.raises(ValueError,match='Start normal monitoring'):capture.start()
        assert not capture.running and not capture.timer.isActive()
    finally:w.close();s.close()

def test_capture_heartbeat_and_monitored_time_ignore_stopped_engine(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from zee.gui import Window
    from zee.ping import Result
    from zee.pilot_dialog import PilotCapture
    import zee.pilot_dialog as module
    app=QApplication.instance() or QApplication([]);s=Store(tmp_path/'monitor.sqlite3');d=Device(name='Unit fixture',host='127.0.0.1',alerts=False);s.save(d);w=Window(s)
    try:
        w.result(d.id,d,Result(True,1));w.engine.running=True;capture=PilotCapture(w);w.pilot_capture=capture;capture.start()
        baseline=capture.started;monkeypatch.setattr(module.time,'monotonic',lambda:baseline+1.049);capture.tick();capture.collect()
        assert capture.session.document['capture']['monitoring_s']==pytest.approx(1.049,abs=1e-7)
        w.engine.running=False;monkeypatch.setattr(module.time,'monotonic',lambda:baseline+2.049);capture.tick()
        assert capture.session.document['capture']['monitoring_s']==pytest.approx(1.049,abs=1e-7)
        # A long GUI stall is measured, but not counted as fresh uninterrupted monitoring.
        w.engine.running=True;monkeypatch.setattr(module.time,'monotonic',lambda:baseline+12.049);capture.tick()
        assert capture.session.document['capture']['max_heartbeat_gap_ms']==10000 and capture.session.document['capture']['monitoring_s']==pytest.approx(1.049,abs=1e-7)
        capture.stop()
    finally:w.close();s.close()

@pytest.mark.parametrize('name',['pilot-evidence.json','monitor.sqlite3','credentials.dpapi.json','license.json','pilot-archive-fixture.json','mobile/paired-devices.json'])
def test_export_cannot_replace_live_data_or_pilot_archives(tmp_path,name):
    session=PilotSession(tmp_path);session.save();target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True)
    if name!='pilot-evidence.json':target.write_bytes(b'preserve this application file')
    before=target.read_bytes()
    with pytest.raises(ValueError):session.export(target)
    assert target.read_bytes()==before

def test_safe_report_export_keeps_internal_evidence_and_notes(tmp_path):
    session=PilotSession(tmp_path);session.record('install',status='Blocked',note='Private operator note');before=session.path.read_bytes();out=tmp_path/'zee-pilot-report.json';session.export(out)
    assert session.path.read_bytes()==before and 'Private operator note' not in out.read_text()
