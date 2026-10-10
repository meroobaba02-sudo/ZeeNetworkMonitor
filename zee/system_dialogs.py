import json,time
from pathlib import Path
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,QFileDialog,QMessageBox,QApplication
from PySide6.QtCore import QTimer
from .licensing import status,fingerprint,verify,public_key_path

class LicenseDialog(QDialog):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWindowTitle('Offline licence / activation');self.resize(620,280)
        layout=QVBoxLayout(self);self.label=QLabel();self.label.setWordWrap(True);layout.addWidget(self.label)
        machine=QLineEdit(fingerprint());machine.setReadOnly(True);layout.addWidget(QLabel('This PC activation fingerprint (not transmitted):'));layout.addWidget(machine)
        for title,fn in [('Export this PC activation request',self.request),('Import signed licence',self.activate),('Deactivate on this PC',self.deactivate)]:
            b=QPushButton(title);b.clicked.connect(fn);layout.addWidget(b)
        self.refresh()
    def refresh(self):
        state=status(self.w.store.path.parent)
        if not state.get('production'):
            text='Owner evaluation — customer licence enforcement is not enabled.\nOwner must initialize the signing key locally and provide only issuer-public.json for a customer rebuild.'
        elif not state['valid']:text='ACTIVATION REQUIRED\n'+state.get('reason','Licence invalid')+'\nMonitoring requires a valid signed licence for this PC.'
        else:
            expiry=time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime(state['expires'])) if state.get('expires') is not None else 'Perpetual'
            text=f"Activated: {state.get('edition','')}\nCustomer: {state.get('customer','')}\nReference: {state.get('reference','')}\nExpiry: {expiry}\nAuthorized PCs: 1"
        self.label.setText(text)
    def request(self):
        path,_=QFileDialog.getSaveFileName(self,'Export activation request','zee-activation-request.json','JSON (*.json)')
        if not path:return
        try:
            # This contains a fingerprint, never device credentials/topology; no automatic transmission.
            payload={'type':'zee-activation-request','version':1,'product':'ZeeNetworkMonitor','machine':fingerprint()}
            Path(path).write_text(json.dumps(payload,indent=2),encoding='utf-8')
            QMessageBox.information(self,'Request saved','Send this file to the software owner yourself. It contains this PC fingerprint; no network credentials or topology.')
        except OSError:QMessageBox.warning(self,'Cannot export request','Check the selected file path and permissions.')
    def activate(self):
        path,_=QFileDialog.getOpenFileName(self,'Signed licence','','JSON (*.json)')
        if not path:return
        try:
            if not public_key_path().exists():raise ValueError('Owner verification key has not been provisioned in this build. See licensing setup guide.')
            if Path(path).stat().st_size>65536:raise ValueError('Licence file too large.')
            doc=json.loads(Path(path).read_text());verify(doc,json.loads(public_key_path().read_text())['public_key'])
            target=self.w.store.path.parent/'license.json';temporary=target.with_suffix('.new');temporary.write_text(json.dumps(doc));temporary.replace(target);self.refresh();QMessageBox.information(self,'Activated','Licence accepted. Restart the application.')
        except Exception:QMessageBox.warning(self,'Activation rejected','Licence invalid, expired, wrong PC, or issuer key not provisioned. Contact the software owner.')
    def deactivate(self):
        if QMessageBox.question(self,'Deactivate','Remove activation from this PC? Offline transfer needs the owner to reissue; deleting this copy cannot revoke copies of the old licence.')==QMessageBox.Yes:
            (self.w.store.path.parent/'license.json').unlink(missing_ok=True);self.w.close();self.close()

class MobileDialog(QDialog):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWindowTitle('Pair phone • opt-in HTTPS');self.resize(650,460)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.host=QLineEdit(w.store.setting('mobile_host','127.0.0.1'));self.port=QLineEdit('8443');form.addRow('PC LAN or VPN IP to listen on',self.host);form.addRow('HTTPS port',self.port)
        note=QLabel('LAN: use the PC LAN IP. Remote: use a configured VPN address; no relay is included and no router/firewall ports are changed. A local TLS certificate is created. Verify its SHA-256 fingerprint and trust it on your own phone before pairing. Do not bypass an unexpected certificate warning. PC and app must stay running.');note.setWordWrap(True);layout.addWidget(note)
        self.info=QLabel();self.info.setWordWrap(True);self.info.setTextInteractionFlags(self.info.textInteractionFlags()|__import__('PySide6.QtCore',fromlist=['Qt']).Qt.TextSelectableByMouse);layout.addWidget(self.info)
        for title,fn in [('Enable HTTPS dashboard',self.start),('New pairing code (5 minutes)',self.pair),('Revoke ALL paired phones',self.revoke),('Stop mobile access',self.stop)]:
            b=QPushButton(title);b.clicked.connect(fn);layout.addWidget(b)
    def start(self):
        try:
            if getattr(self.w,'mobile_server',None):raise ValueError('Dashboard already running; stop it to change address.')
            from .mobile import MobileServer,certificate
            host=self.host.text().strip();port=int(self.port.text())
            if not 1024<=port<=65535:raise ValueError('Use port 1024–65535.')
            folder=self.w.store.path.parent/'mobile';ctx,fp=certificate(folder,host)
            server=MobileServer(folder,host,port,ctx);server.start();self.w.mobile_server=server;self.w.store.set_setting('mobile_host',host)
            self.w.update_mobile();self.info.setText(f'https://{host}:{port}\nCertificate SHA-256: {fp}\nCertificate file: {folder / "mobile-cert.pem"}')
        except Exception as e:QMessageBox.warning(self,'Could not enable HTTPS',str(e))
    def pair(self):
        server=getattr(self.w,'mobile_server',None)
        if server:self.info.setText(self.info.text().split('\nPairing code:')[0]+'\nPairing code: '+server.pair())
    def revoke(self):
        server=getattr(self.w,'mobile_server',None)
        if server:server.revoke();self.info.setText('All paired phones revoked.')
    def stop(self):
        server=getattr(self.w,'mobile_server',None)
        if server:server.stop();self.w.mobile_server=None;self.info.setText('Mobile access stopped.')
