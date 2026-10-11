"""A page-scoped operations overview, using the existing monitoring and incident engines."""
import time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QScrollArea,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QFrame,QTableWidget,QTableWidgetItem,QHeaderView
from .customer_view import wan_view,device_counts


def label(text='',name=''):
    w=QLabel(text);w.setTextFormat(Qt.PlainText);w.setWordWrap(True)
    if name:w.setObjectName(name)
    return w

def action(text,fn):
    b=QPushButton(text);b.clicked.connect(fn);b.setAccessibleName(text);return b

class WanCard(QFrame):
    def __init__(self,w):
        super().__init__();self.w=w;self.id=None;self.setObjectName('wanCard');layout=QVBoxLayout(self);layout.setContentsMargins(15,12,15,12)
        self.name=label('', 'sectionTitle');layout.addWidget(self.name)
        self.host=label('', 'muted');layout.addWidget(self.host)
        self.status=label();layout.addWidget(self.status)
        self.live=label();layout.addWidget(self.live)
        self.test=label('', 'muted');layout.addWidget(self.test)
        self.open_button=action('View / test this connection',self.open);layout.addWidget(self.open_button)
    def update_view(self,d,view):
        self.id=d.id;self.name.setText(view['name']);self.host.setText(view['host'])
        self.status.setText('Router: '+view['router']+'\nInternet: '+view['internet'])
        self.live.setText('LIVE USAGE (Mbps)\n↓ '+view['download']+'    ↑ '+view['upload'])
        self.test.setText('LAST TEST (Mbps)\n↓ '+view['test_download']+'    ↑ '+view['test_upload']+'\n'+view['test_age']);self.test.setToolTip(view['test_note'])
        self.setAccessibleName(d.name+' Internet connection')
    def open(self):
        self.w.tabs.setCurrentIndex(7);panel=self.w.seven_wan;panel.refresh()
        for row in range(panel.table.rowCount()):
            if panel.table.item(row,0).data(Qt.UserRole)==self.id:panel.table.selectRow(row);break

class CustomerDashboard(QScrollArea):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.wan_page=0;self._columns=None;self.setWidgetResizable(True);self.setFrameShape(QFrame.NoFrame)
        body=QWidget();self.setWidget(body);layout=QVBoxLayout(body);layout.setContentsMargins(18,14,18,18);layout.setSpacing(16)
        heading=QHBoxLayout();layout.addLayout(heading);heading.addWidget(label('Network overview','title'));heading.addStretch()
        heading.addWidget(action('Incidents / evidence',w.open_incidents))
        self.scope=label('', 'muted');layout.addWidget(self.scope)
        self.metrics_grid=QGridLayout();self.metrics_grid.setSpacing(12);layout.addLayout(self.metrics_grid)
        self.metrics=[]
        for title in ['Monitored devices','Online devices','Warnings / no reply','Unknown / not checked','Internet connections','Wireless links','Current latency','Sampled loss / uptime','Active alerts','Recent ping failures','Unreachable devices','Internet offline']:
            card=QFrame();card.setObjectName('metricCard');box=QVBoxLayout(card);box.setContentsMargins(15,12,15,12);box.addWidget(label(title,'muted'));value=label('0','metricValue');box.addWidget(value);self.metrics.append((card,value))
        self.setup=QFrame();self.setup.setObjectName('setupCard');box=QVBoxLayout(self.setup);box.addWidget(label('Start with your real network','sectionTitle'));box.addWidget(label('1. Add a device and its IP.  2. Add towers on the map if needed.  3. Start monitoring. No sample devices or readings are added.'))
        row=QHBoxLayout();box.addLayout(row);row.addWidget(action('Add first device',w.add));row.addWidget(action('Add a tower',self.add_tower));row.addStretch();layout.addWidget(self.setup)
        tools=QHBoxLayout();layout.addLayout(tools)
        for title,fn in [('Add device',w.add),('Map / towers',lambda:w.tabs.setCurrentIndex(0)),('Topology / diagnosis',lambda:w.tabs.setCurrentIndex(3)),('All Internet connections',lambda:w.tabs.setCurrentIndex(7))]:tools.addWidget(action(title,fn))
        section=QHBoxLayout();layout.addLayout(section);section_title=label('Seven Internet connections','sectionTitle');section_title.setWordWrap(False);section.addWidget(section_title);section.addStretch();self.wan_count=label('', 'muted');self.wan_count.setWordWrap(False);section.addWidget(self.wan_count)
        self.previous=action('Previous',lambda:self.move_wans(-1));self.next=action('Next',lambda:self.move_wans(1));section.addWidget(self.previous);section.addWidget(self.next)
        self.no_wans=label('No modems configured. Open All Internet connections → Add modem.');layout.addWidget(self.no_wans)
        self.wan_grid=QGridLayout();self.wan_grid.setSpacing(12);layout.addLayout(self.wan_grid);self.wan_cards=[WanCard(w) for _ in range(7)]
        note=label('Live usage comes from verified WAN counters. Manual tests require an independently checked Internet path. Unavailable values mean no measurement; ping alone does not prove Internet or physical-link health.','muted');layout.addWidget(note)
        incident_head=QHBoxLayout();layout.addLayout(incident_head);incident_head.addWidget(label('Open incidents','sectionTitle'));incident_head.addStretch();self.incident_count=label('', 'muted');self.incident_count.setWordWrap(False);incident_head.addWidget(self.incident_count)
        self.incident_text=label();self.incident_text.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(self.incident_text)
        layout.removeItem(incident_head);layout.insertLayout(5,incident_head)
        layout.removeWidget(self.incident_text);layout.insertWidget(6,self.incident_text)
        layout.addWidget(label('Devices to review','sectionTitle'))
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Device','IP / host','Observed status','Last ping']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setSelectionMode(QTableWidget.SingleSelection);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.setAlternatingRowColors(True);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.table.setMinimumHeight(155);self.table.setMaximumHeight(285);self.table.cellDoubleClicked.connect(self.details);self.table.setAccessibleName('Devices to review; double click for details');layout.addWidget(self.table)
        footer=QHBoxLayout();layout.addLayout(footer);footer.addWidget(label('Up to 8 devices shown; attention first.','muted'));footer.addStretch();footer.addWidget(action('Device details',self.selected_details));footer.addWidget(action('Search all devices',lambda:w.focus_device_search()))
        layout.addStretch();self.reflow(3)
    def add_tower(self):self.w.tabs.setCurrentIndex(0);self.w.map_page.add_tower()
    def move_wans(self,delta):self.wan_page=max(0,self.wan_page+delta);self.refresh()
    def reflow(self,columns):
        metric_columns=4 if columns==3 else 3 if self.viewport().width()>=650 else 2
        if columns==self._columns and metric_columns==getattr(self,'_metric_columns',None):return
        self._columns=columns;self._metric_columns=metric_columns
        for i,(card,_) in enumerate(self.metrics):self.metrics_grid.addWidget(card,i//metric_columns,i%metric_columns)
        for i,card in enumerate(self.wan_cards):self.wan_grid.addWidget(card,i//columns,i%columns)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'wan_cards'):self.reflow(2 if self.viewport().width()<1000 else 3)
    def selected_details(self):self.details(self.table.currentRow(),0)
    def details(self,row,col):
        item=self.table.item(row,0)
        d=next((d for d in self.w.devices if item and d.id==item.data(Qt.UserRole)),None)
        if d:self.w.show_details(d)
    def refresh(self):
        w=self.w;now=time.time();devices=w.devices;states={d.id:w.state(d) for d in devices};counts=device_counts(devices,states)
        for (_,widget),key in zip(self.metrics[:4],['devices','online','attention','other']):widget.setText(str(counts[key]))
        from .wan import wan_health
        modems=[d for d in devices if d.wan or d.kind.startswith('WAN')];health=[wan_health(d,states[d.id],w.measurements.latest.get(d.id,{}),w.measurements.speed_latest.get(d.id,{}),now)[0] for d in modems]
        self.metrics[4][1].setText(str(len(modems)));self.metrics[4][0].setToolTip(f'{health.count("Online")} Internet online / {health.count("Offline")} offline / {health.count("Unknown")} unknown; independence needs verified paths')
        links={tuple(sorted((d.id,d.peer_id))) for d in devices if d.peer_id and any(x.id==d.peer_id for x in devices)};self.metrics[5][1].setText(str(len(links)));self.metrics[5][0].setToolTip('Configured wireless peer pairs; no physical links inferred')
        latency=[w.latest[d.id]['latency'] for d in devices if states[d.id] in ('Online','Warning') and w.latest.get(d.id,{}).get('latency') is not None]
        self.metrics[6][1].setText(f'{sum(latency)/len(latency):.1f} ms' if latency else '—');self.metrics[6][0].setToolTip('Mean latest fresh replying-device latency; excludes devices without a reading')
        cached=[w._stats_cache[d.id] for d in devices if d.id in w._stats_cache and w._stats_cache[d.id]['n']];n=sum(r['n'] for r in cached);ok=sum(r['ok'] for r in cached);self.metrics[7][1].setText(f'{100*(n-ok)/n:.1f}% / {100*ok/n:.1f}%' if n else '—');self.metrics[7][0].setToolTip(f'Loss / sampled ICMP uptime, retained samples for {len(cached)} cached devices; not guaranteed service uptime')
        self.metrics[8][1].setText(str(sum(d.id in w.alerted and states[d.id] in ('Warning','No reply') or d.id in w.telemetry_alerted and 0<=now-w.measurements.latest.get(d.id,{}).get('at',0)<=max(30,d.integration.get('poll_seconds',30)*3) for d in devices)))
        if devices:
            failures=w.store.db.execute('SELECT COUNT(*) FROM samples WHERE success=0 AND at>=? AND device IN ('+','.join('?' for _ in devices)+')',[now-3600]+[d.id for d in devices]).fetchone()[0]
        else:failures=0
        self.metrics[9][1].setText(str(failures));self.metrics[9][0].setToolTip('Failed ICMP samples in the last hour, selected network; not confirmed physical faults')
        self.metrics[10][1].setText(str(sum(state=='No reply' for state in states.values())));self.metrics[11][1].setText(str(health.count('Offline')));self.metrics[11][0].setToolTip('Verified external Internet endpoint failures; an unreachable modem alone is not proof of an Internet outage')
        self.setup.setVisible(not devices)
        scope='All active networks are monitored; this overview shows the selected network.' if w.monitor_all_enabled else 'Monitoring scope: selected network.'
        self.scope.setText(w.current_page().name+' • '+('Monitoring running' if w.engine.running else 'Periodic monitoring stopped')+' • '+str(len(w.page_stations()))+' towers\n'+scope)
        modems=[d for d in devices if d.wan or d.kind.startswith('WAN')];pages=max(1,(len(modems)+6)//7);self.wan_page=min(self.wan_page,pages-1);shown=modems[self.wan_page*7:(self.wan_page+1)*7]
        self.no_wans.setVisible(not modems);self.wan_count.setText(f'{len(modems)} connections • page {self.wan_page+1}/{pages}');self.previous.setVisible(pages>1);self.next.setVisible(pages>1);self.previous.setEnabled(self.wan_page>0);self.next.setEnabled(self.wan_page<pages-1)
        for i,card in enumerate(self.wan_cards):
            card.setVisible(i<len(shown))
            if i<len(shown):
                d=shown[i];card.update_view(d,wan_view(d,states[d.id],w.measurements.latest.get(d.id,{}),w.measurements.speed_latest.get(d.id,{}),now))
        n=w.store.db.execute('SELECT COUNT(*) FROM incidents WHERE page_id=? AND resolved IS NULL',(w.page_id,)).fetchone()[0]
        rows=[r for r in w.store.incident_rows(w.page_id,limit=3) if r['resolved'] is None]
        self.incident_count.setText(str(n)+' unresolved')
        lines=[]
        for r in rows:
            d=r['detail'];lines.append(r['status']+' • '+d.get('name','Removed device')+' • '+d['title']+'\nConfidence: '+d['confidence']+' | '+('Acknowledged' if r['acknowledged'] else 'New')+' | '+d['next_step'])
        self.incident_text.setText('\n\n'.join(lines) if lines else 'No unresolved incidents recorded for this network. Missing or stale observations do not prove recovery.')
        selected=self.table.item(self.table.currentRow(),0);selected_id=selected.data(Qt.UserRole) if selected else None
        ranked=sorted(devices,key=lambda d:(states[d.id] not in ('Warning','No reply','Probe error'),states[d.id] not in ('Unknown','Unconfigured'),d.name.casefold()))[:8]
        self.table.setRowCount(len(ranked))
        for i,d in enumerate(ranked):
            last=w.latest.get(d.id,{});age=now-last.get('at',0);stamp=f'{max(0,int(age))}s ago' if last.get('at') else 'Not checked'
            for j,value in enumerate([d.name,d.host or 'IP not configured',states[d.id],stamp]):
                item=QTableWidgetItem(value)
                if j==0:item.setData(Qt.UserRole,d.id)
                self.table.setItem(i,j,item)
            if selected_id==d.id:self.table.selectRow(i)
