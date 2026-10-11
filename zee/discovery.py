"""Explicit, cancellable IPv4 ICMP discovery; no inferred topology or credentials."""
import ipaddress,threading,subprocess,os,json,time,sqlite3
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool,Qt,QTimer,QItemSelectionModel
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QSpinBox,QLabel,QProgressBar,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QCheckBox
from .core import Device
from .ping import probe
from .noc_widgets import action,text

def targets(cidr):
    network=ipaddress.ip_network(cidr.strip(),strict=False)
    if network.version!=4 or network.num_addresses>1024 or network.is_multicast or network.network_address.is_unspecified:raise ValueError('Use an IPv4 subnet with at most 1,024 addresses (for example 192.168.1.0/24).')
    return list(map(str,network.hosts()))

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
class ScanTask(QRunnable):
    def __init__(self,hosts,source,timeout,cancel,signals,probe_fn=probe,resolve=False):super().__init__();self.hosts=hosts;self.source=source;self.timeout=timeout;self.cancel=cancel;self.signals=signals;self.probe=probe_fn;self.resolve=resolve
    def run(self):
        error='';macs=neighbours();iterator=iter(self.hosts)
        try:
            with ThreadPoolExecutor(max_workers=4,thread_name_prefix='zee-discovery') as pool:
                pending={}
                def inspect(host):
                    result=self.probe(Device(name=host,host=host,source=self.source,timeout=self.timeout))
                    name=reverse_name(host) if self.resolve and result.success and not self.cancel.is_set() else 'Unavailable'
                    return result,name
                def replenish():
                    while len(pending)<4 and not self.cancel.is_set():
                        host=next(iterator,None)
                        if host is None:break
                        pending[pool.submit(inspect,host)]=host
                replenish()
                while pending:
                    ready,_=wait(pending,timeout=.1,return_when=FIRST_COMPLETED)
                    for future in ready:
                        host=pending.pop(future)
                        if self.cancel.is_set():continue
                        try:
                            result,hostname=future.result();status='Responding' if result.success else 'Probe error' if result.infrastructure_error else 'No reply'
                            row={'ip':host,'hostname':hostname,'mac':macs.get(host,'Unavailable'),'vendor':'Unavailable','status':status,'latency':result.latency,'error':result.error}
                        except Exception:row={'ip':host,'hostname':'Unavailable','mac':'Unavailable','vendor':'Unavailable','status':'Probe error','latency':None,'error':'Probe could not complete'}
                        self.signals.row.emit(row)
                    replenish()
        except Exception:error='Discovery could not finish; check local network/probe access.'
        self.signals.done.emit(error or ('Stopped; in-flight checks finished' if self.cancel.is_set() else 'Scan complete'))

class DiscoveryPanel(QWidget):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.probe_fn=probe;self.rows=[];self.running=False;self.cancel=threading.Event();self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1);self.signals=Signals();self.signals.row.connect(self.found);self.signals.done.connect(self.finished);self.scan_page=None;self.scan_source='';self.dirty=False
        self.render_timer=QTimer(self);self.render_timer.setInterval(250);self.render_timer.timeout.connect(lambda:self.render() if self.dirty else None);self.render_timer.start()
        self.import_queue=[];self.import_added=0;self.import_timer=QTimer(self);self.import_timer.setInterval(20);self.import_timer.timeout.connect(self.import_batch)
        layout=QVBoxLayout(self);layout.addWidget(text('Network Discovery','title'));layout.addWidget(text('Scan only a network you manage. ICMP response is discovery evidence, not proof of device type or physical connectivity. MAC is a cached Windows neighbour value; unknown fields stay unavailable.','muted'))
        row=QHBoxLayout();layout.addLayout(row);self.subnet=QLineEdit(w.store.setting('discovery_subnet','192.168.1.0/24'));self.subnet.setPlaceholderText('IPv4 subnet');row.addWidget(self.subnet,2);self.timeout=QSpinBox();self.timeout.setRange(100,2000);self.timeout.setValue(w.store.setting('discovery_timeout_ms',500));self.timeout.setSuffix(' ms');row.addWidget(self.timeout);self.filter=QLineEdit();self.filter.setPlaceholderText('Filter IP / status / MAC');self.filter.textChanged.connect(self.render);row.addWidget(self.filter,2)
        self.resolve=QCheckBox('Resolve hostnames with Windows DNS (optional, adds bounded DNS lookups)');self.resolve.setChecked(w.store.setting('discovery_resolve_names',False));layout.addWidget(self.resolve)
        tools=QHBoxLayout();layout.addLayout(tools);self.start=action('Start Scan',self.begin);self.stop=action('Stop Scan',self.stop_scan);self.rescan=action('Rescan',self.begin);self.add=action('Add Selected Devices',self.add_selected)
        for b in (self.start,self.stop,self.rescan,self.add):tools.addWidget(b)
        self.stop.setEnabled(False);self.progress=QProgressBar();layout.addWidget(self.progress);self.status=text('Ready · no scan started');layout.addWidget(self.status)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['IP address','Hostname','MAC (cached)','Vendor','Detection','Latency']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setSelectionMode(QTableWidget.ExtendedSelection);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);layout.addWidget(self.table,1)
    def begin(self):
        if self.running or self.import_queue:return
        try:
            hosts=targets(self.subnet.text());source=self.w.current_page().source_ip
            if source and ipaddress.ip_address(source).version!=4:raise ValueError('This scanner uses IPv4. Select an IPv4 local source/network.')
            if not self.w.policy.allows('monitoring'):raise ValueError('Monitoring permission is required.')
        except ValueError as e:QMessageBox.warning(self,'Cannot scan',str(e));return
        self.scan_page=self.w.page_id;self.scan_source=source;self.rows=[];self.render();self.cancel=threading.Event();self.running=True;self.start.setEnabled(False);self.rescan.setEnabled(False);self.stop.setEnabled(True);self.add.setEnabled(False);self.subnet.setEnabled(False);self.progress.setRange(0,len(hosts));self.progress.setValue(0);self.w.store.set_setting('discovery_subnet',self.subnet.text().strip());self.w.store.set_setting('discovery_timeout_ms',self.timeout.value());self.status.setText('Scanning · 4 background workers · source '+(source or 'Windows route'))
        self.w.store.set_setting('discovery_resolve_names',self.resolve.isChecked());self.pool.start(ScanTask(hosts,source,self.timeout.value(),self.cancel,self.signals,probe_fn=self.probe_fn,resolve=self.resolve.isChecked()))
    def found(self,row):
        if not self.running or self.cancel.is_set():return
        self.rows.append(row);self.progress.setValue(len(self.rows));self.dirty=True
    def finished(self,message):
        self.render()
        self.running=False;self.start.setEnabled(True);self.rescan.setEnabled(True);self.stop.setEnabled(False);self.add.setEnabled(True);self.subnet.setEnabled(True);self.status.setText(message+f' · {len(self.rows)} checked · '+str(sum(r['status']=='Responding' for r in self.rows))+' responding')
    def stop_scan(self):
        if self.import_queue:
            self.import_queue=[];self.finish_import('Import stopped; already added devices retained');return
        if self.running:self.cancel.set();self.stop.setEnabled(False);self.status.setText('Stopping · waiting for at most 4 bounded in-flight checks')
    def render(self):
        self.dirty=False
        selected={self.table.item(i.row(),0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows() if self.table.item(i.row(),0)};query=self.filter.text().casefold();shown=[r for r in self.rows if query in ' '.join(map(str,r.values())).casefold()];self.table.setRowCount(len(shown))
        for i,row in enumerate(shown):
            vals=[row['ip'],row['hostname'],row['mac'],row['vendor'],row['status'],f"{row['latency']:.1f} ms" if row['latency'] is not None else 'Unavailable']
            for j,value in enumerate(vals):
                item=QTableWidgetItem(value);item.setToolTip(row['error'] if j==4 else value)
                if j==0:item.setData(Qt.UserRole,row['ip'])
                self.table.setItem(i,j,item)
            if row['ip'] in selected:self.table.selectionModel().select(self.table.model().index(i,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    def add_selected(self):
        if self.running or self.import_queue:self.status.setText('Stop/wait for the active scan or import before adding.');return
        if not self.w.policy.allows('monitoring'):QMessageBox.warning(self,'Cannot add devices','Monitoring permission is required.');return
        if self.scan_page!=self.w.page_id or self.scan_source!=self.w.current_page().source_ip:QMessageBox.information(self,'Select scanned network','Return to the network where this scan ran before adding devices.');return
        ips={self.table.item(i.row(),0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows()};chosen=[r for r in self.rows if r['ip'] in ips and r['status']=='Responding'];existing={(d.host,d.source or self.w.current_page().source_ip) for d in self.w.devices};new=[r for r in chosen if (r['ip'],self.scan_source) not in existing]
        if not new:self.status.setText('Select responding devices. Existing devices are skipped.');return
        if len(self.w.store.devices())+len(new)>self.w.policy.max_devices:QMessageBox.warning(self,'Device limit','Selection exceeds the current device limit.');return
        if QMessageBox.question(self,'Add discovered devices',f'Add {len(new)} responding devices to this network? Device types and physical links remain unassigned.')!=QMessageBox.Yes:return
        safety=self.w.store.path.parent/f'before-discovery-import-{time.time_ns()}.sqlite3'
        try:
            self.w.store.backup(safety)

        except (ValueError,OSError,sqlite3.Error) as e:
            self.w.reload();QMessageBox.warning(self,'Discovery import failed',str(e)+'\nExisting records are retained; check the pre-import backup if a partial addition occurred.');return
        self.import_queue=list(new);self.import_added=0;self.start.setEnabled(False);self.rescan.setEnabled(False);self.add.setEnabled(False);self.stop.setEnabled(True);self.status.setText('Adding selected devices · pre-import backup saved');self.import_timer.start();self.import_batch()
    def import_batch(self):
        if self.w.page_id!=self.scan_page or self.w.current_page().source_ip!=self.scan_source:self.import_queue=[];self.finish_import('Network/source changed; partial import retained');return
        try:
            for _ in range(min(4,len(self.import_queue))):
                row=self.import_queue[0];existing={(d.host,d.source or self.w.current_page().source_ip) for d in self.w.store.devices() if d.page_id==self.scan_page}
                if (row['ip'],self.scan_source) not in existing:self.w.store.save(Device(name=row['ip'],host=row['ip'],source=self.scan_source,page_id=self.scan_page,notes='Added from operator-started ICMP discovery; type/topology not verified.'));self.import_added+=1
                self.import_queue.pop(0)
        except (ValueError,OSError,sqlite3.Error) as e:
            self.import_queue=[];self.finish_import('Import stopped: '+str(e));return
        self.status.setText(f'Adding selected devices · {self.import_added} saved · {len(self.import_queue)} pending')
        if not self.import_queue:self.finish_import('Import complete; existing devices preserved')
    def finish_import(self,message):
        self.import_timer.stop();self.start.setEnabled(True);self.rescan.setEnabled(True);self.add.setEnabled(True);self.stop.setEnabled(False);self.w.reload();self.status.setText(message+f' · {self.import_added} added · pre-import backup retained')
    def shutdown(self):self.import_timer.stop();self.import_queue=[];self.render_timer.stop();self.cancel.set();self.pool.clear();self.pool.waitForDone()
