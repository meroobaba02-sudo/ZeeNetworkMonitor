"""Recovery and real trusted-TLS acceptance without production signing credentials."""
import base64,json,time,ssl,http.client,threading
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from zee import licensing,mobile
from admin.issuer import issue_document
from tests.test_professional import tls_context

@pytest.fixture
def issuer(tmp_path,monkeypatch):
    key=Ed25519PrivateKey.generate();public=base64.b64encode(key.public_key().public_bytes_raw()).decode()
    path=tmp_path/'issuer-public.json';path.write_text(json.dumps({'public_key':public}))
    monkeypatch.setattr(licensing,'public_key_path',lambda:path)
    def grant(ref='original',**kw):return issue_document(key,licensing.fingerprint(),'Fixture','Professional',ref,**kw)
    return key,grant

def test_import_recovery_revalidates_and_deactivation_removes_backup(tmp_path,issuer):
    _,grant=issuer;source=tmp_path/'incoming.json';first=grant();source.write_text(json.dumps(first))
    licensing.import_licence(tmp_path,source)
    source.write_text(json.dumps(grant('renewal')));licensing.import_licence(tmp_path,source)
    assert licensing.status(tmp_path)['reference']=='renewal'
    (tmp_path/'license.json').write_text('broken')
    licensing.recover_licence(tmp_path)
    assert licensing.status(tmp_path)['reference']=='original'
    licensing.deactivate_licence(tmp_path)
    assert not (tmp_path/'license.previous.json').exists() and not licensing.status(tmp_path)['valid']

@pytest.mark.parametrize('kind',['wrong-machine','expired','tampered','oversized','boolean-version','wrong-profile'])
def test_rejected_import_preserves_existing_activation(tmp_path,issuer,monkeypatch,kind):
    key,grant=issuer;source=tmp_path/'incoming.json';original=grant();source.write_text(json.dumps(original));licensing.import_licence(tmp_path,source);before=(tmp_path/'license.json').read_bytes()
    candidate=grant('candidate')
    if kind=='wrong-machine':candidate['payload']['machine']='b'*64
    if kind=='expired':candidate['payload']['expires']=1
    if kind=='boolean-version':candidate['payload']['version']=True
    if kind in ('wrong-machine','expired','boolean-version'):candidate['signature']=base64.b64encode(key.sign(licensing.canonical(candidate['payload']))).decode()
    if kind=='tampered':candidate['payload']['reference']='changed'
    if kind=='wrong-profile':monkeypatch.setattr(licensing,'customer_profile',lambda:{'customer_id':'another','profile_id':'another'})
    source.write_text('x'*65537 if kind=='oversized' else json.dumps(candidate))
    with pytest.raises(Exception):licensing.import_licence(tmp_path,source)
    assert (tmp_path/'license.json').read_bytes()==before
    assert not (tmp_path/'license.json.new').exists()

def test_failed_atomic_import_keeps_activation(tmp_path,issuer,monkeypatch):
    _,grant=issuer;source=tmp_path/'incoming.json';source.write_text(json.dumps(grant()));licensing.import_licence(tmp_path,source);before=(tmp_path/'license.json').read_bytes();source.write_text(json.dumps(grant('next')))
    replace=Path.replace
    def fail(path,target):
        if path.name=='license.json.new':raise OSError('simulated disk failure')
        return replace(path,target)
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(OSError):licensing.import_licence(tmp_path,source)
    assert (tmp_path/'license.json').read_bytes()==before and not (tmp_path/'license.json.new').exists()

def test_recovery_rejects_expired_old_grant(tmp_path,issuer):
    _,grant=issuer;(tmp_path/'license.previous.json').write_text(json.dumps(grant(expires=1,now=0)))
    with pytest.raises(ValueError):licensing.recover_licence(tmp_path)
    assert not (tmp_path/'license.json').exists()

def test_certificate_stable_and_incomplete_state_fails_closed(tmp_path,monkeypatch):
    monkeypatch.setattr(mobile,'protect',lambda data,*args:data)
    _,first=mobile.certificate(tmp_path,'127.0.0.1');_,second=mobile.certificate(tmp_path,'127.0.0.1');assert first==second
    assert not (tmp_path/'mobile-key-loading.pem').exists()
    (tmp_path/'mobile-key.dpapi').unlink()
    with pytest.raises(ValueError,match='Incomplete'):mobile.certificate(tmp_path,'127.0.0.1')
    assert (tmp_path/'mobile-cert.pem').exists()

def test_certificate_protection_failure_leaves_no_half_identity(tmp_path,monkeypatch):
    def fail(*args):raise OSError('DPAPI failure')
    monkeypatch.setattr(mobile,'protect',fail)
    with pytest.raises(OSError):mobile.certificate(tmp_path,'127.0.0.1')
    assert not (tmp_path/'mobile-cert.pem').exists() and not (tmp_path/'mobile-key.dpapi').exists()

def test_mobile_stop_before_start_is_idempotent(tmp_path,tls_context):
    server=mobile.MobileServer(tmp_path,'127.0.0.1',0,tls_context[0]);thread=threading.Thread(target=lambda:(server.stop(),server.stop()),daemon=True);thread.start();thread.join(2)
    assert not thread.is_alive()
    with pytest.raises(ValueError):server.start()

@pytest.mark.parametrize('stored',[[],{'bad':{'expires':9999999999,'label':'Phone'}},{'a'*64:{'expires':'never','label':'Phone'}}])
def test_corrupt_phone_store_fails_closed(tmp_path,tls_context,stored):
    (tmp_path/'paired-devices.json').write_text(json.dumps(stored))
    with pytest.raises(ValueError):mobile.MobileServer(tmp_path,'127.0.0.1',0,tls_context[0])

def test_real_tls_restart_branding_rate_limit_and_disk_failure(tmp_path,tls_context,monkeypatch):
    ctx,client=tls_context
    server=mobile.MobileServer(tmp_path,'127.0.0.1',0,ctx,{'app_name':'Fixture <script>bad()</script>','watermark':'Owner & Customer'});server.start()
    def request(server,path,body=None,headers=None):
        connection=http.client.HTTPSConnection('127.0.0.1',server.server.server_address[1],context=client,timeout=3)
        try:
            connection.request('POST' if body is not None else 'GET',path,body,headers or {});response=connection.getresponse();return response.status,response.read(),response.getheader('Set-Cookie')
        finally:connection.close()
    try:
        page=request(server,'/')[1].decode();assert '&lt;script&gt;bad()&lt;/script&gt;' in page and 'Owner &amp; Customer' in page
        assert request(server,'/pair',json.dumps({'code':server.pair()}),{'Host':'attacker.invalid','Origin':'https://attacker.invalid'})[0]==403
        code=server.pair();persist=server.persist
        monkeypatch.setattr(server,'persist',lambda:(_ for _ in ()).throw(OSError('storage unavailable')))
        assert request(server,'/pair',json.dumps({'code':code}))[0]==503 and not server.tokens and server.code==code
        monkeypatch.setattr(server,'persist',persist)
        status,_,cookie=request(server,'/pair',json.dumps({'code':code}));assert status==200
        token=cookie.split(';')[0];server.stop();server=mobile.MobileServer(tmp_path,'127.0.0.1',0,ctx);server.start()
        assert request(server,'/api/status',headers={'Cookie':token})[0]==200
        for _ in range(5):assert request(server,'/pair','{"code":"wrong"}')[0]==403
        assert request(server,'/pair','{"code":"wrong"}')[0]==429
        server.revoke();assert request(server,'/api/status',headers={'Cookie':token})[0]==401
    finally:server.stop()

def test_structurally_valid_sqlite_with_bad_device_cannot_replace_live(tmp_path):
    import sqlite3
    from zee.core import Store,Device
    from zee.recovery import restore_pending
    s=Store(tmp_path/'monitor.sqlite3');s.save(Device(name='Original',host='127.0.0.1'));s.close()
    s=Store(tmp_path/'restore.pending.sqlite3');s.save(Device(name='Bad',host='127.0.0.1'));s.db.execute("UPDATE devices SET data='{}'");s.db.commit();s.close()
    with pytest.raises(ValueError):restore_pending(tmp_path)
    s=Store(tmp_path/'monitor.sqlite3');assert s.devices()[0].name=='Original';s.close()
    assert not (tmp_path/'before-restore.bak').exists()

def test_expired_pairings_pruned_and_limit_enforced(tmp_path,tls_context):
    tokens={'a'*64:{'expires':1,'label':'Expired'},'b'*64:{'expires':time.time()+1000,'label':'Retained'}}
    (tmp_path/'paired-devices.json').write_text(json.dumps(tokens));server=mobile.MobileServer(tmp_path,'127.0.0.1',0,tls_context[0])
    try:assert list(server.tokens)==['b'*64]
    finally:server.stop()
    tokens={f'{i:064x}':{'expires':time.time()+1000,'label':'Phone'} for i in range(65)}
    (tmp_path/'paired-devices.json').write_text(json.dumps(tokens))
    with pytest.raises(ValueError):mobile.MobileServer(tmp_path,'127.0.0.1',0,tls_context[0])

def test_reimport_same_grant_preserves_previous_recovery(tmp_path,issuer):
    _,grant=issuer;source=tmp_path/'incoming.json';source.write_text(json.dumps(grant()));licensing.import_licence(tmp_path,source)
    source.write_text(json.dumps(grant('new')));licensing.import_licence(tmp_path,source);saved=(tmp_path/'license.previous.json').read_bytes()
    licensing.import_licence(tmp_path,source);assert (tmp_path/'license.previous.json').read_bytes()==saved

def test_recovery_and_mobile_dialog_controls_fit_and_are_plain_text(tmp_path):
    from PySide6.QtWidgets import QApplication,QPushButton,QScrollArea
    from PySide6.QtCore import Qt
    from zee.core import Store
    from zee.gui import Window
    from zee.system_dialogs import LicenseDialog,MobileDialog
    app=QApplication.instance() or QApplication([]);s=Store(tmp_path/'ui.db');w=Window(s)
    try:
        licence=LicenseDialog(w);licence.show();app.processEvents()
        assert licence.label.textFormat()==Qt.PlainText and licence.label.height()>=licence.label.heightForWidth(licence.label.width())
        assert any(b.text()=='Recover previous valid licence' for b in licence.findChildren(QPushButton));licence.close()
        phone=MobileDialog(w);assert phone.info.textFormat()==Qt.PlainText and phone.findChild(QScrollArea).widgetResizable();phone.close()
    finally:w.close();s.close()
