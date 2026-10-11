import os,time,socket
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog,QInputDialog
from PySide6.QtCore import Qt,QItemSelectionModel
from zee.core import Store,Device
from zee.gui import Window
from zee.ping import Result
from zee.discovery import ScanTask,Signals
from zee.discovery_methods import targets,local_scope,ports,tcp_check,neighbour_for,load_vendors,vendor_name,_ipv4_rows
from zee.alignment import AlignmentSession
from zee.telemetry import clean_metrics,validate_profile

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])
@pytest.fixture
def window(app,tmp_path,monkeypatch):
    from zee import discovery
    monkeypatch.setattr(discovery,'ipv4_inventory',lambda force=False:[])
    store=Store(tmp_path/'db');store.set_setting('auto_cleanup',False);w=Window(store);w.buzzer.sound_fn=lambda _:None
    yield w
    w.close()

def pump(app,condition,timeout=4):
    end=time.monotonic()+timeout
    while not condition() and time.monotonic()<end:app.processEvents();time.sleep(.003)
    assert condition()

def scan(app,hosts,**kwargs):
    import threading
    signals=Signals();rows=[];done=[];signals.row.connect(rows.append);signals.done.connect(done.append)
    task=ScanTask(hosts,'127.0.0.1',100,threading.Event(),signals,probe_fn=lambda d:Result(False,error='No ping reply'),rate=20,neighbour_fn=lambda:[],**kwargs);task.run()
    assert done==['Scan complete'];return rows

def test_range_validation_inventory_and_exact_scope():
    assert targets('10.0.0.1-10.0.0.3')==['10.0.0.1','10.0.0.2','10.0.0.3']
    for value in ('10.0.0.3-10.0.0.1','10.0.0.1-10.0.8.1','224.0.0.0/30','0.0.0.0/32','255.255.255.255/32'):
        with pytest.raises(ValueError):targets(value)
    rows=_ipv4_rows([{'ip':'10.0.0.2','prefix':24,'name':'Ethernet','index':3},{'ip':'::1','prefix':128},{'ip':'invalid','prefix':24}])
    assert rows[0]['mask']=='255.255.255.0' and rows[0]['subnet']=='10.0.0.0/24'
    assert local_scope(['10.0.0.1'],'10.0.0.2',rows)
    assert not local_scope(['10.0.1.1'],'10.0.0.2',rows) and not local_scope(['10.0.0.1'],'',rows)
    assert ports('443,80,443')==[80,443]
    for value in ('1,2,3,4','0','foo'):
        with pytest.raises(ValueError):ports(value)

def test_tcp_connect_without_ping_identifies_live_host_and_sends_no_payload(app):
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();port=sock.getsockname()[1]
    try:
        rows=scan(app,['127.0.0.1'],tcp_ports=[port]);conn,_=sock.accept();conn.settimeout(1);assert conn.recv(10)==b'';conn.close()
        assert rows[0]['status']=='Responding' and 'TCP '+str(port) in rows[0]['method'] and rows[0]['latency'] is not None
    finally:sock.close()

def test_dns_and_cached_neighbour_are_identity_only(app,monkeypatch):
    from zee import discovery
    monkeypatch.setattr(discovery,'reverse_name',lambda host:'station.example.test')
    rows=scan(app,['192.0.2.1'],resolve=True)
    assert rows[0]['status']=='Identified; reachability unconfirmed' and 'DNS PTR' in rows[0]['method'] and rows[0]['latency'] is None
    item={'ip':'192.0.2.1','mac':'00:11:22:33:44:55','index':4,'reachable':False}
    assert neighbour_for('192.0.2.1',[item],4)['reachable'] is False
    assert neighbour_for('192.0.2.1',[item],None) is None and neighbour_for('192.0.2.1',[item],5) is None
    assert neighbour_for('192.0.2.1',[item,dict(item,mac='00:AA:BB:CC:DD:EE')],4) is None

def test_fresh_interface_scoped_arp_evidence_and_no_response_unknown(app):
    import threading
    snapshots=iter([[],[{'ip':'192.0.2.1','mac':'00:11:22:33:44:55','index':4,'reachable':True}]])
    signals=Signals();rows=[];signals.row.connect(rows.append)
    ScanTask(['192.0.2.1'],'192.0.2.2',100,threading.Event(),signals,probe_fn=lambda d:Result(False),rate=20,index=4,on_link=True,neighbour_fn=lambda:next(snapshots)).run()
    assert rows[-1]['status']=='Responding' and 'ARP evidence' in rows[-1]['method'] and rows[-1]['latency'] is None
    rows=scan(app,['192.0.2.9']);assert rows[0]['status']=='No response; status unknown' and 'offline' not in rows[0]['status'].lower()

def test_rate_limit_host_starts_are_spaced_and_worker_count_is_bounded(app):
    import threading
    starts=[];signals=Signals();done=[];signals.done.connect(done.append)
    def probe(d):starts.append(time.monotonic());return Result(True,1)
    ScanTask(['192.0.2.'+str(i) for i in range(1,6)],'',100,threading.Event(),signals,probe_fn=probe,rate=8,neighbour_fn=lambda:[]).run()
    assert len(starts)==5 and all(b-a>=.12 for a,b in zip(starts,starts[1:])) and done

def test_authorization_remote_denial_and_rediscovery_scope_change(window,app,monkeypatch):
    p=window.discovery;calls=[];p.probe_fn=lambda d:(calls.append(d.host) or Result(True,1));p.subnet.setText('192.0.2.1/32')
    p.begin();assert not p.running and not calls
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.No);p.authorize.setChecked(True);p.begin();assert not p.running and not calls
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes);p.begin();pump(app,lambda:not p.running);assert calls==['192.0.2.1']
    p.auto.setChecked(True);assert p.rediscovery_timer.isActive();p.rediscover();pump(app,lambda:not p.running);assert len(calls)==2
    p.subnet.setText('192.0.2.2/32');assert not p.auto.isChecked() and not p.authorize.isChecked();p.rediscover();assert len(calls)==2

def test_adapter_selection_remote_presets_and_export(window,app,tmp_path,monkeypatch):
    p=window.discovery;app.processEvents();pump(app,lambda:not p.inventory_busy)
    row={'ip':'10.0.0.2','name':'Ethernet','index':3,'prefix':24,'mask':'255.255.255.0','subnet':'10.0.0.0/24'};p.inventory_done([row],'');p.adapter.setCurrentIndex(1);p.choose_adapter();assert p.source()=='10.0.0.2' and p.subnet.text()=='10.0.0.0/24' and 'mask 255.255.255.0' in p.adapter_info.text()
    p.subnet.setText('10.20.0.0/24');monkeypatch.setattr(QInputDialog,'getText',lambda *args:('Remote tower',True));p.save_site();assert window.store.setting('discovery_remote_sites')[0]['source']=='10.0.0.2'
    p.remote_site.setCurrentIndex(1);p.choose_site();assert p.remote.isChecked() and not p.authorize.isChecked()
    p.rows=[{'ip':'10.20.0.1','hostname':'=malicious','mac':'Unavailable','vendor':'Unavailable','status':'Responding','latency':1,'error':'','method':'TCP 443','at':time.time()}];p.render();path=tmp_path/'export.csv';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),''));p.export_csv();assert "'=malicious" in path.read_text(encoding='utf-8-sig') and 'TCP 443' in path.read_text(encoding='utf-8-sig')

def test_verified_vendor_assignments_and_locally_administered_mac(tmp_path):
    p=tmp_path/'vendors.csv';p.write_text('Assignment,Organization Name\n001122,Verified Vendor\n0011223,Specific Vendor\n')
    vendors=load_vendors(p);assert vendor_name('00:11:22:33:44:55',vendors)=='Specific Vendor'
    assert 'Unavailable' in vendor_name('02:11:22:33:44:55',vendors) and vendor_name('Unavailable',vendors)=='Unavailable'

def test_repeated_adjustment_steps_are_not_mixed_and_best_stable_position():
    s=AlignmentSession();s.state='Running'
    for t,v in enumerate((-70,-70,-70)):s.capture(t,v)
    s.begin_step('RIGHT',.25,'turns')
    for t,v in enumerate((-65,-65,-65),3):s.capture(t,v)
    s.begin_step('RIGHT',.25,'turns')
    for t,v in enumerate((-75,-75,-75),6):s.capture(t,v)
    assert s.best_stable()['id']==1 and s.comparisons()[-1]['change_db']==-10 and 'RIGHT step 1' in s.guidance() and 'Retain/return' in s.guidance()
    assert not s.capture(4,-40)
    s.begin_step('UP')
    for t,v in enumerate((-60,-65,-55),9):s.capture(t,v)
    assert s.best_stable()['id']==1 and not s.comparisons()[-1]['stable']

def test_alignment_live_quality_gps_and_saved_step_evidence(window,app):
    d=Device(name='Radio',host='192.0.2.1',kind='Rocket M5 / wireless radio',integration={'firmware_verified':True,'device_model':'Rocket M5','firmware_version':'operator fixture'});window.store.save(d);window.reload();p=window.alignment;p.refresh_devices();p.session.state='Running';p.session.started=time.time();p.next_poll=time.monotonic()+100
    metrics={'signal_dbm':-70,'noise_dbm':-95,'signal_chain0_dbm':-69,'signal_chain1_dbm':-73,'tx_ccq':85,'tx_mbps':120,'gps_latitude':31,'gps_longitude':74,'heading_deg':80}
    now=time.time()
    for i in range(3):window.measurements.latest[d.id]={'at':time.time(),'metrics':metrics};p.tick();time.sleep(.001)
    p.render();assert 'Imbalance 4.0 dB' in p.live_metrics.text() and 'Noise -95.0 dBm' in p.live_metrics.text() and 'CCQ 85.0 %' in p.live_metrics.text() and 'Compass 80.0' in p.live_metrics.text()
    p.tag('RIGHT');assert len(p.session.steps)==2;p.pause();assert p.session.state=='Paused';p.finish();p.save();saved=window.store.setting('alignment:'+d.id);assert saved['steps'] and saved['best_stable']['median_dbm']==-70 and saved['samples'][0]['metrics']['noise_dbm']==-95
    window.measurements.latest[d.id]['at']=now-1000;p.render();assert 'Noise Unavailable' in p.live_metrics.text()
    window.measurements.latest[d.id]={'at':time.time(),'metrics':{'signal_dbm':-120}};p.render();assert p.meter.value()==-120

def test_invalid_gps_cannot_create_position_and_profile_stays_verified_only():
    assert clean_metrics({'gps_latitude':91,'gps_longitude':181,'heading_deg':360,'elevation_deg':float('nan')})=={}
    validate_profile({'method':'snmp','oids':{'gps_latitude':{'path':'1.3.6.1.4.1.1','scale':.001}},'firmware_verified':False})


@pytest.mark.skipif(os.name!='nt',reason='Native connected-adapter / neighbour queries require Windows')
def test_native_windows_connected_inventory_and_neighbours():
    from zee.discovery_methods import ipv4_inventory,neighbour_snapshot
    rows=ipv4_inventory(force=True);assert rows and all(r['mask'] and r['subnet'] and r['index']>0 for r in rows)
    neighbours=neighbour_snapshot();assert isinstance(neighbours,list) and all(type(r['reachable']) is bool and r['index']>=0 for r in neighbours)

def test_audio_pitch_is_measured_and_throttled_without_ui_wait(app,monkeypatch):
    from zee import alignment
    from types import SimpleNamespace
    audio=alignment.AlignmentAudio(None);queued=[]
    class Pool:
        def activeThreadCount(self):return 0
        def start(self,task):queued.append(task.pitch)
        def clear(self):pass
    audio.pool=Pool();monkeypatch.setattr(alignment,'os',SimpleNamespace(name='nt'));audio.improvement(-80);audio.improvement(-60);assert len(queued)==1
    audio.last=0;audio.improvement(-60);assert queued[1]>queued[0];audio.stop();assert audio.cancel.is_set()

def test_adjustment_does_not_capture_pre_move_or_old_session_samples():
    s=AlignmentSession();s.state='Running';s.started=10;assert not s.capture(9,-60)
    for t in (10,11,12):assert s.capture(t,-70)
    s.begin_step('LEFT',at=20);assert not s.capture(19,-60)
    for t in (21,22,23):assert s.capture(t,-65)
    assert s.best_stable()['direction']=='LEFT'

def test_telemetry_test_and_web_fallback_controls(window,monkeypatch):
    d=Device(name='Radio',host='192.0.2.1',kind='Rocket M5 / wireless radio');window.store.save(d);window.reload();p=window.alignment;p.refresh_devices();calls=[];monkeypatch.setattr(window.measurements,'submit',lambda d:(calls.append(d.id) or True));p.test_telemetry();assert not calls and 'verified' in p.summary.text()
    from dataclasses import replace
    window.store.save(replace(d,integration={'method':'snmp','firmware_verified':True}));window.reload();p.test_telemetry();assert calls
    opened=[];monkeypatch.setattr(window,'open_management',lambda d:opened.append(d.host));p.open();assert opened==['192.0.2.1']


def test_permission_revocation_cancels_active_discovery(window):
    import threading
    p=window.discovery;p.authorize.setChecked(True);p.running=True;p.cancel=threading.Event();p.authorization=p.scope();p.auto.setChecked(True);p.authorize.setChecked(False)
    assert p.cancel.is_set() and not p.auto.isChecked() and p.authorization is None
    p.running=False

def test_resume_boundary_excludes_paused_readings():
    s=AlignmentSession();s.state='Running';s.min_at=10;assert not s.capture(9,-60);assert s.capture(11,-70)
    s.state='Paused';assert not s.capture(12,-60)
    s.state='Running';s.min_at=20;assert not s.capture(19,-60);assert s.capture(21,-65)
