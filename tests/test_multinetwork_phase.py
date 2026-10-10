import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time,threading
from dataclasses import replace
import pytest
from PySide6.QtWidgets import QApplication
from zee.core import Store,Device,Station
from zee.workspaces import NetworkPage
from zee.gui import Window
from zee.ping import Result
from zee.network_paths import normalize_interfaces,prepare_probe,ambiguous_hosts,inspect_path
from zee.network_setup import NetworkSetup,RadioLinks


@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


def pump(app,until,timeout=5):
    start=time.monotonic()
    while not until() and time.monotonic()-start<timeout:app.processEvents();time.sleep(.003)
    app.processEvents();assert until()


def test_inventory_normalizes_real_payload_without_invented_addresses():
    rows=normalize_interfaces([{'IPAddress':'10.20.30.4','InterfaceAlias':'Ethernet','InterfaceIndex':2,'PrefixLength':24},{'IPAddress':'not-IP'},{'IPAddress':'0.0.0.0'},None])
    assert rows==[{'ip':'10.20.30.4','name':'Ethernet','index':2,'prefix':24}]
    assert normalize_interfaces({'IPAddress':'::1','InterfaceAlias':'Loopback'})[0]['ip']=='::1'


@pytest.mark.skipif(os.name!='nt',reason='Actual Windows interface inventory requires Windows')
def test_real_windows_adapter_inventory():
    import ipaddress
    from zee.network_paths import interfaces
    rows=interfaces();assert rows
    assert all(ipaddress.ip_address(row['ip']) and row['index']>=0 for row in rows)


def test_prepared_probe_freezes_source_and_route_decision():
    d=Device(id='one',host='127.0.0.1');page=NetworkPage(source_ip='127.0.0.2',routing_verified=True)
    seen=[];fn=prepare_probe(d,page,lambda device:(seen.append(device.source) or Result(True,1)),True)
    page.source_ip='127.0.0.3';page.routing_verified=False
    assert fn(d).success and seen==['127.0.0.2'] and d.source==''
    assert prepare_probe(d,page,lambda x:pytest.fail('Must not probe'),True)(d).infrastructure_error
    assert prepare_probe(d,NetworkPage(source_ip='::1'),lambda x:pytest.fail('Wrong family'))(d).infrastructure_error


def test_ambiguous_duplicate_ips_require_disjoint_sources_and_attestation():
    pages={'a':NetworkPage(id='a',routing_verified=True,source_ip='127.0.0.2'),'b':NetworkPage(id='b',routing_verified=True,source_ip='127.0.0.3')}
    devices=[Device(id='1',page_id='a',host='192.168.1.20'),Device(id='2',page_id='b',host='192.168.1.20'),Device(id='3',page_id='a',host='192.168.1.20')]
    assert not ambiguous_hosts(devices,pages)
    pages['b'].source_ip=pages['a'].source_ip;assert ambiguous_hosts(devices,pages)=={'1','2','3'}
    pages['b'].source_ip='';assert ambiguous_hosts(devices,pages)=={'1','2','3'}
    aliases=[Device(id='v6a',page_id='a',host='2001:db8::1'),Device(id='v6b',page_id='b',host='2001:0db8:0:0:0:0:0:1')]
    assert ambiguous_hosts(aliases,pages)=={'v6a','v6b'}


def test_five_pages_monitor_together_keep_sources_results_and_view_isolation(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False)
    pages=[NetworkPage(id='default' if i==0 else str(i),name=f'Network {i+1}',source_ip=f'127.0.0.{i+2}',routing_verified=True) for i in range(5)]
    s.save_pages(pages);devices=[]
    for i,p in enumerate(pages):
        tower=Station(name=f'Tower {i}',page_id=p.id);s.save_station(tower)
        d=Device(name=f'Radio {i}',host='127.0.0.1',page_id=p.id,station_id=tower.id);s.save(d);devices.append(d)
    w=Window(s);gate=threading.Event();seen=[]
    def fake(d):seen.append((d.id,d.page_id,d.source));gate.wait(2);return Result(True,3)
    w.engine.probe_fn=fake
    try:
        w.monitor_all_box.setChecked(True);w.toggle();generation=w.engine.generation
        pump(app,lambda:len(seen)==5)
        w.page_picker.setCurrentIndex(w.page_picker.findData('3'))
        assert w.engine.running and w.engine.generation==generation and len(w.devices)==1
        assert w.devices[0].page_id=='3' and len(w.map_page.window.page_stations())==1
        gate.set();pump(app,lambda:all(s.stats(d.id)['n']==1 for d in devices))
        assert len(w.latest)==5 and len(w.states)==5
        assert {page:source for _,page,source in seen}=={p.id:p.source_ip for p in pages}
        assert all(w.state(d)=='Online' for d in devices)
        assert w.engine.pool.maxThreadCount()==8
    finally:gate.set();w.close()


def test_unverified_all_network_path_cannot_become_false_online(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);d=Device(name='A',host='127.0.0.1');s.save(d)
    w=Window(s);w.engine.probe_fn=lambda d:pytest.fail('Unverified path must not run')
    try:
        w.monitor_all_box.setChecked(True);w.ping_all();pump(app,lambda:not w.engine.pending)
        assert s.stats(d.id)['n']==0 and w.state(d)=='Probe error'
        assert not w.measurements.submit(d)
    finally:w.close()


def test_background_network_fault_buzzer_and_mobile_are_not_hidden(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);s.save_page(NetworkPage(id='other',name='Other',routing_verified=True))
    d=Device(name='Radio',host='127.0.0.1',page_id='other',failure_threshold=1);s.save(d)
    w=Window(s);w.buzzer.sound_fn=lambda *args:None
    class Server:
        def update(self,value):self.value=value
        def stop(self):pass
    server=Server();w.mobile_server=server
    try:
        w.monitor_all_box.setChecked(True);w.result(d.id,d,Result(False,error='No reply'))
        assert w.buzzer.playing and d.id in w.buzzer.active
        w.update_mobile();assert server.value['devices'][0]['status']=='No reply'
        assert d.id in s.setting('active_incident_devices',[])
        assert not w.devices
    finally:w.close()


def test_background_telemetry_uses_own_page_source_and_survives_view_switch(app,tmp_path,monkeypatch):
    import zee.monitoring as module
    from PySide6.QtCore import QRunnable
    seen=[]
    class Fixture(QRunnable):
        def __init__(self,d,source,secrets,signals,speed,cancel,generation):
            super().__init__();self.d=d;self.source=source;self.signals=signals;self.generation=generation;self.speed=speed
        def run(self):
            seen.append((self.d.page_id,self.source));self.signals.done.emit((self.d,self.speed,self.generation),{'at':time.time(),'metrics':{'signal_dbm':-60}})
    monkeypatch.setattr(module,'Task',Fixture)
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False)
    s.save_page(NetworkPage(id='other',name='Other',source_ip='127.0.0.2',routing_verified=True))
    d=Device(name='Radio',host='127.0.0.1',page_id='other');s.save(d);w=Window(s)
    try:
        w.monitor_all_box.setChecked(True);assert w.measurements.submit(d)
        w.page_picker.setCurrentIndex(w.page_picker.findData('other'))
        pump(app,lambda:d.id in w.measurements.latest)
        assert seen==[('other','127.0.0.2')] and len(s.measurements(d.id))==1
        w.monitor_all_box.setChecked(False);assert not w.measurements.latest
    finally:w.close()


def test_link_two_towers_atomic_cycle_and_page_guards(tmp_path):
    s=Store(tmp_path/'db');a=Station(name='A');b=Station(name='B');s.save_station(a);s.save_station(b)
    left=Device(name='Left',host='127.0.0.1',station_id=a.id);right=Device(name='Right',host='127.0.0.2',station_id=b.id);s.save(left);s.save(right)
    s.link_radios(left.id,right.id,True);ds={d.id:d for d in s.devices()}
    assert ds[left.id].peer_id==right.id and ds[right.id].peer_id==left.id and ds[right.id].parent==left.id
    with pytest.raises(ValueError):s.link_radios(right.id,left.id,True)
    assert {d.id:d for d in s.devices()}[left.id].parent==''
    s.save_page(NetworkPage(id='other'));other=Device(name='Other',host='127.0.0.3',page_id='other');s.save(other)
    with pytest.raises(ValueError):s.link_radios(left.id,other.id)
    s.unlink_radios(left.id);assert all(not d.peer_id and not d.parent for d in s.devices())
    s.close();s=Store(tmp_path/'db');assert len(s.stations())==2;s.close()


def test_atomic_page_validation_and_wizard_ip_selection(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False)
    with pytest.raises(ValueError):s.save_pages([NetworkPage(id='a',name='New'),NetworkPage(id='bad',source_ip='invalid')])
    assert len(s.pages())==1
    w=Window(s);dialog=NetworkSetup(w)
    try:
        assert len(dialog.rows)==5
        dialog.completed({'operation':'inventory','value':[{'ip':'127.0.0.1','name':'Real fixture adapter','index':1,'prefix':8}]})
        row=dialog.rows[0];row['source'].setCurrentIndex(1);row['verified'].setChecked(True)
        pages,targets=dialog.values();assert pages[0].source_ip=='127.0.0.1' and pages[0].interface_hint=='Real fixture adapter'
        row['source'].setEditText('127.0.0.2');assert not row['verified'].isChecked()
        dialog.accept();assert len(s.pages())==5 and not w.engine.running
        assert s.pages()[0].source_ip=='127.0.0.2'
    finally:dialog.close();w.close()


def test_stale_path_result_ignored_and_reply_does_not_auto_verify(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);w=Window(s);dialog=NetworkSetup(w)
    try:
        row=dialog.rows[0];row['target'].setText('127.0.0.1')
        result={'operation':'path','context':(0,'','127.0.0.1'),'value':{'reply':True,'text':'fixture reply','target':'127.0.0.1','source':'127.0.0.1'}}
        dialog.completed(result);assert not row['verified'].isChecked()
        assert s.setting('network_path_reports',{})
        row['target'].setText('127.0.0.2');dialog.completed(result);assert 'ignored' in dialog.status.text()
    finally:dialog.close();w.close()


def test_path_check_uses_row_being_edited_not_previous_table_selection(app,tmp_path,monkeypatch):
    import zee.network_setup as module
    seen=[]
    def inspect(target,source):
        seen.append((target,source));return {'text':'fixture','source':source,'target':target,'reply':True}
    monkeypatch.setattr(module,'inspect_path',inspect)
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);w=Window(s);dialog=NetworkSetup(w);dialog.show();app.processEvents()
    try:
        row=dialog.rows[3];row['target'].setText('127.0.0.4');row['target'].setFocus();app.processEvents()
        dialog.check_selected();pump(app,lambda:not dialog.busy)
        assert seen==[('127.0.0.4','')]
    finally:dialog.close();w.close()


def test_route_inspection_loopback_reports_evidence_not_wan_proof(monkeypatch):
    import zee.network_paths as module
    monkeypatch.setattr(module,'probe',lambda d:Result(True,1))
    result=inspect_path('127.0.0.1','127.0.0.1')
    assert result['reply'] and result['source']=='127.0.0.1'
    assert 'not proof' in result['text'] and 'No UDP data was sent' in result['text']


def test_peer_line_requires_both_fresh_endpoint_metrics():
    from zee.network_paths import peer_quality
    a=Device(id='a');b=Device(id='b');now=time.time()
    good={'at':now,'metrics':{'signal_dbm':-58,'tx_ccq':98}}
    assert peer_quality(a,b,{'a':good},now)[0]=='Unknown'
    assert peer_quality(a,b,{'a':good,'b':good},now)[0]=='Good'
    critical={'at':now,'metrics':{'wireless_up':0}}
    assert peer_quality(a,b,{'a':good,'b':critical},now)[0]=='Critical'
    assert peer_quality(a,b,{'a':good,'b':good},now+1000)[0]=='Unknown'
