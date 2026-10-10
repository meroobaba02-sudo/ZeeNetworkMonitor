"""Guided network pages and explicit links, with read-only background path tests."""
from dataclasses import replace
import ipaddress,uuid,time
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool,Qt,QEvent
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QComboBox,QCheckBox,QLineEdit,QDialogButtonBox,QMessageBox,QTextEdit,QFormLayout
from .workspaces import NetworkPage
from .network_paths import interfaces,inspect_path


class Signals(QObject):done=Signal(object)
class Task(QRunnable):
    def __init__(self,operation,fn,signals,context=None):
        super().__init__();self.operation=operation;self.fn=fn;self.signals=signals;self.context=context
    def run(self):
        try:result={'value':self.fn()}
        except Exception:result={'error':'Check unavailable: invalid IP, adapter access, route or timeout. No configuration was changed.'}
        self.signals.done.emit(result|{'operation':self.operation,'context':self.context})


class NetworkSetup(QDialog):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWindowTitle('Network setup — laptop IPs and path checks');self.resize(1000,710)
        self.closed=False;self.busy=False;self.inventory=[];self.rows=[];self.field_rows={};self.selected_row=-1
        self.signals=Signals();self.signals.done.connect(self.completed)
        layout=QVBoxLayout(self)
        note=QLabel('1. Name each network.  2. Select a laptop IP.  3. Test a real target.  4. Verify the intended Windows path, then tick Operator verified.\nThis software does not add IPs, routes, VLANs or VPNs. For multiple subnets, Windows needs reachable routes or suitable adapter addresses. Same target IP on separate networks needs distinct sources and independently verified paths.');note.setWordWrap(True);layout.addWidget(note)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.load=QPushButton('Read laptop IPs / adapters');self.load.clicked.connect(self.load_adapters);actions.addWidget(self.load)
        self.check=QPushButton('Check selected network');self.check.clicked.connect(self.check_selected);actions.addWidget(self.check)
        add=QPushButton('Add network row');add.clicked.connect(lambda:self.add_row());actions.addWidget(add)
        refresh=QPushButton('Refresh monitoring overview');refresh.clicked.connect(self.overview);actions.addWidget(refresh)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Network name','Laptop source IP / adapter','Gateway (reference)','Operator verified','Test target IP'])
        self.table.currentCellChanged.connect(lambda row,*args:setattr(self,'selected_row',row))
        layout.addWidget(self.table)
        pages=[p for p in w.store.pages() if not p.archived]
        for p in pages:self.add_row(p)
        while len(self.rows)<5:self.add_row()
        self.table.setCurrentCell(0,0)
        self.table.resizeColumnsToContents();self.table.setColumnWidth(1,270);self.table.setColumnWidth(0,170)
        self.report=QTextEdit();self.report.setReadOnly(True);layout.addWidget(self.report,1)
        self.status=QLabel('No interface inventory loaded. Enter an existing laptop IP manually, or read adapters.');self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.overview()
    def add_row(self,page=None):
        index=len(self.rows);page=page or NetworkPage(id=str(uuid.uuid4()),name=f'Network {index+1}',order=index)
        self.table.insertRow(index)
        name=QLineEdit(page.name);source=QComboBox();source.setEditable(True)
        source.addItem('Automatic (Windows route)',{'ip':'','name':''});source.setEditText(page.source_ip or 'Automatic (Windows route)')
        gateway=QLineEdit(page.gateway_hint);verified=QCheckBox();verified.setChecked(page.routing_verified)
        target=QLineEdit(self.w.store.setting('network_path_targets',{}).get(page.id,''))
        for col,widget in enumerate((name,source,gateway,verified,target)):self.table.setCellWidget(index,col,widget)
        for widget in (name,source,source.lineEdit(),gateway,verified,target):
            self.field_rows[widget]=index;widget.installEventFilter(self)
        source.currentTextChanged.connect(lambda *args,v=verified:v.setChecked(False))
        gateway.textChanged.connect(lambda *args,v=verified:v.setChecked(False))
        target.textChanged.connect(lambda *args,v=verified:v.setChecked(False))
        self.rows.append({'page':page,'name':name,'source':source,'gateway':gateway,'verified':verified,'target':target})
    def source_value(self,row):
        combo=row['source'];text=combo.currentText().strip();index=combo.findText(text)
        data=combo.itemData(index) if index>=0 else None
        return data if data is not None else {'ip':text,'name':''}
    def eventFilter(self,widget,event):
        if event.type()==QEvent.FocusIn and widget in self.field_rows:self.selected_row=self.field_rows[widget]
        return super().eventFilter(widget,event)
    def begin(self,operation,fn,context=None):
        if self.busy:return
        self.busy=True;self.load.setEnabled(False);self.check.setEnabled(False);self.status.setText('Checking in background…')
        QThreadPool.globalInstance().start(Task(operation,fn,self.signals,context))
    def load_adapters(self):self.begin('inventory',interfaces)
    def check_selected(self):
        index=self.selected_row
        if index<0:self.status.setText('Select a network row first.');return
        row=self.rows[index];source=self.source_value(row)['ip'];target=row['target'].text().strip()
        try:
            ipaddress.ip_address(target)
            if source:ipaddress.ip_address(source)
        except ValueError:self.status.setText('Enter literal target and optional local source IP addresses.');return
        self.begin('path',lambda:inspect_path(target,source),(index,source,target))
    def completed(self,result):
        self.busy=False
        if self.closed:return
        self.load.setEnabled(True);self.check.setEnabled(True)
        if result.get('error'):self.status.setText(result['error']);return
        if result['operation']=='inventory':
            self.inventory=result['value']
            for row in self.rows:
                selected=self.source_value(row)['ip'];combo=row['source'];combo.blockSignals(True);combo.clear();combo.addItem('Automatic (Windows route)',{'ip':'','name':''})
                for item in self.inventory:combo.addItem(item['ip']+' — '+item['name'],item)
                found=next((i for i in range(combo.count()) if combo.itemData(i)['ip']==selected),None)
                if found is not None:combo.setCurrentIndex(found)
                else:combo.setEditText(selected)
                combo.blockSignals(False)
            self.status.setText(f'{len(self.inventory)} local addresses read. Selecting an address does not create a route.')
        else:
            index,source,target=result['context'];row=self.rows[index]
            if self.source_value(row)['ip']!=source or row['target'].text().strip()!=target:
                self.status.setText('Inputs changed during the check; previous result ignored.');return
            self.report.setPlainText(result['value']['text']);self.status.setText('Check finished. Operator verification remains a separate manual decision.')
            reports=self.w.store.setting('network_path_reports',{});reports[row['page'].id]=result['value']|{'configured_source':source};self.w.store.set_setting('network_path_reports',reports)
    def overview(self):
        text=[]
        for page in self.w.store.pages():
            if page.archived:continue
            devices=[d for d in self.w.all_devices if d.page_id==page.id]
            monitored=self.w.monitor_all_enabled or page.id==self.w.page_id
            online=sum(self.w.state(d)=='Online' for d in devices) if monitored else 0
            text.append(f'{page.name}: {len(devices)} devices • {online} replying • '+('in monitoring scope' if monitored else 'not monitored')+f' • source: {page.source_ip or "Automatic"} • '+('operator verified' if page.routing_verified else 'path not operator-verified'))
        self.report.setPlainText('\n'.join(text)+'\n\nSave changes stops monitoring. Start monitoring again after checking paths. All-network mode requires operator verification for each active page. Blank added rows are new pages, not invented devices/IPs.')
    def values(self):
        pages=[];targets={}
        for row in self.rows:
            source=self.source_value(row)
            page=replace(row['page'],name=row['name'].text().strip(),source_ip=source['ip'],interface_hint=source['name'] or (row['page'].interface_hint if source['ip']==row['page'].source_ip else ''),gateway_hint=row['gateway'].text().strip(),routing_verified=row['verified'].isChecked())
            page.validate();target=row['target'].text().strip()
            if target:ipaddress.ip_address(target)
            targets[page.id]=target;pages.append(page)
        return pages,targets
    def accept(self):
        try:pages,targets=self.values()
        except ValueError as e:QMessageBox.warning(self,'Check network setup',str(e));return
        old={p.id:p for p in self.w.store.pages()};changed={p.id for p in pages if p.id not in old or (p.source_ip,p.interface_hint,p.gateway_hint)!=(old[p.id].source_ip,old[p.id].interface_hint,old[p.id].gateway_hint)}
        self.w.engine.invalidate();self.w.measurements.stop();self.w.requested.clear()
        self.w.store.save_pages(pages)
        self.w.store.set_setting('network_path_targets',self.w.store.setting('network_path_targets',{})|targets)
        for d in self.w.store.devices():
            if d.page_id in changed and d.integration.get('wan_verified'):self.w.store.save(replace(d,integration=d.integration|{'wan_verified':False}))
        self.w.states.clear();self.w.latest.clear();self.w.alerted.clear();self.w.telemetry_alerted.clear();self.w.streaks.clear()
        self.w.measurements.latest.clear();self.w.measurements.speed_latest.clear()
        self.w.start_button.setText('▶ Start monitoring');self.w.reload();self.w.store.event('','config','Network setup saved; monitoring stopped')
        self.closed=True;super().accept()
    def reject(self):self.closed=True;super().reject()
    def closeEvent(self,event):self.closed=True;super().closeEvent(event)


class RadioLinks(QDialog):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWindowTitle('Connect radios between towers');self.resize(620,420)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        names={s.id:s.name for s in w.page_stations()};self.first=QComboBox();self.second=QComboBox()
        for d in w.devices:
            for combo in (self.first,self.second):combo.addItem(names.get(d.station_id,'No tower')+' / '+d.name+' ['+d.id[:6]+']',d.id)
        if self.second.count()>1:self.second.setCurrentIndex(1)
        form.addRow('First / upstream radio',self.first);form.addRow('Second / downstream radio',self.second)
        self.upstream=QCheckBox('Use first radio as upstream parent of second');form.addRow(self.upstream)
        note=QLabel('Both endpoints must belong to this network. Peer links represent a configured radio pair; ping is reachability, not proof of a working wireless link. Existing peer links must be removed before replacing them.');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();layout.addLayout(row)
        connect=QPushButton('Save link');connect.clicked.connect(self.connect_pair);row.addWidget(connect)
        remove=QPushButton('Remove first radio peer link');remove.clicked.connect(self.remove_pair);row.addWidget(remove)
        self.report=QTextEdit();self.report.setReadOnly(True);layout.addWidget(self.report);self.refresh()
        close=QPushButton('Close');close.clicked.connect(self.accept);layout.addWidget(close)
    def refresh(self):
        devices={d.id:d for d in self.w.devices};links=[]
        for d in devices.values():
            if d.peer_id in devices and (devices[d.peer_id].peer_id!=d.id or d.id<d.peer_id):links.append(d.name+' ↔ '+devices[d.peer_id].name)
        self.report.setPlainText('\n'.join(links) or 'No configured peer links on this page.')
    def changed(self):
        self.w.engine.invalidate();self.w.measurements.stop();self.w.requested.clear();self.w.start_button.setText('▶ Start monitoring');self.w.reload();self.refresh()
    def connect_pair(self):
        try:self.w.store.link_radios(self.first.currentData(),self.second.currentData(),self.upstream.isChecked());self.changed()
        except ValueError as e:QMessageBox.warning(self,'Cannot link radios',str(e))
    def remove_pair(self):
        try:self.w.store.unlink_radios(self.first.currentData());self.changed()
        except ValueError as e:QMessageBox.warning(self,'Cannot remove link',str(e))
