import os,json,time,threading,http.client
import pytest
from zee import telemetry,wan_paths,connections
from zee.core import Store,Device
from zee.gui import Window
from test_professional import tls_context,app

@pytest.mark.parametrize('gateway',['host.example','0.0.0.0','ff02::1','fe80::1%4'])
def test_gateway_must_be_literal_unscoped_unicast(gateway):
    with pytest.raises(ValueError):telemetry.validate_profile({'speed_gateway':gateway})

def test_guard_checks_actual_socket_and_refuses_wrong_gateway(monkeypatch):
    events=[]
    class Socket:
        def getpeername(self):return ('203.0.113.4',443)
        def getsockname(self):return ('192.168.1.50',45678)
    class Connection:
        sock=Socket()
        def connect(self):events.append('connect')
        def close(self):events.append('close')
    monkeypatch.setattr(wan_paths,'connection',lambda *a:(Connection(),'/bytes'))
    def route(remote,local):
        assert (remote,local)==('203.0.113.4','192.168.1.50')
        return {'gateway':'192.168.1.1','source':local,'remote':remote,'interface':4}
    monkeypatch.setattr(wan_paths,'find_route',route)
    with pytest.raises(wan_paths.PathUnavailable,match='Wrong Internet gateway'):
        wan_paths.checked_factory('192.168.1.2',[])('https://example.test','',5)
    assert events==['connect','close']
    evidence=[];c,_=wan_paths.checked_factory('192.168.1.1',evidence)('https://example.test','',5)
    assert c.auto_open==0 and evidence[0]['gateway']=='192.168.1.1'

@pytest.mark.parametrize('ack',[1048576,1048575,True])
def test_real_https_upload_receiver_exact_ack(tls_context,monkeypatch,ack):
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    serverctx,clientctx=tls_context;seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            data=self.rfile.read(int(self.headers['Content-Length']));seen.append(len(data))
            body=json.dumps({'received_bytes':ack}).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.socket=serverctx.wrap_socket(server.socket,server_side=True);thread=threading.Thread(target=server.serve_forever);thread.start()
    def connect(url,source,timeout):
        u=connections.validate_url(url);return http.client.HTTPSConnection(u.hostname,u.port,context=clientctx,timeout=timeout),u.path
    p={'wan_verified':True,'upload_url':f'https://127.0.0.1:{server.server_port}/upload','upload_mb':1,'speed_seconds':5}
    try:
        if ack==1048576 and not isinstance(ack,bool):
            result=telemetry.upload_test(p,connection_fn=connect);assert result['upload_bytes']==1048576 and result['upload_mbps']>0
        else:
            with pytest.raises(ValueError,match='acknowledge'):telemetry.upload_test(p,connection_fn=connect)
        assert seen==[1048576]
    finally:server.shutdown();server.server_close();thread.join()

def test_upload_cancel_before_payload(monkeypatch):
    class C:
        closed=False
        def close(self):self.closed=True
    c=C();cancel=threading.Event();cancel.set()
    with pytest.raises(ValueError,match='cancelled'):telemetry.upload_test({'wan_verified':True,'upload_url':'https://example.test'},cancel=cancel,connection_fn=lambda *a:(c,'/'))
    assert c.closed

def test_seven_rows_separate_live_test_and_no_default_copy(app,tmp_path):
    s=Store(tmp_path/'db');d=Device(name='WAN1',kind='WAN / Internet',host='127.0.0.1');s.save(d);w=Window(s)
    try:
        p=w.seven_wan;assert p.table.rowCount()==7
        w.measurements.latest[d.id]={'at':time.time(),'download_mbps':12,'upload_mbps':3}
        w.measurements.speed_latest[d.id]={'at':time.time(),'download_mbps':90,'upload_mbps':20,'path_checked':True}
        p.refresh();assert p.table.item(0,2).text()=='12.00' and p.table.item(0,4).text()=='90.00'
        assert p.table.item(1,4).text()=='—'
        w.measurements.speed_latest[d.id].pop('path_checked');p.refresh();assert p.table.item(0,4).text()=='Unavailable'
        w.measurements.latest[d.id]['at']=0;p.refresh();assert p.table.item(0,2).text()=='Unavailable'
    finally:w.close();s.close()

def test_batch_serial_and_cancel(app,tmp_path,monkeypatch):
    s=Store(tmp_path/'db')
    for i in range(7):s.save(Device(name=f'WAN{i}',kind='WAN / Internet',host=f'127.0.0.{i+1}'))
    w=Window(s);calls=[];m=w.measurements
    def submit(d,speed=False,independent=False):
        assert independent and speed and not m.pending
        calls.append(d.id);m.pending[(d.id,True)]=d;m.speed_cancels[d.id]=threading.Event();return True
    monkeypatch.setattr(m,'submit',submit)
    try:
        p=w.seven_wan;p.test_all();assert len(calls)==1 and len(p.queue)==6
        p.tick();assert len(calls)==1
        first=p.active;m.pending.clear();m.speed_latest[first.id]={'at':time.time(),'path_checked':True,'download_mbps':10};p.tick();assert len(calls)==2
        event=m.speed_cancels[p.active.id];p.cancel_tests();assert not p.queue and event.is_set() and not m.cancel.is_set()
    finally:m.pending.clear();w.close();s.close()

def test_upload_download_budget_combined_before_worker(app,tmp_path,monkeypatch):
    s=Store(tmp_path/'db');d=Device(name='WAN',host='127.0.0.1',wan=1,integration={'wan_verified':True,'speed_gateway':'127.0.0.1','speed_url':'https://example.test/bytes','upload_url':'https://example.test/upload','speed_mb':1,'upload_mb':2,'daily_mb':2});s.save(d);w=Window(s)
    try:
        with pytest.raises(ValueError,match='budget'):w.measurements.submit(d,True,independent=True)
        assert not w.measurements.pending
    finally:w.close();s.close()

@pytest.mark.skipif(os.name!='nt',reason='Actual Windows read-only routing API')
def test_windows_actual_socket_route_query():
    # Loopback is deliberately on-link: it must not be accepted as a modem gateway.
    row=wan_paths.find_route('127.0.0.1','127.0.0.1')
    assert row['gateway']=='0.0.0.0' and row['source']=='127.0.0.1' and row['interface']>0

def test_independent_download_and_upload_on_checked_tls_sockets(tls_context,monkeypatch):
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    serverctx,clientctx=tls_context;requests=[];routes=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):
            requests.append('GET');body=b'x'*1048576;self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            requests.append('POST');n=len(self.rfile.read(int(self.headers['Content-Length'])));body=json.dumps({'received_bytes':n}).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.socket=serverctx.wrap_socket(server.socket,server_side=True);thread=threading.Thread(target=server.serve_forever);thread.start()
    def connect(url,source,timeout):
        u=connections.validate_url(url);return http.client.HTTPSConnection(u.hostname,u.port,context=clientctx,timeout=timeout),u.path
    def route(remote,local):
        routes.append((remote,local));return {'source':local,'remote':remote,'gateway':'192.0.2.1','interface':4}
    monkeypatch.setattr(wan_paths,'connection',connect);monkeypatch.setattr(wan_paths,'find_route',route)
    base=f'https://127.0.0.1:{server.server_port}';p={'wan_verified':True,'speed_gateway':'192.0.2.1','speed_url':base+'/bytes','upload_url':base+'/upload'}
    try:
        result=telemetry.independent_speed_test(p)
        assert result['path_checked'] and result['bytes']==result['upload_bytes']==1048576
        assert result['download_mbps']>0 and result['upload_mbps']>0 and len(result['route_evidence'])==2
        assert requests==['GET','POST'] and routes==[('127.0.0.1','127.0.0.1')]*2
        with pytest.raises(wan_paths.PathUnavailable,match='Wrong Internet gateway'):telemetry.independent_speed_test(p|{'speed_gateway':'192.0.2.2'})
        assert requests==['GET','POST']
    finally:server.shutdown();server.server_close();thread.join()

def test_manual_counter_poll_all_reaches_seven_with_bounded_queue(app,tmp_path,monkeypatch):
    s=Store(tmp_path/'db')
    for i in range(7):s.save(Device(name=f'WAN{i}',kind='WAN / Internet',host=f'127.0.0.{i+1}'))
    w=Window(s);seen=[]
    monkeypatch.setattr(w,'drain',lambda:None)
    monkeypatch.setattr(w.measurements,'submit',lambda d:seen.append(d.id) or True)
    try:
        p=w.seven_wan;p.poll()
        for _ in range(7):p.tick()
        assert len(set(seen))==7 and not p.poll_queue and not w.measurements.enabled
    finally:w.close();s.close()
