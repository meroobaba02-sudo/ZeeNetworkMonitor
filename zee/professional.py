"""Network pages, secure integration setup, live detail/alignment and WAN views."""
import json,time,uuid,math
from dataclasses import asdict,replace
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl,QPointF
from PySide6.QtGui import QDesktopServices,QPainter,QColor,QPen
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QCheckBox,QComboBox,QPushButton,QDialogButtonBox,QMessageBox,QFileDialog,QInputDialog,QTextEdit,QTableWidget,QTableWidgetItem,QApplication,QDoubleSpinBox,QSpinBox,QScrollArea)
from .customer_theme import status_color
from .workspaces import NetworkPage
from .connections import management_url,validate_url
from .telemetry import DEFAULT_PROFILE,quality,validate_profile

class PageDialog(QDialog):
    def __init__(self,parent,page):
        super().__init__(parent);self.page=page;self.setWindowTitle('Network page and routing');self.resize(560,410)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form);self.fields={}
        for key,title in [('name','Network name'),('source_ip','Optional local source IP'),('interface_hint','Network adapter name (reference)'),('gateway_hint','Gateway (reference)'),('notes','Routing / cable notes')]:
            edit=QLineEdit(str(getattr(page,key)));self.fields[key]=edit;form.addRow(title,edit)
        self.verified=QCheckBox('I verified the Windows route/interface for this network');self.verified.setChecked(page.routing_verified);form.addRow(self.verified)
        label=QLabel('Selected-page mode stops checks when changing pages. Optional Monitor all networks keeps active pages running together and requires operator-verified paths. Source IP binds supported ICMP/HTTP probes; adapter/gateway names are references, not route changes. Overlapping destinations need distinct sources and verified Windows/VPN routing. No routes are installed automatically.');label.setWordWrap(True);layout.addWidget(label)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def value(self):
        p=replace(self.page,**{k:w.text().strip() for k,w in self.fields.items()},routing_verified=self.verified.isChecked());p.validate();return p
    def accept(self):
        try:self.value()
        except ValueError as e:QMessageBox.warning(self,'Invalid network',str(e));return
        super().accept()

class IntegrationDialog(QDialog):
    def __init__(self,window,d):
        super().__init__(window);self.window=window;self.d=d;self.setWindowTitle('Secure access / telemetry / WAN');self.resize(700,670)
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();scroll.setWidget(body);outer.addWidget(scroll,1);layout=QVBoxLayout(body);form=QFormLayout();layout.addLayout(form)
        self.method=QComboBox();self.method.addItems(['none','snmp','https-json']);self.method.setCurrentText(d.integration.get('method','none'));form.addRow('Measurement method',self.method)
        self.snmp_version=QComboBox();self.snmp_version.addItems(['1','2c']);self.snmp_version.setCurrentText(d.integration.get('snmp_version','2c'));form.addRow('SNMP version (airOS guide: v1)',self.snmp_version)
        self.poll_seconds=QSpinBox();self.poll_seconds.setRange(5,3600);self.poll_seconds.setValue(d.integration.get('poll_seconds',30));form.addRow('Polling interval (seconds)',self.poll_seconds)
        self.trusted=QCheckBox('Allow unencrypted SNMP on my trusted management network');self.trusted.setChecked(d.integration.get('allow_v2c',False));form.addRow(self.trusted)
        self.model=QLineEdit(d.integration.get('device_model',''));form.addRow('Actual device model (optional record)',self.model)
        self.firmware=QLineEdit(d.integration.get('firmware_version',''));form.addRow('Actual firmware version (optional record)',self.firmware)
        self.username=QLineEdit(d.username);form.addRow('Username',self.username)
        self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password);self.password.setPlaceholderText('Blank keeps existing password');form.addRow('Password (Windows protected)',self.password)
        self.community=QLineEdit();self.community.setEchoMode(QLineEdit.Password);self.community.setPlaceholderText('Blank keeps existing read-only community');form.addRow('SNMP community (Windows protected)',self.community)
        self.remove=QCheckBox('Delete all saved credentials for this device');form.addRow(self.remove)
        text=QLabel('No automatic browser login. SNMP v1/v2c community travels unencrypted: enable only on a trusted management network. HTTPS JSON uses validated TLS and sends credentials only to the configured device host. Never enter secrets in the JSON below.');text.setWordWrap(True);layout.addWidget(text)
        self.profile=QTextEdit();self.profile.setPlainText(json.dumps(DEFAULT_PROFILE|d.integration,indent=2));layout.addWidget(self.profile)
        self.profile_verified=QCheckBox('I checked this metric mapping against the actual model / firmware');self.profile_verified.setChecked(d.integration.get('firmware_verified',False));layout.addWidget(self.profile_verified)
        self.profile.textChanged.connect(lambda:self.profile_verified.setChecked(False))
        for edit in (self.model,self.firmware):edit.textChanged.connect(lambda *_:self.profile_verified.setChecked(False))
        for combo in (self.method,self.snmp_version):combo.currentTextChanged.connect(lambda *_:self.profile_verified.setChecked(False))
        helptext=QLabel('Adapter method: none / snmp / https-json. oids or fields: {"signal_dbm": {"path": "verified numeric OID or JSON/key", "scale": 1}}. Verify model/firmware before setting firmware_verified. WAN checks need wan_verified, HTTPS internet_url and internet_marker. Top controls set method, SNMP version and interval. Numeric OIDs still need verification; no model profile is guessed. Speed tests are OFF by default. See PROFESSIONAL_GUIDE.');helptext.setWordWrap(True);layout.addWidget(helptext)
        box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.accepted.connect(self.accept);box.rejected.connect(self.reject);outer.addWidget(box)
    def accept(self):
        try:
            profile=json.loads(self.profile.toPlainText())
            profile.update(method=self.method.currentText(),snmp_version=self.snmp_version.currentText(),poll_seconds=self.poll_seconds.value(),allow_v2c=self.trusted.isChecked(),device_model=self.model.text().strip(),firmware_version=self.firmware.text().strip(),firmware_verified=self.profile_verified.isChecked())
            if any(profile.get(k,'')!=self.d.integration.get(k,'') for k in ('internet_url','internet_marker','speed_url','upload_url','speed_gateway')):profile['wan_verified']=False
            if profile.get('wan_interface','')!=self.d.integration.get('wan_interface',''):profile['wan_counter_verified']=False
            if any(profile.get(k)!=self.d.integration.get(k,DEFAULT_PROFILE.get(k)) for k in ('method','snmp_version','snmp_port','url','oids','fields','device_model','firmware_version')):profile['wan_counter_verified']=False
            validate_profile(profile)
            d=replace(self.d,username=self.username.text().strip(),integration=profile);d.validate()
            if self.remove.isChecked():self.window.vault.delete(d.id)
            elif self.password.text() or self.community.text():
                secrets=self.window.vault.get(d.id)
                if self.password.text():secrets['password']=self.password.text()
                if self.community.text():secrets['community']=self.community.text()
                self.window.vault.set(d.id,secrets)
            self.window._resume_minimized=False;self.window.engine.invalidate();self.window.engine.stop();self.window.measurements.stop();self.window.requested.clear()
            self.window.measurements.latest.pop(d.id,None);self.window.measurements.speed_latest.pop(d.id,None);self.window.telemetry_alerted.pop(d.id,None)
            self.window.store.save(d);self.window.reload()
        except (ValueError,RuntimeError,OSError) as e:QMessageBox.warning(self,'Could not save',str(e));return
        super().accept()

class MetricGraph(QWidget):
    def __init__(self):super().__init__();self.values=[];self.setMinimumHeight(110)
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#0b2034'));p.setPen(QColor('#8facbf'))
        if not self.values:p.drawText(self.rect(),Qt.AlignCenter,'No measured history');return
        vals=[v for v in self.values if v is not None]
        if not vals:return
        lo,hi=min(vals),max(vals);hi=max(hi,lo+1);prev=None;p.setPen(QPen(QColor('#28e3a0'),2))
        for i,v in enumerate(self.values):
            if v is None:prev=None;continue
            pt=QPointF(15+i*(self.width()-30)/max(1,len(self.values)-1),self.height()-20-(v-lo)/(hi-lo)*(self.height()-40))
            if prev:p.drawLine(prev,pt)
            p.drawEllipse(pt,2,2);prev=pt
        p.setPen(QColor('#d1e3ef'));p.drawText(10,14,f'{lo:.1f} … {max(vals):.1f}')

def distance_bearing(a,b):
    if not a or not b or a.latitude is None or b.latitude is None:return None
    lat1,lat2=map(math.radians,(a.latitude,b.latitude));dl=math.radians(b.longitude-a.longitude)
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dl/2)**2
    distance=6371*2*math.asin(min(1,math.sqrt(h)))
    bearing=(math.degrees(math.atan2(math.sin(dl)*math.cos(lat2),math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(dl)))+360)%360
    return distance,bearing

class DeviceDetails(QDialog):
    def __init__(self,w,d):
        super().__init__(w);self.w=w;self.id=d.id;self.previous=None;self.previous_at=None;self.setWindowTitle('Device details / dish alignment');self.resize(760,760)
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();scroll.setWidget(body);outer.addWidget(scroll,1);layout=QVBoxLayout(body);self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.PlainText);self.summary.setObjectName('card');layout.addWidget(self.summary)
        self.details_toggle=QCheckBox('Show detailed metrics / alignment tools');self.details_toggle.setChecked(w.store.setting('advanced_ui',False));layout.addWidget(self.details_toggle)
        self.text=QLabel();self.text.setWordWrap(True);self.text.setTextFormat(Qt.PlainText);layout.addWidget(self.text)
        self.trend_metric=QComboBox();self.trend_metric.addItem('Quality (0–10)','quality');self.trend_metric.addItem('Signal (dBm)','signal_dbm');self.trend_metric.addItem('SNR (dB)','snr_db');self.trend_metric.addItem('TX CCQ (%)','tx_ccq');self.trend_metric.addItem('RX CCQ (%)','rx_ccq');self.trend_metric.currentIndexChanged.connect(self.refresh);layout.addWidget(self.trend_metric)
        self.graph=MetricGraph();layout.addWidget(self.graph)
        self.events=QTextEdit();self.events.setReadOnly(True);self.events.setMaximumHeight(120);layout.addWidget(self.events)
        self.feedback=QCheckBox('Alignment sound when measured quality improves (technician adjusts dish)');layout.addWidget(self.feedback)
        row=QHBoxLayout();outer.addLayout(row)
        for title,fn in [('Open management',self.open),('Refresh / Test connection',self.refresh_now),('Secure settings',self.settings),('Camera setup',self.camera_setup),('Open stream',self.stream)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
            if title in ('Camera setup','Open stream'):b.setVisible(d.kind.startswith('CCTV') or bool(d.service_url))
        def show_details(enabled):
            for widget in (self.text,self.trend_metric,self.graph,self.feedback):widget.setVisible(enabled)
        self.details_toggle.toggled.connect(show_details);show_details(self.details_toggle.isChecked())
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(1500);self.refresh()
    def device(self):return next((d for d in self.w.devices if d.id==self.id),None)
    def open(self):
        d=self.device()
        if d:self.w.open_management(d)
    def stream(self):
        d=self.device()
        if d and d.service_url:
            validate_url(d.service_url,('http','https','rtsp'))
            if not QDesktopServices.openUrl(QUrl(d.service_url)):QMessageBox.warning(self,'Player unavailable','Install/register a compatible external RTSP player, or open the camera web page.')
    def refresh_now(self):
        d=self.device()
        if d:self.w.requested.add(d.id);self.w.drain();self.w.measurements.submit(d)
    def camera_setup(self):
        d=self.device()
        if d:
            from .cctv import CameraDialog
            CameraDialog(self.w,d).exec()
    def settings(self):
        d=self.device()
        if d:IntegrationDialog(self.w,d).exec()
    def refresh(self):
        d=self.device()
        if not d:self.close();return
        r=self.w.measurements.latest.get(d.id,{});m=r.get('metrics',{});age=time.time()-r.get('at',0)
        score,label=quality(m,d.integration,age)
        fresh=0<=age<=max(30,d.integration.get('poll_seconds',30)*3)
        state=self.w.state(d);ping=self.w.latest.get(d.id,{})
        latency=f"{ping['latency']:.1f} ms" if state in ('Online','Warning') and ping.get('latency') is not None else 'Unavailable'
        simple=[d.name+' / '+(d.host or 'IP not configured'),'Ping: '+state+' • Latency: '+latency,'Service: '+(r.get('service','Not configured') if fresh else 'Unknown / no fresh check')]
        if d.wan or d.kind.startswith('WAN'):simple.append('Internet: '+(r.get('internet','Not configured') if fresh else 'Unknown / no fresh check'))
        if 'wireless' in d.kind or d.role or d.peer_id or 'signal_dbm' in m:simple.append('Wireless quality: '+label+(f' ({score}/10)' if score is not None else ''))
        simple.append('Last collection: '+(f'{max(0,int(age))}s ago'+(' • stale' if not fresh else '') if r.get('at') else 'Not collected'))
        self.summary.setText('\n'.join(simple))
        peer=next((a for a in self.w.devices if a.id==d.peer_id or a.id==d.parent),None)
        a=next((s for s in self.w.store.stations() if s.id==d.station_id),None);b=next((s for s in self.w.store.stations() if peer and s.id==peer.station_id),None);geo=distance_bearing(a,b)
        lines=[d.name+' • '+d.host,'Ping: '+self.w.state(d),'Wireless quality: '+label+(f' ({score}/10)' if score is not None else ''),'Peer: '+(peer.name if peer else 'Not assigned'),'Service: '+r.get('service','Not configured'),'Internet: '+r.get('internet','Not configured')]
        lines+=['Recorded model / firmware: '+(d.integration.get('device_model') or 'Not recorded')+' / '+(d.integration.get('firmware_version') or 'Not recorded'),
                'Profile: '+('Operator verified; physical compatibility still needs a device test' if d.integration.get('firmware_verified') else 'Blocked — verify actual firmware mapping'),
                'Measurement source: '+r.get('source_ip','Not recorded'),
                'Quality uses the worst available signal/CCQ (and optional rate), scaled 0–10. Missing metrics are not guessed.']
        if d.kind.startswith('CCTV'):
            from .cctv import camera_health
            lines.append('Camera service health: '+camera_health(d,r,time.time()))
        lines+=['Last collection: '+(time.strftime('%H:%M:%S',time.localtime(r['at'])) if r else 'Never')+(' • STALE' if r and age>max(30,d.integration.get('poll_seconds',30)*3) else '')]
        lines+=[f'{k}: {m.get(k,"Unavailable")}' for k in ['signal_dbm','signal_chain0_dbm','signal_chain1_dbm','noise_dbm','snr_db','tx_ccq','rx_ccq','tx_mbps','rx_mbps','frequency_mhz','channel_width_mhz','uptime_s','ethernet_up','wireless_up','cpu_pct','memory_pct']]
        if geo:lines.append(f'Distance {geo[0]:.2f} km • initial bearing {geo[1]:.1f}° • elevation guidance unavailable')
        rows=self.w.store.measurements(d.id,time.time()-3600,1000)
        metric=self.trend_metric.currentData();scores=[quality(x.get('metrics',{}),d.integration)[0] if metric=='quality' else x.get('metrics',{}).get(metric) for x in rows]
        self.graph.values=scores;self.graph.update();valid=[x for x in scores if x is not None]
        if valid:lines.append(f'Best last-hour {self.trend_metric.currentText()}: {max(valid):.1f} (latest 1,000 samples)')
        fresh=age<=max(30,d.integration.get('poll_seconds',30)*3)
        if score is not None and fresh and r.get('at')!=self.previous_at:
            if self.previous is not None:
                delta=round(score-self.previous,1);lines.append('Alignment trend: '+('Improving' if delta>0 else 'Deteriorating' if delta<0 else 'Stable')+f' ({delta:+.1f} quality points)')
                if self.feedback.isChecked() and delta>0:QApplication.beep()
            self.previous=score;self.previous_at=r.get('at')
        elif not fresh or score is None:self.previous=None;self.previous_at=None;lines.append('Alignment feedback paused: readings stale or unavailable')
        lines.append(r.get('telemetry_error',r.get('method','No telemetry collected')));self.text.setText('\n'.join(lines))
        self.events.setPlainText('\n'.join(x['message'] for x in self.w.store.events(d.id,limit=5)))
    def closeEvent(self,event):
        self.timer.stop();self.w.details_windows=[d for d in self.w.details_windows if d is not self];event.accept();self.deleteLater()

class ProfessionalPanel(QWidget):
    def __init__(self,w):
        super().__init__();self.w=w;layout=QVBoxLayout(self)
        title=QLabel('WAN / SERVICES / WIRELESS');layout.addWidget(title)
        self.ranking=QLabel('No independently measured download tests yet');self.ranking.setWordWrap(True);layout.addWidget(self.ranking)
        self.session_started=time.time()
        self.table=QTableWidget(0,11);self.table.setHorizontalHeaderLabels(['Device','Router ping','Internet / service','WAN health','Download Mbps','Upload Mbps','HTTPS latency (ms)','Method / freshness','Wireless quality','Router loss (recent samples)','Last Internet success']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);layout.addWidget(self.table)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.history_method=QComboBox();self.history_method.addItems(['Controlled download throughput','Interface traffic estimate']);self.history_method.currentIndexChanged.connect(self.history);layout.addWidget(self.history_method)
        self.graph=MetricGraph();layout.addWidget(self.graph)
        row=QHBoxLayout();layout.addLayout(row)
        for title,fn in [('Device details',self.details),('Configure adapter',self.configure),('WAN setup / routing',self.wan_setup),('Refresh measurements',self.poll),('Test Speed Now',self.speed)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        self.table.itemSelectionChanged.connect(self.history)
        self.timer=QTimer(self);self.timer.timeout.connect(lambda:self.refresh() if self.isVisible() else None);self.timer.start(2000)
    def device(self):
        i=self.table.item(self.table.currentRow(),0)
        return next((d for d in self.w.devices if i and d.id==i.data(Qt.UserRole)),None)
    def details(self):
        d=self.device()
        if d:self.w.show_details(d)
    def configure(self):
        d=self.device()
        if d:IntegrationDialog(self.w,d).exec()
    def wan_setup(self):
        d=self.device()
        if d:
            from .wan_dialog import WanDialog
            WanDialog(self.w,d).exec()
    def poll(self):
        d=self.device()
        if d:self.w.measurements.submit(d)
    def speed(self):
        d=self.device()
        if d:
            try:
                if not self.w.measurements.submit(d,True):QMessageBox.information(self,'Busy','Configure/enable the device or wait for running measurements.')
            except ValueError as e:QMessageBox.warning(self,'Cannot measure this WAN',str(e))
    def history(self):
        d=self.device()
        if not d:return
        from datetime import datetime
        from .dashboard import speed_statistics
        now=time.time();midnight=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        rows=self.w.store.measurements(d.id,min(midnight,self.session_started),5000)
        today=[x for x in rows if x['at']>=midnight];session=[x for x in rows if x['at']>=self.session_started]
        controlled=self.history_method.currentIndex()==0
        graph_rows=[x for x in today if x.get('rate_kind','').startswith('Controlled download')==controlled and 'download_mbps' in x]
        self.graph.values=[x.get('download_mbps') for x in graph_rows[-1000:]];self.graph.update()
        self.summary.setText('Today (local): '+speed_statistics(today)+'\nThis app session: '+speed_statistics(session)+'\nLatest 5,000 retained records; traffic usage and controlled throughput are separate. Graph: latest 1,000 samples.')

    def refresh(self):
        selected=self.device();self.table.blockSignals(True);self.table.setRowCount(0);rank=[]
        for d in self.w.devices:
            r=self.w.measurements.latest.get(d.id,{});speed=self.w.measurements.speed_latest.get(d.id,{})
            stale=time.time()-r.get('at',0)>max(30,d.integration.get('poll_seconds',30)*3)
            rate=speed if speed and time.time()-speed.get('at',0)<max(60,d.integration.get('speed_interval',900)) else r
            rate_stale=time.time()-rate.get('at',0)>max(60,d.integration.get('speed_interval',900) if rate is speed else d.integration.get('poll_seconds',30)*3)
            score,label=quality(r.get('metrics',{}),d.integration,time.time()-r.get('at',0))
            if rate is speed and not rate_stale and 'download_mbps' in rate and not d.integration.get('rate_cap_kbps'):rank.append((rate['download_mbps'],d.name))
            from .wan import wan_health
            health,reason=wan_health(d,self.w.state(d),r,speed,time.time()) if d.wan or d.kind.startswith('WAN') else ('—','Not a WAN device')
            recent=self.w.store.samples(d.id,max(0,time.time()-300),limit=30)
            loss=f'{100*sum(not x["success"] for x in recent)/len(recent):.1f}% ({len(recent)} samples)' if recent else 'Unavailable'
            history=self.w.store.measurements(d.id,time.time()-86400,1000)
            last_success=max((x['at'] for x in history if x.get('internet')=='Online'),default=None)
            last_success_text=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(last_success)) if last_success else 'None in latest 1,000 / 24h'
            vals=[d.name,self.w.state(d),'Unknown / stale' if stale else r.get('internet',r.get('service','Unknown')),health,str(round(rate['download_mbps'],2)) if 'download_mbps' in rate and not rate_stale else 'Unavailable',str(round(rate['upload_mbps'],2)) if 'upload_mbps' in rate and not rate_stale else 'Unavailable',str(round(r['internet_latency_ms'],1)) if not stale and 'internet_latency_ms' in r else 'Unavailable',rate.get('rate_kind','Not independently measurable')+(' / STALE' if rate_stale else ''),label,loss,last_success_text]
            row=self.table.rowCount();self.table.insertRow(row)
            for c,v in enumerate(vals):
                item=QTableWidgetItem(v)
                if c==0:item.setData(Qt.UserRole,d.id)
                if c==3:
                    item.setToolTip(reason);item.setForeground(QColor(status_color(health,self.w.ui_theme)))
                self.table.setItem(row,c,item)
            if selected and selected.id==d.id:self.table.selectRow(row)
        if rank:
            rank.sort();self.ranking.setText(f'Latest measured downloads: fastest {rank[-1][1]} {rank[-1][0]:.2f} Mbps • slowest {rank[0][1]} {rank[0][0]:.2f} Mbps. Compare only equivalent test sizes/rate limits; these tests ran at different times.')
        else:self.ranking.setText('No fresh independently measured download tests; router traffic is not ranked as Internet capacity.')
        self.table.resizeColumnsToContents();self.table.blockSignals(False);self.history()
