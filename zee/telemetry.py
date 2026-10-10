"""Read-only explicit adapters. Device OIDs require firmware-specific verification."""
import math,re,time,asyncio,json,base64
from .connections import request,validate_url,service_check,connection
METRICS={'signal_dbm','noise_dbm','snr_db','tx_ccq','rx_ccq','tx_mbps','rx_mbps','frequency_mhz','channel_width_mhz','uptime_s','ethernet_up','wireless_up','cpu_pct','memory_pct','in_octets','out_octets','counter_epoch'}
DEFAULT_PROFILE={'method':'none','poll_seconds':30,'firmware_verified':False,'oids':{},'fields':{},'wan_verified':False,'internet_url':'','internet_marker':'','speed_url':'','speed_mb':1,'speed_seconds':5,'daily_mb':10,'automatic_speed':False,'speed_interval':900,'min_download_mbps':0,'loss_warning_pct':10,'signal_good':-60,'signal_poor':-80,'ccq_good':90,'ccq_poor':50,'snmp_version':'2c','rate_quality_enabled':False,'rate_good_mbps':100,'rate_poor_mbps':10,'internet_latency_warning_ms':1500,'service_alerts':False}

def validate_profile(p):
    if not isinstance(p,dict):raise ValueError('Integration settings must be an object.')
    if set(p)-set(DEFAULT_PROFILE)-{'url','snmp_port','allow_v2c','rate_cap_kbps'}:raise ValueError('Unknown integration setting; secrets belong in the protected credential fields.')
    if p.get('method','none') not in ('none','snmp','https-json'):raise ValueError('Unsupported adapter.')
    if p.get('snmp_version','2c') not in ('1','2c'):raise ValueError('SNMP version must be 1 or 2c.')
    for key in ('rate_quality_enabled','allow_v2c','service_alerts'):
        if key in p and not isinstance(p[key],bool):raise ValueError(key+' must be true or false.')
    if p.get('rate_poor_mbps',10)>=p.get('rate_good_mbps',100):raise ValueError('Good rate must be above poor rate.')
    for key in ('url','internet_url','speed_url'):
        if p.get(key):validate_url(p[key],('https',))
    for key,low,high in [('poll_seconds',5,3600),('speed_mb',1,64),('speed_seconds',1,30),('daily_mb',1,1024),('speed_interval',900,86400),('snmp_port',1,65535),('rate_cap_kbps',0,1000000),('min_download_mbps',0,100000),('loss_warning_pct',0,100),('signal_good',-120,-1),('signal_poor',-130,-2),('ccq_good',1,100),('ccq_poor',0,99),('rate_good_mbps',0.01,100000),('rate_poor_mbps',0,99999),('internet_latency_warning_ms',1,60000)]:
        if key in p and (not isinstance(p[key],(int,float)) or not math.isfinite(p[key]) or not low<=p[key]<=high):raise ValueError('Invalid '+key)
    if p.get('signal_poor',-80)>=p.get('signal_good',-60) or p.get('ccq_poor',50)>=p.get('ccq_good',90):raise ValueError('Good thresholds must be above poor thresholds.')
    for key in ('oids','fields'):
        if not isinstance(p.get(key,{}),dict):raise ValueError('Metric mapping must be an object.')
        for metric,mapping in p.get(key,{}).items():
            if metric not in METRICS or not isinstance(mapping,dict) or set(mapping)-{'path','scale'}:raise ValueError('Unknown metric or mapping field.')
            if not isinstance(mapping.get('path'),str):raise ValueError('Mapping path must be a string.')
            if key=='oids' and not re.fullmatch(r'[0-2](?:\.[0-9]+)+',mapping['path']):raise ValueError('Use numeric SNMP OIDs verified for this firmware.')
            if not isinstance(mapping.get('scale',1),(int,float)) or not math.isfinite(mapping.get('scale',1)):raise ValueError('Invalid metric scale.')

def normalized(raw,mapping):
    result={}
    for name,cfg in mapping.items():
        value=raw
        try:
            for part in cfg['path'].split('/'):value=value[part]
            number=float(value)*cfg.get('scale',1)
            if math.isfinite(number):result[name]=number
        except (ValueError,TypeError,KeyError):continue
    return result

async def snmp_fetch(d,secrets):
    from pysnmp.hlapi.v3arch.asyncio import SnmpEngine,CommunityData,UdpTransportTarget,ContextData,ObjectType,ObjectIdentity,get_cmd
    p=d.integration
    if not p.get('allow_v2c'):raise ValueError('SNMP v1/v2c must be explicitly enabled on a trusted management network; its community travels unencrypted.')
    if not secrets.get('community'):raise ValueError('Save a read-only SNMP community first.')
    engine=SnmpEngine()
    try:
        target=await UdpTransportTarget.create((d.host,int(p.get('snmp_port',161))),timeout=2,retries=0)
        values=list(p.get('oids',{}).items())
        if not values:raise ValueError('No firmware-verified OIDs configured.')
        error,status,index,bindings=await get_cmd(engine,CommunityData(secrets['community'],mpModel=0 if p.get('snmp_version','2c')=='1' else 1),target,ContextData(),*[ObjectType(ObjectIdentity(v['path'])) for k,v in values],lookupMib=False)
        if error or status:raise ValueError('SNMP timeout or rejected request; check firmware, network and read-only community.')
        out={}
        for (name,cfg),binding in zip(values,bindings):
            try:
                value=float(binding[1])*cfg.get('scale',1)
                if math.isfinite(value):out[name]=value
            except (TypeError,ValueError):pass
        return out
    finally:engine.close_dispatcher()

def fetch_metrics(d,secrets,source=''):
    p=d.integration;method=p.get('method','none')
    if method=='none':return {},'Telemetry unavailable — configure a verified adapter'
    if not p.get('firmware_verified'):return {},'Firmware/profile not verified'
    if method=='snmp':
        if source:raise ValueError('SNMP source binding is not implemented; use a verified non-overlapping management route or HTTPS adapter.')
        return asyncio.run(asyncio.wait_for(snmp_fetch(d,secrets),8)), 'SNMP v'+p.get('snmp_version','2c')+' (configured OIDs)'
    url=p.get('url','');u=validate_url(url,('https',))
    # Saved device credentials are never sent to a different target host.
    if u.hostname.lower()!=d.host.lower():raise ValueError('Telemetry URL host must match the device management host.')
    headers={}
    if secrets.get('password'):headers['Authorization']='Basic '+base64.b64encode((d.username+':'+secrets['password']).encode()).decode()
    code,body=request(url,source,headers=headers,max_bytes=65536)
    if code!=200:raise ValueError('Telemetry request failed; HTTP '+str(code))
    return normalized(json.loads(body),p.get('fields',{})),'HTTPS JSON (configured fields)'

def quality(metrics,p,age=0):
    if age>max(30,p.get('poll_seconds',30)*3):return None,'Unknown'
    if metrics.get('wireless_up')==0:return 0,'Critical'
    parts=[]
    for key,poor,good in [('signal_dbm',p.get('signal_poor',-80),p.get('signal_good',-60)),('tx_ccq',p.get('ccq_poor',50),p.get('ccq_good',90)),('rx_ccq',p.get('ccq_poor',50),p.get('ccq_good',90))]:
        if key in metrics:parts.append(max(0,min(10,10*(metrics[key]-poor)/(good-poor))))
    if p.get('rate_quality_enabled'):
        for key in ('tx_mbps','rx_mbps'):
            if key in metrics:parts.append(max(0,min(10,10*(metrics[key]-p.get('rate_poor_mbps',10))/(p.get('rate_good_mbps',100)-p.get('rate_poor_mbps',10)))))
    if not parts:return None,'Unknown'
    score=round(min(parts),1)
    return score,'Good' if score>=8 else 'Fair' if score>=5 else 'Poor'

def counter_rates(previous,current,elapsed):
    # Counter discontinuity/reboot/wrap resets baseline. Never fabricate a negative rate.
    if elapsed<=0 or not previous or previous.get('counter_epoch')!=current.get('counter_epoch'):return {}
    out={}
    for key,name in [('in_octets','download_mbps'),('out_octets','upload_mbps')]:
        if key in previous and key in current and current[key]>=previous[key]:out[name]=(current[key]-previous[key])*8/elapsed/1e6
    return out

def internet_check(p,source):
    if not p.get('wan_verified'):return 'Not independently measurable'
    if not p.get('internet_url') or not p.get('internet_marker'):return 'Unknown — configure HTTPS endpoint and expected response text'
    code,body=request(p['internet_url'],source,max_bytes=4096)
    return 'Online' if code==200 and p['internet_marker'].encode() in body else 'Offline — external check failed'

def speed_test(p,source='',cancel=None):
    if not p.get('wan_verified') or not p.get('speed_url'):raise ValueError('Verify the WAN route and configure a controlled HTTPS download endpoint first.')
    limit=int(p.get('speed_mb',1)*1048576);seconds=p.get('speed_seconds',5);cap=p.get('rate_cap_kbps',0)*1024
    c,path=connection(p['speed_url'],source,min(5,seconds));total=0;start=time.monotonic()
    try:
        c.request('GET',path,headers={'Range':f'bytes=0-{limit-1}','Accept-Encoding':'identity'});r=c.getresponse()
        if r.status not in (200,206):raise ValueError('Speed endpoint rejected the request.')
        while total<limit and time.monotonic()-start<seconds and not (cancel and cancel.is_set()):
            data=r.read(min(16384,limit-total))
            if not data:break
            total+=len(data)
            if cap:time.sleep(min(.25,max(0,total/cap-(time.monotonic()-start))))
        elapsed=time.monotonic()-start
        if not total:raise ValueError('Speed endpoint returned no data.')
        return {'download_mbps':total*8/max(.001,elapsed)/1e6,'bytes':total,'seconds':elapsed,'rate_kind':'Controlled download throughput'+(' (rate capped)' if cap else ''),'upload_note':'Upload test unavailable; router counters can measure upload traffic'}
    finally:c.close()
