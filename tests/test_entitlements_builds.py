import base64,json,uuid,copy
from dataclasses import asdict
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import InvalidSignature
from PySide6.QtWidgets import QApplication
from zee import licensing
from zee.entitlements import Policy,from_status,validate
from zee.build_profile import verify_profile,digest
from zee.core import Store,Device,TYPES,Station
from admin.issuer import issue_document
from admin.customer_build import verify_report,hash_file
from zee.updates import verify_update

@pytest.fixture
def signed(tmp_path,monkeypatch):
    key=Ed25519PrivateKey.generate();public=base64.b64encode(key.public_key().public_bytes_raw()).decode()
    p={'type':'zee-customer-build','version':1,'product':licensing.PRODUCT,'profile_id':str(uuid.uuid4()),'customer_id':str(uuid.uuid4()),'package_id':str(uuid.uuid4()),'customer':'Fixture customer','branding':{'app_name':'Fixture Network','watermark':'Fixture owner','logo_png':''},'entitlements':{'features':['monitoring','map'],'max_devices':2}}
    doc={'payload':p,'signature':base64.b64encode(key.sign(licensing.canonical(p))).decode()}
    assets=tmp_path/'assets';assets.mkdir();(assets/'issuer-public.json').write_text(json.dumps({'public_key':public}));(assets/'customer-profile.json').write_text(json.dumps(doc))
    monkeypatch.setattr(licensing,'public_key_path',lambda:assets/'issuer-public.json');monkeypatch.setattr(licensing,'EXPECTED_PROFILE_SHA256',digest(doc));monkeypatch.setattr(licensing,'REQUIRE_ISSUER',True);monkeypatch.setattr(licensing,'fingerprint',lambda:'a'*64)
    return key,public,p,doc,assets

def test_v2_signed_ceilings_legacy_and_wrong_profile(signed,tmp_path):
    key,public,p,doc,assets=signed
    license=issue_document(key,'a'*64,'Fixture','Package','reference',entitlements={'features':['monitoring','map','wan'],'max_devices':5},customer_id=p['customer_id'],profile_id=p['profile_id'])
    (tmp_path/'license.json').write_text(json.dumps(license));state=licensing.status(tmp_path);assert state['valid']
    policy=from_status(state,licensing.customer_profile());assert policy.max_devices==2 and policy.allows('map') and not policy.allows('wan')
    license=issue_document(key,'a'*64,'Fixture','Package','reference',entitlements=p['entitlements'],customer_id=str(uuid.uuid4()),profile_id=p['profile_id']);(tmp_path/'license.json').write_text(json.dumps(license));assert not licensing.status(tmp_path)['valid']
    old=issue_document(key,'a'*64,'Old','Professional','reference');assert licensing.verify(old,public,'a'*64)['version']==1
    assert from_status(licensing.verify(old,public,'a'*64)|{'valid':True}).allows('wan')
    (tmp_path/'license.json').write_text(json.dumps(old));assert not licensing.status(tmp_path)['valid']

def test_customer_profile_pinned_tamper_missing_key_fails_closed(signed,tmp_path):
    key,public,p,doc,assets=signed
    assert licensing.branding()['app_name']=='Fixture Network'
    changed=copy.deepcopy(doc);changed['payload']['branding']['app_name']='Changed'
    with pytest.raises(InvalidSignature):verify_profile(changed,public)
    changed['signature']=base64.b64encode(key.sign(licensing.canonical(changed['payload']))).decode();(assets/'customer-profile.json').write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='changed'):licensing.customer_profile()
    (assets/'customer-profile.json').unlink();assert not licensing.status(tmp_path)['valid']
    (assets/'issuer-public.json').unlink();assert licensing.status(tmp_path)['production'] and not licensing.status(tmp_path)['valid']

def test_limits_cannot_be_bypassed_by_save_import_or_edit(tmp_path):
    s=Store(tmp_path/'monitor.db');s.policy=Policy(frozenset(['monitoring']),1)
    d=Device(name='First',host='192.0.2.1',kind=TYPES[2]);s.save(d)
    with pytest.raises(ValueError,match='limit'):s.save(Device(name='Second',host='192.0.2.2',kind=TYPES[2]))
    d.name='Updated';s.save(d);assert s.devices()[0].name=='Updated'
    with pytest.raises(ValueError):s.save_station(Station(name='Tower'))
    exported=s.export_page('default');pages=len(s.pages())
    with pytest.raises(ValueError,match='limit'):s.import_page(exported)
    assert len(s.pages())==pages and len(s.devices())==1
    s.delete(d.id);s.save(Device(name='Replacement',host='192.0.2.3',kind=TYPES[2]));s.db.close()

def test_existing_records_retained_workers_blocked_and_restricted_ui(tmp_path,monkeypatch):
    from zee.gui import Window
    from zee.engine import Engine
    from zee.ping import Result
    app=QApplication.instance() or QApplication([]);s=Store(tmp_path/'monitor.db')
    first=Device(name='One',host='192.0.2.1',kind=TYPES[2]);second=Device(name='Two',host='192.0.2.2',kind=TYPES[2]);wan=Device(name='Modem',host='192.0.2.3',kind=TYPES[0]);s.save(first);s.save(second);s.save(wan)
    w=Window(s)
    try:
        policy=Policy(frozenset(['monitoring']),1);w.policy=policy;s.policy=policy;w.apply_package_ui();w.reload()
        assert len(s.devices())==3 and [d.id for d in w.monitor_devices()]==[first.id]
        assert not w.engine.submit(second) and not w.engine.submit(wan)
        assert not w.measurements.submit(wan,True) and not w.tabs.isTabEnabled(0) and not w.tabs.isTabEnabled(7)
        assert w.state(second)=='Package restricted'
        w.tabs.setCurrentIndex(7);assert w.tabs.currentIndex()==8
        w.policy=Policy(frozenset(),0,False);s.policy=w.policy;w.apply_package_ui();assert not w.engine.submit(first)
    finally:w.close();s.db.close()

def test_entitlements_invalid_boolean_unknown_and_malformed():
    for v in [{'features':['unknown'],'max_devices':5},{'features':['map','map'],'max_devices':1},{'features':['map'],'max_devices':True},{'features':None,'max_devices':1}]:
        with pytest.raises(ValueError):validate(v)

def test_build_hash_history_and_update_signature(signed,tmp_path):
    key,public,p,doc,assets=signed
    artifact=tmp_path/'fixture-setup.exe';artifact.write_bytes(b'fixture-not-an-executable')
    entry={'name':artifact.name,'sha256':hash_file(artifact),'bytes':artifact.stat().st_size,'kind':'installer'}
    report={'type':'zee-customer-build-result','status':'passed','version':'0.4.15','profile_id':p['profile_id'],'profile_document':doc,'issuer_public':{'public_key':public},'checks':{'tests':True,'frozen_launch':True,'content_audit':True},'artifacts':[entry]}
    assert verify_report(report,tmp_path)==report
    payload={'type':'zee-offline-update','version':1,'product':licensing.PRODUCT,'profile_id':p['profile_id'],'app_version':'0.4.15','filename':artifact.name,'sha256':entry['sha256'],'bytes':entry['bytes']}
    update={'payload':payload,'signature':base64.b64encode(key.sign(licensing.canonical(payload))).decode()}
    assert verify_update(update,public,p['profile_id'],'0.4.14',artifact)['app_version']=='0.4.15'
    with pytest.raises(ValueError):verify_update(update,public,str(uuid.uuid4()),'0.4.14',artifact)
    with pytest.raises(ValueError):verify_update(update,public,p['profile_id'],'0.4.15',artifact)
    artifact.write_bytes(b'fixture-altered')
    with pytest.raises(ValueError):verify_report(report,tmp_path)
    with pytest.raises(ValueError):verify_update(update,public,p['profile_id'],'0.4.14',artifact)

def test_applied_logo_branding_and_backend_mobile_report_denial(signed,tmp_path,monkeypatch):
    from PySide6.QtCore import QBuffer,QIODevice
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtWidgets import QMessageBox,QFileDialog
    from zee.gui import Window
    from zee.system_dialogs import MobileDialog
    key,public,p,doc,assets=signed;app=QApplication.instance() or QApplication([])
    image=QImage(8,8,QImage.Format_ARGB32);image.fill(QColor('cyan'));buffer=QBuffer();buffer.open(QIODevice.WriteOnly);image.save(buffer,'PNG');p['branding']['logo_png']=base64.b64encode(bytes(buffer.data())).decode();doc['signature']=base64.b64encode(key.sign(licensing.canonical(p))).decode();(assets/'customer-profile.json').write_text(json.dumps(doc));monkeypatch.setattr(licensing,'EXPECTED_PROFILE_SHA256',digest(doc))
    licence=issue_document(key,'a'*64,'Fixture','Package','reference',entitlements=p['entitlements'],customer_id=p['customer_id'],profile_id=p['profile_id']);(tmp_path/'license.json').write_text(json.dumps(licence));s=Store(tmp_path/'monitor.db');w=Window(s)
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:None);monkeypatch.setattr(QMessageBox,'information',lambda *a:None)
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:pytest.fail('Reports must be denied before choosing a file'))
    try:
        assert w.windowTitle().startswith('Fixture Network') and w.watermark.text()=='Fixture owner' and w.policy.max_devices==2
        assert w.branding['logo_png'] and not w.policy.allows('reports');w.export('blocked.csv',[],[])
        dialog=MobileDialog(w);dialog.start();assert not getattr(w,'mobile_server',None) and not (tmp_path/'mobile').exists();dialog.close()
    finally:w.close();s.db.close()
