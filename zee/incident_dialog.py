"""Small, page-scoped incident history; acknowledgement never claims recovery."""
import time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QCheckBox,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QTextEdit,QFileDialog,QInputDialog,QMessageBox,QGridLayout
from .core import export_csv

class IncidentDialog(QDialog):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWindowTitle('Incident history / evidence');self.resize(1050,680)
        layout=QVBoxLayout(self);tools=QHBoxLayout();layout.addLayout(tools)
        self.all_pages=QCheckBox('Show history from all networks');self.all_pages.toggled.connect(self.refresh);tools.addWidget(self.all_pages)
        self.reduce=QCheckBox('Reduce repeated downstream notifications');self.reduce.setChecked(w.store.setting('correlate_alerts',True));self.reduce.toggled.connect(lambda value:w.store.set_setting('correlate_alerts',value));tools.addWidget(self.reduce)
        actions=QHBoxLayout();layout.addLayout(actions)
        for title,fn in [('Acknowledge',self.ack),('Notes',self.notes),('Pin / unpin',self.pin),('Close unverified',self.close_unverified),('Export CSV',self.export)]:
            b=QPushButton(title);b.clicked.connect(fn);actions.addWidget(b)
        note=QLabel('Unobserved = no fresh evidence; incident remains unresolved. Acknowledgement does not silence the buzzer or mark recovery. Duration is elapsed time between observations, not proven continuous downtime. Latest 500 records shown.');note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['Network','Device / check','Status','Started','Last evidence','Resolved','Elapsed','Ack / pinned']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.itemSelectionChanged.connect(self.detail);layout.addWidget(self.table,1)
        self.text=QTextEdit();self.text.setReadOnly(True);self.text.setMaximumHeight(190);layout.addWidget(self.text)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(2000);self.rows=[];self.refresh()
    def selected(self):
        row=self.table.currentRow();return self.rows[row] if 0<=row<len(self.rows) else None
    def refresh(self):
        selected=self.selected();id=selected['id'] if selected else None
        self.w.sync_incidents();self.rows=self.w.store.incident_rows(None if self.all_pages.isChecked() else self.w.page_id)
        pages={p.id:p.name for p in self.w.store.pages()};devices={d.id:d.name for d in self.w.store.devices()}
        stamp=lambda value:time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(value)) if value is not None else 'Not observed'
        self.table.blockSignals(True);self.table.setRowCount(len(self.rows))
        for i,r in enumerate(self.rows):
            elapsed=max(0,(r['resolved'] if r['resolved'] is not None else time.time())-r['at'])
            vals=[pages.get(r['page_id'],'Removed network'),devices.get(r['device'],'Removed device')+' / '+r['category'],r['status'],stamp(r['at']),stamp(r['last_seen']),stamp(r['resolved']),f'{elapsed:.0f}s elapsed',('Acknowledged' if r['acknowledged'] else 'New')+(' / pinned' if r['pinned'] else '')]
            for j,value in enumerate(vals):self.table.setItem(i,j,QTableWidgetItem(str(value)))
            if r['id']==id:self.table.selectRow(i)
        self.table.resizeColumnsToContents();self.table.blockSignals(False);self.detail()
    def detail(self):
        r=self.selected()
        if not r:self.text.setPlainText('Select an incident to see evidence and a suggested next check.');return
        d=r['detail'];self.text.setPlainText(d['title']+'\nObserved device: '+d.get('name','Not recorded')+' @ '+d.get('host','Not recorded')+' | source '+d.get('source','Not recorded')+'\nConfidence: '+d['confidence']+' (qualitative)\nEvidence: '+'; '.join(d['evidence'])+'\nNext check: '+d['next_step']+'\nNotes: '+(r['notes'] or 'None')+'\nStale / missing observations do not establish recovery.')
        if d.get('recovery'):self.text.append('Recovery observation: '+'; '.join(d['recovery']['evidence']))
    def ack(self):
        r=self.selected()
        if r:self.w.store.edit_incident(r['id'],acknowledged=True);self.refresh()
    def pin(self):
        r=self.selected()
        if r:self.w.store.edit_incident(r['id'],pinned=not r['pinned']);self.refresh()
    def notes(self):
        r=self.selected()
        if not r:return
        text,ok=QInputDialog.getMultiLineText(self,'Incident notes','Do not include passwords or tokens.',r['notes'])
        if ok:
            try:self.w.store.edit_incident(r['id'],notes=text);self.refresh()
            except ValueError as e:QMessageBox.warning(self,'Cannot save note',str(e))
    def close_unverified(self):
        r=self.selected()
        if r and r['resolved'] is None and QMessageBox.question(self,'Close without recovery proof','Close this incident as operator-closed / recovery unverified? A still-observed fault can open a new incident.')==QMessageBox.Yes:
            self.w.store.edit_incident(r['id'],close=True);self.refresh()
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export visible incident history','incidents.csv','CSV (*.csv)')
        if path:
            rows=[r|{'name':r['detail'].get('name',''),'host':r['detail'].get('host',''),'source':r['detail'].get('source',''),'title':r['detail']['title'],'confidence':r['detail']['confidence'],'evidence':'; '.join(r['detail']['evidence']),'recovery_evidence':'; '.join(r['detail'].get('recovery',{}).get('evidence',[])),'next_step':r['detail']['next_step']} for r in self.rows]
            try:export_csv(path,rows,['id','page_id','device','name','host','source','category','status','at','last_seen','resolved','acknowledged','pinned','notes','title','confidence','evidence','recovery_evidence','next_step'])
            except OSError as e:QMessageBox.warning(self,'Cannot export incidents',str(e))
    def done(self,result):self.timer.stop();super().done(result)
    def closeEvent(self,event):self.timer.stop();event.accept()
