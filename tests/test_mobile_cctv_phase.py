import os,time,ssl,http.client,json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from tests.test_professional import tls_context
from zee.mobile import MobileServer
from zee.cctv import camera_health
from zee.core import Device

def test_camera_service_is_not_video_or_ping_health():
    d=Device(service_url='rtsp://127.0.0.1/stream');now=time.time()
    assert 'Authentication required' in camera_health(d,{'at':now,'service':'RTSP authentication required (video not tested)'},now)
    assert camera_health(d,{'at':now-1000,'service':'RTSP service responding'},now)=='Unknown / stale'
    assert 'Service unavailable' in camera_health(d,{'at':now,'service':'Unavailable — timeout'},now)

def test_certificate_rejects_wrong_listen_address(tmp_path,monkeypatch):
    from zee import mobile
    monkeypatch.setattr(mobile,'protect',lambda data,*args:data)
    mobile.certificate(tmp_path,'127.0.0.1')
    with pytest.raises(ValueError,match='another IP'):mobile.certificate(tmp_path,'127.0.0.2')

def test_mobile_snapshot_has_tower_and_separate_service_status(tmp_path):
    from PySide6.QtWidgets import QApplication
    from zee.core import Store,TYPES
    from zee.gui import Window
    app=QApplication.instance() or QApplication([]);s=Store(tmp_path/'db');d=Device(name='Camera',host='127.0.0.1',kind=TYPES[4],service_url='rtsp://127.0.0.1/video');s.save(d);w=Window(s)
    class Sink:
        def update(self,data):self.data=data
    sink=Sink();w.mobile_server=sink
    try:
        w.measurements.latest[d.id]={'at':time.time(),'service':'RTSP service responding (video not tested)'}
        w.update_mobile();row=sink.data['devices'][0]
        assert row['status']=='Unknown' and 'Service responding' in row['service']
        assert 'tower_id' in row and row['download']=='Unavailable'
    finally:w.mobile_server=None;w.close();s.db.close()

def test_two_phone_sessions_individual_revocation_and_logout(tmp_path,tls_context):
    serverctx,clientctx=tls_context;server=MobileServer(tmp_path,'127.0.0.1',0,serverctx);server.start();port=server.server.server_address[1]
    def call(path,method='GET',body=None,cookie=None,origin=None):
        c=http.client.HTTPSConnection('127.0.0.1',port,context=clientctx);headers={}
        if cookie:headers['Cookie']=cookie
        if origin:headers['Origin']=origin
        try:c.request(method,path,body,headers);r=c.getresponse();data=r.read();return r.status,r.getheader('Set-Cookie'),data
        finally:c.close()
    try:
        cookies=[]
        for _ in range(2):
            status,cookie,_=call('/pair','POST',json.dumps({'code':server.pair()}));assert status==200;cookies.append(cookie.split(';')[0])
        phones=server.paired();assert len(phones)==2
        server.revoke_one(phones[0]['id'])
        assert call('/api/status',cookie=cookies[0])[0]==401 and call('/api/status',cookie=cookies[1])[0]==200
        assert call('/logout','POST',cookie=cookies[1],origin='https://wrong.example')[0]==403
        status,cookie,_=call('/logout','POST',cookie=cookies[1]);assert status==200 and 'Max-Age=0' in cookie
        assert call('/api/status',cookie=cookies[1])[0]==401
    finally:server.stop()
