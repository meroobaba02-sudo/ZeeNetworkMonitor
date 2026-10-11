"""Seven Internet cards: independent controls and measured history, no sample values."""
import time
from PySide6.QtWidgets import QScrollArea,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFrame,QLabel
from .noc_widgets import text,action,Trend
from .customer_view import wan_view
from .customer_theme import status_color

class ConnectionCard(QFrame):
    def __init__(self,panel,index):
        super().__init__();self.panel=panel;self.id=None;self.index=index;self.history_key=None;self.setObjectName('wanCard');layout=QVBoxLayout(self);self.name=text('', 'sectionTitle');layout.addWidget(self.name);self.status=text();layout.addWidget(self.status);self.rates=text('', 'connectionRates');layout.addWidget(self.rates);self.traffic=text('', 'muted');layout.addWidget(self.traffic);self.ping=text('', 'muted');layout.addWidget(self.ping);self.graph=Trend('Test ↓ / ↑ · last 24 h','Mbps');layout.addWidget(self.graph);self.message=text('', 'muted');layout.addWidget(self.message);tools=QGridLayout();layout.addLayout(tools);self.start=action('Start Test',self.test);self.stop=action('Stop Test',lambda:self.panel.stop_device(self.id));self.again=action('Test Again',self.test);self.setup=action('Setup / Details',self.configure)
        for i,b in enumerate((self.start,self.stop,self.again,self.setup)):tools.addWidget(b,i//2,i%2)
        layout.removeItem(tools);layout.insertLayout(2,tools);self.graph.setFixedHeight(120)
        self.update_view(None)
    def test(self):
        if self.id:self.panel.start_device(self.id)
    def configure(self):
        d=next((d for d in self.panel.modems() if d.id==self.id),None)
        if d:
            from .wan_dialog import WanDialog
            WanDialog(self.panel.w,d).exec()
        else:self.panel.add()
    def update_view(self,d):
        w=self.panel.w;self.id=d.id if d else None
        if not d:
            self.name.setText(f'Connection {self.index+1}');self.status.setText('Not configured');self.rates.setText('Download —   Upload —');self.traffic.setText('Add your actual modem to this network.');self.ping.setText('No ping measurements');self.graph.set_series([]);self.message.setText('No live or example data');self.start.setEnabled(False);self.stop.setEnabled(False);self.again.setEnabled(False);return
        now=time.time();row=w.measurements.latest.get(d.id,{});speed=w.measurements.speed_latest.get(d.id,{});view=wan_view(d,w.state(d),row,speed,now);self.name.setText(d.name+'\n'+d.host);self.status.setText('Router '+view['router']+' · Internet '+view['internet']);self.status.setStyleSheet('color:'+status_color(view['router'],w.ui_theme));self.rates.setText('MEASURED TEST (Mbps)\n↓ '+view['test_download']+'    ↑ '+view['test_upload']);self.traffic.setText('INTERFACE TRAFFIC (Mbps)\n↓ '+view['download']+'    ↑ '+view['upload'])
        if d.id not in w._stats_cache:w._stats_cache[d.id]=w.store.stats(d.id)
        stats=w._stats_cache[d.id]
        ping=w.latest.get(d.id,{});lat=ping.get('latency') if w.state(d) in ('Online','Warning') else None;loss=f"{stats['loss']:.1f}%" if stats.get('loss') is not None else 'Unavailable';last=time.strftime('%H:%M:%S',time.localtime(stats['last_ok'])) if stats.get('last_ok') else 'Not recorded';self.ping.setText('Latency '+(f'{lat:.1f} ms' if lat is not None else 'Unavailable')+' · ICMP loss '+loss+'\nLast reply '+last+' · test '+view['test_age'])
        queued=any(x.id==d.id for x in self.panel.queue);active=self.panel.active is not None and self.panel.active.id==d.id;pending=(d.id,True) in w.measurements.pending;self.start.setEnabled(not queued and not active and not pending);self.again.setEnabled(not queued and not active and not pending);self.stop.setEnabled(queued or active or pending);self.message.setText(self.panel.messages.get(d.id,view['test_note']));self.message.setToolTip(view['test_note'])
        key=(d.id,speed.get('at'),int(now/10))
        if key!=self.history_key:
            self.history_key=key;history=w.store.measurements(d.id,now-86400,240);tests=[r for r in history if r.get('path_checked') and not r.get('error')];self.graph.set_series([('↓ test',[(r['at'],r.get('download_mbps')) for r in tests],'#22b8a8'),('↑ test',[(r['at'],r.get('upload_mbps')) for r in tests],'#5e8ff5')])

class InternetCards(QScrollArea):
    def __init__(self,panel):
        super().__init__();self.panel=panel;self.setWidgetResizable(True);body=QWidget();self.setWidget(body);layout=QVBoxLayout(body);self.page=0;tools=QHBoxLayout();layout.addLayout(tools);self.note=text();tools.addWidget(self.note,1);tools.addWidget(action('Previous',lambda:self.move(-1)));tools.addWidget(action('Next',lambda:self.move(1)));self.grid=QGridLayout();self.cards=[ConnectionCard(panel,i) for i in range(7)];self.columns=None;layout.addLayout(self.grid);layout.addStretch();self.reflow(2)
    def reflow(self,cols):
        if cols==self.columns:return
        self.columns=cols
        for i,card in enumerate(self.cards):self.grid.addWidget(card,i//cols,i%cols)
    def resizeEvent(self,event):super().resizeEvent(event);self.reflow(3 if self.viewport().width()>1050 else 2 if self.viewport().width()>570 else 1)
    def move(self,delta):self.page=max(0,self.page+delta);self.refresh()
    def refresh(self):
        devices=self.panel.modems();pages=max(1,(len(devices)+6)//7);self.page=min(self.page,pages-1);shown=devices[self.page*7:(self.page+1)*7];self.note.setText(f'{len(devices)} configured connections · page {self.page+1}/{pages} · tests queued sequentially to avoid bandwidth competition')
        for i,card in enumerate(self.cards):card.update_view(shown[i] if i<len(shown) else None)
