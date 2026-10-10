"""Separate live WAN traffic and sequential, route-checked active tests."""
import time
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox

class SevenWanPanel(QWidget):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.queue=[];self.active=None;self.generation=None;self.messages={};self.poll_queue=[]
        layout=QVBoxLayout(self)
        title=QLabel('INTERNET CONNECTIONS • LIVE TRAFFIC & SPEED TESTS');title.setObjectName('title');layout.addWidget(title)
        note=QLabel('Each modem has its own row. Live download/upload = verified WAN interface traffic. Test download/upload = controlled HTTPS transfers, not guaranteed maximum capacity. Start monitoring for live readings. Same-subnet LAN IPs alone do not select seven Internet paths.');note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(7,9);self.table.setHorizontalHeaderLabels(['Modem / IP','Ping','Live ↓ Mbps','Live ↑ Mbps','Test ↓ Mbps','Test ↑ Mbps','Last test / age','WAN interface','Test status / path']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setSelectionMode(QTableWidget.SingleSelection);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table,1)
        row=QHBoxLayout();layout.addLayout(row)
        for index,(title,fn) in enumerate([('Add modem',self.add),('Edit modem',self.edit),('WAN setup',self.setup),('Counter adapter',self.adapter),('Check all pings / traffic',self.poll),('Test selected',self.test_one),('Test all (sequential)',self.test_all),('Cancel tests',self.cancel_tests)]):
            if index==4:row=QHBoxLayout();layout.addLayout(row)
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        self.status=QLabel('Manual tests use configured HTTPS endpoints and a per-modem daily data budget. Upload requires an authorized receiver.');self.status.setWordWrap(True);layout.addWidget(self.status)
        browser=QHBoxLayout();layout.addLayout(browser)
        browser.addWidget(QLabel('Browser tests use the laptop current Internet connection:'))
        for name,url in [('Open FAST.com','https://fast.com'),('Open Ookla','https://www.speedtest.net')]:
            b=QPushButton(name);b.clicked.connect(lambda checked=False,u=url:QDesktopServices.openUrl(QUrl(u)));browser.addWidget(b)
        browser.addStretch()
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(500);self.refresh()
    def modems(self):return [d for d in self.w.devices if d.wan or d.kind.startswith('WAN')]
    def device(self):
        item=self.table.item(self.table.currentRow(),0)
        return next((d for d in self.modems() if item and d.id==item.data(Qt.UserRole)),None)
    def add(self):
        from .core import Device
        self.w.edit_device(Device(name='Internet modem',kind='WAN / Internet',wan=1,page_id=self.w.page_id))
        self.refresh()
    def edit(self):
        d=self.device()
        if d:self.w.edit_device(d);self.refresh()
    def setup(self):
        d=self.device()
        if d:
            from .wan_dialog import WanDialog
            WanDialog(self.w,d).exec();self.refresh()
    def adapter(self):
        d=self.device()
        if d:
            from .professional import IntegrationDialog
            IntegrationDialog(self.w,d).exec();self.refresh()
    def poll(self):
        ids={d.id for d in self.modems() if d.enabled and d.host}
        self.w.requested.update(ids);self.w.engine.devices=self.w.monitor_devices()
        self.poll_queue=list(self.modems());self.generation=self.w.engine.generation
        self.w.drain()
        self.tick()
        self.status.setText('Ping checks requested. Start monitoring for recurring WAN counter readings; two counter samples are needed for live rates.')
    def test_one(self):
        d=self.device()
        if d:self.begin([d])
    def test_all(self):self.begin(self.modems())
    def begin(self,devices):
        if self.queue or self.active:
            QMessageBox.information(self,'Tests running','Wait for this batch or cancel it first.');return
        self.queue=list(devices);self.generation=self.w.engine.generation;self.messages={};self.status.setText(f'{len(self.queue)} modem(s) queued. Tests run one at a time; download and optional upload consume the configured data budget.');self.tick()
    def cancel_tests(self):
        for d in self.queue:self.messages[d.id]='Cancelled before test'
        self.queue=[]
        if self.active:
            event=self.w.measurements.speed_cancels.get(self.active.id)
            if event:event.set()
            self.messages[self.active.id]='Cancellation requested'
        self.status.setText('Tests cancelled. Existing live monitoring continues; reserved test data stays charged.')
    def tick(self):
        m=self.w.measurements
        if self.generation is not None and self.generation!=self.w.engine.generation:
            self.cancel_tests();self.poll_queue=[];self.generation=None
        if self.active and (self.active.id,True) not in m.pending:
            r=m.speed_latest.get(self.active.id,{})
            self.messages[self.active.id]=r.get('error',r.get('upload_note','Completed: Windows next-hop checked'))
            self.active=None
        if self.queue and not self.active and not any(speed for _,speed in m.pending):
            d=self.queue[0]
            if d not in self.w.monitor_devices():self.messages[d.id]='Configuration changed; skipped';self.queue.pop(0)
            else:
                try:
                    if m.submit(d,True,independent=True):self.active=d;self.queue.pop(0);self.messages[d.id]='Testing download / upload…'
                    elif d.id in self.w.ambiguous_devices:self.messages[d.id]='Ambiguous target path; skipped';self.queue.pop(0)
                    elif not d.enabled or not d.host:self.messages[d.id]='Disabled or missing modem IP';self.queue.pop(0)
                    elif not self.w.page_for_device(d).routing_verified and (self.w.monitor_all_enabled or self.w.page_for_device(d).gateway_hint or self.w.page_for_device(d).interface_hint):self.messages[d.id]='Verify network path first';self.queue.pop(0)
                except ValueError as e:self.messages[d.id]=str(e);self.queue.pop(0)
        if self.poll_queue and not self.queue and not self.active:
            d=self.poll_queue[0];page=self.w.page_for_device(d)
            blocked=(d not in self.w.monitor_devices() or not d.enabled or not d.host or page is None or page.archived or d.id in self.w.ambiguous_devices or ((self.w.monitor_all_enabled or page.gateway_hint or page.interface_hint) and not page.routing_verified))
            if blocked or m.submit(d):self.poll_queue.pop(0)
        if self.isVisible():self.refresh()
    def refresh(self):
        selected=self.device();devices=self.modems();self.table.setRowCount(max(7,len(devices)));now=time.time()
        def value(r,key,fresh):return f'{r[key]:.2f}' if fresh and key in r else 'Unavailable'
        for i in range(self.table.rowCount()):
            d=devices[i] if i<len(devices) else None
            if not d:vals=[f'Connection {i+1} — Add modem','Not configured']+['—']*7
            else:
                r=self.w.measurements.latest.get(d.id,{});s=self.w.measurements.speed_latest.get(d.id,{})
                live=now-r.get('at',0)<=max(30,d.integration.get('poll_seconds',30)*3)
                tested=s.get('path_checked',False) and not s.get('error');age=now-s.get('at',0)
                stamp=time.strftime('%H:%M:%S',time.localtime(s['at']))+f' ({int(age)}s ago)' if s.get('at') else 'Not tested'
                vals=[d.name+' / '+(d.host or 'IP missing'),self.w.state(d),value(r,'download_mbps',live),value(r,'upload_mbps',live),value(s,'download_mbps',tested),value(s,'upload_mbps',tested),stamp,d.integration.get('wan_interface') or 'Not mapped',self.messages.get(d.id,s.get('error',s.get('upload_note','Gateway: '+(d.integration.get('speed_gateway') or 'not configured'))))]
            for j,v in enumerate(vals):
                item=QTableWidgetItem(v);item.setToolTip(v)
                if j==0 and d:item.setData(Qt.UserRole,d.id)
                self.table.setItem(i,j,item)
            if selected and d and selected.id==d.id:self.table.selectRow(i)
