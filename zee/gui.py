from __future__ import annotations
import os
import time
from pathlib import Path
from dataclasses import asdict
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QDateTime
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox,
    QTabWidget, QDialog, QFormLayout, QSpinBox, QCheckBox, QDialogButtonBox, QMessageBox,
    QFileDialog, QTextEdit, QSystemTrayIcon, QStyle, QScrollArea, QDateTimeEdit, QSplitter, QDoubleSpinBox, QGroupBox, QGridLayout)
from .core import Device, Store, TYPES, VERSION, diagnoses, export_csv, outages
from .engine import Engine
from .page_controls import PageControls

COLORS = {'Online':'#36d399','Warning':'#fbbf24','No reply':'#fb7185','Unknown':'#9aacc0','Checking':'#60a5fa','Disabled':'#94a3b8','Probe error':'#fbbf24','Unconfigured':'#9aacc0'}
from .customer_theme import stylesheet,apply_theme,status_color
STYLE = stylesheet('dark')

def stamp(t):
    return time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(t)) if t else '—'

def button(text, fn, primary=False):
    b = QPushButton(text)
    b.clicked.connect(fn)
    if primary:
        b.setObjectName('primary')
    return b

class DeviceDialog(QDialog):
    def __init__(self, devices, device=None, parent=None, stations=None):
        super().__init__(parent)
        self.setWindowTitle('Edit device' if device else 'Add device')
        self.resize(590,710)
        self.original = device or Device()
        self.fields = {}
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        values = asdict(self.original)
        for key,title in [('name','Device / station name'),('host','IP address or hostname'),('location','Station / location'),('notes','Notes'),('source','Optional local source IP'),('profile','Profile reference'),('management_url','Management HTTP/HTTPS URL'),('service_url','Camera/service HTTP/HTTPS/RTSP URL'),('role','Radio role / local or remote')]:
            edit = QLineEdit(values[key])
            self.fields[key] = edit
            form.addRow(title,edit)
        kind = QComboBox()
        kind.addItems(TYPES)
        kind.setCurrentText(values['kind'])
        self.fields['kind'] = kind
        form.addRow('Device type',kind)
        tower=QComboBox();tower.addItem('Standalone device','')
        for station in stations or []: tower.addItem(station.name,station.id)
        tower.setCurrentIndex(max(0,tower.findData(values['station_id'])))
        self.fields['station_id']=tower;form.addRow('Physical tower',tower)
        side=QComboBox();side.addItem('Left','Left');side.addItem('Right','Right')
        side.setCurrentIndex(max(0,side.findData(values['dish_side'])))
        self.fields['dish_side']=side;form.addRow('Dish side (both transmit / receive)',side)
        for key,title in [('parent','Parent / previous hop'),('next_hop','Next hop (annotation)'),('peer_id','Wireless peer radio')]:
            combo = QComboBox()
            combo.addItem('None','')
            for d in devices:
                if d.id != self.original.id:
                    combo.addItem(d.name,d.id)
            combo.setCurrentIndex(max(0,combo.findData(values[key])))
            self.fields[key] = combo
            form.addRow(title,combo)
        for key,title,low,high in [('wan','WAN number (0 = none)',0,99),('interval','Ping interval (seconds)',1,3600),('timeout','Timeout (ms)',100,10000),('latency_threshold','Latency warning (ms)',1,60000),('failure_threshold','Consecutive failures before alert',1,100)]:
            spin = QSpinBox()
            spin.setRange(low,high)
            spin.setValue(values[key])
            self.fields[key] = spin
            form.addRow(title,spin)
        for key,title in [('enabled','Enable monitoring'),('alerts','Enable alerts for this device')]:
            check = QCheckBox(title)
            check.setChecked(values[key])
            self.fields[key] = check
            form.addRow(check)
        self.map_enabled = QCheckBox('Use custom map position (or drag the marker)')
        self.map_enabled.setChecked(self.original.map_x is not None)
        form.addRow(self.map_enabled)
        for key,title in [('map_x','Map X (%)'),('map_y','Map Y (%)')]:
            spin=QDoubleSpinBox();spin.setRange(0,100);spin.setDecimals(1)
            spin.setValue((values[key] if values[key] is not None else .5)*100)
            self.fields[key]=spin;form.addRow(title,spin)
        help_text = QLabel('WAN independence needs a verified Windows path; this app does not create routes. Configure real read-only telemetry in Secure settings. Host/source edits clear relevant verification; missing readings stay unavailable.')
        help_text.setWordWrap(True)
        form.addRow(help_text)
        self.advanced=QCheckBox('Show advanced routing, links and map settings')
        self.advanced.setChecked(bool(parent and hasattr(parent,'store') and parent.store.setting('advanced_ui',False)))
        basic={'name','host','location','notes','kind','station_id','dish_side','parent','interval','enabled','alerts'}
        def show_advanced(value):
            for key,widget in self.fields.items():
                if key not in basic:form.setRowVisible(widget,value)
            form.setRowVisible(self.map_enabled,value)
        self.advanced.toggled.connect(show_advanced);show_advanced(self.advanced.isChecked())
        outer.addWidget(self.advanced)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        box = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        outer.addWidget(box)

    def device(self):
        values = asdict(self.original)
        for key,w in self.fields.items():
            if isinstance(w,QDoubleSpinBox):
                values[key] = w.value()/100 if self.map_enabled.isChecked() else None
            elif isinstance(w,QLineEdit):
                values[key] = w.text().strip()
            elif isinstance(w,QSpinBox):
                values[key] = w.value()
            elif isinstance(w,QCheckBox):
                values[key] = w.isChecked()
            elif key == 'kind':
                values[key] = w.currentText()
            else:
                values[key] = w.currentData()
        d = Device(**values)
        if d.host!=self.original.host or d.source!=self.original.source:
            d.integration=d.integration|{'wan_verified':False,'wan_counter_verified':False}
        if d.host!=self.original.host:d.integration=d.integration|{'firmware_verified':False}
        d.validate()
        return d

    def accept(self):
        try:
            self.device()
        except ValueError as e:
            QMessageBox.warning(self,'Please correct the device',str(e))
            return
        super().accept()

class LatencyGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.rows=[]
        self.setMinimumHeight(220)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#131e30'))
        area=QRectF(58,25,max(1,self.width()-85),max(1,self.height()-70))
        p.setPen(QColor('#475569'))
        p.drawRect(area)
        if not self.rows:
            p.setPen(QColor('#94a3b8'))
            p.drawText(self.rect().adjusted(15,15,-15,-15),Qt.AlignCenter|Qt.TextWordWrap,'No samples yet — select a device and run a ping')
            return
        values=[r['latency'] for r in self.rows if r['success'] and r['latency'] is not None]
        ceiling=max(10,max(values,default=0)*1.15)
        first,last=self.rows[0]['at'],self.rows[-1]['at']
        spread=max(1,last-first)
        p.setPen(QColor('#94a3b8'))
        p.drawText(5,30,f'{ceiling:.0f} ms')
        p.drawText(10,int(area.bottom()),'0 ms')
        p.drawText(58,self.height()-12,time.strftime('%H:%M',time.localtime(first)) if self.width()<400 else stamp(first))
        p.drawText(max(58,self.width()-(65 if self.width()<400 else 175)),self.height()-12,time.strftime('%H:%M',time.localtime(last)) if self.width()<400 else stamp(last))
        previous=None
        for r in self.rows:
            x=area.left()+(r['at']-first)/spread*area.width()
            if not r['success']:
                p.setPen(QPen(QColor('#fb7185'),2))
                p.drawLine(QPointF(x,area.bottom()-8),QPointF(x,area.bottom()))
                previous=None
            elif r['latency'] is not None:
                pos=QPointF(x,area.bottom()-r['latency']/ceiling*area.height())
                p.setPen(QPen(QColor('#36d399'),2))
                if previous is not None:
                    p.drawLine(previous,pos)
                p.drawEllipse(pos,2,2)
                previous=pos
            else:
                previous=None

class Topology(QWidget):
    def __init__(self):
        super().__init__()
        self.devices=[]
        self.states={}
        self.setMinimumSize(700,400)

    def refresh(self,devices,states):
        self.devices,self.states=devices,states
        depth={}
        lookup={d.id:d for d in devices}
        def level(d,seen):
            if d.id in seen or d.parent not in lookup:
                return 0
            return 1+level(lookup[d.parent],seen|{d.id})
        for d in devices:
            depth[d.id]=level(d,set())
        self.depth=depth
        counts={}
        for d in devices:
            counts[depth[d.id]]=counts.get(depth[d.id],0)+1
        self.setMinimumSize(max(700,max(counts.values(),default=1)*210+40),max(400,(max(depth.values(),default=0)+1)*115+40))
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        points={}
        counts={}
        for d in self.devices:
            level=self.depth.get(d.id,0)
            n=counts.get(level,0)
            counts[level]=n+1
            points[d.id]=QRectF(25+n*210,25+level*115,185,75)
        p.setPen(QPen(QColor('#52657b'),2))
        for d in self.devices:
            if d.parent in points:
                p.drawLine(QPointF(points[d.parent].center().x(),points[d.parent].bottom()),QPointF(points[d.id].center().x(),points[d.id].top()))
        for d in self.devices:
            box=points[d.id]
            color=QColor(COLORS.get(self.states.get(d.id), '#fbbf24'))
            p.setPen(QPen(color,2))
            p.setBrush(QColor('#1e293b'))
            p.drawRoundedRect(box,8,8)
            p.setPen(QColor('#e2e8f0'))
            text=d.name[:25]+'\n'+(d.host or 'Unconfigured')+'\n'+self.states.get(d.id,'Unknown')
            p.drawText(box.adjusted(8,5,-8,-5),Qt.AlignLeft|Qt.AlignVCenter,text)
        if not self.devices:
            p.drawText(self.rect(),Qt.AlignCenter,'Add devices and assign parent hops to draw the topology.')

class Window(PageControls,QMainWindow):
    def __init__(self,store):
        super().__init__()
        self.store=store
        from .licensing import status,customer_profile,branding
        from .entitlements import from_status
        self.branding=branding();self.policy=from_status(status(store.path.parent),customer_profile());store.policy=self.policy
        self.store.suspend_incidents()
        self.page_id=store.setting('active_page','default')
        self.page_snapshot=self.current_page()
        self.monitor_all_enabled=store.setting('monitor_all',False)
        self.network_pages={p.id:p for p in store.pages()}
        self.all_devices=[]
        self.ambiguous_devices=set()
        from .credentials import Vault
        from .monitoring import Measurements
        self.vault=Vault(store.path.parent/'credentials.dpapi.json')
        self.measurements=Measurements(self,self.vault)
        self.details_windows=[]
        self.engine=Engine(self,probe_fn=self.scoped_probe)
        self.engine.prepare_probe=self.prepare_network_probe
        self.allowed_device_ids=set();self.engine.permit=self.permit_device
        self.engine.result.connect(self.result)
        self.engine.busy_changed.connect(self.busy)
        self.states={}
        self.latest={}
        self.streaks={}
        self.alerted={}
        self.telemetry_alerted={}
        self.requested=set()
        self.devices=[]
        self._stats_cache={}
        self._dirty=True
        self._last_view_key=None
        self._table_page=0
        self._resume_minimized=False
        self.ui_theme=self.store.setting('ui_theme','dark')
        if self.ui_theme not in ('dark','light'):self.ui_theme='dark'
        apply_theme(QApplication.instance(),self.ui_theme)
        self.setWindowTitle(self.branding['app_name']+' • '+VERSION)
        self.resize(1360,790)
        self.setMinimumSize(980,650)
        root=QWidget()
        self.setCentralWidget(root)
        layout=QVBoxLayout(root)
        layout.setContentsMargins(22,18,22,18)
        head=QHBoxLayout()
        titles=QVBoxLayout()
        title=QLabel(self.branding['app_name']);title.setTextFormat(Qt.PlainText)
        title.setObjectName('title')
        title.setStyleSheet('font-size:20px; font-weight:700;')
        subtitle=QLabel('Network pages • Live map • Professional preview')
        subtitle.setObjectName('subtitle')
        titles.addWidget(title)
        titles.addWidget(subtitle)
        head.addLayout(titles)
        if self.branding['logo_png']:
            import base64
            from PySide6.QtGui import QPixmap
            logo=QPixmap();logo.loadFromData(base64.b64decode(self.branding['logo_png']),'PNG');logo_label=QLabel();logo_label.setPixmap(logo.scaled(64,64,Qt.KeepAspectRatio,Qt.SmoothTransformation));head.addWidget(logo_label)
        head.addStretch()
        self.mode_badge=QLabel('Professional Edition');self.mode_badge.setObjectName('subtitle');head.addWidget(self.mode_badge)
        layout.addLayout(head)
        head=QHBoxLayout()
        self.start_button=button('▶ Start monitoring',self.toggle,True)
        head.addWidget(self.start_button)
        head.addWidget(button('Ping all now',self.ping_all))
        from .buzzer import Buzzer
        self.buzzer=Buzzer(self,enabled=self.store.setting('buzzer_enabled',True),delay_seconds=self.store.setting('alarm_delay_seconds',15))
        self.buzzer_button=QPushButton();self.buzzer_button.setCheckable(True)
        self.buzzer_button.setChecked(self.buzzer.enabled)
        self.buzzer_button.toggled.connect(self.set_buzzer)
        head.addWidget(self.buzzer_button)
        head.addWidget(button('Silence',self.silence_buzzer))
        self.alarm_status=QLabel('Alarm clear');head.addWidget(self.alarm_status)
        self.buzzer.changed.connect(self.buzzer_status)
        self.buzzer_status()
        layout.addLayout(head)
        self.summary=QLabel()
        self.summary.setTextFormat(Qt.PlainText)
        self.summary.setObjectName('card')
        self.summary.setStyleSheet('font-size:12px; padding:9px;')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tabs=QTabWidget()
        self.tabs.tabBar().hide()
        content=QHBoxLayout()
        self.navigation=QVBoxLayout()
        nav_body=QWidget();nav_body.setLayout(self.navigation)
        self.nav_scroll=QScrollArea();self.nav_scroll.setWidgetResizable(True);self.nav_scroll.setWidget(nav_body);self.nav_scroll.setFixedWidth(190);self.nav_scroll.setFrameShape(QScrollArea.NoFrame)
        content.addWidget(self.nav_scroll)
        content.addWidget(self.tabs,1)
        layout.addLayout(content,1)
        dashboard=QWidget()
        dash=QVBoxLayout(dashboard)
        tools=QHBoxLayout()
        self.search=QLineEdit()
        self.search.setPlaceholderText('Search devices, IPs or notes…')
        self.search.textChanged.connect(self.render_table)
        tools.addWidget(self.search,2)
        self.station=QComboBox()
        self.station.currentTextChanged.connect(self.render_table)
        tools.addWidget(self.station)
        self.kind=QComboBox()
        self.kind.addItems(['All types']+TYPES)
        self.kind.currentTextChanged.connect(self.render_table)
        tools.addWidget(self.kind)
        dash.addLayout(tools)
        paging=QHBoxLayout()
        paging.addWidget(button('Previous page',lambda:self.table_page(-1)))
        self.page_count=QLabel();paging.addWidget(self.page_count)
        paging.addWidget(button('Next page',lambda:self.table_page(1)))
        paging.addStretch();dash.addLayout(paging)
        actions=QGridLayout()
        for i,(title,fn) in enumerate([('Add device',self.add),('Edit',self.edit),('Delete',self.delete),('Ping selected',self.ping_selected),('Continuous selected',self.continuous_selected),('Refresh',self.reload),('Export summary',self.export_summary)]):
            actions.addWidget(button(title,fn),i//4,i%4)
        dash.addLayout(actions)
        self.table=QTableWidget(0,10)
        self.table.setHorizontalHeaderLabels(['Device / station','Host','Type','Location','Status','Latency','Loss (samples)','Checks OK / failed','Last check','WAN mode'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self.device_double_click)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        dash.addWidget(self.table)
        note=QLabel('No reply ≠ confirmed physical failure. Loss/uptime are sampled ICMP estimates. WAN independence requires a verified probe path.')
        note.setWordWrap(True)
        note.setObjectName('subtitle')
        dash.addWidget(note)
        self.tabs.addTab(dashboard,'Devices & WANs')
        self.history_page()
        self.topology_page()
        self.events_page()
        self.settings_page()
        from .mapview import MapDashboard
        self.map_page=MapDashboard(self)
        self.tabs.insertTab(0,self.map_page,'Map')
        from .professional import ProfessionalPanel
        self.pro_panel=ProfessionalPanel(self);self.tabs.addTab(self.pro_panel,'WAN / Radio')
        from .seven_wan import SevenWanPanel
        self.seven_wan=SevenWanPanel(self);self.tabs.addTab(self.seven_wan,'Internet speeds')
        from .customer_dashboard import CustomerDashboard
        self.overview=CustomerDashboard(self);self.tabs.addTab(self.overview,'Overview')
        self.page_picker=QComboBox();self.page_picker.setMaximumWidth(160);self.page_picker.currentIndexChanged.connect(self.change_page)
        self.navigation.addWidget(QLabel('NETWORK PAGE'));self.navigation.addWidget(self.page_picker)
        self.path_button=button('Network setup / paths',self.network_setup);self.navigation.addWidget(self.path_button)
        self.monitor_all_box=QCheckBox('Monitor all networks')
        self.monitor_all_box.setToolTip('Uses shared worker limits; each network must have an operator-verified path. Map/history stay on the selected page.')
        self.monitor_all_box.setChecked(self.monitor_all_enabled)
        self.monitor_all_box.toggled.connect(self.set_monitor_all)
        self.navigation.addWidget(self.monitor_all_box)
        self.pages_button=button('Manage networks',self.manage_pages);self.navigation.addWidget(self.pages_button)
        self.radios_button=button('Connect tower radios',self.connect_radios);self.navigation.addWidget(self.radios_button)
        self.advanced_box=QCheckBox('Advanced controls');self.advanced_box.setToolTip('Shows additional setup tools; this is a display preference, not administrator access.');self.navigation.addWidget(self.advanced_box)
        self.nav_buttons=[]
        for i,text in enumerate(['◉  Map','▤  Devices / WANs','◷  History','⌁  Topology','♧  Alerts','⚙  Settings','◈  WAN / Radio','⇅  Internet speeds','▦  Overview']):
            b=QPushButton(text);b.setObjectName('nav');b.setCheckable(True);b.setFixedWidth(166)
            b.clicked.connect(lambda checked=False,index=i:self.tabs.setCurrentIndex(index))
            if i==8:self.navigation.insertWidget(7,b)
            else:self.navigation.addWidget(b)
            self.nav_buttons.append(b)
        self.navigation.addStretch()
        self.tabs.currentChanged.connect(self.highlight_nav)
        self.advanced_box.toggled.connect(self.set_advanced)
        self.set_advanced(self.store.setting('advanced_ui',False),persist=False)
        self.tabs.setCurrentIndex(8);self.highlight_nav(8)
        self.install_shortcuts()
        self.tray=QSystemTrayIcon(self.style().standardIcon(QStyle.SP_ComputerIcon),self)
        self.tray.setToolTip(self.branding['app_name'])
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.statusBar().showMessage('Ready • Monitoring is stopped')
        self.watermark=QLabel(self.branding['watermark']);self.watermark.setTextFormat(Qt.PlainText);self.statusBar().addPermanentWidget(self.watermark)
        from .resources import Usage
        self.resource_usage=Usage();self.resource_label=QLabel()
        self.resource_label.setToolTip('This app only. CPU: 100% = one core. RAM: working set.')
        self.statusBar().addPermanentWidget(self.resource_label)
        self.queue_timer=QTimer(self)
        self.queue_timer.timeout.connect(self.drain)
        self.queue_timer.start(150)
        self.view_timer=QTimer(self)
        self.view_timer.timeout.connect(self.refresh_states)
        self.view_timer.start(2000)
        from .retention import Cleaner
        self.cleaner=Cleaner(self);self.cleaner.finished.connect(self.cleanup_finished)
        self.measurements.changed.connect(self.request_render)
        self.apply_performance()
        self.cleanup_status.setText(self.store.setting('cleanup_status','No cleanup completed yet.'))
        self.maintenance=QTimer(self)
        self.maintenance.timeout.connect(self.prune)
        self.maintenance.start(600000)
        self.store.event('','application','Application started')
        self.reload()
        self.prune()
        self.apply_package_ui()
        self.license_timer=QTimer(self);self.license_timer.timeout.connect(self.check_licence);self.license_timer.start(60000)

    def permit_device(self,d):
        from .entitlements import category
        return self.policy.allows('monitoring') and self.policy.allows(category(d)) and d.id in self.allowed_device_ids

    def apply_package_ui(self):
        self.allowed_device_ids=self.policy.selected(self.store.devices())
        for index,feature in [(0,'map'),(6,'wireless'),(7,'wan')]:
            allowed=any(self.policy.allows(f) for f in ('wan','wireless','cctv')) if index==6 else self.policy.allows(feature);self.tabs.setTabEnabled(index,allowed);self.nav_buttons[index].setEnabled(allowed);self.nav_buttons[index].setToolTip('' if allowed else 'Not included in this package')
        self.start_button.setEnabled(self.policy.allows('monitoring'))
        self.mode_badge.setToolTip('Package limit: '+str(self.policy.max_devices)+' devices; features: '+', '.join(sorted(self.policy.features)))
        count=len(self.store.devices())
        if count>self.policy.max_devices:self.statusBar().showMessage(f'Package limit: {self.policy.max_devices}. Only the first saved devices within this limit are monitored; other records are retained.')

    def verify_offline_update(self):
        from .licensing import customer_profile,public_key_path,status
        import json
        profile=customer_profile()
        if not profile or not status(self.store.path.parent)['valid']:
            QMessageBox.information(self,'Customer update','This needs an activated customer-specific build.');return
        manifest,_=QFileDialog.getOpenFileName(self,'Owner-signed update manifest','','JSON (*.json)')
        if not manifest:return
        installer,_=QFileDialog.getOpenFileName(self,'Matching downloaded installer','','Installer (*.exe)')
        if not installer:return
        try:
            if Path(manifest).stat().st_size>65536:raise ValueError('Manifest too large.')
            from .updates import verify_update
            p=verify_update(json.loads(Path(manifest).read_text()),json.loads(public_key_path().read_text())['public_key'],profile['profile_id'],VERSION,installer)
            QMessageBox.information(self,'Installer verified','Owner signature, customer profile and file hash match version '+p['app_version']+'. Close this application, then run the verified installer yourself. Nothing is installed automatically.')
        except Exception:QMessageBox.warning(self,'Update rejected','Signature, customer, version or installer integrity did not match.')

    def check_licence(self):
        from .licensing import status
        from .licensing import customer_profile
        from .entitlements import from_status
        state=status(self.store.path.parent)
        try:policy=from_status(state,customer_profile())
        except Exception:state={'valid':False};policy=from_status(state)
        if policy!=self.policy:
            self.engine.invalidate();self.measurements.stop();self.requested.clear();self.policy=policy;self.store.policy=policy;self.apply_package_ui()
            if getattr(self,'mobile_server',None) and not policy.allows('mobile'):self.mobile_server.stop();self.mobile_server=None
        if not state['valid']:
            self.engine.stop();self.measurements.stop();self.requested.clear();self.buzzer.shutdown()
            QMessageBox.warning(self,'Licence expired or invalid','Monitoring is stopped. Import a valid licence on next launch.');self.close()

    def history_page(self):
        page=QWidget()
        layout=QVBoxLayout(page)
        tools=QHBoxLayout()
        self.history_device=QComboBox()
        self.history_device.currentIndexChanged.connect(self.render_history)
        self.range=QComboBox()
        for label,seconds in [('Last hour',3600),('Last 24 hours',86400),('Last 7 days',604800),('All retained history',0)]:
            self.range.addItem(label,seconds)
        self.range.setCurrentIndex(1)
        self.range.currentIndexChanged.connect(self.render_history)
        tools.addWidget(self.history_device)
        tools.addWidget(self.range)
        tools.addStretch()
        tools.addWidget(button('Export samples',self.export_samples))
        layout.addLayout(tools)
        self.history_summary=QLabel()
        self.history_summary.setWordWrap(True)
        layout.addWidget(self.history_summary)
        self.graph=LatencyGraph()
        layout.addWidget(self.graph,1)
        layout.addWidget(QLabel('Green: measured latency • Red: no reply • Graph shows at most the latest 1,000 samples in the selected period.'))
        self.outage_text=QTextEdit()
        self.outage_text.setReadOnly(True)
        layout.addWidget(self.outage_text,1)
        self.tabs.addTab(page,'History & uptime')

    def topology_page(self):
        page=QWidget()
        layout=QVBoxLayout(page)
        layout.addWidget(QLabel('Parent links define the diagnostic tree. Next hop is an annotation only. Edit a device to change links.'))
        self.topology=Topology()
        scroll=QScrollArea()
        scroll.setWidget(self.topology)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll,3)
        self.diagnostic=QTextEdit()
        self.diagnostic.setReadOnly(True)
        layout.addWidget(self.diagnostic,1)
        self.tabs.addTab(page,'Topology & diagnosis')

    def events_page(self):
        page=QWidget()
        layout=QVBoxLayout(page)
        tools=QGridLayout()
        self.event_device=QComboBox()
        self.event_device.currentIndexChanged.connect(self.render_events)
        self.event_tower=QComboBox()
        self.event_tower.currentIndexChanged.connect(self.render_events)
        self.event_search=QLineEdit()
        self.event_search.setPlaceholderText('Search event text / type…')
        self.event_search.textChanged.connect(self.render_events)
        self.event_from=QDateTimeEdit(QDateTime.currentDateTime().addDays(-7))
        self.event_to=QDateTimeEdit(QDateTime.currentDateTime().addYears(1))
        for widget in (self.event_from,self.event_to):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat('yyyy-MM-dd HH:mm')
            widget.dateTimeChanged.connect(self.render_events)
        for i,w in enumerate((self.event_device,self.event_tower,self.event_search,self.event_from,self.event_to)):
            tools.addWidget(w,i//3,i%3)
        tools.addWidget(button('Export events',self.export_events),1,2)
        tools.addWidget(button('Pin / Unpin selected',self.pin_selected_event),2,0)
        layout.addLayout(tools)
        self.event_table=QTableWidget(0,4)
        self.event_table.setHorizontalHeaderLabels(['Time (local)','Device','Type','Message'])
        self.event_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.event_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.event_table)
        layout.addWidget(QLabel('Latest 1,000 matching events shown; export includes all matching retained events.'))
        layout.addWidget(button('Incident history / acknowledge / notes',self.open_incidents))
        self.tabs.addTab(page,'Events & alerts')

    def settings_page(self):
        page=QScrollArea();page.setWidgetResizable(True);body=QWidget();page.setWidget(body);layout=QVBoxLayout(body)
        title=QLabel('Settings');title.setObjectName('title');layout.addWidget(title)
        appearance=QGroupBox('Appearance & controls');form=QFormLayout(appearance);layout.addWidget(appearance)
        self.theme_picker=QComboBox();self.theme_picker.addItem('Dark','dark');self.theme_picker.addItem('Light','light');self.theme_picker.setCurrentIndex(1 if self.ui_theme=='light' else 0);self.theme_picker.currentIndexChanged.connect(lambda *_:self.set_theme(self.theme_picker.currentData()));form.addRow('Theme (saved immediately)',self.theme_picker)
        self.advanced_setting=QCheckBox('Show advanced setup and measurement controls');self.advanced_setting.setChecked(self.store.setting('advanced_ui',False));self.advanced_setting.toggled.connect(self.set_advanced);form.addRow(self.advanced_setting)
        note=QLabel('Simple view keeps daily tasks visible. Advanced controls are a display preference; they do not grant admin access. Windows display scaling is supported.');note.setWordWrap(True);form.addRow(note)
        group=QGroupBox('Alerts & detailed history');form=QFormLayout(group);layout.addWidget(group)
        self.notifications=QCheckBox('Desktop notifications');self.notifications.setChecked(self.store.setting('notifications',True))
        self.beep=QCheckBox('Enable repeating fault buzzer');self.beep.setChecked(self.buzzer.enabled);self.beep.toggled.connect(self.buzzer_button.setChecked)
        self.recovery=QCheckBox('Recovery notifications');self.recovery.setChecked(self.store.setting('recovery',True))
        for widget in (self.notifications,self.beep,self.recovery):form.addRow(widget)
        self.alarm_delay=QSpinBox();self.alarm_delay.setRange(0,300);self.alarm_delay.setValue(self.buzzer.delay_seconds);form.addRow('Buzzer delay after confirmed fault (seconds)',self.alarm_delay)
        from .retention import history_hours
        self.retention=QSpinBox();self.retention.setRange(1,87600);self.retention.setValue(history_hours(self.store));form.addRow('Detailed history retention (hours)',self.retention)
        self.auto_cleanup=QCheckBox('Automatic background cleanup');self.auto_cleanup.setChecked(self.store.setting('auto_cleanup',True));form.addRow(self.auto_cleanup)
        note=QLabel('Default detailed history: 48 hours. Unresolved incidents and pinned records stay protected. Incident retention and archive options are under Advanced monitoring / history.');note.setWordWrap(True);form.addRow(note)
        self.cleanup_status=QLabel();self.cleanup_status.setWordWrap(True);form.addRow(self.cleanup_status)
        row=QHBoxLayout();row.addWidget(button('Save alert / history settings',self.save_settings,True));row.addWidget(button('Clean expired records now',lambda:self.prune(manual=True)));row.addWidget(button('Test buzzer',self.test_buzzer));form.addRow(row)
        tools=QGroupBox('Setup, backup & support');grid=QGridLayout(tools);layout.addWidget(tools)
        actions=[('Real-network pilot / support report',self.pilot_dialog),('Network setup / paths',self.network_setup),('Manage networks',self.manage_pages),('Connect tower radios',self.connect_radios),('Backup database',self.backup),('Restore backup and close',self.restore_database),('Advanced monitoring / history',self.performance_dialog),('Help / About',self.help_about),('Licence / activation',self.license_dialog),('Mobile HTTPS dashboard',self.mobile_dialog),('Add WAN templates',self.wan_templates),('Verify offline installer update',self.verify_offline_update)]
        for i,(title,fn) in enumerate(actions):grid.addWidget(button(title,fn),i//2,i%2)
        info=QLabel(self.branding['app_name']+' • '+self.branding['watermark']+'\nDatabase: '+str(self.store.path)+'\nActual modem/radio profiles and Windows Internet paths require verification on your network.');info.setWordWrap(True);layout.addWidget(info);layout.addStretch();self.tabs.addTab(page,'Settings & scope')

    def set_theme(self,name):
        if name not in ('dark','light'):return
        self.ui_theme=name;self.store.set_setting('ui_theme',name);apply_theme(QApplication.instance(),name);self.buzzer_status();self._dirty=True
        if hasattr(self,'view_timer'):self.refresh_states()

    def set_advanced(self,enabled,persist=True):
        enabled=bool(enabled)
        if persist:self.store.set_setting('advanced_ui',enabled)
        for name in ('advanced_box','advanced_setting'):
            widget=getattr(self,name,None)
            if widget:widget.blockSignals(True);widget.setChecked(enabled);widget.blockSignals(False)
        if hasattr(self,'nav_buttons'):
            for index in (2,6):self.nav_buttons[index].setVisible(enabled or self.tabs.currentIndex()==index)
            for widget in (self.path_button,self.pages_button,self.radios_button):widget.setVisible(enabled)
            self.monitor_all_box.setVisible(enabled or self.monitor_all_enabled)
        self.mode_badge.setText('Advanced controls' if enabled else 'Simple view')

    def focus_device_search(self):
        self.tabs.setCurrentIndex(1);self.search.setFocus();self.search.selectAll()

    def install_shortcuts(self):
        from PySide6.QtGui import QShortcut,QKeySequence
        self.shortcuts=[]
        for keys,index in [('Ctrl+1',8),('Ctrl+2',0),('Ctrl+3',1),('Ctrl+4',7)]:
            shortcut=QShortcut(QKeySequence(keys),self);shortcut.activated.connect(lambda i=index:self.tabs.setCurrentIndex(i));self.shortcuts.append(shortcut)
        shortcut=QShortcut(QKeySequence('Ctrl+F'),self);shortcut.activated.connect(self.focus_device_search);self.shortcuts.append(shortcut)

    def help_about(self):
        dialog=QDialog(self);dialog.setWindowTitle('Help / About');dialog.resize(700,520)
        layout=QVBoxLayout(dialog);text=QTextEdit();text.setReadOnly(True)
        text.setPlainText(f"{self.branding['app_name']} {VERSION}\n{self.branding['watermark']}\n\nFIRST NETWORK\nManage networks > Add. Select the page, then Map > Add tower. Devices > Add device: enter name and management IP, select tower, save. Start monitoring. Selected page by default; Monitor all networks checks all active pages.\n\nRADIO / WAN\nWAN / Radio > select device > Configure adapter. Use a verified firmware profile and real OIDs/API fields. Ping is separate from wireless quality and Internet reachability. Missing measurements remain Unknown/Unavailable. Traffic rate is usage, not capacity. Controlled speed tests consume data; automatic tests are off by default.\n\nFIVE NETWORKS\nConfigure Windows interfaces and routes first. Page source IP selects the source where supported; gateway hints do not create routes. Overlapping subnets require separate routing/interface setup.\n\nCCTV\nSet HTTP/HTTPS management and optional RTSP endpoint. Service status is separate from ping; no continuous video preview.\n\nMOBILE\nSettings > Mobile HTTPS dashboard. Explicitly start the service, verify certificate fingerprint, then pair from a phone. Remote access requires your configured VPN.\n\nSAFETY / BACKUP\nSettings > Backup database. Credentials use Windows DPAPI and are not included in configuration exports. Licence manager belongs to the owner. See Licence / activation for this build’s issuer and package status.\n\nTESTING\nReal Rocket firmware, physical Windows 10 and phone compatibility require field testing. See the packaged PROFESSIONAL_GUIDE for details.")
        layout.addWidget(text);layout.addWidget(button('Close',dialog.accept));dialog.exec()

    def reload(self):
        pages=[p for p in self.store.pages() if not p.archived]
        if not any(p.id==self.page_id for p in pages):self.page_id=pages[0].id
        self.page_snapshot=self.current_page()
        self._stats_cache.clear()
        self._dirty=True
        self.page_picker.blockSignals(True);self.page_picker.clear()
        for p in pages:self.page_picker.addItem(p.name,p.id)
        self.page_picker.setCurrentIndex(self.page_picker.findData(self.page_id));self.page_picker.blockSignals(False)
        self.network_pages={p.id:p for p in self.store.pages()}
        self.allowed_device_ids=self.policy.selected(self.store.devices())
        self.all_devices=[d for d in self.store.devices() if d.page_id in self.network_pages and not self.network_pages[d.page_id].archived]
        self.devices=[d for d in self.all_devices if d.page_id==self.page_id]
        from .network_paths import ambiguous_hosts
        self.ambiguous_devices=ambiguous_hosts(self.all_devices,self.network_pages)
        self.engine.devices=self.monitor_devices()
        self.requested &= {d.id for d in self.monitor_devices() if d.enabled and d.host}
        current=self.station.currentText()
        self.station.blockSignals(True)
        self.station.clear()
        self.station.addItems(['All locations']+sorted({d.location for d in self.devices if d.location}))
        self.station.setCurrentText(current if self.station.findText(current)>=0 else 'All locations')
        self.station.blockSignals(False)
        for combo,include_all in [(self.history_device,False),(self.event_device,True)]:
            previous=combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            if include_all:
                combo.addItem('All devices','')
            for d in self.devices:
                combo.addItem(d.name,d.id)
            combo.setCurrentIndex(max(0,combo.findData(previous)))
            combo.blockSignals(False)
        previous=self.event_tower.currentData()
        self.event_tower.blockSignals(True);self.event_tower.clear();self.event_tower.addItem('All towers','')
        for tower in self.page_stations():self.event_tower.addItem(tower.name,tower.id)
        self.event_tower.setCurrentIndex(max(0,self.event_tower.findData(previous)));self.event_tower.blockSignals(False)
        # Last check is displayed, but previous-session status is never treated as fresh.
        for d in self.devices:
            if d.id not in self.latest:
                row=self.store.db.execute('SELECT * FROM samples WHERE device=? ORDER BY at DESC,id DESC LIMIT 1',(d.id,)).fetchone()
                if row:
                    self.latest[d.id]=dict(row)
        self.render_all()
        if hasattr(self,'advanced_box'):self.set_advanced(self.advanced_box.isChecked(),persist=False)

    def highlight_nav(self,index):
        if not self.tabs.isTabEnabled(index):self.tabs.setCurrentIndex(8);return
        for i,b in enumerate(self.nav_buttons):b.setChecked(i==index)
        self.summary.setVisible(True)
        if hasattr(self,'advanced_box'):self.set_advanced(self.advanced_box.isChecked(),persist=False)
        self._dirty=True
        if hasattr(self,'view_timer'):self.refresh_states()

    def set_buzzer(self,enabled):
        self.store.set_setting('buzzer_enabled',enabled)
        self.buzzer.set_enabled(enabled)
        if hasattr(self,'beep'):
            self.beep.blockSignals(True);self.beep.setChecked(enabled);self.beep.blockSignals(False)

    def silence_buzzer(self):
        self.buzzer.silence()
        self.store.event('','alert_control','Current alarm incidents silenced')

    def test_buzzer(self):
        self.buzzer.sound(True)
        def finish():
            self.buzzer.sound(False)
            if self.buzzer.playing:self.buzzer.sound(True)
        QTimer.singleShot(1000,self,finish)

    def buzzer_status(self):
        self.buzzer_button.setText('♪ Buzzer ON' if self.buzzer.enabled else '♪ Buzzer OFF')
        self.buzzer_button.setStyleSheet('color:'+status_color('Online' if self.buzzer.enabled else 'Unknown',self.ui_theme if hasattr(self,'ui_theme') else 'dark'))
        self.alarm_status.setText('FAULT ALARM' if self.buzzer.playing else ('Alarm pending / muted' if self.buzzer.active else 'Alarm clear'))
        self.alarm_status.setStyleSheet('color:'+status_color('No reply' if self.buzzer.playing else 'Unknown',self.ui_theme if hasattr(self,'ui_theme') else 'dark'))

    def refresh_map(self,draw=True):
        if draw and hasattr(self,'map_page'):self.map_page.refresh()
        active={}
        for d in self.monitor_devices():
            state=self.state(d)
            if state=='Checking':state=self.states.get(d.id,'Unknown')
            if d.alerts and state in ('Warning','No reply') and self.alerted.get(d.id):
                active[d.id]=self.alerted[d.id]
        for d in self.monitor_devices():
            r=self.measurements.latest.get(d.id,{})
            if d.enabled and d.alerts and d.id in self.telemetry_alerted and time.time()-r.get('at',0)<max(30,d.integration.get('poll_seconds',30)*3):active[d.id]=self.telemetry_alerted[d.id]
        self.buzzer.update(active)

    def request_render(self):
        self._dirty=True
        self.sync_incidents()
        self.refresh_map(False)
        self.protect_active_alerts()

    def protect_active_alerts(self):
        saved=set(self.store.setting('active_incident_devices',[]))
        active=set(self.alerted)|set(self.telemetry_alerted)|{r[0] for r in self.store.db.execute('SELECT DISTINCT device FROM incidents WHERE resolved IS NULL')}
        for d in self.monitor_devices():
            if d.id in active:saved.add(d.id)
            elif d.id in self.states or not d.enabled:saved.discard(d.id)
        value=sorted(saved)
        if value!=self.store.setting('active_incident_devices',[]):self.store.set_setting('active_incident_devices',value)

    def refresh_states(self):
        self.sync_incidents()
        usage=self.resource_usage.sample()
        ram=f"{usage['working_set_mb']} MB" if usage['working_set_mb'] is not None else 'Unavailable'
        self.resource_label.setText(f"CPU {usage['cpu_percent_one_core']}% • RAM {ram}")
        key=tuple((d.id,self.state(d)) for d in self.devices)
        if self._dirty or key!=self._last_view_key:
            self.render_table()
            tab=self.tabs.currentIndex()
            if tab==0:self.refresh_map()
            elif tab==2:self.render_history()
            elif tab==3:
                self.topology.refresh(self.devices,{d.id:self.state(d) for d in self.devices});self.render_diagnosis()
            elif tab==4:self.render_events()
            elif tab==6:self.pro_panel.refresh()
            elif tab==8:self.overview.refresh()
            self._dirty=False;self._last_view_key=key
        self.refresh_map(False)
        self.update_mobile()

    def table_page(self,delta):
        self._table_page=max(0,self._table_page+delta);self.render_table()

    def state(self,d):
        if hasattr(self,'policy') and not self.permit_device(d):return 'Package restricted'
        if not d.enabled:
            return 'Disabled' if d.host else 'Unconfigured'
        if d.id in self.engine.pending:
            return 'Checking'
        if not d.host:
            return 'Unconfigured'
        last=self.latest.get(d.id)
        if last and time.time()-last['at']>max(30,max(d.interval,self.engine.minimum_interval)*3):
            return 'Unknown'
        return self.states.get(d.id,'Unknown')

    def selected(self):
        row=self.table.currentRow()
        if row<0 or not self.table.item(row,0):
            return None
        id=self.table.item(row,0).data(Qt.UserRole)
        return next((d for d in self.devices if d.id==id),None)

    def selection_changed(self):
        d=self.selected()
        if d:
            self.history_device.setCurrentIndex(self.history_device.findData(d.id))

    def render_all(self):
        self.render_table()
        self.render_history()
        self.render_events()
        self.topology.refresh(self.devices,{d.id:self.state(d) for d in self.devices})
        self.render_diagnosis()
        self.refresh_map()
        if hasattr(self,'overview'):self.overview.refresh()

    def render_diagnosis(self):
        from .faults import evaluate
        _,items=evaluate(self.devices,self.latest,self.states,self.measurements.latest,self.streaks,time.time(),self.network_pages,self.engine.minimum_interval)
        text=[]
        for x in items:
            text.append(f"{x['title']}\nConfidence: {x['confidence']} (qualitative, not a probability)\nLast observed replying hop: {x['last_good']}\nFirst observed failing hop: {x['first_failure']}\nObserved failing downstream: {', '.join(x['affected']) or 'None'}\nEvidence: {x['explanation']}\nNext check: {x['next_step']}")
        self.diagnostic.setPlainText('\n\n'.join(text) or 'No suspected segment identified from the current observations. Unknown/stale states are not evidence of a good link.')

    def sync_incidents(self):
        from .faults import evaluate
        outcomes,_=evaluate(self.monitor_devices(),self.latest,self.states,self.measurements.latest,self.streaks,time.time(),self.network_pages,self.engine.minimum_interval,correlate=False)
        self.store.observe_incidents(outcomes)

    def open_incidents(self):
        from .incident_dialog import IncidentDialog
        IncidentDialog(self).exec()

    def render_table(self):
        if not hasattr(self,'table'):
            return
        selected=self.selected()
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        query=self.search.text().casefold()
        visible=[d for d in self.devices if (not query or query in ' '.join([d.name,d.host,d.location,d.notes]).casefold()) and self.station.currentText() in ('All locations','',d.location) and self.kind.currentText() in ('All types',d.kind)]
        pages=max(1,(len(visible)+199)//200);self._table_page=min(self._table_page,pages-1)
        self.page_count.setText(f'Page {self._table_page+1} / {pages} • {len(visible)} devices')
        visible=visible[self._table_page*200:(self._table_page+1)*200]
        all_states=[]
        latencies=[]
        failed=0
        for d in visible:
            state=self.state(d)
            all_states.append(state)
            if d.id not in self._stats_cache:self._stats_cache[d.id]=self.store.stats(d.id)
            stats=self._stats_cache[d.id]
            failed+=stats['n']-stats['ok']
            last=self.latest.get(d.id,{})
            if state in ('Online','Warning') and last.get('latency') is not None:
                latencies.append(last['latency'])
            query=self.search.text().casefold()
            if query and query not in ' '.join([d.name,d.host,d.location,d.notes]).casefold():
                continue
            if self.station.currentText() not in ('All locations','',d.location) or self.kind.currentText() not in ('All types',d.kind):
                continue
            values=[d.name,d.host or '—',d.kind,d.location,state, f"{last['latency']:.1f} ms" if last.get('latency') is not None else '—',f"{stats['loss']:.1f}%" if stats['loss'] is not None else '—',f"{stats['ok']} / {stats['n']-stats['ok']}",stamp(last.get('at')),'Source-bound (verify path)' if (d.source or self.page_snapshot.source_ip) else ('Reachability only' if d.wan or d.kind==TYPES[0] else 'Local probe')]
            row=self.table.rowCount()
            self.table.insertRow(row)
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                if col==0:
                    item.setData(Qt.UserRole,d.id)
                    item.setToolTip('ID: '+d.id+'\n'+d.notes)
                if col==4:
                    item.setForeground(QColor(status_color(state,self.ui_theme)))
                self.table.setItem(row,col,item)
            if selected and selected.id==d.id:
                self.table.selectRow(row)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        lookup={d.id:self.state(d) for d in self.devices}
        active_links=sum(1 for d in self.devices if d.parent and lookup.get(d.parent) in ('Online','Warning') and lookup[d.id] in ('Online','Warning'))
        avg=f'{sum(latencies)/len(latencies):.1f} ms' if latencies else '—'
        from .dashboard import dashboard_text
        self.summary.setText(dashboard_text(self.devices,lookup,self.measurements.latest,self.measurements.speed_latest,len(self.page_stations()),self.alerted,self.telemetry_alerted,time.time()))

    def render_history(self):
        if not hasattr(self,'graph'):
            return
        id=self.history_device.currentData()
        seconds=self.range.currentData() or 0
        since=time.time()-seconds if seconds else 0
        rows=self.store.samples(id,since,limit=1000) if id else []
        self.graph.rows=rows[-1000:]
        self.graph.update()
        if not id:
            self.history_summary.setText('Choose a device to see its measured history.')
            self.outage_text.clear()
            return
        stats=self.store.stats(id,since)
        avg=f"{stats['latency']:.1f} ms" if stats['latency'] is not None else '—'
        uptime=f"{stats['uptime']:.1f}%" if stats['uptime'] is not None else '—'
        self.history_summary.setText(f"Checks: {stats['n']} • Replies: {stats['ok']} • Sampled availability: {uptime} • Average latency: {avg}\nLast success: {stamp(stats['last_ok'])} • Last failure: {stamp(stats['last_fail'])}\nGraph/outage list: latest 1,000 samples. Totals cover the selected retained window. Unobserved downtime is unknown.")
        text=[]
        for start,end in outages(rows):
            duration=f'{end-start:.0f} seconds between observations' if end is not None else 'Recovery not observed'
            text.append(f'{stamp(start)} → {stamp(end)} | {duration}')
        self.outage_text.setPlainText('Observed no-reply intervals within selected window:\n'+'\n'.join(text) if text else 'No no-reply intervals observed in this window.')

    def event_rows(self,limit=1000):
        tower=self.event_tower.currentData() or ''
        ids=({d.id for d in self.devices if d.station_id==tower}|{tower}) if tower else {d.id for d in self.devices}|{s.id for s in self.page_stations()}
        # Apply page/tower scope before the limit, so busy unrelated pages cannot hide matches.
        return self.store.events(self.event_device.currentData() or '',self.event_from.dateTime().toSecsSinceEpoch(),self.event_to.dateTime().toSecsSinceEpoch(),self.event_search.text(),limit,scope=sorted(ids))

    def render_events(self):
        if not hasattr(self,'event_table'):
            return
        rows=self.event_rows()
        pins={r[0] for r in self.store.db.execute('SELECT event_id FROM event_pins')}
        names={d.id:d.name for d in self.devices}
        self.event_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,value in enumerate([stamp(r['at']),names.get(r['device'],'Application / deleted device'),r['kind'],r['message']]):
                item=QTableWidgetItem(value)
                if j==0:item.setData(Qt.UserRole,r['id'])
                if r['id'] in pins:item.setToolTip('Pinned: protected from cleanup');item.setForeground(QColor('#fbbf24'))
                self.event_table.setItem(i,j,item)

    def add(self):
        self.edit_device(None)

    def edit(self,*args):
        d=self.selected()
        if d:
            self.edit_device(d)

    def edit_device(self,d):
        dialog=DeviceDialog(self.devices,d or Device(page_id=self.page_id),self,stations=self.page_stations())
        if dialog.exec()==QDialog.Accepted:
            try:
                value=dialog.device()
                if d and (value.host!=d.host or value.source!=d.source):
                    self._resume_minimized=False;self.engine.invalidate();self.measurements.stop();self.requested.clear()
                    self.measurements.latest.pop(value.id,None);self.measurements.speed_latest.pop(value.id,None);self.telemetry_alerted.pop(value.id,None)
                self.store.save(value)
                self.states.pop(value.id,None)
                self.streaks.pop(value.id,None)
                self.alerted.pop(value.id,None)
                self.engine.due.pop(value.id,None)
                self.reload()
            except (ValueError,OSError) as e:
                QMessageBox.warning(self,'Could not save',str(e))

    def delete(self):
        d=self.selected()
        if d and QMessageBox.question(self,'Delete device','Delete '+d.name+'? Its historical records will be retained.')==QMessageBox.Yes:
            self.vault.delete(d.id)
            self.store.delete(d.id)
            self.reload()

    def toggle(self):
        self._resume_minimized=False
        if self.engine.running:
            self.engine.stop()
            self.measurements.stop()
            self.requested.clear()
            self.buzzer.silence()
            self.start_button.setText('▶ Start monitoring')
            self.store.event('','application','Periodic monitoring stopped')
        else:
            self.engine.devices=self.monitor_devices()
            self.engine.start()
            self.measurements.enabled=True
            self.start_button.setText('■ Stop monitoring')
            self.store.event('','application','Periodic monitoring started')
        self.render_all()

    def ping_all(self):
        self.requested.update(d.id for d in self.monitor_devices() if d.enabled and d.host)
        self.drain()
        for d in self.monitor_devices():self.measurements.submit(d)

    def ping_selected(self):
        d=self.selected()
        if d and d.enabled and d.host:
            self.requested.add(d.id)
            self.drain()
        else:
            QMessageBox.information(self,'Select a device','Select a configured device with monitoring enabled.')

    def continuous_selected(self):
        d=self.selected()
        if not d or not d.host or not d.enabled:
            QMessageBox.information(self,'Select a device','Select a configured enabled device first.')
            return
        if self.monitor_all_enabled:self.monitor_all_box.setChecked(False)
        # Continuous selection uses an explicit scope. Start monitoring restores all devices.
        if self.engine.running and self.engine.devices==[d]:
            self.toggle()
        else:
            self.engine.stop()
            self.engine.devices=[d]
            self.engine.start()
            self.start_button.setText('■ Stop monitoring')
            self.store.event(d.id,'application','Continuous selected-device monitoring started')
            self.render_all()

    def drain(self):
        for d in self.monitor_devices():
            if d.id in self.requested:
                if d.id in self.engine.pending:
                    self.requested.discard(d.id)
                elif self.engine.submit(d):
                    self.requested.discard(d.id)
        self.busy()

    def busy(self):
        scope='all networks' if self.monitor_all_enabled else 'selected page'
        self.statusBar().showMessage(f"{'Monitoring active' if self.engine.running else 'Periodic monitoring stopped'} • {scope} • {len(self.engine.pending)} probes running • {len(self.requested)} queued")

    def result(self,id,snapshot,result):
        current=next((d for d in self.monitor_devices() if d.id==id),None)
        if current is None or {k:v for k,v in asdict(current).items() if k not in ('map_x','map_y')}!={k:v for k,v in asdict(snapshot).items() if k not in ('map_x','map_y')}:
            return # Ignore an obsolete probe after edit/delete.
        previous=self.states.get(id,'Unknown')
        if result.infrastructure_error:
            self.states[id]='Probe error'
            self.store.event(id,'probe_error',result.error)
            self.request_render()
            return
        now=time.time()
        self.store.record(id,result,now)
        self._stats_cache.pop(id,None)
        from .faults import context
        from .faults import fresh
        old=self.latest.get(id,{})
        failure_since=old.get('failure_since',now) if old.get('success') is False and fresh(old,now,max(30,max(current.interval,self.engine.minimum_interval)*3)) else now
        self.latest[id]={'at':now,'latency':result.latency,'success':result.success,'error':result.error,'context':context(current,self.page_for_device(current)),'failure_since':None if result.success else failure_since}
        state='Warning' if result.success and result.latency is not None and result.latency>current.latency_threshold else ('Online' if result.success else 'No reply')
        if result.success and current.integration.get('loss_warning_pct') is not None:
            recent=self.store.samples(id,max(0,now-300),limit=30)
            if len(recent)>=3 and 100*sum(not r['success'] for r in recent)/len(recent)>current.integration['loss_warning_pct']:state='Warning'
        self.states[id]=state
        self.streaks[id]=0 if result.success else self.streaks.get(id,0)+1
        if previous!=state:
            self.store.event(id,'status',previous+' → '+state,now)
        if not result.success:
            self.store.event(id,'ping_failure',result.error,now)
        elif state=='Warning' and previous!='Warning':
            self.store.event(id,'latency',f'High latency: {result.latency:.1f} ms',now)
        alert='No reply' if self.streaks[id]>=current.failure_threshold else ('Latency / packet loss warning' if state=='Warning' else '')
        prior_alert=self.alerted.get(id,'')
        if current.alerts and alert and prior_alert!=alert:
            self.alerted[id]=alert
            self.notify(id,current.name,alert)
        elif result.success and prior_alert and not alert:
            self.alerted.pop(id,None)
            if current.alerts and self.recovery.isChecked():
                self.notify(id,current.name,'Reply received — recovered')
        self.request_render()

    def notify(self,id,name,message):
        if message=='No reply' and self.store.setting('correlate_alerts',True):
            from .faults import evaluate,fresh,service_responding
            _,findings=evaluate(self.monitor_devices(),self.latest,self.states,self.measurements.latest,self.streaks,time.time(),self.network_pages,self.engine.minimum_interval)
            roots={f['device'] for f in findings if f['correlated']}
            lookup={d.id:d for d in self.monitor_devices()};d=lookup.get(id);cursor=d.parent if d else '';seen={id}
            tele=self.measurements.latest.get(id,{})
            if d and fresh(tele,time.time(),max(30,d.integration.get('poll_seconds',30)*3)) and service_responding(tele):cursor=''
            while cursor in lookup and cursor not in seen:
                seen.add(cursor);parent=lookup[cursor];row=self.latest.get(cursor,{});tele=self.measurements.latest.get(cursor,{})
                alternative=fresh(tele,time.time(),max(30,parent.integration.get('poll_seconds',30)*3)) and service_responding(tele)
                if cursor in roots and parent.page_id==d.page_id and self.states.get(cursor)=='No reply' and self.streaks.get(cursor,0)>=parent.failure_threshold and fresh(row,time.time(),max(30,max(parent.interval,self.engine.minimum_interval)*3)) and not alternative:
                    self.store.event(id,'alert','Repeated downstream notification suppressed; possible upstream issue at '+parent.name+'. Device incident remains recorded.');return
                cursor=parent.parent
        if self.monitor_all_enabled:
            d=next((d for d in self.all_devices if d.id==id),None)
            if d:name=self.network_pages[d.page_id].name+' / '+name
        self.store.event(id,'alert',name+': '+message)
        if self.notifications.isChecked() and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage('Zee Network Monitor',name+': '+message,QSystemTrayIcon.Information,5000)


    def save_settings(self):
        self.store.set_setting('alarm_delay_seconds',self.alarm_delay.value())
        self.buzzer.set_delay(self.alarm_delay.value())
        for key,value in [('notifications',self.notifications.isChecked()),('beep',self.beep.isChecked()),('recovery',self.recovery.isChecked()),('detail_hours',self.retention.value()),('auto_cleanup',self.auto_cleanup.isChecked())]:
            self.store.set_setting(key,value)
        self.store.event('','config','Alert and retention settings saved')
        self.prune()
        self.statusBar().showMessage('Settings saved')

    def prune(self,manual=False):
        from .retention import Policy,history_hours
        if not manual and not self.store.setting('auto_cleanup',True):return
        self.protect_active_alerts()
        policy=Policy(history_hours(self.store),self.store.setting('incident_days',90),self.store.setting('disk_warning_mb',250),self.store.setting('archive_cleanup',False))
        if getattr(self,'_cleanup_continuation',False):
            from dataclasses import replace
            policy=replace(policy,archive=False)
        self._cleanup_continuation=False
        if self.cleaner.start(self.store.path,policy):
            self._cleanup_manual=manual
            self.cleanup_status.setText('Cleaning expired records in background…')

    def cleanup_finished(self,result):
        if result.get('error'):
            text=result['error'];self._cleanup_retry=True
        else:
            text=f"Last cleanup: {stamp(result['at'])} • {result['deleted']} records removed • DB {result['physical_mb']} MB"
            if result.get('archive'):text+=' • Database archive saved'
            if result.get('disk_warning'):text+=' • Disk warning: protected/fresh data or archives may need review'
            self._stats_cache.clear();self.request_render();self._cleanup_retry=False
        self.cleanup_status.setText(text);self.store.set_setting('cleanup_status',text)
        self.store.set_setting('last_cleanup',result)
        if result.get('more'):
            self._cleanup_continuation=True
            QTimer.singleShot(1000,lambda:self.prune(manual=self._cleanup_manual) if not self.cleaner.cancel.is_set() else None)
        elif result.get('error') and self.store.setting('auto_cleanup',True):
            QTimer.singleShot(60000,lambda:self.prune() if not self.cleaner.cancel.is_set() else None)

    def performance_dialog(self):
        from .performance import PerformanceDialog
        PerformanceDialog(self).exec()

    def apply_performance(self):
        self.engine.configure(self.store.setting('ping_workers',8),self.store.setting('ping_retries',0),self.store.setting('retry_delay',1),self.store.setting('minimum_interval',1))
        self.measurements.configure(self.store.setting('telemetry_workers',2))
        milliseconds=self.store.setting('refresh_seconds',2)*1000
        self.view_timer.setInterval(milliseconds);self.pro_panel.timer.setInterval(milliseconds)

    def pin_selected_event(self):
        item=self.event_table.item(self.event_table.currentRow(),0)
        if item:
            self.store.pin_event(item.data(Qt.UserRole));self.render_events()

    def changeEvent(self,event):
        from PySide6.QtCore import QEvent
        super().changeEvent(event)
        if event.type()!=QEvent.WindowStateChange or not hasattr(self,'engine'):return
        if self.isMinimized() and self.store.setting('pause_minimized',False):
            self._resume_minimized=self.engine.running
            if self._resume_minimized:self.engine.stop();self.measurements.stop()
        elif not self.isMinimized() and self._resume_minimized:
            self._resume_minimized=False;self.engine.start();self.measurements.enabled=True


    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,'Save database backup','ZeeNetworkMonitor-backup.sqlite3','SQLite (*.sqlite3)')
        if path:
            if Path(path).resolve()==self.store.path.resolve():
                QMessageBox.warning(self,'Choose another file','Do not overwrite the active database.')
                return
            try:
                self.store.backup(path)
                self.statusBar().showMessage('Database backup saved')
            except Exception as e:
                QMessageBox.warning(self,'Backup failed',str(e))

    def wan_templates(self):
        if not self.policy.allows('wan'):
            QMessageBox.information(self,'Package permission','WAN monitoring is not included in this package.');return
        existing={d.wan for d in self.devices}
        missing=sum(i not in existing for i in range(1,6))
        if len(self.store.devices())+missing>self.policy.max_devices:
            QMessageBox.information(self,'Device limit','These templates would exceed your package limit. Add individual modems instead.');return
        for i in range(1,6):
            if i not in existing:
                self.store.save(Device(page_id=self.page_id,name=f'WAN-{i}',kind=TYPES[0],location='',wan=i,enabled=False,notes='Configure a verified WAN-specific target/path. Reachability only until verified.'))
        self.reload()

    def export(self,filename,rows,fields):
        if not self.policy.allows('reports'):
            QMessageBox.information(self,'Package permission','Reports are not included in this package.');return
        path,_=QFileDialog.getSaveFileName(self,'Export CSV',filename,'CSV (*.csv)')
        if path:
            try:
                export_csv(path,rows,fields)
                self.statusBar().showMessage('CSV exported: '+path)
            except Exception as e:
                QMessageBox.warning(self,'Export failed',str(e))

    def export_summary(self):
        rows=[]
        for d in self.devices:
            s=self.store.stats(d.id)
            rows.append({'name':d.name,'host':d.host,'location':d.location,'status':self.state(d),'checks':s['n'],'replies':s['ok'],'loss_pct':s['loss'],'sampled_uptime_pct':s['uptime'],'average_latency_ms':s['latency'],'last_success':stamp(s['last_ok']),'last_failure':stamp(s['last_fail'])})
        self.export('device-summary.csv',rows,list(rows[0]) if rows else ['name','host','status'])

    def export_samples(self):
        id=self.history_device.currentData()
        seconds=self.range.currentData() or 0
        self.export('ping-samples.csv',self.store.samples(id,time.time()-seconds if seconds else 0),['id','device','at','success','latency','error'])

    def export_events(self):
        self.export('events.csv',self.event_rows(2147483647),['id','device','at','kind','message'])

    def closeEvent(self,event):
        if getattr(self,'pilot_capture',None):
            try:self.pilot_capture.stop()
            except Exception:__import__('logging').warning('Pilot evidence could not be saved during shutdown.')
        for dialog in self.details_windows:dialog.close()
        self.pro_panel.timer.stop()
        self.seven_wan.timer.stop()
        self.license_timer.stop()
        self.cleaner.shutdown()
        self.measurements.shutdown()
        if hasattr(self,'mobile_server') and self.mobile_server:self.mobile_server.stop()
        self.map_page.shutdown()
        self.buzzer.shutdown()
        self.queue_timer.stop()
        self.view_timer.stop()
        self.maintenance.stop()
        self.requested.clear()
        self.engine.shutdown()
        self.store.event('','application','Application stopped')
        self.tray.hide()
        self.store.close()
        event.accept()

