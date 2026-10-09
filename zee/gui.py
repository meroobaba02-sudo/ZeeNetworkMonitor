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
    QFileDialog, QTextEdit, QSystemTrayIcon, QStyle, QScrollArea, QDateTimeEdit, QSplitter, QDoubleSpinBox)
from .core import Device, Store, TYPES, VERSION, diagnoses, export_csv, outages
from .engine import Engine

COLORS = {'Online':'#36d399','Warning':'#fbbf24','No reply':'#fb7185','Unknown':'#fbbf24','Checking':'#60a5fa','Disabled':'#94a3b8','Probe error':'#fbbf24','Unconfigured':'#fbbf24'}
STYLE = '''
QWidget { background:#071827; color:#e2e8f0; font-family:Segoe UI; font-size:12px; }
QMainWindow, QDialog { background:#101827; }
QLabel#title { font-size:26px; font-weight:700; }
QLabel#subtitle { color:#94a3b8; }
QLabel#card { background:#1e293b; border-radius:9px; padding:14px; font-size:17px; font-weight:600; }
QPushButton { background:#27364d; border:1px solid #34445c; padding:8px 13px; border-radius:6px; }
QPushButton:hover { background:#36516d; }
QPushButton:disabled { color:#64748b; }
QPushButton#primary { background:#087f8c; border:0; font-weight:600; }
QLineEdit,QComboBox,QSpinBox,QTextEdit,QDateTimeEdit { background:#1e293b; border:1px solid #34445c; border-radius:4px; padding:6px; }
QTableWidget { background:#131e30; gridline-color:#27364d; border:1px solid #27364d; alternate-background-color:#19253a; }
QHeaderView::section { background:#24324a; padding:8px; border:0; font-weight:600; }
QTableWidget::item:selected { background:#214c62; }
QTabBar::tab { background:#1e293b; padding:10px 18px; margin:3px; border-radius:5px; }
QTabBar::tab:selected { background:#087f8c; }
QCheckBox { spacing:8px; }
'''

def stamp(t):
    return time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(t)) if t else '—'

def button(text, fn, primary=False):
    b = QPushButton(text)
    b.clicked.connect(fn)
    if primary:
        b.setObjectName('primary')
    return b

class DeviceDialog(QDialog):
    def __init__(self, devices, device=None, parent=None):
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
        for key,title in [('name','Device / station name'),('host','IP address or hostname'),('location','Station / location'),('notes','Notes'),('source','Optional IPv6 source IP'),('profile','Reserved profile reference')]:
            edit = QLineEdit(values[key])
            self.fields[key] = edit
            form.addRow(title,edit)
        kind = QComboBox()
        kind.addItems(TYPES)
        kind.setCurrentText(values['kind'])
        self.fields['kind'] = kind
        form.addRow('Device type',kind)
        for key,title in [('parent','Parent / previous hop'),('next_hop','Next hop (annotation)')]:
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
        help_text = QLabel('WAN without source binding: host reachability only. IPv4 WAN independence needs verified Windows routing; this app does not create routes.\nProfile reference is reserved; no credential collection or radio telemetry in this release.')
        help_text.setWordWrap(True)
        form.addRow(help_text)
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

class Window(QMainWindow):
    def __init__(self,store):
        super().__init__()
        self.store=store
        self.engine=Engine(self)
        self.engine.result.connect(self.result)
        self.engine.busy_changed.connect(self.busy)
        self.states={}
        self.latest={}
        self.streaks={}
        self.alerted={}
        self.requested=set()
        self.devices=[]
        self.setWindowTitle(f'Zee Network Monitor • {VERSION}')
        self.resize(1360,790)
        self.setMinimumSize(980,650)
        root=QWidget()
        self.setCentralWidget(root)
        layout=QVBoxLayout(root)
        layout.setContentsMargins(22,18,22,18)
        head=QHBoxLayout()
        titles=QVBoxLayout()
        title=QLabel('ZEE  /  NETWORK MONITOR')
        title.setObjectName('title')
        title.setStyleSheet('font-size:20px; font-weight:700;')
        subtitle=QLabel('Your network • Live device map • Windows desktop')
        subtitle.setObjectName('subtitle')
        titles.addWidget(title)
        titles.addWidget(subtitle)
        head.addLayout(titles)
        head.addStretch()
        self.start_button=button('▶ Start monitoring',self.toggle,True)
        head.addWidget(self.start_button)
        head.addWidget(button('Ping all now',self.ping_all))
        from .buzzer import Buzzer
        self.buzzer=Buzzer(self,enabled=self.store.setting('buzzer_enabled',True))
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
        self.summary.setObjectName('card')
        self.summary.hide()
        self.tabs=QTabWidget()
        self.tabs.tabBar().hide()
        content=QHBoxLayout()
        self.navigation=QVBoxLayout()
        content.addLayout(self.navigation)
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
        actions=QHBoxLayout()
        for title,fn in [('Add device',self.add),('Edit',self.edit),('Delete',self.delete),('Ping selected',self.ping_selected),('Continuous selected',self.continuous_selected),('Refresh',self.reload),('Export summary',self.export_summary)]:
            actions.addWidget(button(title,fn))
        actions.addStretch()
        dash.addLayout(actions)
        self.table=QTableWidget(0,10)
        self.table.setHorizontalHeaderLabels(['Device / station','Host','Type','Location','Status','Latency','Loss (samples)','Checks OK / failed','Last check','WAN mode'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self.edit)
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
        self.nav_buttons=[]
        for i,text in enumerate(['◉  Map','▤  Devices / WANs','◷  History','⌁  Topology','♧  Alerts','⚙  Settings']):
            b=QPushButton(text);b.setObjectName('nav');b.setCheckable(True);b.setFixedWidth(148)
            b.clicked.connect(lambda checked=False,index=i:self.tabs.setCurrentIndex(index))
            self.navigation.addWidget(b);self.nav_buttons.append(b)
        self.navigation.addStretch()
        self.tabs.currentChanged.connect(self.highlight_nav)
        self.tabs.setCurrentIndex(0);self.highlight_nav(0)
        self.tray=QSystemTrayIcon(self.style().standardIcon(QStyle.SP_ComputerIcon),self)
        self.tray.setToolTip('Zee Network Monitor')
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.statusBar().showMessage('Ready • Monitoring is stopped')
        self.queue_timer=QTimer(self)
        self.queue_timer.timeout.connect(self.drain)
        self.queue_timer.start(150)
        self.view_timer=QTimer(self)
        self.view_timer.timeout.connect(self.refresh_states)
        self.view_timer.start(2000)
        self.maintenance=QTimer(self)
        self.maintenance.timeout.connect(self.prune)
        self.maintenance.start(3600000)
        self.store.event('','application','Application started')
        self.reload()
        self.prune()

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
        tools=QHBoxLayout()
        self.event_device=QComboBox()
        self.event_device.currentIndexChanged.connect(self.render_events)
        self.event_search=QLineEdit()
        self.event_search.setPlaceholderText('Search event text / type…')
        self.event_search.textChanged.connect(self.render_events)
        self.event_from=QDateTimeEdit(QDateTime.currentDateTime().addDays(-7))
        self.event_to=QDateTimeEdit(QDateTime.currentDateTime().addYears(1))
        for widget in (self.event_from,self.event_to):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat('yyyy-MM-dd HH:mm')
            widget.dateTimeChanged.connect(self.render_events)
        for w in (self.event_device,self.event_search,self.event_from,self.event_to):
            tools.addWidget(w)
        tools.addWidget(button('Export events',self.export_events))
        layout.addLayout(tools)
        self.event_table=QTableWidget(0,4)
        self.event_table.setHorizontalHeaderLabels(['Time (local)','Device','Type','Message'])
        self.event_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.event_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.event_table)
        layout.addWidget(QLabel('Latest 1,000 matching events shown; export includes all matching retained events.'))
        self.tabs.addTab(page,'Events & alerts')

    def settings_page(self):
        page=QWidget()
        form=QFormLayout(page)
        self.notifications=QCheckBox('Desktop notifications (when system tray is available)')
        self.notifications.setChecked(self.store.setting('notifications',True))
        self.beep=QCheckBox('Beep on alert')
        self.beep.setChecked(self.buzzer.enabled)
        self.beep.setText('Enable repeating fault buzzer')
        self.beep.toggled.connect(self.buzzer_button.setChecked)
        self.recovery=QCheckBox('Recovery notifications')
        self.recovery.setChecked(self.store.setting('recovery',True))
        self.retention=QSpinBox()
        self.retention.setRange(1,3650)
        self.retention.setValue(self.store.setting('retention',90))
        for w in (self.notifications,self.beep,self.recovery):
            form.addRow(w)
        form.addRow('History retention (days)',self.retention)
        form.addRow(button('Test buzzer (1 second)',self.test_buzzer))
        form.addRow(button('Save settings',self.save_settings,True))
        form.addRow(button('Backup database',self.backup))
        form.addRow(button('Add 5 unconfigured WAN templates',self.wan_templates))
        info=QLabel('Database: '+str(self.store.path)+'\n\nAdvanced adapters: not implemented in v0.1.0.\nRocket M5 uses basic ping only. No SNMP/SSH/API secrets are stored.\nRemote agents, encrypted reporting and service installation are not available.\nNo fabricated signal, speed, CCQ, bandwidth or agent data is displayed.\n\nClosing the app stops local monitoring. Existing probes finish within their deadline.')
        info.setWordWrap(True)
        form.addRow(info)
        self.tabs.addTab(page,'Settings & scope')

    def reload(self):
        self.devices=self.store.devices()
        self.engine.devices=self.devices
        self.requested &= {d.id for d in self.devices if d.enabled and d.host}
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
        # Last check is displayed, but previous-session status is never treated as fresh.
        for d in self.devices:
            if d.id not in self.latest:
                row=self.store.db.execute('SELECT * FROM samples WHERE device=? ORDER BY at DESC,id DESC LIMIT 1',(d.id,)).fetchone()
                if row:
                    self.latest[d.id]=dict(row)
        self.render_all()

    def highlight_nav(self,index):
        for i,b in enumerate(self.nav_buttons):b.setChecked(i==index)

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
        self.buzzer_button.setStyleSheet('color:#28e3a0' if self.buzzer.enabled else 'color:#9aacc0')
        self.alarm_status.setText('FAULT ALARM' if self.buzzer.playing else ('Silenced' if self.buzzer.active else 'Alarm clear'))
        self.alarm_status.setStyleSheet('color:#ff6478' if self.buzzer.playing else 'color:#9aacc0')

    def refresh_map(self):
        if hasattr(self,'map_page'):self.map_page.refresh()
        active={}
        for d in self.devices:
            state=self.state(d)
            if state=='Checking':state=self.states.get(d.id,'Unknown')
            if d.alerts and state in ('Warning','No reply') and self.alerted.get(d.id):
                active[d.id]=self.alerted[d.id]
        self.buzzer.update(active)

    def refresh_states(self):
        self.render_table()
        self.topology.refresh(self.devices,{d.id:self.state(d) for d in self.devices})
        self.render_diagnosis()
        self.refresh_map()

    def state(self,d):
        if not d.enabled:
            return 'Disabled' if d.host else 'Unconfigured'
        if d.id in self.engine.pending:
            return 'Checking'
        if not d.host:
            return 'Unconfigured'
        last=self.latest.get(d.id)
        if last and time.time()-last['at']>max(30,d.interval*3):
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

    def render_diagnosis(self):
        items=diagnoses(self.devices,{d.id:self.state(d) for d in self.devices})
        text=[]
        for x in items:
            text.append(f"Last known good hop: {x['last_good']}\nFirst observed failing hop: {x['first_failure']}\nDownstream: {', '.join(x['affected']) or 'None'}\n{x['explanation']}")
        self.diagnostic.setPlainText('\n\n'.join(text) or 'No suspected segment identified from the current observations. Unknown/stale states are not evidence of a good link.')

    def render_table(self):
        if not hasattr(self,'table'):
            return
        selected=self.selected()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        all_states=[]
        latencies=[]
        failed=0
        for d in self.devices:
            state=self.state(d)
            all_states.append(state)
            stats=self.store.stats(d.id)
            failed+=stats['n']-stats['ok']
            last=self.latest.get(d.id,{})
            if state in ('Online','Warning') and last.get('latency') is not None:
                latencies.append(last['latency'])
            query=self.search.text().casefold()
            if query and query not in ' '.join([d.name,d.host,d.location,d.notes]).casefold():
                continue
            if self.station.currentText() not in ('All locations','',d.location) or self.kind.currentText() not in ('All types',d.kind):
                continue
            values=[d.name,d.host or '—',d.kind,d.location,state, f"{last['latency']:.1f} ms" if last.get('latency') is not None else '—',f"{stats['loss']:.1f}%" if stats['loss'] is not None else '—',f"{stats['ok']} / {stats['n']-stats['ok']}",stamp(last.get('at')),'IPv6 source-bound (verify path)' if d.source else ('Reachability only' if d.wan or d.kind==TYPES[0] else 'Local probe')]
            row=self.table.rowCount()
            self.table.insertRow(row)
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                if col==0:
                    item.setData(Qt.UserRole,d.id)
                    item.setToolTip('ID: '+d.id+'\n'+d.notes)
                if col==4:
                    item.setForeground(QColor(COLORS[state]))
                self.table.setItem(row,col,item)
            if selected and selected.id==d.id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        lookup={d.id:self.state(d) for d in self.devices}
        active_links=sum(1 for d in self.devices if d.parent and lookup.get(d.parent) in ('Online','Warning') and lookup[d.id] in ('Online','Warning'))
        avg=f'{sum(latencies)/len(latencies):.1f} ms' if latencies else '—'
        self.summary.setText(f"Devices  {len(self.devices)}   |   Stations  {len({d.location for d in self.devices if d.location})}   |   Online  {all_states.count('Online')}   |   Warning  {all_states.count('Warning')}   |   No reply  {all_states.count('No reply')}   |   Other  {len(all_states)-sum(all_states.count(s) for s in ('Online','Warning','No reply'))}\nObserved active links  {active_links}   |   Failed checks (retained)  {failed}   |   Latest average latency  {avg}")

    def render_history(self):
        if not hasattr(self,'graph'):
            return
        id=self.history_device.currentData()
        seconds=self.range.currentData() or 0
        since=time.time()-seconds if seconds else 0
        rows=self.store.samples(id,since) if id else []
        self.graph.rows=rows[-1000:]
        self.graph.update()
        if not id:
            self.history_summary.setText('Choose a device to see its measured history.')
            self.outage_text.clear()
            return
        stats=self.store.stats(id,since)
        avg=f"{stats['latency']:.1f} ms" if stats['latency'] is not None else '—'
        uptime=f"{stats['uptime']:.1f}%" if stats['uptime'] is not None else '—'
        self.history_summary.setText(f"Checks: {stats['n']} • Replies: {stats['ok']} • Sampled availability: {uptime} • Average latency: {avg}\nLast success: {stamp(stats['last_ok'])} • Last failure: {stamp(stats['last_fail'])}\nThese are sample estimates; downtime during application shutdown or missing observations is unknown.")
        text=[]
        for start,end in outages(rows):
            duration=f'{end-start:.0f} seconds between observations' if end is not None else 'Recovery not observed'
            text.append(f'{stamp(start)} → {stamp(end)} | {duration}')
        self.outage_text.setPlainText('Observed no-reply intervals within selected window:\n'+'\n'.join(text) if text else 'No no-reply intervals observed in this window.')

    def event_rows(self,limit=1000):
        return self.store.events(self.event_device.currentData() or '',self.event_from.dateTime().toSecsSinceEpoch(),self.event_to.dateTime().toSecsSinceEpoch(),self.event_search.text(),limit)

    def render_events(self):
        if not hasattr(self,'event_table'):
            return
        rows=self.event_rows()
        names={d.id:d.name for d in self.devices}
        self.event_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,value in enumerate([stamp(r['at']),names.get(r['device'],'Application / deleted device'),r['kind'],r['message']]):
                self.event_table.setItem(i,j,QTableWidgetItem(value))

    def add(self):
        self.edit_device(None)

    def edit(self,*args):
        d=self.selected()
        if d:
            self.edit_device(d)

    def edit_device(self,d):
        dialog=DeviceDialog(self.devices,d,self)
        if dialog.exec()==QDialog.Accepted:
            try:
                value=dialog.device()
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
            self.store.delete(d.id)
            self.reload()

    def toggle(self):
        if self.engine.running:
            self.engine.stop()
            self.requested.clear()
            self.buzzer.silence()
            self.start_button.setText('▶ Start monitoring')
            self.store.event('','application','Periodic monitoring stopped')
        else:
            self.engine.devices=self.devices
            self.engine.start()
            self.start_button.setText('■ Stop monitoring')
            self.store.event('','application','Periodic monitoring started')
        self.render_all()

    def ping_all(self):
        self.requested.update(d.id for d in self.devices if d.enabled and d.host)
        self.drain()

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
        for d in self.devices:
            if d.id in self.requested:
                if d.id in self.engine.pending:
                    self.requested.discard(d.id)
                elif self.engine.submit(d):
                    self.requested.discard(d.id)
        self.busy()

    def busy(self):
        self.statusBar().showMessage(f"{'Monitoring active' if self.engine.running else 'Periodic monitoring stopped'} • {len(self.engine.pending)} probes running • {len(self.requested)} queued")

    def result(self,id,snapshot,result):
        current=next((d for d in self.devices if d.id==id),None)
        if current is None or {k:v for k,v in asdict(current).items() if k not in ('map_x','map_y')}!={k:v for k,v in asdict(snapshot).items() if k not in ('map_x','map_y')}:
            return # Ignore an obsolete probe after edit/delete.
        previous=self.states.get(id,'Unknown')
        if result.infrastructure_error:
            self.states[id]='Probe error'
            self.store.event(id,'probe_error',result.error)
            self.render_all()
            return
        now=time.time()
        self.store.record(id,result,now)
        self.latest[id]={'at':now,'latency':result.latency,'success':result.success,'error':result.error}
        state='Warning' if result.success and result.latency is not None and result.latency>current.latency_threshold else ('Online' if result.success else 'No reply')
        self.states[id]=state
        self.streaks[id]=0 if result.success else self.streaks.get(id,0)+1
        if previous!=state:
            self.store.event(id,'status',previous+' → '+state,now)
        if not result.success:
            self.store.event(id,'ping_failure',result.error,now)
        elif state=='Warning' and previous!='Warning':
            self.store.event(id,'latency',f'High latency: {result.latency:.1f} ms',now)
        alert='No reply' if self.streaks[id]>=current.failure_threshold else ('High latency' if state=='Warning' else '')
        prior_alert=self.alerted.get(id,'')
        if current.alerts and alert and prior_alert!=alert:
            self.alerted[id]=alert
            self.notify(id,current.name,alert)
        elif result.success and prior_alert and not alert:
            self.alerted.pop(id,None)
            if current.alerts and self.recovery.isChecked():
                self.notify(id,current.name,'Reply received — recovered')
        self.render_all()

    def notify(self,id,name,message):
        self.store.event(id,'alert',name+': '+message)
        if self.notifications.isChecked() and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage('Zee Network Monitor',name+': '+message,QSystemTrayIcon.Information,5000)


    def save_settings(self):
        for key,value in [('notifications',self.notifications.isChecked()),('beep',self.beep.isChecked()),('recovery',self.recovery.isChecked()),('retention',self.retention.value())]:
            self.store.set_setting(key,value)
        self.store.event('','config','Alert and retention settings saved')
        self.prune()
        self.statusBar().showMessage('Settings saved')

    def prune(self):
        self.store.prune(self.store.setting('retention',90))

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
        existing={d.wan for d in self.devices}
        for i in range(1,6):
            if i not in existing:
                self.store.save(Device(name=f'WAN-{i}',kind=TYPES[0],location='',wan=i,enabled=False,notes='Configure a verified WAN-specific target/path. Reachability only until verified.'))
        self.reload()

    def export(self,filename,rows,fields):
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

STYLE += '''
QLabel#mapCard { background:#0c2135; border:1px solid #1d3b51; border-radius:8px; padding:13px; font-size:15px; font-weight:600; }
QLabel#mapEvents { background:#0b2034; border:1px solid #1d3b51; border-radius:8px; padding:11px; color:#acc7dd; }
QLabel#detailTitle {font-size:20px; font-weight:700;}
QPushButton#nav {text-align:left; padding:12px; border:0; background:#0a2033;}
QPushButton#nav:checked {background:#105369; border-left:3px solid #25e3aa;}
'''
