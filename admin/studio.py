"""Separate owner/viewer desktop Studio; protected actions go through authenticated services."""
import argparse,base64,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QTimer,QLockFile
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,QCheckBox,QSpinBox,QComboBox,QDialog,QDialogButtonBox,QFileDialog,QMessageBox,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QStackedWidget,QScrollArea,QInputDialog
from admin.studio_store import StudioStore,FEATURES
from admin.issuer import read_request,write_atomic
from zee.customer_theme import apply_theme
from zee.core import VERSION,export_csv


def label(text):
    w=QLabel(text);w.setWordWrap(True);w.setTextFormat(Qt.PlainText);return w

def button(text,fn):
    w=QPushButton(text);w.clicked.connect(fn);return w

class RecordDialog(QDialog):
    def __init__(self,studio,kind,record=None):
        super().__init__(studio);self.studio=studio;self.kind=kind;self.setWindowTitle('Edit '+kind[:-1]);self.resize(600,620);self.fields={};self.features={};data=record['data'] if record else {};self.logo=data.get('logo_png','')
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();scroll.setWidget(body);outer.addWidget(scroll,1);form=QFormLayout(body)
        keys=[('name','Name')]
        if kind=='customers':keys += [('contact','Contact / organization'),('notes','Notes (no passwords)')]
        if kind=='profiles':keys += [('app_name','Planned app name'),('watermark','Planned watermark')]
        for key,title in keys:
            default='Zee Network Monitor' if key=='app_name' else 'Created by Zeeshan Rasool' if key=='watermark' else ''
            edit=QLineEdit(data.get(key,default));self.fields[key]=edit;form.addRow(title,edit)
        if kind=='packages':
            for key,title,low,high,default in [('days','Licence days (0 = perpetual)',0,36500,365),('max_devices','Planned device limit',1,10000,100)]:
                edit=QSpinBox();edit.setRange(low,high);edit.setValue(data.get(key,default));self.fields[key]=edit;form.addRow(title,edit)
            for feature in FEATURES:
                check=QCheckBox(feature.title());check.setChecked(feature in data.get('features',['monitoring','map','wan']));self.features[feature]=check;form.addRow(check)
            form.addRow(label('Licence validity is applied when issuing. Feature/device limits are planning metadata until customer enforcement in Phase 8.2.'))
        if kind=='profiles':
            for key,record_kind,title in [('customer_id','customers','Customer'),('package_id','packages','Package')]:
                combo=QComboBox()
                for r in studio.store.records(studio.token,record_kind):
                    if not r['archived']:combo.addItem(r['name'],r['id'])
                if data.get(key):combo.setCurrentIndex(combo.findData(data[key]))
                self.fields[key]=combo;form.addRow(title,combo)
            form.addRow(button('Choose PNG logo',self.choose_logo));form.addRow(button('Remove custom logo',self.remove_logo));self.preview=QLabel();self.preview.setMinimumHeight(110);self.preview.setAlignment(Qt.AlignCenter);form.addRow(self.preview);self.preview_logo()
            form.addRow(label('This saves a real reviewed build profile. Exported branding is not yet applied to the customer EXE; build integration is Phase 8.2.'))
        box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.accepted.connect(self.accept);box.rejected.connect(self.reject);outer.addWidget(box)
    def choose_logo(self):
        path,_=QFileDialog.getOpenFileName(self,'Logo (PNG, up to 2 MiB / 2048 px)','','PNG (*.png)')
        if not path:return
        try:
            if Path(path).stat().st_size>2*1048576:raise ValueError('Logo too large.')
            old=self.logo;self.logo=base64.b64encode(Path(path).read_bytes()).decode()
            try:self.studio.store.normalize(self.studio.token,self.kind,self.values())
            except Exception:self.logo=old;raise
            self.preview_logo()
        except Exception as e:QMessageBox.warning(self,'Cannot use logo',str(e))
    def remove_logo(self):self.logo='';self.preview_logo()
    def preview_logo(self):
        if not self.logo:self.preview.setText('Default branding • no custom logo');return
        pix=QPixmap();pix.loadFromData(base64.b64decode(self.logo));self.preview.setPixmap(pix.scaled(240,110,Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def values(self):
        data={key:widget.currentData() if isinstance(widget,QComboBox) else widget.value() if isinstance(widget,QSpinBox) else widget.text().strip() for key,widget in self.fields.items()}
        if self.kind=='packages':data['features']=[key for key,w in self.features.items() if w.isChecked()]
        if self.kind=='profiles':data['logo_png']=self.logo
        return data
    def accept(self):
        try:self.studio.store.normalize(self.studio.token,self.kind,self.values())
        except Exception as e:QMessageBox.warning(self,'Please correct the record',str(e));return
        super().accept()

class Studio(QMainWindow):
    def __init__(self,store):
        super().__init__();self.store=store;self.token=None;self.rows={};self.owner_buttons=[];self.setWindowTitle('Zee Admin Studio — Network Monitor Edition Manager');self.resize(1100,750)
        apply_theme(QApplication.instance(),'dark');self.stack=QStackedWidget();self.setCentralWidget(self.stack)
        login=QWidget();layout=QVBoxLayout(login);layout.setContentsMargins(140,90,140,90);layout.addStretch();title=label('Zee Admin Studio');title.setObjectName('title');layout.addWidget(title)
        self.login_note=label('');layout.addWidget(self.login_note);form=QFormLayout();layout.addLayout(form)
        self.username=QLineEdit('owner');self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password);self.password.setMaxLength(256);self.password.setPlaceholderText('At least 12 characters');form.addRow('Username',self.username);form.addRow('Password',self.password)
        self.login_button=button('Sign in',self.sign_in);layout.addWidget(self.login_button);self.password.returnPressed.connect(self.sign_in);layout.addWidget(label('Owner credentials are created locally. No default password and no automatic Internet connection.'));layout.addStretch();self.stack.addWidget(login)
        work=QWidget();layout=QVBoxLayout(work);header=QHBoxLayout();layout.addLayout(header);heading=label('ZEE / ADMIN STUDIO');heading.setObjectName('title');header.addWidget(heading);header.addStretch();self.session_label=label('');header.addWidget(self.session_label);header.addWidget(button('Lock / sign out',self.lock))
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        dashboard=QWidget();box=QVBoxLayout(dashboard);self.dashboard=label('');self.dashboard.setObjectName('card');box.addWidget(self.dashboard)
        note=label('Phase 8.1: real records, reviewed profiles, signed one-PC licences and protected owner actions. Package feature/device enforcement, customer build branding and release/update automation are Phase 8.2.');box.addWidget(note)
        for title,fn in [('Initialize Studio issuer / export public key',self.initialize),('Export encrypted issuer recovery key',self.export_recovery),('Import encrypted issuer recovery key',self.import_recovery),('Create read-only viewer',self.create_viewer),('Encrypted Studio backup',self.backup),('Restore encrypted Studio backup',self.restore)]:
            b=button(title,lambda checked=False,f=fn:self.run(f));box.addWidget(b);self.owner_buttons.append(b)
        box.addWidget(label('Existing issuer? Import its encrypted recovery PEM before creating a new Studio key. Keep recovery passwords and private files off GitHub. Export only the public key for a reviewed customer rebuild.'))
        box.addStretch();self.tabs.addTab(dashboard,'Overview')
        for kind in ('customers','packages','profiles'):
            page=QWidget();box=QVBoxLayout(page);search=QLineEdit();search.setPlaceholderText('Search name, contact or saved profile…');search.textChanged.connect(lambda _,k=kind:self.render_records(k));box.addWidget(search);setattr(self,kind+'_search',search)
            table=self.make_table(['Name','Details','Status']);setattr(self,kind+'_table',table);box.addWidget(table,1);row=QHBoxLayout();box.addLayout(row)
            for title,fn in [('Add',lambda k=kind:self.edit(k)),('Edit',lambda k=kind:self.edit(k,True)),('Archive / restore',lambda k=kind:self.archive(k))]:
                b=button(title,lambda checked=False,f=fn:self.run(f));row.addWidget(b);self.owner_buttons.append(b)
            if kind=='profiles':
                b=button('Export reviewed build profile',lambda:self.run(self.export_profile));row.addWidget(b);self.owner_buttons.append(b)
            box.addWidget(label('Up to 1,000 saved records loaded; first 200 matching rows shown. Archived records are retained for history.'));self.tabs.addTab(page,kind.title())
        page=QWidget();box=QVBoxLayout(page);form=QFormLayout();box.addLayout(form);self.customer=QComboBox();self.package=QComboBox();self.profile=QComboBox();self.machine=QLineEdit();self.machine.setPlaceholderText('64-character activation fingerprint from customer PC');form.addRow('Customer',self.customer);form.addRow('Package',self.package);form.addRow('Optional reviewed profile',self.profile);form.addRow('One customer PC',self.machine)
        row=QHBoxLayout();box.addLayout(row)
        for title,fn in [('Import activation request',self.import_request),('Issue / save signed licence',self.issue),('Export selected licence',self.export_licence),('Revoke in Studio register',self.revoke)]:
            b=button(title,lambda checked=False,f=fn:self.run(f));row.addWidget(b);self.owner_buttons.append(b)
        self.licence_table=self.make_table(['Customer / reference','Package','Machine','Status']);box.addWidget(self.licence_table,1);box.addWidget(label('Offline licences cannot be remotely revoked. Revocation here records an owner decision; previously exported offline copies remain valid. Package feature/device limits are not yet enforced in the customer app.'));self.tabs.addTab(page,'Licences')
        page=QWidget();box=QVBoxLayout(page);self.audit_table=self.make_table(['Time (UTC)','Actor','Action','Target','Detail']);box.addWidget(self.audit_table,1);box.addWidget(button('Export audit CSV',lambda:self.run(self.export_audit)));self.audit_note=label('');box.addWidget(self.audit_note);self.tabs.addTab(page,'Audit')
        layout.addWidget(label('Created by Zeeshan Rasool'));self.stack.addWidget(work);self.reset_login()
        self.timer=QTimer(self);self.timer.timeout.connect(self.check_session);self.timer.start(30000)
    def make_table(self,headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers);table.setSelectionBehavior(QTableWidget.SelectRows);table.setSelectionMode(QTableWidget.SingleSelection);table.setEditTriggers(QTableWidget.NoEditTriggers);table.setAlternatingRowColors(True);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);return table
    def reset_login(self):
        first=not self.store.configured();self.login_button.setText('Create local owner account' if first else 'Sign in');self.login_note.setText('First run: choose your owner username and password. Keep them safely; no automatic password reset is provided.' if first else 'Sign in. Sessions expire after 15 minutes; protected actions require the owner account.');self.password.clear();self.stack.setCurrentIndex(0)
    def sign_in(self):
        try:
            if not self.store.configured():self.store.setup(self.username.text().strip(),self.password.text())
            self.token=self.store.login(self.username.text().strip(),self.password.text());self.password.clear();self.refresh();self.stack.setCurrentIndex(1)
        except Exception as e:self.password.clear();QMessageBox.warning(self,'Sign in failed',str(e) if isinstance(e,(ValueError,PermissionError)) else 'Check the local Studio database and file permissions.')
    def lock(self):
        if self.token:self.store.logout(self.token)
        self.token=None;self.machine.clear()
        for kind in ('customers','packages','profiles'):getattr(self,kind+'_table').setRowCount(0)
        self.licence_table.setRowCount(0);self.audit_table.setRowCount(0);self.rows={};self.reset_login()
    def check_session(self):
        if not self.token:return
        try:self.store.require(self.token,recovery=True)
        except PermissionError:self.lock()
    def run(self,fn):
        try:fn()
        except PermissionError as e:
            QMessageBox.warning(self,'Protected action',str(e));self.check_session()
        except Exception as e:QMessageBox.warning(self,'Operation failed',str(e) if isinstance(e,ValueError) else 'Check credentials, Windows protection, recovery password and file permissions.')
    def refresh(self):
        session=self.store.require(self.token,recovery=True);owner=session['role']=='owner';recovery=session.get('recovery_only');self.session_label.setText(session['actor']+' / '+session['role']+(' / recovery only' if recovery else ''))
        for b in self.owner_buttons:b.setEnabled(owner and not recovery)
        for index in range(1,self.tabs.count()):self.tabs.setTabEnabled(index,not recovery)
        if recovery:
            self.dashboard.setText('Audit integrity failed. Only trusted backup restore is permitted.');self.tabs.setCurrentIndex(0)
            # Locate the actual restore control, not a separate unguarded path.
            for b in self.owner_buttons:
                if b.text()=='Restore encrypted Studio backup':b.setEnabled(owner)
            return
        for kind in ('customers','packages','profiles'):self.render_records(kind)
        customers=self.store.records(self.token,'customers');packages=self.store.records(self.token,'packages');profiles=self.store.records(self.token,'profiles')
        for combo,records in [(self.customer,customers),(self.package,packages),(self.profile,profiles)]:
            old=combo.currentData();combo.clear()
            if combo is self.profile:combo.addItem('No profile','')
            for r in records:
                if not r['archived']:combo.addItem(r['name'],r['id'])
            if old:combo.setCurrentIndex(max(0,combo.findData(old)))
        licences=self.store.licences(self.token);self.rows['licences']=licences;self.fill(self.licence_table,[[r['signed']['payload']['customer']+' / '+r['id'],r['signed']['payload']['edition'],r['machine'],r['status']] for r in licences])
        audit=self.store.audit_rows(self.token);self.rows['audit']=audit;import time
        self.fill(self.audit_table,[[time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(r['at'])),r['actor'],r['action'],r['target'],r['detail']] for r in audit]);n=self.store.verify_audit();self.audit_note.setText(f'{n} audit entries verified. Hash-chain checks detect non-recomputed changes; local filesystem administrators can still tamper with records. No passwords or signing keys are recorded.')
        self.dashboard.setText(f'Customers: {sum(not r["archived"] for r in customers)}    Packages: {sum(not r["archived"] for r in packages)}    Profiles: {sum(not r["archived"] for r in profiles)}\nLicence register: {len(licences)} latest records\nIssuer key: '+('Stored locally; password + Windows protection' if self.store.keyfile.exists() else 'Not initialized — initialize on your owner Windows PC'))
    def fill(self,table,rows):
        table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):item=QTableWidgetItem(str(value));item.setToolTip(str(value));table.setItem(i,j,item)
    def render_records(self,kind):
        if not self.token:return
        records=self.store.records(self.token,kind);q=getattr(self,kind+'_search').text().casefold();records=[r for r in records if q in json.dumps(r['data']).casefold()][:200];self.rows[kind]=records;values=[]
        for r in records:
            data=r['data'];detail=data['contact'] if kind=='customers' else f'{data["days"]} days / planned {data["max_devices"]} devices' if kind=='packages' else data['app_name']+' / planned branding'
            values.append([r['name'],detail,'Archived' if r['archived'] else 'Active'])
        self.fill(getattr(self,kind+'_table'),values)
    def selected(self,kind):
        table=self.licence_table if kind=='licences' else getattr(self,kind+'_table');i=table.currentRow();return self.rows.get(kind,[])[i] if 0<=i<len(self.rows.get(kind,[])) else None
    def edit(self,kind,existing=False):
        self.store.require(self.token,True);r=self.selected(kind) if existing else None
        if existing and not r:return
        d=RecordDialog(self,kind,r)
        if d.exec()==QDialog.Accepted:self.store.save_record(self.token,kind,d.values(),r['id'] if r else None);self.refresh()
    def archive(self,kind):
        r=self.selected(kind)
        if r:self.store.archive(self.token,kind,r['id']);self.refresh()
    def save_file(self,title,name,raw,filter='JSON (*.json)'):
        path,_=QFileDialog.getSaveFileName(self,title,name,filter)
        if path:write_atomic(path,raw)
        return bool(path)
    def initialize(self):
        public=self.store.initialize_key(self.token);self.save_file('Export PUBLIC verification key','issuer-public.json',json.dumps(public,indent=2).encode());self.refresh()
    def export_profile(self):
        r=self.selected('profiles')
        if r:self.save_file('Export reviewed profile','zee-build-profile.json',json.dumps(self.store.export_profile(self.token,r['id']),indent=2).encode());self.refresh()
    def import_request(self):
        self.store.require(self.token,True);path,_=QFileDialog.getOpenFileName(self,'Customer activation request','','JSON (*.json)')
        if path:
            if Path(path).stat().st_size>65536:raise ValueError('Request too large.')
            self.machine.setText(read_request(json.loads(Path(path).read_text())))
    def issue(self):
        self.store.require(self.token,True)
        path,_=QFileDialog.getSaveFileName(self,'Save signed licence','zee-license.json','JSON (*.json)')
        if not path:return
        id,doc=self.store.issue(self.token,self.customer.currentData(),self.package.currentData(),self.machine.text().strip(),self.profile.currentData() or '');write_atomic(path,json.dumps(doc,indent=2).encode());self.refresh()
    def export_licence(self):
        self.store.require(self.token,True);r=self.selected('licences')
        if r:self.save_file('Export saved signed licence','zee-license.json',json.dumps(r['signed'],indent=2).encode())
    def revoke(self):
        self.store.require(self.token,True);r=self.selected('licences')
        if not r:return
        reason,ok=QInputDialog.getText(self,'Record revocation','Reason (offline exported copies remain valid)')
        if ok:self.store.revoke(self.token,r['id'],reason);self.refresh()
    def password_prompt(self):return QInputDialog.getText(self,'Encryption password','At least 12 characters; keep separately.',QLineEdit.Password)
    def export_recovery(self):
        password,ok=self.password_prompt()
        if ok:self.save_file('Encrypted issuer recovery','studio-issuer-recovery.pem',self.store.recovery_export(self.token,password),'PEM (*.pem)');self.refresh()
    def import_recovery(self):
        self.store.require(self.token,True);path,_=QFileDialog.getOpenFileName(self,'Encrypted issuer recovery','','PEM (*.pem)')
        if not path:return
        if Path(path).stat().st_size>65536:raise ValueError('Recovery file too large.')
        password,ok=self.password_prompt()
        if ok:self.store.recovery_import(self.token,Path(path).read_bytes(),password);self.refresh()
    def create_viewer(self):
        self.store.require(self.token,True);name,ok=QInputDialog.getText(self,'Create viewer','Read-only username')
        if not ok:return
        password,ok=self.password_prompt()
        if ok:self.store.add_viewer(self.token,name,password);self.refresh()
    def backup(self):
        password,ok=self.password_prompt()
        if ok:self.save_file('Encrypted Studio backup','zee-studio-backup.zas',self.store.backup(self.token,password),'Studio backup (*.zas)');self.refresh()
    def restore(self):
        self.store.require(self.token,True,recovery=True);path,_=QFileDialog.getOpenFileName(self,'Encrypted Studio backup','','Studio backup (*.zas)')
        if not path:return
        if Path(path).stat().st_size>64*1048576:raise ValueError('Backup file too large.')
        password,ok=self.password_prompt()
        if not ok:return
        if QMessageBox.question(self,'Replace Studio records','Restore saved records, accounts and encrypted issuer key? A recovery checkpoint is kept. Studio will close; log in with the restored owner credentials. Other Windows accounts may also need the separate issuer recovery PEM.')!=QMessageBox.Yes:return
        self.store.restore(self.token,Path(path).read_bytes(),password,allow_key_change=True);self.close()
    def export_audit(self):
        rows=self.store.audit_rows(self.token);path,_=QFileDialog.getSaveFileName(self,'Audit CSV','studio-audit.csv','CSV (*.csv)')
        if path:export_csv(path,rows,['seq','at','actor','action','target','detail','previous','digest'])
    def closeEvent(self,event):
        self.timer.stop()
        if self.token:self.store.logout(self.token)
        self.store.close();event.accept()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path);parser.add_argument('--smoke-test',action='store_true');args=parser.parse_args()
    app=QApplication(sys.argv);root=args.data_dir or Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ZeeAdminStudio';root.mkdir(parents=True,exist_ok=True);lock=QLockFile(str(root/'studio.lock'))
    if not lock.tryLock(100):return 2
    failures=[]
    def error_hook(kind,value,tb):
        failures.append(kind.__name__)
        if not args.smoke_test:QMessageBox.critical(None,'Studio error','An operation failed. Check the local Studio data and backup. No private keys are sent anywhere.')
    sys.excepthook=error_hook
    try:
        w=Studio(StudioStore(root));w.show()
        if args.smoke_test:QTimer.singleShot(400,w.close)
        code=app.exec()
        if args.smoke_test and not failures:write_atomic(root/'studio-smoke-ok.txt',b'Admin Studio login startup/shutdown passed. No account/key provisioned by smoke test.')
        return 1 if failures else code
    finally:lock.unlock()

if __name__=='__main__':raise SystemExit(main())
