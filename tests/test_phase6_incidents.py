import json,sqlite3,time
from dataclasses import replace
import pytest
from zee.core import Device,Store
from zee.faults import evaluate,context
from zee.workspaces import NetworkPage

def devices():
    return [Device(id='g',name='Gateway',host='127.0.0.1',failure_threshold=1),
            Device(id='r',name='Station',host='127.0.0.2',parent='g',failure_threshold=1),
            Device(id='a',name='Remote A',host='127.0.0.3',parent='r',failure_threshold=1),
            Device(id='b',name='Remote B',host='127.0.0.4',parent='r',failure_threshold=1)]

def scenario(ds,fail=(),unknown=(),latest=None,now=100):
    pings={d.id:{'at':now,'success':d.id not in fail} for d in ds if d.id not in unknown}
    states={d.id:'No reply' if d.id in fail else 'Online' for d in ds}
    return evaluate(ds,pings,states,latest or {},{id:3 for id in fail},now)

def test_common_upstream_counts_only_fresh_failed_descendants():
    ds=devices()+[Device(id='u',name='Unobserved remote',host='127.0.0.5',parent='r')]
    _,findings=scenario(ds,('r','a','b'),('u',))
    assert len(findings)==1 and findings[0]['affected']==['Remote A','Remote B']
    assert findings[0]['confidence']=='Medium' and findings[0]['correlated']
    assert findings[0]['last_good']=='Gateway' and 'not confirmed' in findings[0]['explanation']

def test_one_endpoint_or_mixed_branch_is_not_common_upstream_proof():
    _,findings=scenario(devices(),('a',))
    assert len(findings)==1 and findings[0]['device']=='a' and findings[0]['confidence']=='Low'
    _,findings=scenario(devices(),('r','a'))
    assert not findings[0]['correlated'] and 'still reply' in findings[0]['explanation']

@pytest.mark.parametrize('service',['HTTP service responding (200)','Authentication required (401)','RTSP service responding (video not tested)'])
def test_icmp_blocked_but_application_response_prevents_total_unreachable_claim(service):
    outcomes,findings=scenario(devices(),('r','a','b'),latest={'r':{'at':100,'service':service}})
    incident=next(x for x in outcomes if x['device']=='r' and x['category']=='reachability')
    assert 'service responds' in incident['title'] and not any(f['correlated'] for f in findings)
    assert len(findings)==3

@pytest.mark.parametrize('state,at',[('No reply',1),('Probe error',100),('Unknown',1)])
def test_stale_or_probe_error_is_unknown_without_fault_claim(state,at):
    ds=devices()[:1];outcomes,findings=evaluate(ds,{'g':{'at':at,'success':False}},{'g':state},{},{'g':10},100)
    assert not findings and outcomes[0]['status']=='unknown'

def test_separate_wan_external_failure_with_router_reply():
    ds=[Device(id='w1',name='WAN 1',host='127.0.0.1',wan=1,integration={'wan_verified':True}),Device(id='w2',name='WAN 2',host='127.0.0.2',wan=2,integration={'wan_verified':True})]
    outcomes,_=scenario(ds,latest={'w1':{'at':100,'internet':'Offline — external check failed'},'w2':{'at':100,'internet':'Online'}})
    internet={x['device']:x for x in outcomes if x['category']=='internet'}
    assert internet['w1']['status']=='active' and 'router responds' in internet['w1']['title']
    assert internet['w2']['status']=='healthy'

def test_wireless_failure_and_recovery_require_actual_fresh_metrics():
    ds=devices()[:1]
    outcomes,_=scenario(ds,latest={'g':{'at':100,'metrics':{'wireless_up':0}}})
    assert next(x for x in outcomes if x['category']=='wireless')['status']=='active'
    outcomes,_=scenario(ds,latest={'g':{'at':1,'metrics':{'wireless_up':0}}})
    assert next(x for x in outcomes if x['category']=='wireless')['status']=='unknown'

def test_service_auth_response_proves_reachability_without_claiming_service_recovery():
    ds=[replace(devices()[0],service_url='https://127.0.0.1/')]
    outcomes,_=scenario(ds,latest={'g':{'at':100,'service':'Unavailable — TLS error'}})
    assert next(x for x in outcomes if x['category']=='service')['status']=='active'
    outcomes,_=scenario(ds,latest={'g':{'at':100,'service':'Authentication required (401)'}})
    assert next(x for x in outcomes if x['category']=='service')['status']=='unknown'

def test_latency_warning_recovers_only_after_fresh_successful_normal_check():
    ds=devices()[:1];pings={'g':{'at':100,'success':True}}
    outcomes,_=evaluate(ds,pings,{'g':'Warning'},{},{},100)
    assert next(x for x in outcomes if x['category']=='ping_performance')['status']=='active'
    outcomes,_=evaluate(ds,pings,{'g':'Online'},{},{},200)
    assert next(x for x in outcomes if x['category']=='ping_performance')['status']=='unknown'
    outcomes,_=evaluate(ds,{'g':{'at':201,'success':True}},{'g':'Online'},{},{},201)
    assert next(x for x in outcomes if x['category']=='ping_performance')['status']=='healthy'

def test_incident_lifecycle_restart_gap_acknowledgement_and_recurrence(tmp_path):
    path=tmp_path/'state.db';s=Store(path);ds=devices()[:1]
    outcomes,_=scenario(ds,('g',));outcomes[0]['started']=90
    assert len(s.observe_incidents(outcomes))==1
    s.observe_incidents(outcomes);row=s.incident_rows()[0];id=row['id']
    assert row['at']==90 and row['last_seen']==100
    s.edit_incident(id,acknowledged=True,pinned=True,notes='Technician checking the route')
    s.close();s=Store(path);s.suspend_incidents()
    assert s.incident_rows()[0]['status']=='Unobserved' and s.incident_rows()[0]['resolved'] is None
    missing,_=scenario(ds,unknown=('g',),now=1000);s.observe_incidents(missing)
    assert s.incident_rows()[0]['resolved'] is None
    healthy,_=scenario(ds,now=1010);assert s.observe_incidents(healthy)[0][0]=='recovered'
    row=s.incident_rows()[0];assert row['resolved']==1010 and row['acknowledged'] and row['pinned'] and row['notes']
    assert 'failures reached' in row['detail']['opening']['evidence'][0]
    assert row['detail']['recovery']['evidence']==['Fresh ICMP reply']
    failed,_=scenario(ds,('g',),now=1020);s.observe_incidents(failed)
    assert len(s.incident_rows())==2 and s.incident_rows()[0]['id']!=id
    s.close()

def test_context_change_and_disabled_check_cannot_heal_old_incident(tmp_path):
    s=Store(tmp_path/'state.db');ds=devices()[:1];outcomes,_=scenario(ds,('g',));s.observe_incidents(outcomes)
    new=[replace(ds[0],host='127.0.0.9')];healthy,_=scenario(new);s.observe_incidents(healthy)
    assert s.incident_rows()[0]['status']=='Unobserved' and s.incident_rows()[0]['resolved'] is None
    disabled,_=scenario([replace(ds[0],enabled=False)]);s.observe_incidents(disabled)
    assert s.incident_rows()[0]['resolved'] is None
    s.edit_incident(s.incident_rows()[0]['id'],close=True)
    assert 'unverified' in s.incident_rows()[0]['status']
    s.close()

def test_retention_protects_unresolved_and_pinned_incidents(tmp_path):
    from zee.retention import cleanup,Policy
    s=Store(tmp_path/'state.db');ds=devices()[:1]
    failed,_=scenario(ds,('g',),now=100);s.observe_incidents(failed)
    healthy,_=scenario(ds,now=110);s.observe_incidents(healthy);old=s.incident_rows()[0]['id']
    failed,_=scenario(ds,('g',),now=200);s.observe_incidents(failed)
    healthy,_=scenario(ds,now=210);s.observe_incidents(healthy);pinned=s.incident_rows()[0]['id'];s.edit_incident(pinned,pinned=True)
    failed,_=scenario(ds,('g',),now=300);s.observe_incidents(failed);active=s.incident_rows()[0]['id']
    cleanup(s.path,Policy(1,1),now=200000)
    assert {r['id'] for r in s.incident_rows()}=={pinned,active}
    s.close()

def test_schema3_upgrade_creates_recoverable_backup_and_schema4_restore(tmp_path):
    from zee.recovery import open_backup
    path=tmp_path/'state.db';s=Store(path);d=devices()[0];s.save(d);s.close()
    with sqlite3.connect(path) as db:db.execute('DROP TABLE incidents');db.execute('PRAGMA user_version=3')
    s=Store(path);assert s.db.execute('PRAGMA user_version').fetchone()[0]==4 and s.devices()[0]==d
    with sqlite3.connect(str(path)+'.pre-v0410.bak') as backup:assert backup.execute('PRAGMA user_version').fetchone()[0]==3
    s.backup(tmp_path/'backup.db');backup=open_backup(tmp_path/'backup.db')
    assert backup.execute('PRAGMA user_version').fetchone()[0]==4;backup.close();s.close()

def test_gui_fault_injection_noise_reduction_recovery_and_history_scope(tmp_path):
    from PySide6.QtWidgets import QApplication
    from zee.gui import Window
    from zee.ping import Result
    from zee.incident_dialog import IncidentDialog
    app=QApplication.instance() or QApplication([]);s=Store(tmp_path/'state.db');ds=devices()
    for d in ds:s.save(d)
    w=Window(s)
    try:
        w.notifications.setChecked(False)
        for d in ds:w.result(d.id,d,Result(d.id=='g',latency=1 if d.id=='g' else None,error='' if d.id=='g' else 'fixture timeout'))
        rows=s.incident_rows();assert len(rows)==3 and all(r['resolved'] is None for r in rows)
        assert any('suppressed' in e['message'] for e in s.events(device='b'))
        w.render_diagnosis();assert 'Possible common upstream' in w.diagnostic.toPlainText()
        for d in ds[1:]:w.result(d.id,d,Result(False,error='fixture timeout'))
        assert len(s.incident_rows())==3
        w.result('g',ds[0],Result(False,error='local bind error',infrastructure_error=True))
        assert not any(r['device']=='g' for r in s.incident_rows())
        for d in ds:w.result(d.id,d,Result(True,1))
        assert all(r['resolved'] is not None for r in s.incident_rows())
        s.save_page(NetworkPage(id='p2',name='Other network'));other=replace(ds[0],id='other',page_id='p2');failed,_=scenario([other],('other',));s.observe_incidents(failed)
        dlg=IncidentDialog(w);assert len(dlg.rows)==3
        dlg.all_pages.setChecked(True);assert len(dlg.rows)==4
        dlg.table.selectRow(0);dlg.ack();assert dlg.rows[0]['acknowledged']
        dlg.pin();assert dlg.rows[0]['pinned'];dlg.close()
    finally:w.close();s.close()
