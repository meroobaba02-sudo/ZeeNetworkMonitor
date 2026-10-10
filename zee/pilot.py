"""Local real-network pilot evidence. No device mutation or automatic release approval."""
import copy,hashlib,json,math,os,platform,time,uuid
from pathlib import Path
from .core import VERSION
from .resources import Usage

SCENARIOS=(
 ('endpoint','One endpoint stops replying'),('gateway','Gateway stops replying'),
 ('upstream','Upstream / intermediate tower outage'),('internet-local','Internet fails; local router replies'),
 ('wan-isolation','One WAN fails; another remains working'),('radio-unreachable','Rocket M5 management unreachable'),
 ('radio-metrics','Rocket readings compared with actual firmware'),('icmp-filtered','ICMP blocked; another service still works'),
 ('recovery','Device recovers after outage'),('mass-faults','Many devices fail together'),
 ('long-run','At least 4 hours of continuous monitoring'),('retention','Expired logs cleaned; protected records remain'),
 ('restart','Restart preserves settings'),('backup','Backup / restore / safety copy verified'),
 ('install','Clean Windows install / upgrade / uninstall'),('multi-networks','Five network paths / page isolation'),
 ('seven-wans','Seven modem paths independently verified'),('mobile','Phone LAN / VPN pairing and revocation'))
STATUSES=('Not performed','Pass','Fail','Blocked')
METRICS=('signal_dbm','noise_dbm','snr_db','tx_ccq','rx_ccq','tx_mbps','rx_mbps','ethernet_up','wireless_up')
SAMPLE_LIMIT=1440
FAULTS={'endpoint','gateway','upstream','internet-local','wan-isolation','radio-unreachable','icmp-filtered','recovery','mass-faults'}


def number(value,maximum=1e12):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=maximum:raise ValueError('Use a finite non-negative number.')
    return value


def atomic_json(path,document):
    temporary=path.with_name(path.name+'.new')
    try:
        with temporary.open('w',encoding='utf-8') as output:
            output.write(json.dumps(document,allow_nan=False,indent=2));output.flush();os.fsync(output.fileno())
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def fresh_document():
    return {'format':'zee-pilot-1','session':str(uuid.uuid4()),'version':VERSION,'created':time.time(),
        'platform':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'cpu_count':os.cpu_count()},
        'results':{key:{'status':'Not performed','note':'','detection_s':None,'recovery_s':None,'false_positive':None,'false_negative':None,'at':None} for key,_ in SCENARIOS},
        'capture':{'state':'Not recorded','started':None,'duration_s':0,'monitoring_s':0,'samples':[],'total_samples':0,'observed_samples':0,'max_heartbeat_gap_ms':0,'devices':[],'devices_truncated':False}}


def validate_document(doc):
    if not isinstance(doc,dict) or set(doc)!=set(fresh_document()) or doc.get('format')!='zee-pilot-1':raise ValueError('Unsupported pilot evidence file.')
    uuid.UUID(doc['session']);number(doc['created'])
    if not isinstance(doc['version'],str) or len(doc['version'])>32:raise ValueError('Invalid pilot version.')
    if not isinstance(doc['platform'],dict) or set(doc['platform'])!={'system','release','machine','cpu_count'}:raise ValueError('Invalid pilot platform.')
    for key in ('system','release','machine'):
        if not isinstance(doc['platform'][key],str) or len(doc['platform'][key])>256:raise ValueError('Invalid pilot platform.')
    if doc['platform']['cpu_count'] is not None:number(doc['platform']['cpu_count'],100000)
    if not isinstance(doc['results'],dict) or set(doc['results'])!={key for key,_ in SCENARIOS}:raise ValueError('Pilot scenarios missing or changed.')
    for result in doc['results'].values():validate_result(result)
    capture=doc['capture'];expected=set(fresh_document()['capture'])
    if not isinstance(capture,dict) or set(capture)!=expected or capture['state'] not in ('Not recorded','Recording','Stopped','Interrupted'):raise ValueError('Invalid pilot capture.')
    for key in ('duration_s','monitoring_s','total_samples','observed_samples','max_heartbeat_gap_ms'):number(capture[key])
    if capture['started'] is not None:number(capture['started'])
    if capture['state']!='Not recorded' and capture['started'] is None:raise ValueError('Capture start time missing.')
    if capture['monitoring_s']>capture['duration_s']+0.01:raise ValueError('Fresh monitoring duration exceeds capture duration.')
    for key in ('total_samples','observed_samples'):
        if type(capture[key]) is not int:raise ValueError('Invalid pilot sample count.')
    if capture['observed_samples']>capture['total_samples']:raise ValueError('Observed count exceeds sampled count.')
    if not isinstance(capture['samples'],list) or len(capture['samples'])>SAMPLE_LIMIT:raise ValueError('Pilot capture too large.')
    if capture['total_samples']<len(capture['samples']):raise ValueError('Invalid pilot retained sample count.')
    fields={'at','cpu_percent_one_core','working_set_mb','database_bytes','log_bytes','monitored_devices','fresh_ping_devices','monitoring_active'}
    for sample in capture['samples']:
        if not isinstance(sample,dict) or set(sample)!=fields or type(sample['monitoring_active']) is not bool:raise ValueError('Invalid pilot sample.')
        for key in fields-{'monitoring_active'}:
            if sample[key] is None and key=='working_set_mb':continue
            number(sample[key])
    if type(capture['devices_truncated']) is not bool or not isinstance(capture['devices'],list) or len(capture['devices'])>200:raise ValueError('Invalid pilot snapshot.')
    for row in capture['devices']:
        if not isinstance(row,dict) or set(row)!={'alias','kind','ping_state','measurement_age_s','metrics','download_mbps','upload_mbps','download_test_mbps'}:raise ValueError('Invalid pilot device snapshot.')
        if not isinstance(row['alias'],str) or len(row['alias'])!=12 or not row['alias'].startswith('D-') or any(x not in '0123456789abcdef' for x in row['alias'][2:]):raise ValueError('Invalid pilot alias.')
        if row['kind'] not in ('WAN','Radio','Camera','Other') or row['ping_state'] not in ('Online','No reply','Warning','Probe error','Unknown','Not monitored'):raise ValueError('Invalid pilot device state.')
        for key in ('measurement_age_s','download_mbps','upload_mbps','download_test_mbps'):
            if row[key] is not None:number(row[key])
        if not isinstance(row['metrics'],dict) or set(row['metrics'])-set(METRICS):raise ValueError('Invalid pilot metrics.')
        for value in row['metrics'].values():
            if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1e12:raise ValueError('Invalid pilot metric value.')
    return doc


def validate_result(result):
    fields={'status','note','detection_s','recovery_s','false_positive','false_negative','at'}
    if not isinstance(result,dict) or set(result)!=fields or result['status'] not in STATUSES or not isinstance(result['note'],str) or len(result['note'])>2000:raise ValueError('Invalid pilot result.')
    if result['status']=='Pass' and len(result['note'].strip())<8:raise ValueError('Record what was actually tested before marking Pass.')
    for field in ('detection_s','recovery_s','at'):
        if result[field] is not None:number(result[field])
    for field in ('false_positive','false_negative'):
        if result[field] is not None and (type(result[field]) is not int or not 0<=result[field]<=1000000):raise ValueError('Invalid false-alert count.')


class PilotSession:
    def __init__(self,folder):
        self.path=Path(folder)/'pilot-evidence.json';self.document=fresh_document()
        if self.path.exists():
            if self.path.stat().st_size>2*1024*1024:raise ValueError('Pilot evidence file too large; preserve it for support before starting a new session.')
            self.document=validate_document(json.loads(self.path.read_text(encoding='utf-8')))
            if self.document['capture']['state']=='Recording':
                self.document['capture']['state']='Interrupted';self.save()
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);validate_document(self.document);atomic_json(self.path,self.document)
    def record(self,key,**values):
        if key not in self.document['results']:raise ValueError('Unknown pilot scenario.')
        candidate=copy.deepcopy(self.document);candidate['results'][key].update(values);candidate['results'][key]['at']=time.time();validate_document(candidate)
        atomic_json(self.path,candidate);self.document=candidate
    def reset(self):
        # Preserve completed or interrupted evidence, never silently replace it.
        if self.path.exists():
            archive=self.path.with_name('pilot-archive-'+self.document['session']+'.json')
            if archive.exists():raise ValueError('Pilot archive already exists; preserve both files before starting another session.')
            atomic_json(archive,self.document)
        candidate=fresh_document();atomic_json(self.path,candidate);self.document=candidate
    def review(self):
        doc=self.document;results=doc['results'];capture=doc['capture'];blockers=[]
        for key,label in SCENARIOS:
            result=results[key]
            if result['status']!='Pass':blockers.append(label+': '+result['status'])
            elif key in FAULTS and (result['false_positive'] is None or result['false_negative'] is None):blockers.append(label+': false-alert counts not recorded')
            elif result['false_positive'] or result['false_negative']:blockers.append(label+': false alerts require investigation')
            if result['status']=='Pass' and key in FAULTS-{'recovery','icmp-filtered'} and result['detection_s'] is None:blockers.append(label+': detection delay not measured')
            if result['status']=='Pass' and key=='recovery' and result['recovery_s'] is None:blockers.append(label+': recovery delay not measured')
        if capture['state']!='Stopped':blockers.append('Performance capture is not completed')
        if capture['duration_s']<4*3600:blockers.append('At least 4 hours of continuous capture required')
        if capture['monitoring_s']<4*3600:blockers.append('At least 4 hours with fresh monitored observations required')
        if capture['observed_samples']<480 or not capture['samples'] or not any(s['monitoring_active'] and s['fresh_ping_devices'] for s in capture['samples']):blockers.append('At least 480 fresh monitoring samples required')
        if doc['platform']['system']!='Windows':blockers.append('Pilot must also run on the actual supported Windows laptop')
        if doc['version']!=VERSION:blockers.append('Evidence belongs to another app version; start a new session for this release')
        return {'ready_for_owner_review':not blockers,'commercial_release_approved':False,'blockers':blockers,
            'basis':'Operator-reported scenarios plus local measured capture. Owner evidence review and critical-issue resolution are still required.'}
    def export(self,path,include_notes=False):
        target=Path(path);resolved=target.resolve();base=self.path.parent.resolve()
        protected={'pilot-evidence.json','monitor.sqlite3','monitor.sqlite3-wal','monitor.sqlite3-shm','credentials.dpapi.json','license.json','license.previous.json','studio.sqlite3','issuer-private.dpapi'}
        if resolved==self.path.resolve() or (resolved.parent==base and (resolved.name in protected or resolved.name.startswith('pilot-archive-'))):
            raise ValueError('Choose a different report file. Application data and pilot archives must be preserved.')
        if resolved.is_relative_to(base/'mobile'):
            raise ValueError('Save the report outside the private mobile-data folder.')
        atomic_json(target,self.report(include_notes))
    def report(self,include_notes=False):
        report=copy.deepcopy(self.document)
        if not include_notes:
            for row in report['results'].values():row['note']='[Operator note omitted]' if row['note'] else ''
        report['review']=self.review();report['exported_at']=time.time();report['privacy']={'notes_included':bool(include_notes),'excluded':'IP/hostnames, device/network names, URLs, raw events/logs, database, credentials, licences, fingerprints, keys and pairing tokens'}
        return report


def byte_size(folder,names):
    total=0
    for name in names:
        try:total+=(Path(folder)/name).stat().st_size
        except FileNotFoundError:pass
    return total


def snapshot(window,now=None):
    now=time.time() if now is None else now;selected=window.monitor_devices();rows=[];fresh_count=0
    for device in selected:
        ping=window.latest.get(device.id,{})
        fresh_ping=type(ping.get('at')) in (int,float) and 0<=now-ping['at']<=max(30,max(device.interval,getattr(window.engine,'minimum_interval',1))*3)
        fresh_count+=bool(fresh_ping)
        if len(rows)>=200:continue
        measurement=window.measurements.latest.get(device.id,{})
        stamp=measurement.get('at');age=now-stamp if type(stamp) in (int,float) and math.isfinite(stamp) else None
        fresh=age is not None and 0<=age<=max(30,device.integration.get('poll_seconds',30)*3)
        metrics={k:v for k,v in measurement.get('metrics',{}).items() if k in METRICS and type(v) in (int,float) and math.isfinite(v) and abs(v)<=1e12} if fresh else {}
        state=window.state(device) if fresh_ping else 'Unknown'
        if state not in ('Online','No reply','Warning','Probe error','Unknown','Not monitored'):state='Unknown'
        def rate(key):
            value=measurement.get(key)
            return value if fresh and type(value) in (int,float) and math.isfinite(value) and 0<=value<=1e12 else None
        speed=window.measurements.speed_latest.get(device.id,{})
        speed_at=speed.get('at');speed_value=speed.get('download_mbps')
        download_test=speed_value if type(speed_at) in (int,float) and 0<=now-speed_at<=max(60,device.integration.get('speed_interval',900)) and type(speed_value) in (int,float) and math.isfinite(speed_value) and 0<=speed_value<=1e12 and str(speed.get('rate_kind','')).startswith('Controlled download') else None
        rows.append({'alias':'D-'+hashlib.sha256(device.id.encode()).hexdigest()[:10],'kind':'WAN' if device.wan or device.kind.startswith('WAN') else 'Radio' if device.kind.startswith('Rocket') else 'Camera' if device.kind.startswith('CCTV') else 'Other','ping_state':state,'measurement_age_s':round(age,1) if age is not None and 0<=age<=1e12 else None,'metrics':metrics,'download_mbps':rate('download_mbps'),'upload_mbps':rate('upload_mbps'),'download_test_mbps':download_test})
    return rows,{'monitored_devices':len(selected),'fresh_ping_devices':fresh_count,'monitoring_active':bool(window.engine.running)},len(selected)>200
