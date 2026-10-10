import os,json,base64,time
import pytest
from cryptography.exceptions import InvalidTag
from PySide6.QtWidgets import QApplication
from admin import studio_store as module
from admin.studio_store import StudioStore
from zee.licensing import verify

PASSWORD='fixture-owner-password-123'
BACKUP_PASSWORD='fixture-backup-password-123'

@pytest.fixture
def store(tmp_path,monkeypatch):
    # Explicit crypto fixture only; production protect() retains Windows-only fail-closed behaviour.
    monkeypatch.setattr(module,'protect',lambda raw,decrypt=False:raw)
    s=StudioStore(tmp_path/'studio');s.setup('owner',PASSWORD);token=s.login('owner',PASSWORD)
    yield s,token
    s.close()

def records(s,t):
    customer=s.save_record(t,'customers',{'name':'Test Network','contact':'Owner','notes':'Pilot'})
    package=s.save_record(t,'packages',{'name':'Professional','days':365,'max_devices':100,'features':['monitoring','map','wan']})
    profile=s.save_record(t,'profiles',{'name':'Pilot build','customer_id':customer,'package_id':package,'app_name':'Zee Network Monitor','watermark':'Created by Zeeshan Rasool','logo_png':''})
    return customer,package,profile

def test_owner_viewer_expiry_and_no_second_owner(store):
    s,t=store;s.add_viewer(t,'viewer','fixture-viewer-password');v=s.login('viewer','fixture-viewer-password')
    for action in [lambda:s.save_record(v,'customers',{'name':'Denied','contact':'','notes':''}),lambda:s.initialize_key(v),lambda:s.backup(v,BACKUP_PASSWORD),lambda:s.add_viewer(v,'new','fixture-new-password')]:
        with pytest.raises(PermissionError):action()
    assert not s.records(v,'customers')
    with pytest.raises(PermissionError):s.setup('other',PASSWORD)
    s.sessions[t]['expires']=0
    with pytest.raises(PermissionError):s.records(t,'customers')
    with pytest.raises(PermissionError):s.issue(v,'','','a'*64)

def test_failed_login_lockout_and_no_password_audit(store):
    s,t=store
    for _ in range(5):
        with pytest.raises(PermissionError):s.login('owner','incorrect-fixture-password')
    with pytest.raises(PermissionError,match='temporarily locked'):s.login('owner',PASSWORD)
    data=json.dumps(s.audit_rows(t));assert PASSWORD not in data and 'incorrect-fixture-password' not in data
    assert s.verify_audit()>=7

def test_customer_package_profile_to_real_client_signed_licence(store):
    s,t=store;customer,package,profile=records(s,t);public=s.initialize_key(t)
    id,doc=s.issue(t,customer,package,'a'*64,profile)
    assert verify(doc,public['public_key'],'a'*64)['customer']=='Test Network'
    with pytest.raises(ValueError):verify(doc,public['public_key'],'b'*64)
    s.revoke(t,id,'Owner recorded cancellation')
    assert s.licences(t)[0]['status'].startswith('Revoked in Studio')
    assert verify(doc,public['public_key'],'a'*64) # Offline copy honestly remains valid.
    profile_json=s.export_profile(t,profile)
    assert 'Pending Phase 8.2' in profile_json['client_application']
    assert set(profile_json['branding'])=={'app_name','watermark','logo_png'}
    assert 'private' not in json.dumps(profile_json)
    s.archive(t,'customers',customer)
    with pytest.raises(ValueError,match='archived'):s.issue(t,customer,package,'a'*64)
    s.archive(t,'customers',customer);assert s.record(t,'customers',customer)['name']=='Test Network'

def test_profile_refs_logo_bounds_and_unknown_secret_fields(store):
    s,t=store;c,p,id=records(s,t);data=s.record(t,'profiles',id)['data']
    with pytest.raises(ValueError):s.save_record(t,'profiles',data|{'password':'must-never-save'})
    with pytest.raises(ValueError):s.save_record(t,'profiles',data|{'customer_id':'missing'})
    with pytest.raises(ValueError):s.save_record(t,'profiles',data|{'logo_png':base64.b64encode(b'notPNG').decode()})
    with pytest.raises(ValueError):s.save_record(t,'packages',{'name':'Bad','days':1,'max_devices':True,'features':['unknown']})

def test_password_wrap_is_not_the_stored_verifier(store):
    s,t=store;public=s.initialize_key(t);raw=s.key(t).private_bytes_raw();file=s.keyfile.read_bytes()
    assert raw not in file and PASSWORD.encode() not in file
    envelope=json.loads(file);verifier=s.db.execute('SELECT verifier FROM users WHERE name=?',('owner',)).fetchone()[0]
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    with pytest.raises(InvalidTag):AESGCM(verifier).decrypt(base64.b64decode(envelope['nonce']),base64.b64decode(envelope['ciphertext']),b'ZeeAdminStudio issuer|owner')
    recovery=s.recovery_export(t,BACKUP_PASSWORD);s.keyfile.unlink();s.recovery_import(t,recovery,BACKUP_PASSWORD)
    assert s.key(t).public_key().public_bytes_raw()==base64.b64decode(public['public_key'])
    with pytest.raises(ValueError,match='cannot be overwritten'):s.recovery_import(t,recovery,BACKUP_PASSWORD)

def test_encrypted_backup_restore_wrong_password_and_checkpoint(store):
    s,t=store;c,p,profile=records(s,t);s.initialize_key(t);doc=s.issue(t,c,p,'a'*64,profile)[1]
    backup=s.backup(t,BACKUP_PASSWORD)
    assert b'Test Network' not in backup and PASSWORD.encode() not in backup
    s.save_record(t,'customers',{'name':'Added later','contact':'','notes':''})
    with pytest.raises(InvalidTag):s.restore(t,backup,'wrong-backup-password')
    assert len(s.records(t,'customers'))==2
    s.restore(t,backup,BACKUP_PASSWORD)
    with pytest.raises(PermissionError):s.records(t,'customers')
    token=s.login('owner',PASSWORD);assert len(s.records(token,'customers'))==1
    assert verify(doc,s.initialize_key(token)['public_key'],'a'*64)
    assert list(s.root.glob('pre-restore-*/studio.sqlite3')) and s.verify_audit()>0

def test_corrupt_audit_is_recovery_only_until_verified_restore(store):
    s,t=store;records(s,t);backup=s.backup(t,BACKUP_PASSWORD);s.logout(t)
    with s.db:s.db.execute("UPDATE audit SET detail='tampered' WHERE seq=1")
    with pytest.raises(ValueError):s.verify_audit()
    t=s.login('owner',PASSWORD)
    assert s.require(t,recovery=True)['recovery_only']
    with pytest.raises(PermissionError,match='Recovery-only'):s.save_record(t,'customers',{'name':'Denied','contact':'','notes':''})
    s.restore(t,backup,BACKUP_PASSWORD);t=s.login('owner',PASSWORD);assert s.verify_audit()>0 and not s.require(t)['recovery_only']

def test_studio_gui_records_viewer_and_lock(store):
    from admin.studio import Studio
    app=QApplication.instance() or QApplication([]);s,t=store;records(s,t);s.add_viewer(t,'viewer','fixture-viewer-password');s.logout(t)
    w=Studio(s);w.username.setText('owner');w.password.setText(PASSWORD);w.sign_in()
    try:
        assert w.stack.currentIndex()==1 and w.customers_table.rowCount()==1 and 'Customers: 1' in w.dashboard.text()
        assert not w.password.text();w.lock();assert w.stack.currentIndex()==0 and w.customers_table.rowCount()==0
        w.username.setText('viewer');w.password.setText('fixture-viewer-password');w.sign_in()
        assert all(not b.isEnabled() for b in w.owner_buttons)
        with pytest.raises(PermissionError):s.save_record(w.token,'customers',{'name':'Denied','contact':'','notes':''})
    finally:
        w.timer.stop();s.logout(w.token);w.token=None;w.hide() # Fixture closes the store.

@pytest.mark.skipif(os.name!='nt',reason='Actual Windows DPAPI issuer protection')
def test_actual_windows_studio_key_signing_and_restore(tmp_path):
    s=StudioStore(tmp_path/'native');s.setup('owner',PASSWORD);t=s.login('owner',PASSWORD)
    try:
        c,p,profile=records(s,t);public=s.initialize_key(t);doc=s.issue(t,c,p,'a'*64,profile)[1]
        assert verify(doc,public['public_key'],'a'*64)
        backup=s.backup(t,BACKUP_PASSWORD);s.restore(t,backup,BACKUP_PASSWORD);t=s.login('owner',PASSWORD)
        assert s.initialize_key(t)==public
    finally:s.close()
