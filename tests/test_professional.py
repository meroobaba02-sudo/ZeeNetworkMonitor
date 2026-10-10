import os,json,time,base64,ssl,threading,http.client,datetime
from pathlib import Path
from dataclasses import replace
import pytest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from zee.core import Store,Device,Station
from zee.workspaces import NetworkPage
from zee.telemetry import quality,counter_rates,validate_profile,normalized
from zee.licensing import verify,canonical,PRODUCT
from zee.connections import validate_url,service_check
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtWidgets import QApplication

@pytest.fixture
def app():return QApplication.instance() or QApplication([])

def test_pages_import_export_no_secrets_remapped_references(tmp_path):
    s=Store(tmp_path/'db');p=NetworkPage(id='second',name='Cameras');s.save_page(p)
    tower=Station(name='A',page_id=p.id);s.save_station(tower)
    a=Device(name='A',host='127.0.0.1',station_id=tower.id,page_id=p.id);s.save(a)
    b=Device(name='B',host='127.0.0.2',page_id=p.id,parent=a.id,peer_id=a.id);s.save(b)
    copy=s.import_page(s.export_page(p.id));ds=[d for d in s.devices() if d.page_id==copy.id]
    assert len(ds)==2 and all(not d.enabled for d in ds)
    assert ds[1].parent==ds[0].id and ds[1].peer_id==ds[0].id and ds[0].id!=a.id
    with pytest.raises(ValueError):s.save(Device(name='Wrong page',host='localhost',parent=a.id))
    s.delete_page(copy.id);assert len(s.devices())==2
    s.close();s=Store(tmp_path/'db');assert len(s.pages())==2;s.close()

def test_page_switch_stops_probes_and_hides_unrelated_devices(app,tmp_path):
    from zee.gui import Window
    s=Store(tmp_path/'db');s.save_page(NetworkPage(id='p2',name='CCTV'))
    a=Device(name='A',host='127.0.0.1');b=Device(name='B',host='127.0.0.1',page_id='p2');s.save(a);s.save(b)
    w=Window(s);w.engine.running=True;w.requested.add(a.id);w.page_picker.setCurrentIndex(w.page_picker.findData('p2'))
    assert not w.engine.running and not w.requested and [d.id for d in w.devices]==[b.id]
    assert w.table.rowCount()==1 and not w.buzzer.active
    assert w.store.setting('active_page')=='p2';w.close()

def test_multiple_add_towers_use_different_positions(app,tmp_path,monkeypatch):
    from zee.gui import Window
    import zee.mapview as module
    from PySide6.QtWidgets import QDialog
    def execute(dialog):dialog.name.setText('Tower '+str(len(dialog.parent().window.page_stations())+1));return QDialog.Accepted
    monkeypatch.setattr(module.TowerDialog,'exec',execute)
    w=Window(Store(tmp_path/'db'))
    for i in range(5):w.map_page.add_tower()
    towers=w.store.stations();assert len(towers)==5 and len({(s.map_x,s.map_y) for s in towers})==5
    w.close()

def test_quality_never_green_from_ping_and_counter_reset():
    assert quality({},{} )==(None,'Unknown')
    assert quality({'signal_dbm':-58,'tx_ccq':98},{})==(10,'Good')
    assert quality({'wireless_up':0},{})==(0,'Critical')
    assert quality({'signal_dbm':-58},{},age=1000)==(None,'Unknown')
    assert counter_rates({'in_octets':100},{'in_octets':1100},2)['download_mbps']==.004
    assert counter_rates({'in_octets':200},{'in_octets':10},2)=={}
    assert counter_rates({'in_octets':100,'counter_epoch':1},{'in_octets':200,'counter_epoch':2},2)=={}

@pytest.mark.parametrize('url',['file:///etc/passwd','http://user:secret@localhost','javascript:alert(1)','http://localhost:99999'])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):validate_url(url)

def test_profiles_reject_secrets_and_invalid_limits():
    with pytest.raises(ValueError):validate_profile({'password':'do not save'})
    with pytest.raises(ValueError):validate_profile({'speed_mb':100000})
    with pytest.raises(ValueError):validate_profile({'oids':{'signal_dbm':{'path':'shell command'}}})
    assert normalized({'radio':{'signal':'-65'}},{'signal_dbm':{'path':'radio/signal'}})=={'signal_dbm':-65}

def signed_license():
    key=Ed25519PrivateKey.generate();pub=base64.b64encode(key.public_key().public_bytes_raw()).decode()
    payload={'version':1,'product':PRODUCT,'machine':'a'*64,'activations':1,'issued':100,'expires':1000,'edition':'Professional'}
    return pub,{'payload':payload,'signature':base64.b64encode(key.sign(canonical(payload))).decode()}

def test_signed_licence_machine_expiry_tamper():
    pub,doc=signed_license();assert verify(doc,pub,'a'*64,500)['edition']=='Professional'
    with pytest.raises(ValueError):verify(doc,pub,'b'*64,500)
    with pytest.raises(ValueError):verify(doc,pub,'a'*64,1500)
    doc['payload']['expires']=99999
    with pytest.raises(Exception):verify(doc,pub,'a'*64,500)

@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI and native ICMP require Windows')
def test_windows_dpapi_and_source_bound_ping(tmp_path):
    from zee.credentials import Vault
    from zee.windows_ping import echo
    v=Vault(tmp_path/'vault');v.set('radio',{'password':'SECRET_TEST_VALUE'});assert 'SECRET_TEST_VALUE' not in (tmp_path/'vault').read_text();assert v.get('radio')['password']=='SECRET_TEST_VALUE'
    v.delete('radio');assert not v.get('radio')
    assert echo('127.0.0.1','127.0.0.1',1000).success

@pytest.fixture
def tls_context(tmp_path):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import hashes,serialization
    import ipaddress
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048);subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')]);now=datetime.datetime.now(datetime.timezone.utc)
    cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False).sign(key,hashes.SHA256())
    cp=tmp_path/'cert.pem';kp=tmp_path/'key.pem';cp.write_bytes(cert.public_bytes(serialization.Encoding.PEM));kp.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server.load_cert_chain(cp,kp);client=ssl.create_default_context(cafile=str(cp));return server,client

def test_mobile_https_pairing_authentication_expiry_revocation(tmp_path,tls_context):
    from zee.mobile import MobileServer
    serverctx,clientctx=tls_context;server=MobileServer(tmp_path,'127.0.0.1',0,serverctx);server.start();port=server.server.server_address[1]
    def request(path,method='GET',body=None,headers=None):
        c=http.client.HTTPSConnection('127.0.0.1',port,context=clientctx,timeout=3)
        try:c.request(method,path,body,headers or {});r=c.getresponse();return r.status,r.read(),r.getheader('Set-Cookie')
        finally:c.close()
    try:
        assert request('/api/status')[0]==401
        code=server.pair();status,body,cookie=request('/pair','POST',json.dumps({'code':code}),{'Content-Type':'application/json'});assert status==200 and 'HttpOnly' in cookie
        assert request('/pair','POST',json.dumps({'code':code}))[0]==403
        assert request('/api/status',headers={'Cookie':cookie.split(';')[0]})[0]==200
        server.revoke();assert request('/api/status',headers={'Cookie':cookie.split(';')[0]})[0]==401
        code=server.pair();server.code_until=0;assert request('/pair','POST',json.dumps({'code':code}))[0]==403
    finally:server.stop()

def test_service_check_distinct_from_ping():
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):self.send_response(401);self.send_header('Content-Length','0');self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever);thread.start()
    try:assert 'Authentication required' in service_check(f'http://127.0.0.1:{server.server_port}/')
    finally:server.shutdown();server.server_close();thread.join()

def test_measurements_do_not_accept_result_from_previous_network(app,tmp_path):
    from zee.gui import Window
    s=Store(tmp_path/'db');d=Device(name='Radio',host='127.0.0.1');s.save(d);w=Window(s)
    generation=w.engine.generation;w.engine.invalidate()
    w.measurements.complete((d,False,generation),{'at':time.time(),'metrics':{'signal_dbm':-55}})
    assert not w.measurements.latest and not s.measurements(d.id);w.close()

def test_actual_tower_drag_saves_without_local_replace_error(app,tmp_path):
    from types import SimpleNamespace
    from PySide6.QtCore import QPointF
    from zee.gui import Window
    s=Store(tmp_path/'db');tower=Station(name='Drag me');s.save_station(tower);w=Window(s);w.show();app.processEvents();canvas=w.map_page.canvas;canvas.grab()
    point=canvas.station_boxes[tower.id].center()
    canvas.mousePressEvent(SimpleNamespace(position=lambda:point))
    target=point+QPointF(30,25)
    canvas.mouseMoveEvent(SimpleNamespace(position=lambda:target))
    canvas.mouseReleaseEvent(SimpleNamespace())
    saved=s.stations()[0];assert saved.latitude is not None and (saved.map_x,saved.map_y)!=(.5,.5);w.close()

def test_actual_snmp_adapter_against_local_protocol_fixture():
    import socket,asyncio
    from pyasn1.codec.ber import decoder,encoder
    from pysnmp.proto.api import v2c
    from zee.telemetry import snmp_fetch
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.settimeout(5)
    errors=[]
    def serve():
        try:
            raw,addr=sock.recvfrom(65535);msg,_=decoder.decode(raw,asn1Spec=v2c.Message());reply=v2c.apiMessage.get_response(msg);pdu=v2c.apiMessage.get_pdu(reply)
            v2c.apiPDU.set_varbinds(pdu,[('1.3.6.1.2.1.1.3.0',v2c.Integer(-65))]);sock.sendto(encoder.encode(reply),addr)
        except Exception as e:errors.append(e)
    thread=threading.Thread(target=serve);thread.start()
    d=Device(host='127.0.0.1',integration={'method':'snmp','allow_v2c':True,'snmp_port':sock.getsockname()[1],'oids':{'signal_dbm':{'path':'1.3.6.1.2.1.1.3.0'}}})
    try:assert asyncio.run(snmp_fetch(d,{'community':'fixture-only'}))=={'signal_dbm':-65}
    finally:thread.join();sock.close()
    assert not errors

def test_controlled_https_speed_and_external_check(tls_context,monkeypatch):
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    from zee import connections,telemetry
    serverctx,clientctx=tls_context
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):
            body=b'fixture-internet-marker' if self.path=='/check' else b'x'*1048576
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.socket=serverctx.wrap_socket(server.socket,server_side=True);thread=threading.Thread(target=server.serve_forever);thread.start()
    def connection(url,source='',timeout=5):
        u=connections.validate_url(url);return http.client.HTTPSConnection(u.hostname,u.port,context=clientctx,source_address=(source,0) if source else None,timeout=timeout),u.path
    monkeypatch.setattr(connections,'connection',connection);monkeypatch.setattr(telemetry,'connection',connection)
    url=f'https://127.0.0.1:{server.server_port}'
    p={'wan_verified':True,'internet_url':url+'/check','internet_marker':'fixture-internet-marker','speed_url':url+'/bytes','speed_mb':1,'speed_seconds':5}
    try:
        assert telemetry.internet_check(p,'127.0.0.1')=='Online'
        assert telemetry.internet_check(p|{'wan_verified':False},'127.0.0.1')=='Not independently measurable'
        result=telemetry.speed_test(p,'127.0.0.1');assert result['bytes']==1048576 and result['download_mbps']>0
    finally:server.shutdown();server.server_close();thread.join()

def test_compiled_mib_loader_format(tmp_path):
    import sys
    from pysnmp.smi.builder import DirMibSource
    from zee.snmp_runtime import install
    install()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from compile_runtime_mibs import compile_mibs
    source=tmp_path/'TEST.py';source.write_text('answer=42')
    entries=compile_mibs([('pysnmp/smi/mibs/TEST.py',str(source),'DATA')],tmp_path/'out')
    dest=Path(entries[0][1]);code,_=DirMibSource(str(dest.parent)).read('TEST');scope={};exec(code,scope);assert scope['answer']==42
    import runpy
    assert runpy.run_path(str(dest))['answer']==42
