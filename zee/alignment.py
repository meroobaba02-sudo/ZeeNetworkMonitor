"""Measured dish alignment sessions; directions require operator-tagged sweep evidence."""
import time,statistics,sqlite3,os,threading
from PySide6.QtCore import QTimer,QRunnable,QThreadPool
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QProgressBar,QCheckBox,QDoubleSpinBox,QFormLayout,QApplication,QMessageBox,QScrollArea
from .noc_widgets import text,action,Trend,current,number
from .telemetry import clean_metrics,quality

class AlignmentSession:
    def __init__(self):self.reset()
    def reset(self):self.samples=[];self.steps=[{'id':0,'direction':'Baseline','amount':None,'unit':None,'at':None,'before_dbm':None}];self.peak=None;self.last_at=None;self.direction='Baseline';self.state='Ready';self.started=None;self.finished=None;self.min_at=None
    def begin_step(self,direction,amount=None,unit=None,at=None):
        if direction not in ('Baseline','LEFT','RIGHT','UP','DOWN'):raise ValueError('Unsupported adjustment direction.')
        before=[r['signal_dbm'] for r in self.samples if r.get('step_id',0)==self.steps[-1]['id']][-5:]
        self.direction=direction;self.steps.append({'id':self.steps[-1]['id']+1,'direction':direction,'amount':amount,'unit':unit,'at':at if number(at) else self.last_at,'before_dbm':statistics.median(before) if len(before)>=3 and max(before)-min(before)<=2 else None});self.steps=self.steps[-100:]
    def capture(self,at,signal,metrics=None):
        if self.state!='Running' or not number(at) or (self.last_at is not None and at<=self.last_at) or not number(signal) or not -130<=signal<=0:return False
        if self.direction!=self.steps[-1]['direction']:self.begin_step(self.direction)
        if self.started is not None and at<self.started:return False
        if self.min_at is not None and at<self.min_at:return False
        if self.steps[-1]['at'] is not None and at<=self.steps[-1]['at']:return False
        self.last_at=at;self.samples.append({'at':at,'signal_dbm':signal,'adjustment':self.direction,'step_id':self.steps[-1]['id'],'metrics':clean_metrics(metrics or {})});self.samples=self.samples[-600:];self.peak=signal if self.peak is None else max(self.peak,signal);return True
    def comparisons(self):
        rows=[]
        for step in self.steps:
            values=[r['signal_dbm'] for r in self.samples if r.get('step_id',0)==step['id']]
            stable=len(values)>=3 and max(values)-min(values)<=2
            median=statistics.median(values) if values else None;before=step['before_dbm'];rows.append(step|{'count':len(values),'median_dbm':median,'stable':stable,'spread_db':max(values)-min(values) if values else None,'change_db':median-before if stable and before is not None else None})
        return rows
    def best_stable(self):
        candidates=[r for r in self.comparisons() if r['stable']]
        return max(candidates,key=lambda r:r['median_dbm']) if candidates else None
    def guidance(self):
        best=self.best_stable()
        if not best:return 'Direction unavailable · record a baseline and at least 3 fresh samples after a measured adjustment. Signal strength alone cannot identify left/right/up/down.'
        stable=f"Best stable measured position: step {best['id']} ({best['direction']}, {best['median_dbm']:.1f} dBm). Retain/return to that recorded position if other quality indicators also remain acceptable."
        base=next((r for r in self.comparisons() if r['direction']=='Baseline' and r['stable']),None)
        if not base or best['direction']=='Baseline' or best['median_dbm']-base['median_dbm']<1:return 'Direction unavailable · measured sweep has no clear improvement over a stable baseline. '+stable
        return f"Measured sweep: {best['direction']} step {best['id']} recorded the strongest stable improvement (+{best['median_dbm']-base['median_dbm']:.1f} dB over baseline). "+stable+' This is a measured position comparison, not an angle sensor or proof of perfect alignment.'
    def stability(self):
        values=[r['signal_dbm'] for r in self.samples[-10:]]
        if len(values)<3:return 'Unavailable · need 3 measured samples'
        spread=max(values)-min(values);return f'{"Stable" if spread<=2 else "Variable"} · last {len(values)} samples span {spread:.1f} dB'

class ToneTask(QRunnable):
    def __init__(self,pitch,cancel):super().__init__();self.pitch=pitch;self.cancel=cancel
    def run(self):
        if self.cancel.is_set():return
        try:
            import winsound
            winsound.Beep(self.pitch,90)
        except (RuntimeError,OSError,ImportError):pass

class AlignmentAudio:
    def __init__(self,parent):self.pool=QThreadPool(parent);self.pool.setMaxThreadCount(1);self.cancel=threading.Event();self.last=0
    def improvement(self,signal):
        if time.monotonic()-self.last<5 or self.pool.activeThreadCount():return
        self.last=time.monotonic();self.cancel.clear()
        if os.name=='nt':self.pool.start(ToneTask(round(400+max(0,min(70,signal+100))*18),self.cancel))
        else:QApplication.beep()
    def stop(self):self.cancel.set();self.pool.clear()
    def shutdown(self):self.stop();self.pool.waitForDone(500)

class AlignmentPanel(QScrollArea):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.session=AlignmentSession();self.device_id=None;self.next_poll=0;self.feedback=AlignmentAudio(self)
        self.setWidgetResizable(True);body=QWidget();self.setWidget(body)
        layout=QVBoxLayout(body);layout.addWidget(text('Dish Alignment','title'));layout.addWidget(text('Read-only assistant · the technician moves the dish. Start collects supported live signal measurements; it never changes device configuration.','muted'))
        layout.addWidget(text('Rooftop safety: use trained personnel, fall protection and safe access. Stay clear of power lines; isolate electrical/PoE equipment before handling cables. Never adjust during unsafe weather.','alignmentGuidance'))
        row=QHBoxLayout();layout.addLayout(row);self.picker=QComboBox();self.picker.currentIndexChanged.connect(self.select);row.addWidget(self.picker,2);row.addWidget(action('Configure telemetry',self.configure));row.addWidget(action('Test telemetry',self.test_telemetry));row.addWidget(action('Open device',self.open))
        self.signal=text('Unavailable','signalValue');layout.addWidget(self.signal);self.meter=QProgressBar();self.meter.setRange(-130,0);self.meter.setFormat('Signal strength · no fresh measurement');self.meter.setValue(-130);layout.addWidget(self.meter)
        self.live_metrics=text('Noise / chains / CCQ / rates unavailable');layout.addWidget(self.live_metrics);self.compatibility=text('Configure a firmware-verified read-only telemetry profile; use Open device for the airOS tool.','muted');layout.addWidget(self.compatibility);self.summary=text('Ready · no session samples');layout.addWidget(self.summary);self.graph=Trend('Measured signal trend','dBm');layout.addWidget(self.graph,1);self.guidance=text(self.session.guidance(),'alignmentGuidance');layout.addWidget(self.guidance)
        adjustments=QHBoxLayout();layout.addLayout(adjustments)
        for direction in ('Baseline','LEFT','RIGHT','UP','DOWN'):adjustments.addWidget(action('Record '+direction,lambda checked=False,d=direction:self.tag(d)))
        step_row=QHBoxLayout();layout.addLayout(step_row);step_row.addWidget(text('Manual step amount (optional reference)'));self.step_amount=QDoubleSpinBox();self.step_amount.setRange(0,30);self.step_amount.setSingleStep(.25);self.step_amount.setSpecialValueText('Not recorded');step_row.addWidget(self.step_amount);self.step_unit=QComboBox();self.step_unit.addItems(['operator units','degrees (measured manually)','turns','mm']);step_row.addWidget(self.step_unit);self.step_evidence=text('No stable step comparison yet','muted');layout.addWidget(self.step_evidence)
        self.audio=QCheckBox('Audio on measured improvement · higher pitch for stronger signal');self.audio.toggled.connect(lambda enabled:self.feedback.stop() if not enabled else None);layout.addWidget(self.audio)
        form=QFormLayout();layout.addLayout(form);self.bearing=QDoubleSpinBox();self.bearing.setRange(-1,359.9);self.bearing.setSpecialValueText('Not provided');self.bearing.setValue(-1);self.bearing.setSuffix('°');form.addRow('Target bearing (operator reference)',self.bearing);self.elevation=QDoubleSpinBox();self.elevation.setRange(-91,90);self.elevation.setSpecialValueText('Not provided');self.elevation.setValue(-91);self.elevation.setSuffix('°');form.addRow('Target elevation (operator reference)',self.elevation)
        controls=QHBoxLayout();layout.addLayout(controls)
        for title,fn in [('Start Alignment',self.start),('Pause',self.pause),('Reset Peak',self.reset_peak),('Finish Alignment',self.finish),('Save Results',self.save)]:controls.addWidget(action(title,fn))
        layout.removeItem(controls);layout.insertLayout(4,controls)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(1000);self.refresh_devices()
    def device(self):return next((d for d in self.w.devices if d.id==self.device_id),None)
    def refresh_devices(self):
        devices=[d for d in self.w.devices if d.kind.startswith('Rocket') or d.role or d.peer_id or 'signal_dbm' in d.integration.get('oids',{}) or 'signal_dbm' in d.integration.get('fields',{})];ids=[self.picker.itemData(i) for i in range(self.picker.count())]
        if ids==[d.id for d in devices]:return
        previous=self.device_id;self.picker.blockSignals(True);self.picker.clear()
        for d in devices:self.picker.addItem(d.name,d.id)
        self.picker.setCurrentIndex(max(0,self.picker.findData(previous)));self.picker.blockSignals(False)
        new=self.picker.currentData()
        if new!=previous:self.select()
    def select(self,*_):
        new=self.picker.currentData()
        if new!=self.device_id:self.feedback.stop();self.device_id=new;self.session.reset();self.next_poll=0
        self.render()
    def start(self):
        d=self.device()
        if not d or not d.enabled or not d.host or not self.w.permit_device(d):self.summary.setText('Select an enabled radio with a configured IP and monitoring permission.');return
        if self.session.state in ('Ready','Finished'):self.session.reset();self.session.started=time.time()
        self.session.min_at=time.time();self.session.state='Running';self.next_poll=0;self.tick()
    def pause(self):
        if self.session.state=='Running':self.session.state='Paused'
        self.feedback.stop();self.render()
    def reset_peak(self):self.session.peak=None;self.render()
    def finish(self):
        if self.session.state in ('Running','Paused'):self.session.state='Finished';self.session.finished=time.time()
        self.feedback.stop();self.render()
    def tag(self,direction):
        if self.session.state!='Running':self.summary.setText('Start the session before tagging a manual adjustment.');return
        self.session.begin_step(direction,self.step_amount.value() or None,self.step_unit.currentText(),time.time());self.render()
    def test_telemetry(self):
        d=self.device()
        if not d or not d.integration.get('firmware_verified') or d.integration.get('method','none')=='none':self.summary.setText('Configure a mapping verified against the actual model/firmware first; Open device remains available.');return
        self.summary.setText('Read-only telemetry test requested; fresh metrics appear when the device responds.' if self.w.measurements.submit(d) else 'Telemetry test not started: check enabled/IP, permissions, route or running measurements.')
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
                previous=self.session.peak;added=self.session.capture(row.get('at'),row.get('metrics',{}).get('signal_dbm'),row.get('metrics',{}))
                if added and self.audio.isChecked() and previous is not None and self.session.peak>previous:self.feedback.improvement(self.session.peak)
            if time.monotonic()>=self.next_poll:
                if self.w.measurements.submit(d):self.next_poll=time.monotonic()+max(5,d.integration.get('poll_seconds',30))
        if self.isVisible():self.render()
    def render(self):
        d=self.device();row=self.w.measurements.latest.get(d.id,{}) if d else {};value=clean_metrics(row.get('metrics',{})).get('signal_dbm') if d and current(row,d) else None
        self.signal.setText(f'{value:.1f} dBm' if number(value) else 'Signal unavailable');self.meter.setValue(round(value) if number(value) else -130);self.meter.setFormat(f'{value:.1f} dBm · fresh telemetry' if number(value) else 'No fresh supported signal measurement')
        metrics=clean_metrics(row.get('metrics',{})) if d and current(row,d) else {}
        def show(key,unit=''):return f'{metrics[key]:.1f} {unit}' if key in metrics else 'Unavailable'
        imbalance=abs(metrics['signal_chain0_dbm']-metrics['signal_chain1_dbm']) if all(k in metrics for k in ('signal_chain0_dbm','signal_chain1_dbm')) else None
        label=quality(metrics,d.integration,0)[1] if d and metrics else 'Unknown'
        self.live_metrics.setText('Noise '+show('noise_dbm','dBm')+' · SNR '+show('snr_db','dB')+'\nChain 0 '+show('signal_chain0_dbm','dBm')+' · Chain 1 '+show('signal_chain1_dbm','dBm')+' · Imbalance '+(f'{imbalance:.1f} dB' if imbalance is not None else 'Unavailable')+'\nTX/RX CCQ '+show('tx_ccq','%')+' / '+show('rx_ccq','%')+' · TX/RX rate '+show('tx_mbps','Mbps')+' / '+show('rx_mbps','Mbps')+'\nMeasured link quality '+label+' · RSSI alone does not prove perfect alignment.\nVerified GPS '+show('gps_latitude','°')+', '+show('gps_longitude','°')+' · Compass '+show('heading_deg','°')+' · Elevation '+show('elevation_deg','°'))
        p=d.integration if d else {};self.compatibility.setText(('Model '+(p.get('device_model') or 'not recorded')+' · firmware '+(p.get('firmware_version') or 'not recorded')+' · '+p.get('method','none')+' · poll '+str(max(5,p.get('poll_seconds',30)))+' s\n')+('Operator-verified mapping; compatibility still needs an actual device test.' if p.get('firmware_verified') else 'Telemetry compatibility not verified. Configure model/firmware and verified mappings, or use Open device → Tools → Align Antenna.')+(('\nLast check: '+str(row.get('telemetry_error',''))) if row.get('telemetry_error') else ''))
        comparison=self.session.comparisons()[-1];delta=comparison['change_db'];best=self.session.best_stable();self.step_evidence.setText(f"Current step {comparison['id']}: {comparison['direction']} · {comparison['amount'] or 'unspecified'} {comparison['unit'] or ''} · {comparison['count']} samples · "+(f"before {comparison['before_dbm']:.1f} → after {comparison['median_dbm']:.1f} dBm ({delta:+.1f} dB)" if delta is not None else 'Need stable before/after measurements')+('\nBest stable: step '+str(best['id'])+' · '+f"{best['median_dbm']:.1f} dBm" if best else ''))
        peak=f'{self.session.peak:.1f} dBm'  if self.session.peak is not None else 'Unavailable';self.summary.setText(f'{self.session.state} · {len(self.session.samples)} session samples · Peak {peak}\n'+self.session.stability());self.guidance.setText(self.session.guidance());self.graph.set_series([('RSSI',[(r['at'],r['signal_dbm']) for r in self.session.samples],'#22b8a8')])
    def save(self):
        d=self.device()
        if not d or self.session.state!='Finished' or not self.session.samples:self.summary.setText('Finish a session with measured samples before saving.');return
        payload={'format':'zee-alignment-1','device_id':d.id,'started':self.session.started,'finished':self.session.finished,'peak_dbm':self.session.peak,'samples':self.session.samples,'stability':self.session.stability(),'guidance':self.session.guidance(),'steps':self.session.comparisons(),'best_stable':self.session.best_stable(),'target_bearing':self.bearing.value() if self.bearing.value()>=0 else None,'target_elevation':self.elevation.value() if self.elevation.value()>-91 else None}
        try:self.w.store.set_setting('alignment:'+d.id,payload);self.w.store.event(d.id,'alignment','Measured alignment session saved');self.summary.setText('Results saved to the existing database · included in database backups.')
        except (OSError,sqlite3.Error,ValueError):QMessageBox.warning(self,'Save failed','Could not save alignment results. Keep the session open and check disk access.')
    def shutdown(self):self.session.state='Paused';self.timer.stop();self.feedback.shutdown()
