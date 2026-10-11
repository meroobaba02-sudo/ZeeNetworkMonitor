"""Measured dish alignment sessions; directions require operator-tagged sweep evidence."""
import time,statistics,sqlite3
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QProgressBar,QCheckBox,QDoubleSpinBox,QFormLayout,QApplication,QMessageBox,QScrollArea
from .noc_widgets import text,action,Trend,current,number

class AlignmentSession:
    def __init__(self):self.reset()
    def reset(self):self.samples=[];self.peak=None;self.last_at=None;self.direction='Baseline';self.state='Ready';self.started=None;self.finished=None
    def capture(self,at,signal):
        if self.state!='Running' or at==self.last_at or not number(signal) or not -130<=signal<=0:return False
        self.last_at=at;self.samples.append({'at':at,'signal_dbm':signal,'adjustment':self.direction});self.samples=self.samples[-600:];self.peak=signal if self.peak is None else max(self.peak,signal);return True
    def guidance(self):
        groups={direction:[r['signal_dbm'] for r in self.samples if r['adjustment']==direction] for direction in ('Baseline','LEFT','RIGHT','UP','DOWN')};base=groups['Baseline']
        candidates=[(statistics.median(values),direction) for direction,values in groups.items() if direction!='Baseline' and len(values)>=3 and max(values)-min(values)<=3]
        if len(base)<3 or not candidates:return 'Direction unavailable · record a baseline and at least 3 fresh samples after a measured adjustment. Signal strength alone cannot identify left/right/up/down.'
        score,direction=max(candidates)
        if score-statistics.median(base)<1:return 'Measured sweep has no clear improvement over baseline. Recheck alignment manually.'
        return f'Measured sweep: {direction} recorded the strongest stable improvement (+{score-statistics.median(base):.1f} dB over baseline). Verify manually; this is not an angle sensor.'
    def stability(self):
        values=[r['signal_dbm'] for r in self.samples[-10:]]
        if len(values)<3:return 'Unavailable · need 3 measured samples'
        spread=max(values)-min(values);return f'{"Stable" if spread<=2 else "Variable"} · last {len(values)} samples span {spread:.1f} dB'

class AlignmentPanel(QScrollArea):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.session=AlignmentSession();self.device_id=None;self.next_poll=0
        self.setWidgetResizable(True);body=QWidget();self.setWidget(body)
        layout=QVBoxLayout(body);layout.addWidget(text('Dish Alignment','title'));layout.addWidget(text('Read-only assistant · the technician moves the dish. Start collects supported live signal measurements; it never changes device configuration.','muted'))
        row=QHBoxLayout();layout.addLayout(row);self.picker=QComboBox();self.picker.currentIndexChanged.connect(self.select);row.addWidget(self.picker,2);row.addWidget(action('Configure telemetry',self.configure));row.addWidget(action('Open device',self.open))
        self.signal=text('Unavailable','signalValue');layout.addWidget(self.signal);self.meter=QProgressBar();self.meter.setRange(-100,-30);self.meter.setFormat('Signal strength · no fresh measurement');self.meter.setValue(-100);layout.addWidget(self.meter)
        self.summary=text('Ready · no session samples');layout.addWidget(self.summary);self.graph=Trend('Measured signal trend','dBm');layout.addWidget(self.graph,1);self.guidance=text(self.session.guidance(),'alignmentGuidance');layout.addWidget(self.guidance)
        adjustments=QHBoxLayout();layout.addLayout(adjustments)
        for direction in ('Baseline','LEFT','RIGHT','UP','DOWN'):adjustments.addWidget(action('Record '+direction,lambda checked=False,d=direction:self.tag(d)))
        self.audio=QCheckBox('Audio feedback when a fresh measured signal improves');layout.addWidget(self.audio)
        form=QFormLayout();layout.addLayout(form);self.bearing=QDoubleSpinBox();self.bearing.setRange(-1,359.9);self.bearing.setSpecialValueText('Not provided');self.bearing.setValue(-1);self.bearing.setSuffix('°');form.addRow('Target bearing (operator reference)',self.bearing);self.elevation=QDoubleSpinBox();self.elevation.setRange(-91,90);self.elevation.setSpecialValueText('Not provided');self.elevation.setValue(-91);self.elevation.setSuffix('°');form.addRow('Target elevation (operator reference)',self.elevation)
        controls=QHBoxLayout();layout.addLayout(controls)
        for title,fn in [('Start',self.start),('Pause',self.pause),('Reset Peak',self.reset_peak),('Finish',self.finish),('Save Results',self.save)]:controls.addWidget(action(title,fn))
        layout.removeItem(controls);layout.insertLayout(3,controls)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(1000);self.refresh_devices()
    def device(self):return next((d for d in self.w.devices if d.id==self.device_id),None)
    def refresh_devices(self):
        devices=[d for d in self.w.devices if d.kind.startswith('Rocket') or d.role or d.peer_id];ids=[self.picker.itemData(i) for i in range(self.picker.count())]
        if ids==[d.id for d in devices]:return
        previous=self.device_id;self.picker.blockSignals(True);self.picker.clear()
        for d in devices:self.picker.addItem(d.name,d.id)
        self.picker.setCurrentIndex(max(0,self.picker.findData(previous)));self.picker.blockSignals(False)
        new=self.picker.currentData()
        if new!=previous:self.select()
    def select(self,*_):
        new=self.picker.currentData()
        if new!=self.device_id:self.device_id=new;self.session.reset();self.next_poll=0
        self.render()
    def start(self):
        d=self.device()
        if not d or not d.enabled or not d.host or not self.w.permit_device(d):self.summary.setText('Select an enabled radio with a configured IP and monitoring permission.');return
        if self.session.state in ('Ready','Finished'):self.session.reset();self.session.started=time.time()
        self.session.state='Running';self.next_poll=0;self.tick()
    def pause(self):
        if self.session.state=='Running':self.session.state='Paused'
        self.render()
    def reset_peak(self):self.session.peak=None;self.render()
    def finish(self):
        if self.session.state in ('Running','Paused'):self.session.state='Finished';self.session.finished=time.time()
        self.render()
    def tag(self,direction):
        if self.session.state!='Running':self.summary.setText('Start the session before tagging a manual adjustment.');return
        self.session.direction=direction;self.render()
    def configure(self):
        d=self.device()
        if d:
            from .professional import IntegrationDialog
            IntegrationDialog(self.w,d).exec()
    def open(self):
        d=self.device()
        if d:self.w.open_management(d)
    def tick(self):
        self.refresh_devices();d=self.device()
        if d and self.session.state=='Running':
            row=self.w.measurements.latest.get(d.id,{})
            if current(row,d):
                previous=self.session.peak;added=self.session.capture(row.get('at'),row.get('metrics',{}).get('signal_dbm'))
                if added and self.audio.isChecked() and previous is not None and self.session.peak>previous:QApplication.beep()
            if time.monotonic()>=self.next_poll:
                if self.w.measurements.submit(d):self.next_poll=time.monotonic()+max(5,d.integration.get('poll_seconds',30))
        if self.isVisible():self.render()
    def render(self):
        d=self.device();row=self.w.measurements.latest.get(d.id,{}) if d else {};value=row.get('metrics',{}).get('signal_dbm') if d and current(row,d) else None
        self.signal.setText(f'{value:.1f} dBm' if number(value) else 'Signal unavailable');self.meter.setValue(round(value) if number(value) else -100);self.meter.setFormat(f'{value:.1f} dBm · fresh telemetry' if number(value) else 'No fresh supported signal measurement')
        peak=f'{self.session.peak:.1f} dBm' if self.session.peak is not None else 'Unavailable';self.summary.setText(f'{self.session.state} · {len(self.session.samples)} session samples · Peak {peak}\n'+self.session.stability());self.guidance.setText(self.session.guidance());self.graph.set_series([('RSSI',[(r['at'],r['signal_dbm']) for r in self.session.samples],'#22b8a8')])
    def save(self):
        d=self.device()
        if not d or self.session.state!='Finished' or not self.session.samples:self.summary.setText('Finish a session with measured samples before saving.');return
        payload={'format':'zee-alignment-1','device_id':d.id,'started':self.session.started,'finished':self.session.finished,'peak_dbm':self.session.peak,'samples':self.session.samples,'stability':self.session.stability(),'guidance':self.session.guidance(),'target_bearing':self.bearing.value() if self.bearing.value()>=0 else None,'target_elevation':self.elevation.value() if self.elevation.value()>-91 else None}
        try:self.w.store.set_setting('alignment:'+d.id,payload);self.w.store.event(d.id,'alignment','Measured alignment session saved');self.summary.setText('Results saved to the existing database · included in database backups.')
        except (OSError,sqlite3.Error,ValueError):QMessageBox.warning(self,'Save failed','Could not save alignment results. Keep the session open and check disk access.')
    def shutdown(self):self.session.state='Paused';self.timer.stop()
