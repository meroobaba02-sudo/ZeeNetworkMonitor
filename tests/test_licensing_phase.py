import os,json,base64
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from admin.issuer import issue_document,activation_request,read_request,write_atomic
from zee import licensing

def test_activation_request_has_no_credentials_or_topology():
    doc=activation_request('a'*64)
    assert set(doc)=={'type','version','product','machine'}
    assert read_request(doc)=='a'*64
    with pytest.raises(ValueError):read_request({'type':'other'})

def test_explicit_expiry_perpetual_wrong_machine_and_boolean_activation():
    key=Ed25519PrivateKey.generate();public=base64.b64encode(key.public_key().public_bytes_raw()).decode()
    doc=issue_document(key,'a'*64,'Customer','Professional','ref',expires=200,now=100)
    assert licensing.verify(doc,public,'a'*64,150)['expires']==200
    with pytest.raises(ValueError):licensing.verify(doc,public,'b'*64,150)
    with pytest.raises(ValueError):licensing.verify(doc,public,'a'*64,201)
    perpetual=issue_document(key,'a'*64,'Customer','Professional','ref',days=0,now=100)
    assert licensing.verify(perpetual,public,'a'*64,10000)['expires'] is None
    perpetual['payload']['activations']=True;perpetual['signature']=base64.b64encode(key.sign(licensing.canonical(perpetual['payload']))).decode()
    with pytest.raises(ValueError):licensing.verify(perpetual,public,'a'*64,10000)

def test_encrypted_recovery_roundtrip_and_atomic_file(tmp_path):
    key=Ed25519PrivateKey.generate();password=b'fixture-only-password'
    raw=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(password))
    path=tmp_path/'recovery.pem';write_atomic(path,raw)
    restored=serialization.load_pem_private_key(path.read_bytes(),password)
    assert restored.public_key().public_bytes_raw()==key.public_key().public_bytes_raw()
    assert not path.with_name(path.name+'.new').exists()
    with pytest.raises(ValueError):serialization.load_pem_private_key(raw,b'wrong')

def test_status_reports_invalid_customer_mode_without_evaluation_message(tmp_path,monkeypatch):
    key=Ed25519PrivateKey.generate();public=base64.b64encode(key.public_key().public_bytes_raw()).decode();path=tmp_path/'public.json';path.write_text(json.dumps({'public_key':public}))
    monkeypatch.setattr(licensing,'public_key_path',lambda:path)
    state=licensing.status(tmp_path)
    assert state['production'] and not state['valid'] and state['reason']=='Licence file missing.'

def test_owner_manager_and_license_status_render(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from admin.license_manager import Manager
    from zee.core import Store
    from zee.gui import Window
    from zee.system_dialogs import LicenseDialog
    app=QApplication.instance() or QApplication([]);monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    manager=Manager();assert 'not initialized' in manager.key_status.text();manager.close()
    store=Store(tmp_path/'app.db');w=Window(store);dialog=LicenseDialog(w)
    assert 'Owner evaluation' in dialog.label.text()
    dialog.close();w.close();store.db.close()
