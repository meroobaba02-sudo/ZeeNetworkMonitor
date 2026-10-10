"""Owner-only desktop tool. Private issuer key created locally, protected by DPAPI."""
import sys,os,json,time,base64,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QFormLayout,QLineEdit,QPushButton,QLabel,QFileDialog,QMessageBox,QInputDialog
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from zee.credentials import protect
from zee.licensing import canonical,PRODUCT

class Manager(QWidget):
    def __init__(self):
        super().__init__();self.setWindowTitle('Zee License Manager — Authorized Owner');self.resize(640,420)
        self.root=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ZeeLicenseManager';self.root.mkdir(parents=True,exist_ok=True)
        self.keyfile=self.root/'issuer-private.dpapi';layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form);self.fields={}
        for key,text,default in [('customer','Customer / organization',''),('edition','Edition','Professional'),('machine','Customer PC fingerprint',''),('days','Days (0 = perpetual)','365'),('reference','Reference','')]:
            edit=QLineEdit(default);self.fields[key]=edit;form.addRow(text,edit)
        for text,fn in [('Initialize owner key / export public key',self.initialize),('Generate one-PC signed licence',self.issue),('Export encrypted recovery key',self.backup),('Restore encrypted recovery key',self.restore)]:
            b=QPushButton(text);b.clicked.connect(fn);layout.addWidget(b)
        note=QLabel('Private key stays in your Windows DPAPI store. Never upload it to GitHub or customers. Put only issuer-public.json into assets, then rebuild the customer app. Each licence binds one PC; multiple customers require separate licences. Offline transfers require owner review; old offline copies cannot be remotely revoked.');note.setWordWrap(True);layout.addWidget(note)
    def key(self):return Ed25519PrivateKey.from_private_bytes(protect(self.keyfile.read_bytes(),True))
    def error(self,e):QMessageBox.warning(self,'Operation failed',type(e).__name__+': check key, fingerprint, password and file permissions.')
    def initialize(self):
        try:
            if not self.keyfile.exists():self.keyfile.write_bytes(protect(Ed25519PrivateKey.generate().private_bytes_raw()))
            public=base64.b64encode(self.key().public_key().public_bytes_raw()).decode()
            path,_=QFileDialog.getSaveFileName(self,'Export PUBLIC verification key','issuer-public.json','JSON (*.json)')
            if path:Path(path).write_text(json.dumps({'public_key':public,'product':PRODUCT}))
        except Exception as e:self.error(e)
    def issue(self):
        try:
            import re
            machine=self.fields['machine'].text().strip()
            if not re.fullmatch('[a-f0-9]{64}',machine):raise ValueError('Fingerprint')
            days=int(self.fields['days'].text())
            if not 0<=days<=36500:raise ValueError('Duration')
            payload={'version':1,'product':PRODUCT,'machine':machine,'customer':self.fields['customer'].text(),'edition':self.fields['edition'].text(),'reference':self.fields['reference'].text() or str(uuid.uuid4()),'activations':1,'issued':time.time(),'expires':time.time()+days*86400 if days else None}
            doc={'payload':payload,'signature':base64.b64encode(self.key().sign(canonical(payload))).decode()}
            path,_=QFileDialog.getSaveFileName(self,'Save signed licence','zee-license.json','JSON (*.json)')
            if path:Path(path).write_text(json.dumps(doc,indent=2))
        except Exception as e:self.error(e)
    def password(self):return QInputDialog.getText(self,'Recovery password','Enter a strong recovery password (keep separately)',QLineEdit.Password)
    def backup(self):
        try:
            password,ok=self.password()
            if not ok:return
            if len(password)<12:raise ValueError('Password too short')
            raw=self.key().private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(password.encode()))
            path,_=QFileDialog.getSaveFileName(self,'Save owner encrypted private key','owner-recovery.pem','PEM (*.pem)')
            if path:Path(path).write_bytes(raw)
        except Exception as e:self.error(e)
    def restore(self):
        try:
            if self.keyfile.exists():raise ValueError('Existing issuer key must not be overwritten')
            path,_=QFileDialog.getOpenFileName(self,'Encrypted recovery key','','PEM (*.pem)')
            if not path:return
            password,ok=self.password()
            if not ok:return
            key=serialization.load_pem_private_key(Path(path).read_bytes(),password.encode())
            if not isinstance(key,Ed25519PrivateKey):raise ValueError('Wrong key type')
            self.keyfile.write_bytes(protect(key.private_bytes_raw()))
        except Exception as e:self.error(e)

if __name__=='__main__':
    app=QApplication(sys.argv);w=Manager();w.show()
    if '--smoke-test' in sys.argv:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300,w.close)
    raise SystemExit(app.exec())
