"""Rocket cards and bounded history, backed by existing firmware-verified telemetry."""
import time
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QScrollArea,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QComboBox,QLabel,QFrame
from .noc_widgets import action,text,Trend,current,number
from .telemetry import quality
from .customer_theme import status_color

class RadioPanel(QScrollArea):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWidgetResizable(True);self.ids=[];self.cards={};self.history_key=None;body=QWidget();self.setWidget(body);layout=QVBoxLayout(body);layout.addWidget(text('Rocket M5 Monitor','title'));layout.addWidget(text('Firmware-verified measurements · unsupported or stale readings stay unavailable. Radio rates describe the wireless link, not Internet speed.','muted'));self.grid=QGridLayout();layout.addLayout(self.grid);self.picker=QComboBox();self.picker.currentIndexChanged.connect(self.history);layout.addWidget(self.picker);self.detail=text('Select a configured radio');layout.addWidget(self.detail);self.graph=Trend('Signal history · latest 240 samples','dBm');layout.addWidget(self.graph);row=QHBoxLayout();layout.addLayout(row)
        for label,fn in [('Device details',self.details),('Configure adapter',self.configure),('Open web interface',self.open),('Connection test',self.poll),('Dish Alignment',self.align)]:row.addWidget(action(label,fn))
        layout.addStretch();self.timer=QTimer(self);self.timer.timeout.connect(lambda:self.refresh() if self.isVisible() else None);self.timer.start(2000)
    def radios(self):return [d for d in self.w.devices if d.kind.startswith('Rocket') or d.role or d.peer_id]
    def device(self):return next((d for d in self.radios() if d.id==self.picker.currentData()),None)
    def refresh(self):
        ds=self.radios();ids=[d.id for d in ds]
        if ids!=self.ids:
            self.ids=ids;selected=self.picker.currentData();self.picker.blockSignals(True);self.picker.clear()
            for frame,_ in self.cards.values():self.grid.removeWidget(frame);frame.deleteLater()
            self.cards={}
            for i,d in enumerate(ds):
                self.picker.addItem(d.name,d.id);frame=QFrame();frame.setObjectName('metricCard');box=QVBoxLayout(frame);label=text();box.addWidget(label);box.addWidget(action('Open details',lambda checked=False,device_id=d.id:self.show(device_id)));self.cards[d.id]=(frame,label);self.grid.addWidget(frame,i//2,i%2)
            self.picker.setCurrentIndex(max(0,self.picker.findData(selected)));self.picker.blockSignals(False)
        for i,d in enumerate(ds):
            self.picker.setItemText(i,d.name);r=self.w.measurements.latest.get(d.id,{});m=r.get('metrics',{}) if current(r,d) else {};_,health=quality(m,d.integration,time.time()-r.get('at',0));values=[]
            for key,name,unit in [('signal_dbm','RSSI','dBm'),('noise_dbm','Noise','dBm'),('tx_ccq','TX CCQ','%'),('tx_mbps','TX','Mbps'),('rx_mbps','RX','Mbps')]:values.append(name+': '+(f'{m[key]:.1f} {unit}' if number(m.get(key)) else 'Unavailable'))
            self.cards[d.id][1].setText(d.name+' · '+d.host+'\nPing '+self.w.state(d)+' · Link quality '+health+'\n'+'   |   '.join(values));self.cards[d.id][0].setToolTip('Last telemetry: '+(time.strftime('%H:%M:%S',time.localtime(r['at'])) if r else 'Not measured'))
        self.history()
    def history(self,*_):
        d=self.device()
        if not d:self.detail.setText('No configured radio. Add a Rocket device in Device Manager.');self.graph.set_series([]);return
        r=self.w.measurements.latest.get(d.id,{});m=r.get('metrics',{}) if current(r,d) else {};keys=[('signal_chain0_dbm','Chain 0 RSSI','dBm'),('signal_chain1_dbm','Chain 1 RSSI','dBm'),('rx_ccq','RX CCQ','%'),('snr_db','SNR','dB')];self.detail.setText(d.name+'\n'+' · '.join(name+': '+(f'{m[k]:.1f} {unit}' if number(m.get(k)) else 'Unavailable / unsupported') for k,name,unit in keys))
        key=(d.id,r.get('at'),int(time.time()/10))
        if key!=self.history_key:
            self.history_key=key;rows=self.w.store.measurements(d.id,time.time()-86400,240);self.graph.set_series([('RSSI',[(r['at'],r.get('metrics',{}).get('signal_dbm')) for r in rows],'#22b8a8')])
    def show(self,id):
        d=next((d for d in self.radios() if d.id==id),None)
        if d:self.picker.setCurrentIndex(self.picker.findData(id));self.w.show_details(d)
    def details(self):
        d=self.device()
        if d:self.w.show_details(d)
    def configure(self):
        d=self.device()
        if d:
            from .professional import IntegrationDialog
            IntegrationDialog(self.w,d).exec()
    def open(self):
        d=self.device()
        if d:self.w.open_management(d)
    def poll(self):
        d=self.device()
        if d:self.w.requested.add(d.id);self.w.drain();self.w.measurements.submit(d)
    def align(self):
        d=self.device();self.w.tabs.setCurrentIndex(10);self.w.alignment.refresh_devices()
        if d:self.w.alignment.picker.setCurrentIndex(self.w.alignment.picker.findData(d.id))
    def shutdown(self):self.timer.stop()
