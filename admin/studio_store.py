"""Local authenticated Admin Studio records, signed licences and encrypted backups."""
import base64,hashlib,hmac,json,os,re,secrets,sqlite3,time,uuid,tempfile
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from zee.credentials import protect
from zee.licensing import canonical,PRODUCT
from admin.issuer import issue_document,write_atomic

FEATURES=('monitoring','map','wan','wireless','cctv','mobile','reports')
ITERATIONS=600000
MAX_BACKUP=32*1048576
SCHEMA='''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY,salt BLOB,verifier BLOB,role TEXT,failed INTEGER DEFAULT 0,locked_until REAL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_owner ON users(role) WHERE role='owner';
CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT PRIMARY KEY,name TEXT,payload TEXT,archived INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS record_kind ON records(kind,name);
CREATE TABLE IF NOT EXISTS licences(id TEXT PRIMARY KEY,customer_id TEXT,package_id TEXT,profile_id TEXT,machine TEXT,status TEXT,document TEXT,reason TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,at REAL,actor TEXT,action TEXT,target TEXT,detail TEXT,previous TEXT,digest TEXT);
'''

def text(value,label,limit=200,required=False):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):raise ValueError('Invalid '+label)
    value=value.strip()
    if required and not value:raise ValueError(label+' is required.')
    return value

def master(password,salt):
    if not isinstance(password,str) or not 12<=len(password)<=256:raise ValueError('Use a password of 12–256 characters.')
    return hashlib.pbkdf2_hmac('sha256',password.encode(),salt,ITERATIONS,32)

def username(name):
    if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,64}',name):raise ValueError('Username: 1–64 letters, numbers, dots, underscores or hyphens.')
    return name.casefold()

def decode64(value):return base64.b64decode(value,validate=True)

def encode64(value):return base64.b64encode(value).decode()

class StudioStore:
    def __init__(self,root,clock=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'studio.sqlite3';self.keyfile=self.root/'issuer-private.dpapi';self.sessions={};self.clock=clock or time.monotonic
        self.open()
    def open(self):
        self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row;self.db.executescript(SCHEMA)
        version=self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if version and version[0]!='1':self.db.close();raise ValueError('Unsupported Admin Studio schema.')
        with self.db:self.db.execute("INSERT OR IGNORE INTO meta VALUES('schema','1')")
    def configured(self):return bool(self.db.execute("SELECT 1 FROM users WHERE role='owner'").fetchone())
    def audit(self,actor,action,target='',detail=''):
        last=self.db.execute('SELECT digest FROM audit ORDER BY seq DESC LIMIT 1').fetchone();previous=last[0] if last else ''
        at=time.time();data=[at,actor,action,target,detail,previous];digest=hashlib.sha256(canonical(data)).hexdigest()
        self.db.execute('INSERT INTO audit(at,actor,action,target,detail,previous,digest) VALUES(?,?,?,?,?,?,?)',(*data,digest))
    def verify_audit(self):
        previous='';seq=0
        for r in self.db.execute('SELECT * FROM audit ORDER BY seq'):
            if r['seq']!=seq+1 or r['previous']!=previous or r['digest']!=hashlib.sha256(canonical([r[k] for k in ('at','actor','action','target','detail','previous')])).hexdigest():raise ValueError('Audit chain does not match; review/restore a trusted backup.')
            previous=r['digest'];seq=r['seq']
        return seq
    def setup(self,name,password):
        if self.configured():raise PermissionError('Owner already configured.')
        name=username(name);salt=os.urandom(16);key=master(password,salt)
        with self.db:
            self.db.execute('INSERT INTO users(name,salt,verifier,role) VALUES(?,?,?,?)',(name,salt,hashlib.sha256(b'auth-verifier'+key).digest(),'owner'))
            self.audit(name,'owner-created')
    def login(self,name,password):
        name=username(name);row=self.db.execute('SELECT * FROM users WHERE name=?',(name,)).fetchone()
        if row and row['locked_until']>time.time():raise PermissionError('Login temporarily locked; retry after one minute.')
        # Unknown users incur the same derivation cost. Passwords never enter audit records.
        key=master(password,row['salt'] if row else b'unknown-user-salt')
        valid=row and hmac.compare_digest(hashlib.sha256(b'auth-verifier'+key).digest(),row['verifier'])
        if not valid:
            with self.db:
                if row:
                    failed=row['failed']+1;self.db.execute('UPDATE users SET failed=?,locked_until=? WHERE name=?',(failed,time.time()+60 if failed>=5 else 0,name))
                self.audit(name,'login-rejected')
            raise PermissionError('Username or password incorrect.')
        recovery_only=False
        try:self.verify_audit()
        except ValueError:
            if row['role']!='owner':raise PermissionError('Audit integrity needs owner recovery.')
            recovery_only=True
        token=secrets.token_urlsafe(32)
        self.sessions[token]={'actor':name,'role':row['role'],'master':key if row['role']=='owner' else None,'expires':self.clock()+900,'recovery_only':recovery_only}
        if not recovery_only:
            with self.db:self.db.execute('UPDATE users SET failed=0,locked_until=0 WHERE name=?',(name,));self.audit(name,'login')
        return token
    def require(self,token,owner=False,recovery=False):
        session=self.sessions.get(token)
        if not session or self.clock()>=session['expires']:
            self.sessions.pop(token,None);raise PermissionError('Session expired or locked; log in again.')
        if session.get('recovery_only') and not recovery:raise PermissionError('Recovery-only session: restore a verified backup before normal operations.')
        if owner and session['role']!='owner':raise PermissionError('Owner access required for this action.')
        return session
    def logout(self,token):
        s=self.sessions.pop(token,None)
        if s and not s.get('recovery_only'):
            with self.db:self.audit(s['actor'],'logout')
    def add_viewer(self,token,name,password):
        s=self.require(token,True);name=username(name);salt=os.urandom(16);key=master(password,salt)
        with self.db:
            self.db.execute('INSERT INTO users(name,salt,verifier,role) VALUES(?,?,?,?)',(name,salt,hashlib.sha256(b'auth-verifier'+key).digest(),'viewer'));self.audit(s['actor'],'viewer-created',name)
    def records(self,token,kind):
        self.require(token)
        if kind not in ('customers','packages','profiles'):raise ValueError('Unknown record type.')
        return [dict(r)|{'data':json.loads(r['payload'])} for r in self.db.execute('SELECT * FROM records WHERE kind=? ORDER BY name,id LIMIT 1000',(kind,))]
    def record(self,token,kind,id,active=True):
        self.require(token);r=self.db.execute('SELECT * FROM records WHERE kind=? AND id=?',(kind,id)).fetchone()
        if not r or (active and r['archived']):raise ValueError(kind.title()+' record missing or archived.')
        return dict(r)|{'data':json.loads(r['payload'])}
    def normalize(self,token,kind,data):
        allowed={'customers':{'name','contact','notes'},'packages':{'name','days','max_devices','features'},'profiles':{'name','customer_id','package_id','app_name','watermark','logo_png'}}
        if kind not in allowed or not isinstance(data,dict) or set(data)!=allowed[kind]:raise ValueError('Unexpected record fields; credentials/keys do not belong in profiles.')
        out=dict(data);out['name']=text(out['name'],'Name',120,True)
        if kind=='customers':out.update(contact=text(out['contact'],'Contact',200),notes=text(out['notes'],'Notes',1000))
        if kind=='packages':
            for field,low,high in [('days',0,36500),('max_devices',1,10000)]:
                if type(out[field]) is not int or not low<=out[field]<=high:raise ValueError('Invalid '+field)
            if not isinstance(out['features'],list) or len(set(out['features']))!=len(out['features']) or any(x not in FEATURES for x in out['features']):raise ValueError('Select known package features.')
        if kind=='profiles':
            self.record(token,'customers',out['customer_id']);self.record(token,'packages',out['package_id'])
            out['app_name']=text(out['app_name'],'App name',80,True);out['watermark']=text(out['watermark'],'Watermark',120,True)
            if not isinstance(out['logo_png'],str) or len(out['logo_png'])>2800000:raise ValueError('PNG logo must be at most 2 MiB.')
            if out['logo_png']:
                import struct
                from PySide6.QtGui import QImage
                raw=decode64(out['logo_png'])
                if len(raw)>2*1048576 or len(raw)<24 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':raise ValueError('Choose a valid PNG logo.')
                width,height=struct.unpack('>II',raw[16:24])
                if not 1<=width<=2048 or not 1<=height<=2048 or QImage.fromData(raw).isNull():raise ValueError('PNG dimensions must be 1–2048 pixels.')
        return out
    def save_record(self,token,kind,data,id=None):
        s=self.require(token,True);data=self.normalize(token,kind,data)
        if id:self.record(token,kind,id,active=False)
        id=id or str(uuid.uuid4())
        with self.db:
            self.db.execute('INSERT INTO records(kind,id,name,payload) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,payload=excluded.payload',(kind,id,data['name'],json.dumps(data,allow_nan=False)))
            self.audit(s['actor'],'record-saved',id,kind)
        return id
    def archive(self,token,kind,id):
        s=self.require(token,True);self.record(token,kind,id,active=False)
        with self.db:self.db.execute('UPDATE records SET archived=1-archived WHERE id=?',(id,));self.audit(s['actor'],'archive-toggled',id,kind)
    def key(self,token):
        s=self.require(token,True)
        if not self.keyfile.exists():raise ValueError('Initialize the Studio issuer key on Windows first.')
        envelope=json.loads(protect(self.keyfile.read_bytes(),True));raw=AESGCM(s['master']).decrypt(decode64(envelope['nonce']),decode64(envelope['ciphertext']),('ZeeAdminStudio issuer|'+s['actor']).encode())
        return Ed25519PrivateKey.from_private_bytes(raw)
    def store_key(self,token,key):
        s=self.require(token,True);nonce=os.urandom(12);cipher=AESGCM(s['master']).encrypt(nonce,key.private_bytes_raw(),('ZeeAdminStudio issuer|'+s['actor']).encode())
        write_atomic(self.keyfile,protect(json.dumps({'nonce':encode64(nonce),'ciphertext':encode64(cipher)}).encode()))
        public=encode64(key.public_key().public_bytes_raw())
        with self.db:self.db.execute("INSERT OR REPLACE INTO meta VALUES('public_key',?)",(public,));self.audit(s['actor'],'issuer-key-stored')
        return {'public_key':public,'product':PRODUCT}
    def initialize_key(self,token):
        self.require(token,True)
        if self.keyfile.exists():key=self.key(token);return {'public_key':encode64(key.public_key().public_bytes_raw()),'product':PRODUCT}
        return self.store_key(token,Ed25519PrivateKey.generate())
    def export_profile(self,token,id):
        s=self.require(token,True);p=self.record(token,'profiles',id);data=p['data'];customer=self.record(token,'customers',data['customer_id']);package=self.record(token,'packages',data['package_id'])
        result={'type':'zee-reviewed-build-profile','version':1,'profile_id':id,'customer_id':customer['id'],'package_id':package['id'],'branding':{k:data[k] for k in ('app_name','watermark','logo_png')},'package':package['data'],'client_application':'Pending Phase 8.2; metadata is not client enforcement'}
        with self.db:self.audit(s['actor'],'profile-exported',id)
        return result
    def issue(self,token,customer_id,package_id,machine,profile_id=''):
        s=self.require(token,True);customer=self.record(token,'customers',customer_id);package=self.record(token,'packages',package_id)
        if profile_id:
            profile=self.record(token,'profiles',profile_id)['data']
            if (profile['customer_id'],profile['package_id'])!=(customer_id,package_id):raise ValueError('Build profile belongs to a different customer/package.')
        id=str(uuid.uuid4());doc=issue_document(self.key(token),machine,customer['name'],package['name'],id,package['data']['days'])
        with self.db:
            self.db.execute('INSERT INTO licences(id,customer_id,package_id,profile_id,machine,status,document) VALUES(?,?,?,?,?,?,?)',(id,customer_id,package_id,profile_id,machine,'Issued',json.dumps(doc)))
            self.audit(s['actor'],'licence-issued',id)
        return id,doc
    def licences(self,token):
        self.require(token);return [dict(r)|{'signed':json.loads(r['document'])} for r in self.db.execute('SELECT * FROM licences ORDER BY rowid DESC LIMIT 1000')]
    def revoke(self,token,id,reason):
        s=self.require(token,True);reason=text(reason,'Reason',500,True)
        if not self.db.execute('SELECT 1 FROM licences WHERE id=?',(id,)).fetchone():raise ValueError('Licence missing.')
        with self.db:self.db.execute('UPDATE licences SET status=?,reason=? WHERE id=?',('Revoked in Studio; offline copy still valid',reason,id));self.audit(s['actor'],'licence-revoked-locally',id,reason)
    def recovery_export(self,token,password):
        s=self.require(token,True);master(password,b'password-length-check')
        raw=self.key(token).private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(password.encode()))
        with self.db:self.audit(s['actor'],'encrypted-key-recovery-export')
        return raw
    def recovery_import(self,token,raw,password):
        self.require(token,True)
        if len(raw)>65536:raise ValueError('Recovery file too large.')
        key=serialization.load_pem_private_key(raw,password.encode())
        if not isinstance(key,Ed25519PrivateKey):raise ValueError('Expected an Ed25519 recovery key.')
        current=self.db.execute("SELECT value FROM meta WHERE key='public_key'").fetchone()
        if current and current[0]!=encode64(key.public_key().public_bytes_raw()):raise ValueError('Recovery key does not match this Studio issuer.')
        if self.keyfile.exists():
            try:self.key(token)
            except Exception:pass
            else:raise ValueError('Existing readable issuer key cannot be overwritten.')
        return self.store_key(token,key)
    def audit_rows(self,token):
        self.require(token,recovery=True);return [dict(r) for r in self.db.execute('SELECT * FROM audit ORDER BY seq DESC LIMIT 1000')]
    def backup(self,token,password):
        s=self.require(token,True);self.verify_audit();salt=os.urandom(16);key=master(password,salt)
        fd,path=tempfile.mkstemp(dir=self.root,suffix='.backup-tmp');os.close(fd)
        try:
            destination=sqlite3.connect(path);self.db.backup(destination);destination.close();raw=Path(path).read_bytes()
            if len(raw)>MAX_BACKUP:raise ValueError('Studio backup exceeds 32 MiB limit.')
            body=json.dumps({'database':encode64(raw),'issuer':encode64(self.keyfile.read_bytes()) if self.keyfile.exists() else ''}).encode();nonce=os.urandom(12)
            output=json.dumps({'type':'zee-studio-backup','version':1,'salt':encode64(salt),'nonce':encode64(nonce),'ciphertext':encode64(AESGCM(key).encrypt(nonce,body,b'ZeeAdminStudio backup v1'))}).encode()
            with self.db:self.audit(s['actor'],'encrypted-backup-created')
            return output
        finally:Path(path).unlink(missing_ok=True)
    def restore(self,token,raw,password,allow_key_change=False):
        s=self.require(token,True,recovery=True)
        if len(raw)>2*MAX_BACKUP:raise ValueError('Backup file too large.')
        doc=json.loads(raw)
        if doc.get('type')!='zee-studio-backup' or doc.get('version')!=1:raise ValueError('Not a Studio backup.')
        key=master(password,decode64(doc['salt']));body=json.loads(AESGCM(key).decrypt(decode64(doc['nonce']),decode64(doc['ciphertext']),b'ZeeAdminStudio backup v1'))
        database=decode64(body['database']);issuer=decode64(body['issuer'])
        if len(database)>MAX_BACKUP or len(issuer)>65536:raise ValueError('Backup content exceeds limits.')
        temp=self.root/'restore-validated.sqlite3';temp.write_bytes(database)
        try:
            check=sqlite3.connect(temp);check.row_factory=sqlite3.Row
            try:
                if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup database integrity failed.')
                if check.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]!='1' or not check.execute("SELECT 1 FROM users WHERE role='owner'").fetchone():raise ValueError('Backup schema/owner missing.')
                original=self.db;self.db=check
                try:self.verify_audit()
                finally:self.db=original
                target=check.execute("SELECT value FROM meta WHERE key='public_key'").fetchone();current=self.db.execute("SELECT value FROM meta WHERE key='public_key'").fetchone()
                if not allow_key_change and target!=current:raise ValueError('Backup changes issuer identity; explicit restore confirmation required.')
            finally:check.close()
            # A recovery checkpoint protects both records and the encrypted key before replacement.
            checkpoint=self.root/('pre-restore-'+str(time.time_ns()));checkpoint.mkdir()
            copy=sqlite3.connect(checkpoint/'studio.sqlite3');self.db.backup(copy);copy.close()
            if self.keyfile.exists():write_atomic(checkpoint/'issuer-private.dpapi',self.keyfile.read_bytes())
            self.sessions.clear();self.db.close()
            try:
                os.replace(temp,self.path)
                if issuer:write_atomic(self.keyfile,issuer)
                else:self.keyfile.unlink(missing_ok=True)
                self.open()
                with self.db:self.audit(s['actor'],'backup-restored','', 'Owner must log in again with restored credentials')
            except Exception:
                if hasattr(self,'db'):
                    try:self.db.close()
                    except Exception:pass
                write_atomic(self.path,(checkpoint/'studio.sqlite3').read_bytes())
                if (checkpoint/'issuer-private.dpapi').exists():write_atomic(self.keyfile,(checkpoint/'issuer-private.dpapi').read_bytes())
                else:self.keyfile.unlink(missing_ok=True)
                self.open();raise
        finally:temp.unlink(missing_ok=True)
    def close(self):self.sessions.clear();self.db.close()
