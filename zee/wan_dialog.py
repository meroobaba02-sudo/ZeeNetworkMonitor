"""Beginner WAN controls and asynchronous, read-only route inspection."""
from dataclasses import replace
import time,socket
from urllib.parse import urlsplit
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QSpinBox,QDoubleSpinBox,QCheckBox,QLabel,QTextEdit,QPushButton,QDialogButtonBox,QMessageBox,QScrollArea,QWidget
from .telemetry import validate_profile
from .wan import route_report

class Signals(QObject):done=Signal(str)
class RouteTask(QRunnable):
    def __init__(self,target,source,signals):super().__init__();self.target=target;self.source=source;self.signals=signals
    def run(self):
        try:
            host=urlsplit(self.target).hostname
            if host:
                family=socket.AF_INET6 if ':' in self.source else socket.AF_INET
                target=socket.getaddrinfo(host,443,family,socket.SOCK_STREAM)[0][4][0]
            else:target=self.target
            text=route_report(target,self.source)
            from .wan_paths import find_route
            import re
            selected=re.search(r'OS-selected local source: ([^\s]+)',text).group(1)
            route=find_route(target,selected)
            text='Internet next hop: '+route['gateway']+'\nLocal laptop IP: '+route['source']+'\nInterface index: '+str(route['interface'])+'\n\n'+text
        except (ValueError,OSError) as e:text='Cannot verify Internet route: '+str(e)
        self.signals.done.emit(text)

class WanDialog(QDialog):
    def __init__(self,w,d):
        super().__init__(w);self.w=w;self.d=d;self.setWindowTitle('WAN setup / Windows route check');self.resize(760,740)
        layout=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();form=QFormLayout(body);scroll.setWidget(body);layout.addWidget(scroll,2);self.fields={};p=d.integration
        for key,title in [('internet_url','HTTPS Internet-check endpoint'),('internet_marker','Expected response text'),('speed_url','HTTPS download-test endpoint'),('upload_url','Authorized HTTPS upload receiver'),('speed_gateway','Modem Internet gateway IP (actual next hop)')]:
            edit=QLineEdit(p.get(key,''));self.fields[key]=edit;form.addRow(title,edit)
        self.source=QLineEdit(d.source or w.current_page().source_ip);form.addRow('Local source IP (blank = OS route)',self.source)
        for key,title,low,high,default in [('poll_seconds','Check interval (seconds)',5,3600,30),('speed_mb','Download test limit (MiB)',1,64,1),('upload_mb','Upload test limit (MiB)',1,16,1),('speed_seconds','Transfer duration limit (seconds)',1,30,5),('daily_mb','Daily test budget (MiB)',1,1024,10),('speed_interval','Automatic test interval (seconds)',900,86400,900),('rate_cap_kbps','Read-rate cap (KiB/s, 0 = none)',0,1000000,0),('internet_latency_warning_ms','HTTPS latency warning (ms)',1,60000,1500)]:
            spin=QSpinBox();spin.setRange(low,high);spin.setValue(p.get(key,default));self.fields[key]=spin;form.addRow(title,spin)
        for key,title,high,default in [('min_download_mbps','Low measured download warning (Mbps)',100000,0),('loss_warning_pct','Router ping loss warning (%)',100,10)]:
            spin=QDoubleSpinBox();spin.setRange(0,high);spin.setValue(p.get(key,default));self.fields[key]=spin;form.addRow(title,spin)
        self.auto=QCheckBox('Enable automatic download tests (consumes data)');self.auto.setChecked(p.get('automatic_speed',False));form.addRow(self.auto)
        self.verified=QCheckBox('I verified this source/interface/gateway reaches this specific WAN');self.verified.setChecked(p.get('wan_verified',False));form.addRow(self.verified)
        self.counter_interface=QLineEdit(p.get('wan_interface',''));form.addRow('WAN counter interface (e.g. actual port name)',self.counter_interface)
        self.counter_verified=QCheckBox('I verified these counters measure this WAN interface');self.counter_verified.setChecked(p.get('wan_counter_verified',False));form.addRow(self.counter_verified)
        for key in ('internet_url','internet_marker','speed_url','upload_url','speed_gateway'):self.fields[key].textChanged.connect(lambda *_:self.verified.setChecked(False))
        self.source.textChanged.connect(lambda *_:self.verified.setChecked(False))
        self.counter_interface.textChanged.connect(lambda *_:self.counter_verified.setChecked(False))
        day=time.strftime('%Y-%m-%d');used=w.store.setting('speed-budget:'+d.id+':'+day,0)
        note=QLabel(f'Today: {used/1048576:.2f} MiB reserved for tests. Failed tests retain the reservation. Internet speeds tests verify the Windows next hop on each actual TLS socket. Upload receiver must acknowledge JSON received_bytes. Live traffic requires verified WAN counters. Browser tests use the laptop current connection. Router ping and external HTTPS status are separate. HTTPS latency includes connection/TLS/server time. Rate cap limits reads, not guaranteed wire bandwidth.');note.setWordWrap(True);layout.addWidget(note)
        preset=QPushButton('Use Cloudflare download-test setup');preset.clicked.connect(self.download_preset);layout.addWidget(preset)
        hint=QLabel('Gateway = the modem Internet next hop, not necessarily its management/ping IP. Source = an IP assigned to this laptop. Seven modems on one switch need correct Windows routes or separate interfaces; the software cannot select a modem by ping IP alone.');hint.setWordWrap(True);layout.addWidget(hint)
        self.check=QPushButton('Inspect Internet route / adapters (read-only)');self.check.clicked.connect(self.inspect);layout.addWidget(self.check)
        self.report=QTextEdit();self.report.setReadOnly(True);layout.addWidget(self.report,1)
        self.signals=Signals();self.signals.done.connect(self.finished_report)
        box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.accepted.connect(self.accept);box.rejected.connect(self.reject);layout.addWidget(box)
    def download_preset(self):
        self.fields['internet_url'].setText('https://speed.cloudflare.com/cdn-cgi/trace')
        self.fields['internet_marker'].setText('h=')
        self.fields['speed_url'].setText('https://speed.cloudflare.com/__down?bytes=1048576')
        self.fields['speed_mb'].setValue(1)
        self.fields['rate_cap_kbps'].setValue(0)
        self.verified.setChecked(False)
        self.report.setPlainText('Download endpoint configured. Inspect the Internet route, enter the actual next hop, verify this WAN path, then Save. Upload still requires an authorized receiver. No test has started.')

    def inspect(self):
        self.check.setEnabled(False);self.report.setPlainText('Inspecting local route...')
        QThreadPool.globalInstance().start(RouteTask(self.fields['speed_url'].text().strip() or self.fields['internet_url'].text().strip() or 'https://speed.cloudflare.com/__down?bytes=0',self.source.text().strip(),self.signals))
    def finished_report(self,text):self.report.setPlainText(text);self.check.setEnabled(True)
    def value(self):
        p=dict(self.d.integration)
        for key,widget in self.fields.items():p[key]=widget.text().strip() if isinstance(widget,QLineEdit) else widget.value()
        p.update(automatic_speed=self.auto.isChecked(),wan_verified=self.verified.isChecked(),wan_interface=self.counter_interface.text().strip(),wan_counter_verified=self.counter_verified.isChecked());validate_profile(p)
        source=self.source.text().strip()
        if source!=(self.d.source or self.w.current_page().source_ip):p['wan_verified']=False
        d=replace(self.d,integration=p,source=source);d.validate();return d
    def accept(self):
        try:
            value=self.value()
            self.w._resume_minimized=False
            self.w.engine.invalidate();self.w.engine.stop();self.w.measurements.stop();self.w.requested.clear()
            self.w.store.save(value)
            self.w.measurements.latest.pop(self.d.id,None);self.w.measurements.speed_latest.pop(self.d.id,None);self.w.telemetry_alerted.pop(self.d.id,None)
            self.w.reload()
        except (ValueError,OSError) as e:QMessageBox.warning(self,'Cannot save WAN',str(e));return
        super().accept()
