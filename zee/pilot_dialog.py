"""Simple field-pilot checklist and opt-in bounded performance recording."""
import logging,time
from PySide6.QtCore import QObject,QTimer,Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QComboBox,QPlainTextEdit,QDoubleSpinBox,QSpinBox,QFileDialog,QMessageBox,QCheckBox,QScrollArea,QWidget
from .pilot import PilotSession,SCENARIOS,STATUSES,Usage,byte_size,snapshot,atomic_json,SAMPLE_LIMIT

class PilotCapture(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.session=PilotSession(window.store.path.parent);self.running=False
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.previous_tick=0;self.sample_at=0
    def start(self):
        if self.running:return
        if not self.window.engine.running:raise ValueError('Start normal monitoring first, then start pilot capture.')
        if self.session.document['version']!=__import__('zee.core',fromlist=['VERSION']).VERSION:raise ValueError('Start a new pilot session for this app version.')
        if self.session.document['capture']['state']!='Not recorded':raise ValueError('Start a new session to record another continuous run. Previous evidence will be archived.')
        self.started=time.monotonic();self.previous_tick=self.started;self.sample_at=self.started;self.usage=Usage();capture=self.session.document['capture'];capture['state']='Recording';capture['started']=time.time()
        self.session.save();self.running=True;self.timer.start(1000)
        try:self.collect()
        except Exception:
            self.timer.stop();self.running=False;capture['state']='Interrupted';raise
    def tick(self):
        if not self.running:return
        now=time.monotonic();capture=self.session.document['capture'];elapsed=now-self.previous_tick
        last=capture['samples'][-1] if capture['samples'] else {}
        if self.window.engine.running and last.get('monitoring_active') and last.get('fresh_ping_devices') and elapsed<=5:capture['monitoring_s']=capture['monitoring_s']+elapsed
        capture['max_heartbeat_gap_ms']=round(max(capture['max_heartbeat_gap_ms'],(now-self.previous_tick)*1000),1);self.previous_tick=now;capture['duration_s']=now-self.started
        if now-self.sample_at>=30:
            try:self.collect();self.sample_at=now
            except Exception:
                self.timer.stop();self.running=False;capture['state']='Interrupted'
                logging.warning('Pilot capture stopped: evidence could not be saved.')
                QMessageBox.warning(self.window,'Pilot capture stopped','Could not save the pilot report. Check free disk space and data-folder permissions. Existing evidence remains on disk; export available in-memory evidence before closing.')
    def collect(self):
        capture=self.session.document['capture'];rows,counts,truncated=snapshot(self.window);folder=self.window.store.path.parent
        sample={'at':time.time(),**self.usage.sample(),**counts,'database_bytes':byte_size(folder,['monitor.sqlite3','monitor.sqlite3-wal','monitor.sqlite3-shm']),'log_bytes':byte_size(folder,['diagnostic.log','diagnostic.log.1','diagnostic.log.2','diagnostic.log.3'])}
        capture['samples'].append(sample);capture['samples']=capture['samples'][-SAMPLE_LIMIT:];capture['total_samples']+=1;capture['observed_samples']+=bool(counts['monitoring_active'] and counts['fresh_ping_devices']);capture['devices']=rows;capture['devices_truncated']=truncated;self.session.save()
    def stop(self):
        if not self.running:return
        self.timer.stop();self.running=False;capture=self.session.document['capture'];capture['duration_s']=time.monotonic()-self.started;capture['state']='Stopped';self.collect()

class PilotDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setWindowTitle('Real-network pilot / support report');self.resize(780,680)
        if not getattr(window,'pilot_capture',None):window.pilot_capture=PilotCapture(window)
        self.capture=window.pilot_capture;self.session=self.capture.session
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll)
        note=QLabel('Test your own network. Record what you actually observed; this panel never disconnects devices or changes routes. Plan controlled faults with affected users first. Missing hardware stays Not performed / Blocked. Passing checkboxes alone never approves commercial release.');note.setWordWrap(True);layout.addWidget(note)
        self.summary=QLabel();self.summary.setTextFormat(Qt.PlainText);self.summary.setWordWrap(True);layout.addWidget(self.summary)
        row=QHBoxLayout();layout.addLayout(row)
        for title,fn in [('Start performance capture',self.start),('Stop & save capture',self.stop),('New session / archive old',self.reset)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        form=QFormLayout();layout.addLayout(form);self.scenario=QComboBox()
        for key,label in SCENARIOS:self.scenario.addItem(label,key)
        form.addRow('Test',self.scenario);self.status=QComboBox();self.status.addItems(STATUSES);form.addRow('Observed result',self.status)
        self.note=QPlainTextEdit();self.note.setPlaceholderText('What did you test? Which evidence confirmed the result? No passwords, private keys or pairing codes.');self.note.setMaximumHeight(100);form.addRow('Evidence / issue note',self.note)
        self.detection=QDoubleSpinBox();self.recovery=QDoubleSpinBox()
        for field in (self.detection,self.recovery):field.setRange(-1,86400);field.setDecimals(1);field.setSpecialValueText('Not measured')
        form.addRow('Detection delay (seconds)',self.detection);form.addRow('Recovery delay (seconds)',self.recovery)
        self.fp=QSpinBox();self.fn=QSpinBox()
        for field in (self.fp,self.fn):field.setRange(-1,1000000);field.setSpecialValueText('Not measured')
        form.addRow('False positives (wrong alerts)',self.fp);form.addRow('False negatives (missed faults)',self.fn)
        save=QPushButton('Save selected test result');save.clicked.connect(self.save);layout.addWidget(save)
        self.include_notes=QCheckBox('Include my test notes in exported report (review them for private information)');layout.addWidget(self.include_notes)
        export=QPushButton('Export support / pilot report');export.clicked.connect(self.export);layout.addWidget(export)
        self.scenario.currentIndexChanged.connect(self.load);self.load();self.refresh();self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(2000)
    def load(self):
        result=self.session.document['results'][self.scenario.currentData()];self.status.setCurrentText(result['status']);self.note.setPlainText(result['note'])
        for field,key in [(self.detection,'detection_s'),(self.recovery,'recovery_s'),(self.fp,'false_positive'),(self.fn,'false_negative')]:field.setValue(result[key] if result[key] is not None else -1)
    def refresh(self):
        doc=self.session.document;capture=doc['capture'];passed=sum(r['status']=='Pass' for r in doc['results'].values());last=capture['samples'][-1] if capture['samples'] else {};ram=last.get('working_set_mb');cpu=last.get('cpu_percent_one_core');review=self.session.review()
        self.summary.setText(f"Tests: {passed}/{len(SCENARIOS)} operator-reported pass • Capture: {capture['state']} • {capture['duration_s']/3600:.2f} hours • Fresh monitoring: {capture['monitoring_s']/3600:.2f} hours\nCPU: {cpu if cpu is not None else 'Unavailable'}% of one core • RAM: {ram if ram is not None else 'Unavailable'} MB • Observed samples: {capture['observed_samples']}\nCommercial release: NOT APPROVED • {len(review['blockers'])} open checklist / evidence blockers\n"+(review['blockers'][0] if review['blockers'] else 'Ready for owner evidence review; approval still required.'))
    def guarded(self,fn):
        try:fn();self.refresh()
        except Exception as error:QMessageBox.warning(self,'Pilot operation failed',str(error))
    def start(self):self.guarded(self.capture.start)
    def stop(self):self.guarded(self.capture.stop)
    def save(self):
        def save():
            values={'status':self.status.currentText(),'note':self.note.toPlainText()}
            for field,key in [(self.detection,'detection_s'),(self.recovery,'recovery_s'),(self.fp,'false_positive'),(self.fn,'false_negative')]:values[key]=None if field.value()<0 else field.value()
            self.session.record(self.scenario.currentData(),**values)
        self.guarded(save)
    def reset(self):
        if self.capture.running:QMessageBox.information(self,'Stop capture first','Stop and save the current continuous capture before starting a new session.');return
        if QMessageBox.question(self,'Archive and start again','Keep current evidence in a local archive and start a fresh pilot session?')!=QMessageBox.Yes:return
        self.guarded(self.session.reset);self.load()
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export report without credentials','zee-pilot-report.json','JSON (*.json)')
        if path:self.guarded(lambda:atomic_json(__import__('pathlib').Path(path),self.session.report(self.include_notes.isChecked())))
    def closeEvent(self,event):self.timer.stop();event.accept()
