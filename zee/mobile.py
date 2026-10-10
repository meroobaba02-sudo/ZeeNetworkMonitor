"""Opt-in read-only HTTPS dashboard. No port forwarding, relay or device writes."""
import json,secrets,hashlib,time,threading,ssl,ipaddress,datetime
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes,serialization
from .credentials import protect

HTML='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Zee Network Monitor</title><style>body{background:#081c2b;color:#dce9f5;font:16px system-ui;max-width:960px;margin:auto;padding:16px}input,button,select{padding:10px;margin:4px;border-radius:8px;max-width:100%;box-sizing:border-box}article{background:#123047;border-radius:12px;padding:14px;margin:10px 0;border-left:4px solid #98b3c8}small{color:#98b3c8}.filters{display:flex;flex-wrap:wrap}#alerts{white-space:pre-wrap}</style></head><body><h1>Zee Network Monitor</h1><p>Read-only mobile dashboard</p><div id="pair"><input id="code" placeholder="Pairing code from PC"><button id="connect">Pair phone</button></div><p id="message"></p><div class="filters"><select id="pages"></select><select id="towers"></select><input id="search" placeholder="Search name or IP"><button id="refresh">Refresh</button><button id="logout">Logout this phone</button></div><p id="summary"></p><main id="devices"></main><h3>Recent alerts / events</h3><div id="alerts"></div><small>Created by Zeeshan Rasool</small><script>\nconst el=id=>document.getElementById(id);let snapshot=null;el(\'pages\').add(new Option(\'All networks\',\'\'));el(\'towers\').add(new Option(\'All towers\',\'\'));\nfunction clear(){snapshot=null;el(\'devices\').replaceChildren();el(\'alerts\').textContent=\'\';el(\'summary\').textContent=\'\';el(\'pair\').hidden=false;}\nel(\'connect\').onclick=async()=>{try{let r=await fetch(\'/pair\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({code:el(\'code\').value})});el(\'message\').textContent=r.ok?\'Phone paired\':\'Pairing rejected or expired\';el(\'code\').value=\'\';if(r.ok)load()}catch(e){el(\'message\').textContent=\'PC unreachable\'}};\nel(\'logout\').onclick=async()=>{try{let r=await fetch(\'/logout\',{method:\'POST\'});if(r.ok||r.status===401){clear();el(\'message\').textContent=\'Logged out\'}}catch(e){el(\'message\').textContent=\'Cannot log out: PC unreachable\'}};\nfunction matches(d){return (!el(\'pages\').value||d.page===el(\'pages\').value)&&(!el(\'towers\').value||d.tower_id===el(\'towers\').value)&&(!el(\'search\').value||((d.name||\'\')+\' \'+(d.host||\'\')).toLowerCase().includes(el(\'search\').value.toLowerCase()));}\nfunction towers(){let selected=el(\'towers\').value;el(\'towers\').replaceChildren(new Option(\'All towers\',\'\'));let ids=new Set();for(const d of snapshot.devices){if(d.tower_id&&!ids.has(d.tower_id)&&(!el(\'pages\').value||d.page===el(\'pages\').value)){ids.add(d.tower_id);el(\'towers\').add(new Option(d.tower,d.tower_id))}}el(\'towers\').value=[...el(\'towers\').options].some(o=>o.value===selected)?selected:\'\';}\nfunction draw(){if(!snapshot)return;el(\'devices\').replaceChildren();let devices=snapshot.devices.filter(matches);el(\'summary\').textContent=devices.length+\' devices • \'+devices.filter(d=>d.status===\'Online\').length+\' ping online • \'+devices.filter(d=>d.status===\'No reply\').length+\' no reply\';for(const d of devices){let a=document.createElement(\'article\');let h=document.createElement(\'h3\');h.textContent=d.name+\' — \'+d.status;a.append(h);let p=document.createElement(\'p\');p.textContent=d.host+\' | \'+d.network+\' / \'+(d.tower||\'No tower\')+\' | Internet: \'+d.internet+\' | WAN: \'+d.wan_health+\' | Wireless: \'+d.quality+\' | CCTV service: \'+d.service+\' | Download: \'+d.download+\' | Upload: \'+d.upload;a.append(p);el(\'devices\').append(a)}let visible=new Set(devices.map(d=>d.id));el(\'alerts\').textContent=snapshot.events.filter(e=>visible.has(e.device)).map(e=>e.time+\' • \'+e.message).join(\'\\n\')||\'No retained matching events\';}\nasync function load(){try{let r=await fetch(\'/api/status\',{cache:\'no-store\'});if(!r.ok){clear();el(\'message\').textContent=\'Pairing required or revoked\';return}snapshot=await r.json();el(\'pair\').hidden=true;let selected=el(\'pages\').value;el(\'pages\').replaceChildren(new Option(\'All networks\',\'\'));for(let p of snapshot.pages)el(\'pages\').add(new Option(p.name,p.id));el(\'pages\').value=[...el(\'pages\').options].some(o=>o.value===selected)?selected:\'\';towers();el(\'message\').textContent=\'Updated \'+new Date(snapshot.at*1000).toLocaleTimeString()+\' • only PC-selected network is actively checked\';draw()}catch(e){el(\'message\').textContent=\'PC unreachable • displayed values are last snapshot, not live\';}}\nel(\'pages\').onchange=()=>{if(snapshot)towers();draw()};el(\'towers\').onchange=draw;el(\'search\').oninput=draw;el(\'refresh\').onclick=load;load();setInterval(load,5000);\n</script></body></html>\n'

def certificate(folder,host):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);cert=folder/'mobile-cert.pem';keyfile=folder/'mobile-key.dpapi'
    if not cert.exists() or not keyfile.exists():
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Zee Network Monitor local dashboard')]);now=datetime.datetime.now(datetime.timezone.utc)
        certobj=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(days=365)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]),critical=False).sign(key,hashes.SHA256())
        cert.write_bytes(certobj.public_bytes(serialization.Encoding.PEM));keyfile.write_bytes(protect(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())))
    certobj=x509.load_pem_x509_certificate(cert.read_bytes())
    if ipaddress.ip_address(host) not in certobj.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress):raise ValueError('Certificate belongs to another IP. Stop service and reset local certificate, then trust the new fingerprint on your phone.')
    if certobj.not_valid_after_utc<=datetime.datetime.now(datetime.timezone.utc):raise ValueError('Local certificate expired. Stop service and reset certificate.')
    fingerprint=certobj.fingerprint(hashes.SHA256()).hex()
    # SSLContext requires a file. Create briefly in the per-user folder, then remove it.
    temp=folder/'mobile-key-loading.pem'
    try:
        temp.write_bytes(protect(keyfile.read_bytes(),True));context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(cert,temp)
    finally:temp.unlink(missing_ok=True)
    return context,fingerprint

class MobileServer:
    def __init__(self,folder,host,port,context):
        ipaddress.ip_address(host);self.folder=Path(folder);self.lock=threading.Lock();self.snapshot={'at':time.time(),'pages':[],'devices':[],'events':[]};self.code='';self.code_until=0;self.attempts={};self.tokens={};self.threads=threading.BoundedSemaphore(8)
        self.tokens_path=self.folder/'paired-devices.json'
        if self.tokens_path.exists():self.tokens=json.loads(self.tokens_path.read_text())
        owner=self
        class Server(ThreadingHTTPServer):
            daemon_threads=True
            def get_request(self):
                sock,addr=self.socket.accept();sock.settimeout(5)
                try:return context.wrap_socket(sock,server_side=True),addr
                except Exception:sock.close();raise
            def process_request(self,request,address):
                if not owner.threads.acquire(False):request.close();return
                super().process_request(request,address)
            def process_request_thread(self,*args):
                try:super().process_request_thread(*args)
                finally:owner.threads.release()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,code,data,html=False,cookie=None):
                raw=data.encode() if html else json.dumps(data,allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','text/html; charset=utf-8' if html else 'application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
                if cookie:self.send_header('Set-Cookie',cookie)
                self.end_headers();self.wfile.write(raw)
            def authenticated(self):
                try:
                    cookie=SimpleCookie(self.headers.get('Cookie',''));token=cookie['zee_session'].value;digest=hashlib.sha256(token.encode()).hexdigest()
                    with owner.lock:return owner.tokens.get(digest,{}).get('expires',0)>time.time()
                except Exception:return False
            def do_GET(self):
                if self.path=='/':self.reply(200,HTML,True)
                elif self.path=='/api/status':
                    if not self.authenticated():self.reply(401,{'error':'Pair this phone first'});return
                    with owner.lock:data=owner.snapshot.copy()
                    self.reply(200,data)
                else:self.reply(404,{'error':'Not found'})
            def do_POST(self):
                if self.path not in ('/pair','/logout'):self.reply(404,{});return
                origin=self.headers.get('Origin')
                if origin and origin!='https://'+self.headers.get('Host',''):self.reply(403,{});return
                if self.path=='/logout':
                    if not self.authenticated():self.reply(401,{});return
                    cookie=SimpleCookie(self.headers.get('Cookie',''));digest=hashlib.sha256(cookie['zee_session'].value.encode()).hexdigest()
                    owner.revoke_one(digest)
                    self.reply(200,{'logged_out':True},cookie='zee_session=; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=2048:raise ValueError()
                    data=json.loads(self.rfile.read(length));code=str(data.get('code',''))
                except Exception:self.reply(400,{});return
                now=time.time();ip=self.client_address[0]
                with owner.lock:
                    count,until=owner.attempts.get(ip,(0,now+60))
                    if now>until:count,until=0,now+60
                    owner.attempts[ip]=(count+1,until)
                    if count>=5:self.reply(429,{});return
                    if not owner.code or now>owner.code_until or not secrets.compare_digest(code,owner.code):self.reply(403,{});return
                    owner.code='';token=secrets.token_urlsafe(32);owner.tokens[hashlib.sha256(token.encode()).hexdigest()]={'label':'Phone '+time.strftime('%Y-%m-%d %H:%M'),'expires':now+30*86400};owner.persist()
                self.reply(200,{'paired':True},cookie='zee_session='+token+'; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000')
        self.server=Server((host,port),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def persist(self):
        p=self.tokens_path.with_suffix('.tmp');p.write_text(json.dumps(self.tokens));p.replace(self.tokens_path)
    def pair(self):
        with self.lock:self.code=secrets.token_urlsafe(18);self.code_until=time.time()+300;return self.code
    def revoke(self):
        with self.lock:self.tokens={};self.code='';self.persist()
    def paired(self):
        with self.lock:return [{'id':key,'label':value.get('label','Phone'),'expires':value.get('expires',0)} for key,value in self.tokens.items() if value.get('expires',0)>time.time()]
    def revoke_one(self,id):
        with self.lock:self.tokens.pop(id,None);self.persist()
    def update(self,snapshot):
        with self.lock:self.snapshot=snapshot
    def start(self):self.thread.start()
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=6)
