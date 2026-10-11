"""Explicit, cancellable IPv4 ICMP discovery; no inferred topology or credentials."""
import ipaddress,threading,subprocess,os,json,time,sqlite3,csv
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool,Qt,QTimer,QItemSelectionModel
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QSpinBox,QLabel,QProgressBar,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QCheckBox,QComboBox,QFileDialog,QInputDialog,QScrollArea,QTabWidget
from .core import Device
from .ping import probe
from .noc_widgets import action,text

from .discovery_methods import targets,ipv4_inventory,local_scope,ports,tcp_check,neighbour_snapshot,neighbour_for,load_vendors,vendor_name,connected_plan

def neighbours():
    if os.name!='nt':return {}
    try:
        r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command','Get-NetNeighbor -AddressFamily IPv4 | Select-Object IPAddress,LinkLayerAddress | ConvertTo-Json -Compress'],capture_output=True,text=True,timeout=3,creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode or not r.stdout.strip():return {}
        rows=json.loads(r.stdout.lstrip('\ufeff'));rows=rows if isinstance(rows,list) else [rows];out={}
        for row in rows:
            ip=row.get('IPAddress');mac=row.get('LinkLayerAddress','')
            if ip and mac and mac not in ('00-00-00-00-00-00','FF-FF-FF-FF-FF-FF'):out.setdefault(ip,set()).add(mac)
        return {ip:next(iter(macs)) for ip,macs in out.items() if len(macs)==1}
    except (OSError,subprocess.TimeoutExpired,ValueError,TypeError):return {}

def reverse_name(host):
    if os.name!='nt':return 'Unavailable'
    try:
        host=str(ipaddress.IPv4Address(host))
        command="Resolve-DnsName -Name '"+host+"' -Type PTR -QuickTimeout -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty NameHost"
        row=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=2,creationflags=subprocess.CREATE_NO_WINDOW)
        value=row.stdout.strip()[:253]
        return value if row.returncode==0 and value and not any(ord(c)<32 for c in value) else 'Unavailable'
    except (ValueError,OSError,subprocess.TimeoutExpired):return 'Unavailable'

class Signals(QObject):
    row=Signal(object);done=Signal(str)
class InventorySignals(QObject):
    done=Signal(object,str)
class InventoryTask(QRunnable):
    def __init__(self,signals,force=False):super().__init__();self.signals=signals;self.force=force
    def run(self):
        try:self.signals.done.emit(ipv4_inventory(self.force),'')
        except Exception:self.signals.done.emit([],'Adapter detection unavailable; enter a source IP and range manually.')

class ScanTask(QRunnable):
    def __init__(self,hosts,source,timeout,cancel,signals,probe_fn=probe,resolve=False,rate=8,tcp_ports=(),index=None,on_link=False,vendors=None,tcp_fn=tcp_check,neighbour_fn=None):
        super().__init__();self.hosts=hosts;self.source=source;self.timeout=timeout;self.cancel=cancel;self.signals=signals;self.probe=probe_fn;self.resolve=resolve;self.rate=rate;self.tcp_ports=tcp_ports;self.index=index;self.on_link=on_link;self.vendors=vendors or {};self.tcp=tcp_fn;self.neighbour_fn=neighbour_fn or neighbour_snapshot
    def run(self):
        error='';iterator=iter(self.hosts);rows={};next_start=0
        try:
            snapshot=self.neighbour_fn()
            with ThreadPoolExecutor(max_workers=4,thread_name_prefix='zee-discovery') as pool:
                pending={}
                def inspect(host):
                    result=self.probe(Device(name=host,host=host,source=self.source,timeout=self.timeout));methods=[];latency=result.latency if result.success else None;reachable=result.success
                    if result.success:methods.append('ICMP')
                    cached=neighbour_for(host,snapshot,self.index) if self.on_link else None
                    if cached:methods.append('Neighbour cache (not liveness proof)')
                    for port in self.tcp_ports:
                        if self.cancel.is_set():break
                        try:ok,ms=self.tcp(host,self.source,port,self.timeout)
                        except OSError:ok,ms=False,None
                        if ok:reachable=True;methods.append('TCP '+str(port)+' connect');latency=latency if latency is not None else ms;break
                    name=reverse_name(host) if self.resolve and not self.cancel.is_set() else 'Unavailable'
                    if name!='Unavailable':methods.append('DNS PTR (identity only)')
                    status='Responding' if reachable else 'Identified; reachability unconfirmed' if cached or name!='Unavailable' else 'Probe error' if result.infrastructure_error else 'No response; status unknown'
                    mac=cached['mac'] if cached else 'Unavailable'
                    return {'ip':host,'hostname':name,'mac':mac,'vendor':vendor_name(mac,self.vendors),'status':status,'latency':latency,'error':result.error if not result.success else '', 'method':', '.join(methods) or 'No supported response','at':time.time()}
                def replenish():
                    nonlocal next_start
                    while len(pending)<4 and not self.cancel.is_set() and time.monotonic()>=next_start:
                        host=next(iterator,None)
                        if host is None:break
                        pending[pool.submit(inspect,host)]=host;next_start=time.monotonic()+1/max(1,self.rate)
                replenish()
                while pending or not self.cancel.is_set():
                    if pending:
                        ready,_=wait(pending,timeout=.025,return_when=FIRST_COMPLETED)
                        for future in ready:
                            host=pending.pop(future)
                            if self.cancel.is_set():continue
                            try:row=future.result()
                            except Exception:row={'ip':host,'hostname':'Unavailable','mac':'Unavailable','vendor':'Unavailable','status':'Probe error','latency':None,'error':'Probe could not complete','method':'Unavailable','at':time.time()}
                            rows[host]=row;self.signals.row.emit(row)
                    else:
                        if self.cancel.wait(.025):break
                    replenish()
                    # Iterator exhaustion is known only when a start is allowed.
                    if not pending and time.monotonic()>=next_start:
                        host=next(iterator,None)
                        if host is None:break
                        pending[pool.submit(inspect,host)]=host;next_start=time.monotonic()+1/max(1,self.rate)
            if self.on_link and not self.cancel.is_set():
                fresh=self.neighbour_fn()
                for host,row in rows.items():
                    item=neighbour_for(host,fresh,self.index)
                    if not item:continue
                    row=row|{'mac':item['mac'],'vendor':vendor_name(item['mac'],self.vendors),'at':time.time()}
                    if item['reachable']:
                        row['status']='Responding';row['method']+=', Windows neighbour Reachable (ARP evidence)'
                    elif row['status'] not in ('Responding',):row['status']='Identified; reachability unconfirmed'
                    self.signals.row.emit(row)
        except Exception:error='Discovery could not finish; check local network/probe access.'
        self.signals.done.emit(error or ('Stopped; in-flight checks finished' if self.cancel.is_set() else 'Scan complete'))

class BatchScanTask(QRunnable):
    def __init__(self,plan,timeout,cancel,signals,**options):
        super().__init__();self.plan=plan;self.timeout=timeout;self.cancel=cancel;self.signals=signals;self.options=options
    def run(self):
        from types import SimpleNamespace
        errors=[]
        class Relay:
            def __init__(self,fn):self.emit=fn
        for scope in self.plan:
            if self.cancel.is_set():break
            def forward(row,s=scope):self.signals.row.emit(row|{'source_ip':s['ip'],'subnet':s['subnet'],'adapter_name':s['name'],'interface_index':s['index']})
            messages=[];relay=SimpleNamespace(row=Relay(forward),done=Relay(messages.append))
            ScanTask(scope['hosts'],scope['ip'],self.timeout,self.cancel,relay,index=scope['index'],on_link=True,**self.options).run()
            if messages and messages[-1] not in ('Scan complete','Stopped; in-flight checks finished'):errors.append(scope['subnet'])
        self.signals.done.emit('Stopped; partial results retained' if self.cancel.is_set() else 'Connected-network scan complete'+(' · scopes with probe errors: '+', '.join(errors) if errors else ''))

class DiscoveryPanel(QScrollArea):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.probe_fn=probe;self.rows=[];self.running=False;self.cancel=threading.Event();self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1);self.signals=Signals();self.signals.row.connect(self.found);self.signals.done.connect(self.finished);self.scan_page=None;self.scan_source='';self.dirty=False;self.inventory=[];self.inventory_busy=False;self.authorization=None;self.vendors={};self.closed=False
        self.inventory_signals=InventorySignals();self.inventory_signals.done.connect(self.inventory_done)
        self.all_mode=False;self.pending_all=False;self.batch_plan=[];self.batch_skipped=[]
        self.rediscovery_timer=QTimer(self);self.rediscovery_timer.timeout.connect(self.rediscover)
        self.render_timer=QTimer(self);self.render_timer.setInterval(250);self.render_timer.timeout.connect(lambda:self.render() if self.dirty else None);self.render_timer.start()
        self.import_queue=[];self.import_added=0;self.import_timer=QTimer(self);self.import_timer.setInterval(20);self.import_timer.timeout.connect(self.import_batch)
        self.setWidgetResizable(True);body=QWidget();self.setWidget(body)
        layout=QVBoxLayout(body);layout.addWidget(text('Network Discovery','title'));layout.addWidget(text('Scan only a network you manage. ICMP response is discovery evidence, not proof of device type or physical connectivity. DNS/cache identity is separate from reachability. No response means unknown, not offline.','muted'))
        adapter_row=QHBoxLayout();layout.addLayout(adapter_row);self.adapter=QComboBox();self.adapter.addItem('Current network source / Windows route',None);self.adapter.activated.connect(self.choose_adapter);adapter_row.addWidget(self.adapter,1);self.read_adapters=action('Refresh adapters',lambda:self.load_adapters(True));adapter_row.addWidget(self.read_adapters);self.adapter_info=text('Detecting local IPv4 adapters…','muted');layout.addWidget(self.adapter_info)
        row=QHBoxLayout();layout.addLayout(row);self.subnet=QLineEdit(w.store.setting('discovery_subnet','192.168.1.0/24'));self.subnet.setPlaceholderText('IPv4 subnet or start-end range');row.addWidget(self.subnet,2);self.timeout=QSpinBox();self.timeout.setRange(100,2000);self.timeout.setValue(w.store.setting('discovery_timeout_ms',500));self.timeout.setSuffix(' ms');row.addWidget(self.timeout);self.filter=QLineEdit();self.filter.setPlaceholderText('Filter IP / status / MAC');self.filter.textChanged.connect(self.render);row.addWidget(self.filter,2)
        self.resolve=QCheckBox('Resolve hostnames with Windows DNS (optional, adds bounded DNS lookups)');self.resolve.setChecked(w.store.setting('discovery_resolve_names',False));layout.addWidget(self.resolve)
        options=QHBoxLayout();layout.addLayout(options);self.rate=QSpinBox();self.rate.setRange(1,20);self.rate.setValue(w.store.setting('discovery_rate',8));self.rate.setSuffix(' hosts/sec');options.addWidget(self.rate);self.tcp=QCheckBox('Optional TCP connect');options.addWidget(self.tcp);self.tcp_ports=QLineEdit('80,443');self.tcp_ports.setPlaceholderText('Max 3 ports');options.addWidget(self.tcp_ports);options.addWidget(action('Load vendor CSV',self.load_vendor_csv))
        sites=QHBoxLayout();layout.addLayout(sites);self.remote_site=QComboBox();self.remote_site.addItem('Manual / local range',None);self.remote_site.activated.connect(self.choose_site);sites.addWidget(self.remote_site,1);sites.addWidget(action('Save remote station',self.save_site));self.remote=QCheckBox('Remote / third-party network');sites.addWidget(self.remote)
        self.authorize=QCheckBox('I own/administer this exact range or have explicit permission to scan it');self.authorize.toggled.connect(self.permission_changed);layout.addWidget(self.authorize)
        auto=QHBoxLayout();layout.addLayout(auto);self.auto=QCheckBox('Rediscover this authorized scope during this session');self.auto.toggled.connect(self.auto_changed);auto.addWidget(self.auto);self.auto_minutes=QSpinBox();self.auto_minutes.setRange(1,60);self.auto_minutes.setValue(5);self.auto_minutes.setSuffix(' min');self.auto_minutes.valueChanged.connect(self.auto_changed);auto.addWidget(self.auto_minutes);auto.addWidget(action('Export CSV',self.export_csv))
        self.refresh_sites();QTimer.singleShot(0,self.load_adapters)
        for widget,signal in [(self.subnet,'textChanged'),(self.adapter,'currentIndexChanged'),(self.remote,'toggled'),(self.tcp,'toggled'),(self.tcp_ports,'textChanged'),(self.resolve,'toggled')]:getattr(widget,signal).connect(self.invalidate_scope)
        tools=QHBoxLayout();layout.addLayout(tools);self.start=action('Start Scan',self.begin);self.stop=action('Stop Scan',self.stop_scan);self.rescan=action('Rescan',lambda:self.begin_all() if self.all_mode else self.begin());self.add=action('Add Selected Devices',self.add_selected)
        self.scan_all=action('Scan all connected networks',self.begin_all)
        for b in (self.start,self.scan_all,self.stop,self.rescan,self.add):tools.addWidget(b)
        self.stop.setEnabled(False);self.progress=QProgressBar();layout.addWidget(self.progress);self.status=text('Ready · no scan started');layout.addWidget(self.status)
        self.results=QTabWidget();layout.addWidget(self.results,1)
        self.found_table=self.result_table();self.identified_table=self.result_table();self.table=self.result_table()
        for widget,title in [(self.found_table,'Found now (0)'),(self.identified_table,'Identified only (0)'),(self.table,'All checked (0)')]:self.results.addTab(widget,title)
        self.results.setCurrentIndex(2)
        self.result_summary=text('No discovery results yet','muted');layout.addWidget(self.result_summary)
    def result_table(self):
        table=QTableWidget(0,11);table.setHorizontalHeaderLabels(['IP address','Hostname','MAC','Vendor','Detection','Response time','Discovery method','Last checked','Network / subnet','Adapter','Local source IP']);table.setSelectionBehavior(QTableWidget.SelectRows);table.setSelectionMode(QTableWidget.ExtendedSelection);table.setEditTriggers(QTableWidget.NoEditTriggers);table.setMinimumHeight(170);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);return table
    def row_key(self,row):return row['source_ip']+'|'+row['ip'] if 'source_ip' in row else row['ip']
    def active_table(self):return self.results.currentWidget()
    def batch_controls(self,enabled):
        for widget in (self.adapter,self.read_adapters,self.remote_site,self.remote,self.subnet,self.tcp,self.tcp_ports,self.resolve,self.rate,self.timeout):widget.setEnabled(enabled)
    def begin_all(self):
        if self.running or self.import_queue or self.pending_all:return
        if self.inventory_busy:self.status.setText('Adapter detection is running; retry Scan all when it finishes.');return
        if not self.w.policy.allows('monitoring'):QMessageBox.warning(self,'Cannot scan','Monitoring permission is required.');return
        self.pending_all=True;self.scan_all.setEnabled(False);self.status.setText('Refreshing connected IPv4 networks…');self.load_adapters(True)
    def begin_all_ready(self):
        if self.closed or self.running or self.import_queue or not self.w.policy.allows('monitoring'):return
        try:
            plan,skipped=connected_plan(self.inventory);tcp_ports=ports(self.tcp_ports.text()) if self.tcp.isChecked() else []
            if not plan:raise ValueError('No eligible connected IPv4 subnets. Large subnets must be narrowed in manual scan.\n'+'\n'.join(skipped))
        except ValueError as e:QMessageBox.warning(self,'Cannot scan all',str(e));return
        summary='\n'.join(s['name']+' · '+s['subnet']+' · source '+s['ip']+' · '+str(len(s['hosts']))+' addresses' for s in plan)
        question='Scan these connected networks only if you own/administer them or have permission?\n\n'+summary+'\n\n4 workers maximum; '+str(self.rate.value())+' hosts/sec. Remote ranges are not inferred.'
        if skipped:question+='\n\nSkipped (not scanned):\n'+'\n'.join(skipped)
        if QMessageBox.question(self,'Authorize connected-network scan',question)!=QMessageBox.Yes:return
        self.all_mode=True;self.batch_plan=plan;self.batch_skipped=skipped;self.auto.setChecked(False);self.auto.setEnabled(False);self.auto.setToolTip('For all connected networks use Rescan; timed rediscovery remains available for a single authorized range.')
        self.authorize.blockSignals(True);self.authorize.setChecked(True);self.authorize.blockSignals(False)
        self.authorization=None;self.scan_network_source=self.w.current_page().source_ip;self.scan_page=self.w.page_id;self.scan_source='';self.rows=[];self.render();self.cancel=threading.Event();self.running=True
        for button in (self.start,self.scan_all,self.rescan,self.add):button.setEnabled(False)
        self.stop.setEnabled(True);self.batch_controls(False);self.progress.setRange(0,sum(len(s['hosts']) for s in plan));self.progress.setValue(0)
        self.status.setText('Scanning '+str(len(plan))+' connected networks · results retain their subnet and source IP');self.results.setCurrentIndex(0)
        self.pool.start(BatchScanTask(plan,self.timeout.value(),self.cancel,self.signals,probe_fn=self.probe_fn,resolve=self.resolve.isChecked(),rate=self.rate.value(),tcp_ports=tcp_ports,vendors=dict(self.vendors)))
    def permission_changed(self,enabled):
        if not enabled:
            self.authorization=None
            if hasattr(self,'auto'):self.auto.setChecked(False)
            if self.running:self.cancel.set();self.status.setText('Permission revoked; stopping bounded in-flight checks')
    def invalidate_scope(self,*_):
        self.authorization=None;self.authorize.setChecked(False);self.auto.setChecked(False)
    def source(self):
        item=self.adapter.currentData()
        return item['ip'] if item else self.w.current_page().source_ip
    def scope(self):return (self.w.page_id,self.subnet.text().strip(),self.source(),self.tcp.isChecked(),self.tcp_ports.text(),self.resolve.isChecked(),self.remote.isChecked())
    def load_adapters(self,force=False):
        if self.closed or self.inventory_busy:return
        self.inventory_busy=True;self.read_adapters.setEnabled(False);self.pool.start(InventoryTask(self.inventory_signals,force))
    def inventory_done(self,rows,error):
        self.inventory_busy=False
        if self.closed:return
        self.read_adapters.setEnabled(True);self.inventory=rows;previous=self.source();self.adapter.blockSignals(True);self.adapter.clear();self.adapter.addItem('Current network source / Windows route',None)
        for row in rows:self.adapter.addItem(row['name']+' · '+row['ip']+' · '+row['subnet'],row)
        for i in range(1,self.adapter.count()):
            if self.adapter.itemData(i)['ip']==previous:self.adapter.setCurrentIndex(i);break
        self.adapter.blockSignals(False);self.adapter_info.setText(error or '\n'.join(r['name']+' · IPv4 '+r['ip']+' · mask '+r['mask']+' · connected subnet '+r['subnet'] for r in rows) or 'No IPv4 adapters available. Configure a source IP manually in Network setup.');self.adapter_info.setToolTip(self.adapter_info.text())
        if self.authorization and self.scope()!=self.authorization:self.authorization=None;self.auto.setChecked(False)
        if self.pending_all:
            self.pending_all=False;self.scan_all.setEnabled(True)
            if not error:QTimer.singleShot(0,self.begin_all_ready)
            else:self.status.setText(error)
    def choose_adapter(self,*_):
        item=self.adapter.currentData()
        if item:self.subnet.setText(item['subnet'])
        self.authorization=None;self.auto.setChecked(False)
    def refresh_sites(self):
        self.remote_site.clear();self.remote_site.addItem('Manual / local range',None)
        for site in self.w.store.setting('discovery_remote_sites',[])[:64]:self.remote_site.addItem(site['name']+' · '+site['range'],site)
    def save_site(self):
        try:targets(self.subnet.text())
        except ValueError as e:QMessageBox.warning(self,'Invalid range',str(e));return
        name,ok=QInputDialog.getText(self,'Remote station','Station name (range/source saved; authorization is not saved)')
        if not ok or not name.strip():return
        sites=self.w.store.setting('discovery_remote_sites',[]);site={'name':name.strip()[:100],'range':self.subnet.text().strip(),'source':self.source(),'page_id':self.w.page_id};sites=[s for s in sites if s['name']!=site['name']];self.w.store.set_setting('discovery_remote_sites',(sites+[site])[-64:]);self.refresh_sites()
    def choose_site(self,*_):
        site=self.remote_site.currentData()
        if not site:return
        if site['page_id']!=self.w.page_id:QMessageBox.information(self,'Select station network','Select the saved station network page first.');return
        self.subnet.setText(site['range']);self.adapter.setCurrentIndex(0)
        for i in range(1,self.adapter.count()):
            if self.adapter.itemData(i)['ip']==site['source']:self.adapter.setCurrentIndex(i);break
        if self.source()!=site['source']:QMessageBox.warning(self,'Source unavailable','Saved source IP is unavailable. Configure/select that source before scanning.');return
        self.remote.setChecked(True);self.authorize.setChecked(False);self.authorization=None;self.auto.setChecked(False)
    def load_vendor_csv(self):
        path,_=QFileDialog.getOpenFileName(self,'Load trusted vendor assignments CSV','','CSV (*.csv)')
        if not path:return
        try:self.vendors=load_vendors(path);self.status.setText(f'{len(self.vendors)} vendor assignments loaded for this session')
        except (ValueError,OSError) as e:QMessageBox.warning(self,'Cannot load vendor CSV',str(e))
    def export_csv(self):
        path,_=QFileDialog.getSaveFileName(self,'Export filtered discovery results','discovery.csv','CSV (*.csv)')
        if not path:return
        # CSV formula escaping: device-supplied names remain data.
        try:
            with open(path,'w',encoding='utf-8-sig',newline='') as f:
                table=self.active_table();writer=csv.writer(f);writer.writerow([table.horizontalHeaderItem(i).text() for i in range(table.columnCount())])
                for i in range(table.rowCount()):writer.writerow([("'"+v if v[:1] in ('=','+','-','@') else v) for v in [table.item(i,j).text() for j in range(table.columnCount())]])
            self.status.setText('Filtered discovery results exported')
        except OSError:QMessageBox.warning(self,'Export failed','Cannot write the selected file.')
    def auto_changed(self,*_):
        self.rediscovery_timer.stop()
        if self.auto.isChecked():self.rediscovery_timer.start(self.auto_minutes.value()*60000)
    def rediscover(self):
        if not self.authorization or self.scope()!=self.authorization or not self.authorize.isChecked():self.auto.setChecked(False);self.status.setText('Rediscovery stopped: authorize the changed scope with Start Scan.');return
        if not self.running and not self.import_queue:self.begin(automatic=True)
    def begin(self,checked=False,automatic=False):
        if self.running or self.import_queue:return
        try:
            hosts=targets(self.subnet.text());source=self.source();tcp_ports=ports(self.tcp_ports.text()) if self.tcp.isChecked() else []
            if source and ipaddress.ip_address(source).version!=4:raise ValueError('This scanner uses IPv4. Select an IPv4 local source/network.')
            if not self.w.policy.allows('monitoring'):raise ValueError('Monitoring permission is required.')
        except ValueError as e:QMessageBox.warning(self,'Cannot scan',str(e));return
        if not self.authorize.isChecked():self.status.setText('Authorize this exact range before scanning.');return
        source_indices={r['index'] for r in self.inventory if r['ip']==source};on_link=local_scope(hosts,source,self.inventory) and len(source_indices)==1;remote=self.remote.isChecked() or not on_link
        if remote and self.authorization!=self.scope():
            if automatic:self.auto.setChecked(False);return
            if QMessageBox.question(self,'Authorize remote / third-party discovery',f'Scan {self.subnet.text().strip()} from {source or "Windows route"}? Only proceed with permission from this network owner. The maximum is 4 workers and {self.rate.value()} hosts/sec; TCP checks send no application data.')!=QMessageBox.Yes:return
        self.all_mode=False;self.auto.setEnabled(True);self.auto.setToolTip('');self.batch_skipped=[];self.authorization=self.scope();index=next(iter(source_indices)) if len(source_indices)==1 else None
        self.scan_network_source=self.w.current_page().source_ip;self.scan_page=self.w.page_id;self.scan_source=source;self.rows=[];self.render();self.cancel=threading.Event();self.running=True;self.start.setEnabled(False);self.rescan.setEnabled(False);self.stop.setEnabled(True);self.add.setEnabled(False);self.subnet.setEnabled(False);self.progress.setRange(0,len(hosts));self.progress.setValue(0);self.w.store.set_setting('discovery_subnet',self.subnet.text().strip());self.w.store.set_setting('discovery_timeout_ms',self.timeout.value());self.status.setText('Scanning · 4 background workers · source '+(source or 'Windows route'))
        self.w.store.set_setting('discovery_rate',self.rate.value());self.w.store.set_setting('discovery_resolve_names',self.resolve.isChecked());self.pool.start(ScanTask(hosts,source,self.timeout.value(),self.cancel,self.signals,probe_fn=self.probe_fn,resolve=self.resolve.isChecked(),rate=self.rate.value(),tcp_ports=tcp_ports,index=index,on_link=on_link,vendors=dict(self.vendors)))
        self.scan_all.setEnabled(False)
    def found(self,row):
        if not self.running or self.cancel.is_set():return
        existing=next((i for i,r in enumerate(self.rows) if self.row_key(r)==self.row_key(row)),None)
        if existing is None:self.rows.append(row)
        else:self.rows[existing]=row
        self.progress.setValue(len(self.rows));self.dirty=True
    def finished(self,message):
        self.render()
        self.running=False;self.start.setEnabled(True);self.rescan.setEnabled(True);self.stop.setEnabled(False);self.add.setEnabled(True);self.subnet.setEnabled(True);self.status.setText(message+f' · {len(self.rows)} checked · '+str(sum(r['status']=='Responding' for r in self.rows))+' responding')
        self.scan_all.setEnabled(True);self.batch_controls(True);self.results.setCurrentIndex(0)
        if self.batch_skipped:self.status.setText(self.status.text()+'\nSkipped ranges (not scanned): '+'; '.join(self.batch_skipped))
    def stop_scan(self):
        if self.import_queue:
            self.auto.setChecked(False);self.import_queue=[];self.finish_import('Import stopped; already added devices retained');return
        self.auto.setChecked(False)
        if self.running:self.cancel.set();self.stop.setEnabled(False);self.status.setText('Stopping · waiting for at most 4 bounded in-flight checks')
    def render(self):
        self.dirty=False
        query=self.filter.text().casefold();filtered=[r for r in self.rows if query in ' '.join(map(str,r.values())).casefold()]
        found=[r for r in filtered if r['status']=='Responding'];identified=[r for r in filtered if r['status'].startswith('Identified')]
        for table,shown in [(self.found_table,found),(self.identified_table,identified),(self.table,filtered)]:self.render_table(table,shown)
        for i,label,count in [(0,'Found now',len(found)),(1,'Identified only',len(identified)),(2,'All checked',len(filtered))]:self.results.setTabText(i,f'{label} ({count})')
        self.result_summary.setText(f"{sum(r['status']=='Responding' for r in self.rows)} responding · {sum(r['status'].startswith('Identified') for r in self.rows)} identified without confirmed response · {len(self.rows)} checked. Results are observations at their check time; no response remains unknown.")
    def render_table(self,table,shown):
        selected={table.item(i.row(),0).data(Qt.UserRole) for i in table.selectionModel().selectedRows() if table.item(i.row(),0)};table.setRowCount(len(shown))
        shown=sorted(shown,key=lambda r:(r.get('subnet',''),r.get('source_ip',''),int(ipaddress.IPv4Address(r['ip']))))
        for i,row in enumerate(shown):
            vals=[row['ip'],row['hostname'],row['mac'],row['vendor'],row['status'],f"{row['latency']:.1f} ms" if row['latency'] is not None else 'Unavailable',row.get('method','ICMP' if row['status']=='Responding' else 'Unavailable'),time.strftime('%H:%M:%S',time.localtime(row['at'])) if row.get('at') else 'Unavailable',row.get('subnet',''),row.get('adapter_name',''),row.get('source_ip',self.scan_source)]
            for j,value in enumerate(vals):
                item=QTableWidgetItem(value);item.setToolTip(row['error'] if j==4 else value)
                if j==0:item.setData(Qt.UserRole,self.row_key(row))
                table.setItem(i,j,item)
            if self.row_key(row) in selected:table.selectionModel().select(table.model().index(i,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    def import_scope_valid(self):
        return self.scan_page==self.w.page_id and getattr(self,'scan_network_source',self.scan_source)==self.w.current_page().source_ip and (self.all_mode or self.source()==self.scan_source)
    def add_selected(self):
        if self.running or self.import_queue:self.status.setText('Stop/wait for the active scan or import before adding.');return
        if not self.w.policy.allows('monitoring'):QMessageBox.warning(self,'Cannot add devices','Monitoring permission is required.');return
        if not self.import_scope_valid():QMessageBox.information(self,'Select scanned network','Return to the network where this scan ran before adding devices.');return
        table=self.active_table();ips={table.item(i.row(),0).data(Qt.UserRole) for i in table.selectionModel().selectedRows()};chosen=[r for r in self.rows if self.row_key(r) in ips and (r['status']=='Responding' or r['status'].startswith('Identified'))];existing={(d.host,d.source or self.w.current_page().source_ip) for d in self.w.devices};new=[r for r in chosen if (r['ip'],r.get('source_ip',self.scan_source)) not in existing]
        if not new:self.status.setText('Select responding/identified devices. Existing devices are skipped.');return
        if len(self.w.store.devices())+len(new)>self.w.policy.max_devices:QMessageBox.warning(self,'Device limit','Selection exceeds the current device limit.');return
        if QMessageBox.question(self,'Add discovered devices',f'Add {len(new)} identified devices to this network? Device types and physical links remain unassigned.')!=QMessageBox.Yes:return
        safety=self.w.store.path.parent/f'before-discovery-import-{time.time_ns()}.sqlite3'
        try:
            self.w.store.backup(safety)

        except (ValueError,OSError,sqlite3.Error) as e:
            self.w.reload();QMessageBox.warning(self,'Discovery import failed',str(e)+'\nExisting records are retained; check the pre-import backup if a partial addition occurred.');return
        self.import_queue=list(new);self.import_added=0;self.start.setEnabled(False);self.scan_all.setEnabled(False);self.rescan.setEnabled(False);self.add.setEnabled(False);self.stop.setEnabled(True);self.status.setText('Adding selected devices · pre-import backup saved');self.import_timer.start();self.import_batch()
    def import_batch(self):
        if not self.import_scope_valid():self.import_queue=[];self.finish_import('Network/source changed; partial import retained');return
        try:
            for _ in range(min(4,len(self.import_queue))):
                row=self.import_queue[0];existing={(d.host,d.source or self.w.current_page().source_ip) for d in self.w.store.devices() if d.page_id==self.scan_page}
                source=row.get('source_ip',self.scan_source)
                if (row['ip'],source) not in existing:self.w.store.save(Device(name=row['ip'],host=row['ip'],source=source,page_id=self.scan_page,notes='Added from authorized multi-method discovery; type/topology/liveness not assumed.'));self.import_added+=1
                self.import_queue.pop(0)
        except (ValueError,OSError,sqlite3.Error) as e:
            self.import_queue=[];self.finish_import('Import stopped: '+str(e));return
        self.status.setText(f'Adding selected devices · {self.import_added} saved · {len(self.import_queue)} pending')
        if not self.import_queue:self.finish_import('Import complete; existing devices preserved')
    def finish_import(self,message):
        self.import_timer.stop();self.start.setEnabled(True);self.scan_all.setEnabled(True);self.rescan.setEnabled(True);self.add.setEnabled(True);self.stop.setEnabled(False);self.w.reload();self.status.setText(message+f' · {self.import_added} added · pre-import backup retained')
    def shutdown(self):self.closed=True;self.rediscovery_timer.stop();self.import_timer.stop();self.import_queue=[];self.render_timer.stop();self.cancel.set();self.pool.clear();self.pool.waitForDone()
