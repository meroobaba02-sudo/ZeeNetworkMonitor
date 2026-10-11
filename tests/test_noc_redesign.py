import os,time,threading
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt,QTimer,QItemSelectionModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QPushButton
from zee.core import Store,Device,Station
from zee.gui import Window
from zee.ping import Result
from zee.discovery import targets,ScanTask,Signals
from zee.alignment import AlignmentSession
from zee.telemetry import clean_metrics

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])
@pytest.fixture
def window(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);w=Window(s);w.buzzer.sound_fn=lambda _:None
    yield w
    w.close()

def spin(app,condition,seconds=3):
    end=time.monotonic()+seconds
    while not condition() and time.monotonic()<end:app.processEvents();time.sleep(.002)
    assert condition()

def test_nine_noc_routes_global_search_theme_and_small_screen(window,app):
    w=window;d=Device(name='Roof Rocket',host='192.0.2.4');w.store.save(d);w.reload();w.show()
    expected={8:'Dashboard',7:'Internet Monitor',9:'Network Discovery',0:'Network Map',11:'Rocket M5 Monitor',10:'Dish Alignment',4:'Alerts & History',1:'Device Manager',5:'Settings'}
    for index,label in expected.items():
        assert w.nav_buttons[index].text()==label;w.nav_buttons[index].click();app.processEvents();assert w.tabs.currentIndex()==index
        w.resize(980,650);app.processEvents();assert w.width()==980 and w.height()==650
    w.global_search.setText('Roof');QTest.keyClick(w.global_search,Qt.Key_Return);assert w.tabs.currentIndex()==1 and w.search.text()=='Roof' and w.table.rowCount()==1
    w.theme_picker.setCurrentIndex(1);assert w.store.setting('ui_theme')=='light'
    w.theme_picker.setCurrentIndex(0);assert w.store.setting('ui_theme')=='dark'

def test_internet_placeholders_and_real_test_vs_traffic(window):
    p=window.seven_wan;p.cards.refresh();assert len(p.cards.cards)==7
    assert all(not c.start.isEnabled() and c.id is None and '—' in c.rates.text() for c in p.cards.cards)
    d=Device(name='WAN',host='192.0.2.1',wan=1);window.store.save(d);window.reload();now=time.time()
    window.measurements.latest[d.id]={'at':now,'internet':'Online','download_mbps':4,'upload_mbps':1}
    window.measurements.speed_latest[d.id]={'at':now,'path_checked':True,'download_mbps':12,'upload_mbps':2};p.cards.refresh();c=p.cards.cards[0]
    assert '12.00' in c.rates.text() and '4.00' in c.traffic.text()
    window.measurements.speed_latest[d.id]['at']=now-10000;p.cards.refresh();assert 'Unavailable' in c.rates.text() and '4.00' in c.traffic.text()

def test_per_connection_start_queue_and_stop_are_independent(window,monkeypatch):
    ds=[Device(name='WAN'+str(i),host='192.0.2.'+str(i+1),wan=i+1) for i in range(2)]
    for d in ds:window.store.save(d)
    window.reload();events={}
    def submit(d,*args,**kwargs):
        window.measurements.pending[(d.id,True)]=d;events[d.id]=threading.Event();window.measurements.speed_cancels[d.id]=events[d.id];return True
    monkeypatch.setattr(window.measurements,'submit',submit);p=window.seven_wan;p.start_device(ds[0].id);p.start_device(ds[1].id)
    assert p.active.id==ds[0].id and [d.id for d in p.queue]==[ds[1].id]
    p.stop_device(ds[1].id);assert not p.queue and not events[ds[0].id].is_set()
    p.stop_device(ds[0].id);assert events[ds[0].id].is_set()

@pytest.mark.parametrize('cidr',['0.0.0.0/0','192.168.0.0/16','::1/128','224.0.0.0/24','invalid'])
def test_scan_bounds(cidr):
    with pytest.raises(ValueError):targets(cidr)

def test_scan_thread_is_bounded_cancellable_and_keeps_ui_heartbeat(app,monkeypatch):
    from zee import discovery
    monkeypatch.setattr(discovery,'neighbours',lambda:{})
    signals=Signals();rows=[];done=[];signals.row.connect(rows.append);signals.done.connect(done.append);cancel=threading.Event();lock=threading.Lock();active=[0,0];started=[]
    def fake(d):
        with lock:active[0]+=1;active[1]=max(active);started.append(d.host)
        time.sleep(.04)
        with lock:active[0]-=1
        return Result(True,2)
    task=ScanTask(targets('192.0.2.0/24'),'',100,cancel,signals,probe_fn=fake)
    from PySide6.QtCore import QThreadPool
    pool=QThreadPool();ticks=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start();pool.start(task)
    spin(app,lambda:len(rows)>=4);cancel.set();spin(app,lambda:bool(done));pool.waitForDone();timer.stop()
    assert active[1]<=4 and len(started)<254 and len(ticks)>=2 and 'Stopped' in done[0]

def test_discovery_add_selected_backup_dedup_and_scope_guard(window,monkeypatch):
    from zee import discovery
    p=window.discovery;monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes);monkeypatch.setattr(QMessageBox,'information',lambda *args:None)
    p.scan_page=window.page_id;p.scan_source='';p.rows=[{'ip':'192.0.2.'+str(i),'hostname':'Unavailable','mac':'Unavailable','vendor':'Unavailable','status':'Responding','latency':2,'error':''} for i in (1,2)];p.render()
    for row in (0,1):p.table.selectionModel().select(p.table.model().index(row,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    p.add_selected();assert len(window.store.devices())==2 and list(window.store.path.parent.glob('before-discovery-import-*.sqlite3'))
    p.add_selected();assert len(window.store.devices())==2
    p.scan_page='other';p.rows.append(dict(p.rows[0],ip='192.0.2.3'));p.render();p.table.selectRow(2);p.add_selected();assert len(window.store.devices())==2

def test_alignment_requires_measured_sweep_deduplicates_and_pause():
    s=AlignmentSession();assert 'Direction unavailable' in s.guidance();s.state='Running'
    for i in range(3):assert s.capture(i,-70)
    assert not s.capture(2,-50)
    s.direction='RIGHT'
    for i in range(3,6):s.capture(i,-65)
    assert 'RIGHT' in s.guidance() and s.peak==-65
    s.state='Paused';assert not s.capture(7,-40);assert s.peak==-65
    s.reset();assert not s.samples and s.peak is None

def test_alignment_stale_reading_and_saved_session(window):
    d=Device(name='Radio',host='192.0.2.1',kind='Rocket M5 / wireless radio');window.store.save(d);window.reload();p=window.alignment;p.refresh_devices();p.session.state='Running';p.session.started=time.time();p.next_poll=float('inf')
    window.measurements.latest[d.id]={'at':time.time()-1000,'metrics':{'signal_dbm':-50}};p.tick();assert not p.session.samples
    for value in [-70,-69,-70]:window.measurements.latest[d.id]={'at':time.time(),'metrics':{'signal_dbm':value}};p.tick();time.sleep(.001)
    assert len(p.session.samples)==3;p.finish();p.save();saved=window.store.setting('alignment:'+d.id);assert saved['format']=='zee-alignment-1' and saved['peak_dbm']==-69

def test_topology_uses_only_configured_links_and_last_reachable(window):
    a=Device(id='a',name='Lahore',host='192.0.2.1');b=Device(id='b',name='Sargodha',host='192.0.2.2',parent=a.id);c=Device(name='Unlinked',host='192.0.2.3')
    for d in (a,b,c):window.store.save(d)
    window.reload();window.result(a.id,a,Result(True,2));window.result(b.id,b,Result(False));t=window.map_page.noc_topology;t.refresh()
    assert '1 configured links' in t.caption.text() and 'Lahore' in t.evidence.text() and 'Sargodha' in t.evidence.text()
    t.view.scale_by(1.2);assert t.view.transform().m11()>0;t.fit()

def test_duplicate_detail_windows_and_supported_chain_metrics(window,app):
    d=Device(name='Radio',host='192.0.2.1');window.store.save(d);window.reload();window.show_details(d);window.show_details(d);assert len(window.details_windows)==1
    assert clean_metrics({'signal_chain0_dbm':-60,'signal_chain1_dbm':-63,'signal_dbm':float('nan')})=={'signal_chain0_dbm':-60,'signal_chain1_dbm':-63}

def test_noc_startup_backup_is_once_and_preserves_existing_data(tmp_path):
    from zee.noc_widgets import prepare_backup
    store=Store(tmp_path/'db');store.save(Device(name='Existing',host='192.0.2.1'));store.set_setting('retained','pre-existing setting');backup=prepare_backup(store,'0.5.0');old=backup.read_bytes();assert prepare_backup(store,'0.5.0') is None
    store.save(Device(name='Later',host='192.0.2.2'));assert backup.read_bytes()==old
    import sqlite3
    c=sqlite3.connect(backup);assert c.execute('SELECT COUNT(*) FROM devices').fetchone()[0]==1;c.close();assert len(store.devices())==2 and store.setting('retained')=='pre-existing setting';store.close()

def test_discovery_positive_results_with_optional_dns_filter_and_progress(window,app,monkeypatch):
    from zee import discovery
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes);monkeypatch.setattr(discovery,'reverse_name',lambda host:'gateway.example.test')
    p=window.discovery;p.probe_fn=lambda d:Result(True,3);p.subnet.setText('192.0.2.0/30');p.resolve.setChecked(True);p.authorize.setChecked(True);p.begin();spin(app,lambda:not p.running)
    assert p.progress.value()==2 and len(p.rows)==2 and all(r['hostname']=='gateway.example.test' for r in p.rows)
    assert p.rows[0]['vendor']=='Unavailable';p.filter.setText('192.0.2.1');assert p.table.rowCount()==1 and p.table.item(0,0).text()=='192.0.2.1'

def test_topology_radio_health_reacts_to_fresh_and_stale_measurements(window):
    from dataclasses import replace
    from PySide6.QtWidgets import QGraphicsLineItem
    from zee.customer_theme import status_color
    a=Device(id='radio-a',name='A',host='192.0.2.1',kind='Rocket M5 / wireless radio',integration={'firmware_verified':True});window.store.save(a)
    b=Device(id='radio-b',name='B',host='192.0.2.2',kind='Rocket M5 / wireless radio',peer_id=a.id,integration={'firmware_verified':True});window.store.save(b);a=replace(a,peer_id=b.id);window.store.save(a);window.reload()
    for d in (a,b):window.result(d.id,d,Result(True,2));window.measurements.latest[d.id]={'at':time.time(),'metrics':{'signal_dbm':-110,'tx_ccq':1,'wireless_up':0}}
    t=window.map_page.noc_topology;t.refresh();lines=[i for i in t.scene.items() if isinstance(i,QGraphicsLineItem)];assert len(lines)==1 and lines[0].pen().color().name()==status_color('No reply',window.ui_theme)
    for d in (a,b):window.measurements.latest[d.id]['at']=time.time()-1000
    t.refresh();line=next(i for i in t.scene.items() if isinstance(i,QGraphicsLineItem));assert line.pen().color().name()==status_color('Unknown',window.ui_theme)

def test_discovery_import_batches_leave_ui_responsive_and_stop_retains_saved(window,app,monkeypatch):
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes);p=window.discovery;p.scan_page=window.page_id;p.scan_source='';p.rows=[{'ip':f'192.0.2.{i}','hostname':'Unavailable','mac':'Unavailable','vendor':'Unavailable','status':'Responding','latency':2,'error':''} for i in range(1,21)];p.render()
    for row in range(20):p.table.selectionModel().select(p.table.model().index(row,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    p.add_selected();assert len(window.store.devices())==4 and p.import_queue
    p.stop_scan();assert not p.import_queue and not p.import_timer.isActive() and len(window.store.devices())==4 and p.start.isEnabled()
