import json,time
from pathlib import Path
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,QFileDialog,QMessageBox,QApplication,QComboBox,QScrollArea,QWidget
from PySide6.QtCore import QTimer,Qt
from .licensing import status,fingerprint,import_licence,recover_licence,deactivate_licence

class LicenseDialog(QDialog):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWindowTitle('Offline licence / activation');self.resize(620,380);self.setMinimumHeight(380)
        layout=QVBoxLayout(self);self.label=QLabel();self.label.setTextFormat(Qt.PlainText);self.label.setWordWrap(True);layout.addWidget(self.label)
        machine=QLineEdit(fingerprint());machine.setReadOnly(True);layout.addWidget(QLabel('This PC activation fingerprint (not transmitted):'));layout.addWidget(machine)
        for title,fn in [('Export this PC activation request',self.request),('Import signed licence',self.activate),('Recover previous valid licence',self.recover),('Deactivate on this PC',self.deactivate)]:
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
            if state.get('entitlements'):
                from .entitlements import from_status
                from .licensing import customer_profile
                policy=from_status(state,customer_profile());text+='\nDevice limit: '+str(policy.max_devices)+'\nFeatures: '+', '.join(sorted(policy.features))
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
            import_licence(self.w.store.path.parent,path);self.refresh();QMessageBox.information(self,'Activated','Licence accepted. Restart the application to apply permissions.')
        except Exception:QMessageBox.warning(self,'Activation rejected','Licence invalid, expired, wrong PC, or issuer key not provisioned. Contact the software owner.')
    def recover(self):
        try:
            recover_licence(self.w.store.path.parent);self.refresh()
            QMessageBox.information(self,'Licence recovered','Previous licence verified and restored. Restart to apply permissions.')
        except Exception:
            QMessageBox.warning(self,'Recovery unavailable','No valid previous licence for this PC and customer profile. Ask the owner to reissue a signed licence.')
    def deactivate(self):
        if QMessageBox.question(self,'Deactivate','Remove activation from this PC? Offline transfer needs the owner to reissue; deleting this copy cannot revoke copies of the old licence.')==QMessageBox.Yes:
            deactivate_licence(self.w.store.path.parent);self.w.close();self.close()

class MobileDialog(QDialog):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWindowTitle('Pair phone • opt-in HTTPS');self.resize(650,460)
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll);form=QFormLayout();layout.addLayout(form)
        self.host=QLineEdit(w.store.setting('mobile_host','127.0.0.1'));self.port=QLineEdit('8443');form.addRow('PC LAN or VPN IP to listen on',self.host);form.addRow('HTTPS port',self.port)
        note=QLabel('LAN: use the PC LAN IP. Remote: use a configured VPN address; no relay is included and no router/firewall ports are changed. A local TLS certificate is created. Verify its SHA-256 fingerprint and trust it on your own phone before pairing. Do not bypass an unexpected certificate warning. PC and app must stay running.');note.setWordWrap(True);layout.addWidget(note)
        self.info=QLabel();self.info.setTextFormat(Qt.PlainText);self.info.setWordWrap(True);self.info.setTextInteractionFlags(self.info.textInteractionFlags()|__import__('PySide6.QtCore',fromlist=['Qt']).Qt.TextSelectableByMouse);layout.addWidget(self.info)
        self.phones=QComboBox();layout.addWidget(self.phones)
        for title,fn in [('Refresh paired phones',self.refresh_phones),('Revoke selected phone',self.revoke_selected),('Reset local TLS certificate (service must be stopped)',self.reset_certificate),('Enable HTTPS dashboard',self.start),('New pairing code (5 minutes)',self.pair),('Revoke ALL paired phones',self.revoke),('Stop mobile access',self.stop)]:
            b=QPushButton(title);b.clicked.connect(fn);layout.addWidget(b)
    def start(self):
        try:
            if hasattr(self.w,'policy'):self.w.policy.require('mobile')
            if getattr(self.w,'mobile_server',None):raise ValueError('Dashboard already running; stop it to change address.')
            from .mobile import MobileServer,certificate
            host=self.host.text().strip();port=int(self.port.text())
            if not 1024<=port<=65535:raise ValueError('Use port 1024–65535.')
            folder=self.w.store.path.parent/'mobile';ctx,fp=certificate(folder,host)
            server=MobileServer(folder,host,port,ctx,branding=getattr(self.w,'branding',None));server.start();self.w.mobile_server=server;self.w.store.set_setting('mobile_host',host)
            self.w.update_mobile();self.info.setText(f'https://{host}:{port}\nCertificate SHA-256: {fp}\nCertificate file: {folder / "mobile-cert.pem"}')
        except Exception as e:QMessageBox.warning(self,'Could not enable HTTPS',str(e))
    def refresh_phones(self):
        self.phones.clear();server=getattr(self.w,'mobile_server',None)
        if server:
            for phone in server.paired():self.phones.addItem(phone['label']+' • '+phone['id'][:6],phone['id'])
    def revoke_selected(self):
        server=getattr(self.w,'mobile_server',None);id=self.phones.currentData()
        if server and id:server.revoke_one(id);self.refresh_phones()
    def reset_certificate(self):
        if getattr(self.w,'mobile_server',None):QMessageBox.information(self,'Stop service first','Stop mobile access before resetting the certificate.');return
        if QMessageBox.question(self,'Reset certificate','Create a new certificate at next start and revoke all paired phones? Your phone must trust the new fingerprint.')!=QMessageBox.Yes:return
        folder=self.w.store.path.parent/'mobile'
        for name in ('mobile-cert.pem','mobile-key.dpapi','paired-devices.json'):(folder/name).unlink(missing_ok=True)
        self.info.setText('Certificate reset; paired phones revoked. Verify and trust the new fingerprint at next start.')
    def pair(self):
        server=getattr(self.w,'mobile_server',None)
        if server:self.info.setText(self.info.text().split('\nPairing code:')[0]+'\nPairing code: '+server.pair())
    def revoke(self):
        server=getattr(self.w,'mobile_server',None)
        if server:server.revoke();self.refresh_phones();self.info.setText('All paired phones revoked.')
    def stop(self):
        server=getattr(self.w,'mobile_server',None)
        if server:server.stop();self.w.mobile_server=None;self.info.setText('Mobile access stopped.')
