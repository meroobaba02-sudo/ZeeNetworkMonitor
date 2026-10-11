import os,time,threading
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog
from PySide6.QtCore import Qt
from zee.core import Store
from zee.gui import Window
from zee.ping import Result
from zee.discovery import BatchScanTask,Signals
from zee.discovery_methods import connected_plan

def adapter(ip,subnet,index=1):
    return {'ip':ip,'subnet':subnet,'index':index,'name':'Ethernet '+str(index),'mask':'255.255.255.252','prefix':30}

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

@pytest.fixture
def window(app,tmp_path,monkeypatch):
    from zee import discovery
    monkeypatch.setattr(discovery,'ipv4_inventory',lambda force=False:[])
    s=Store(tmp_path/'monitor.sqlite3');s.set_setting('auto_cleanup',False);w=Window(s);w.buzzer.sound_fn=lambda _:None
    yield w
    w.close()

def pump(app,condition,timeout=5):
    end=time.monotonic()+timeout
    while not condition() and time.monotonic()<end:app.processEvents();time.sleep(.003)
    assert condition()

def test_plan_finds_all_alias_subnets_and_deduplicates_same_interface_subnet():
    inventory=[adapter('192.168.11.222','192.168.11.0/24'),adapter('192.168.30.222','192.168.30.0/24'),adapter('192.168.43.222','192.168.43.0/24'),adapter('192.168.10.100','192.168.10.0/24'),adapter('192.168.10.34','192.168.10.0/24',2),adapter('192.168.11.223','192.168.11.0/24')]
    plan,skipped=connected_plan(inventory)
    assert len(plan)==5 and not skipped and sum(len(s['hosts']) for s in plan)==1270
    assert {s['ip'] for s in plan}=={'192.168.11.222','192.168.30.222','192.168.43.222','192.168.10.100','192.168.10.34'}

def test_large_ranges_are_reported_without_partial_silent_scan():
    plan,skipped=connected_plan([adapter('10.0.0.1','10.0.0.0/16'),adapter('127.0.0.1','127.0.0.0/8'),adapter('192.168.11.222','192.168.11.0/24')])
    assert len(plan)==1 and len(skipped)==1 and '10.0.0.0/16' in skipped[0]
    plan,skipped=connected_plan([adapter('10.0.0.2','10.0.0.0/24')],total_limit=2)
    assert not plan and skipped

def test_batch_preserves_source_subnet_and_arp_interface(app):
    plan,_=connected_plan([adapter('192.0.2.2','192.0.2.0/30'),adapter('198.51.100.2','198.51.100.0/30',2)])
    signals=Signals();rows=[];messages=[];calls=[];signals.row.connect(rows.append);signals.done.connect(messages.append)
    def check(d):calls.append((d.host,d.source));return Result(True,2)
    BatchScanTask(plan,100,threading.Event(),signals,probe_fn=check,rate=20,neighbour_fn=lambda:[]).run()
    assert len(calls)==4 and len(rows)==4 and messages==['Connected-network scan complete']
    assert all(r['source_ip']=='192.0.2.2' for r in rows if r['subnet']=='192.0.2.0/30')
    assert all(r['interface_index']==2 for r in rows if r['subnet']=='198.51.100.0/30')

def test_cancel_does_not_start_later_subnets(app):
    plan,_=connected_plan([adapter('192.0.2.2','192.0.2.0/30'),adapter('198.51.100.2','198.51.100.0/30',2)])
    cancel=threading.Event();signals=Signals();calls=[];done=[];signals.done.connect(done.append)
    def check(d):calls.append(d.host);cancel.set();return Result(True,1)
    BatchScanTask(plan,100,cancel,signals,probe_fn=check,rate=20,neighbour_fn=lambda:[]).run()
    assert len(calls)==1 and done==['Stopped; partial results retained']

def test_scan_all_needs_no_selected_ip_and_requires_exact_plan_permission(window,app,monkeypatch):
    from zee import discovery
    p=window.discovery;pump(app,lambda:not p.inventory_busy)
    inventory=[adapter('192.0.2.2','192.0.2.0/30'),adapter('198.51.100.2','198.51.100.0/30',2)]
    monkeypatch.setattr(discovery,'ipv4_inventory',lambda force=False:inventory)
    calls=[];p.probe_fn=lambda d:(calls.append((d.host,d.source)) or Result(d.host.endswith('.1'),2))
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.No)
    p.begin_all();pump(app,lambda:not p.pending_all and not p.inventory_busy);app.processEvents()
    assert not p.running and not calls
    prompts=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *args:(prompts.append(args[2]) or QMessageBox.Yes))
    p.begin_all();pump(app,lambda:len(calls)==4 and not p.running)
    assert p.all_mode and len(p.batch_plan)==2 and p.progress.value()==4 and p.progress.maximum()==4
    assert p.found_table.rowCount()==2 and p.table.rowCount()==4 and p.identified_table.rowCount()==0
    assert p.results.currentIndex()==0 and '198.51.100.0/30' in prompts[0]
    assert all(source for host,source in calls) and p.adapter.currentIndex()==0
    assert not p.auto.isEnabled()

def row(ip,source,status='Responding'):
    return {'ip':ip,'source_ip':source,'subnet':'192.0.2.0/24','adapter_name':'Ethernet','interface_index':1,'hostname':'Unavailable','mac':'Unavailable','vendor':'Unavailable','status':status,'latency':1 if status=='Responding' else None,'method':'ICMP' if status=='Responding' else 'DNS PTR (identity only)','at':time.time(),'error':''}

def test_separate_results_import_original_source_and_deduplicate(window,app,monkeypatch,tmp_path):
    p=window.discovery;pump(app,lambda:not p.inventory_busy)
    p.all_mode=True;p.scan_page=window.page_id;p.scan_network_source=window.current_page().source_ip;p.scan_source=''
    p.rows=[row('192.0.2.1','192.0.2.2'),row('192.0.2.1','192.0.2.3'),row('192.0.2.4','192.0.2.2','Identified; reachability unconfirmed'),row('192.0.2.5','192.0.2.2','No response; status unknown')]
    p.render();p.results.setCurrentIndex(0)
    assert p.found_table.rowCount()==2 and p.identified_table.rowCount()==1 and p.table.rowCount()==4
    assert p.found_table.item(0,0).data(Qt.UserRole)!=p.found_table.item(1,0).data(Qt.UserRole)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    p.found_table.selectAll();p.add_selected();pump(app,lambda:not p.import_queue)
    assert {(d.host,d.source) for d in window.store.devices()}=={('192.0.2.1','192.0.2.2'),('192.0.2.1','192.0.2.3')}
    assert list(tmp_path.glob('before-discovery-import-*.sqlite3'))
    p.found_table.selectAll();p.add_selected();assert len(window.store.devices())==2
    p.filter.setText('192.0.2.2');assert p.found_table.rowCount()==1
    export=tmp_path/'found.csv';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(export),''));p.export_csv()
    content=export.read_text(encoding='utf-8-sig');assert '192.0.2.2' in content and '192.0.2.3' not in content and '192.0.2.5' not in content

def test_neighbour_update_does_not_duplicate_row_and_permission_revokes_batch(window):
    p=window.discovery;p.running=True;p.cancel=threading.Event();p.authorize.setChecked(True)
    p.found(row('192.0.2.1','192.0.2.2','No response; status unknown'));p.found(row('192.0.2.1','192.0.2.2'))
    assert len(p.rows)==1 and p.rows[0]['status']=='Responding'
    p.authorize.setChecked(False);assert p.cancel.is_set();p.running=False
