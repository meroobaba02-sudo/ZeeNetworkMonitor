"""Read-only explicit adapters. Device OIDs require firmware-specific verification."""
import math,re,time,asyncio,json,base64,ipaddress
from .connections import request,validate_url,service_check,connection
METRICS={'gps_latitude','gps_longitude','heading_deg','elevation_deg','signal_chain0_dbm','signal_chain1_dbm','signal_dbm','noise_dbm','snr_db','tx_ccq','rx_ccq','tx_mbps','rx_mbps','frequency_mhz','channel_width_mhz','uptime_s','ethernet_up','wireless_up','cpu_pct','memory_pct','in_octets','out_octets','counter_epoch'}
DEFAULT_PROFILE={'method':'none','poll_seconds':30,'firmware_verified':False,'oids':{},'fields':{},'wan_verified':False,'internet_url':'','internet_marker':'','speed_url':'','speed_mb':1,'speed_seconds':5,'daily_mb':10,'automatic_speed':False,'speed_interval':900,'min_download_mbps':0,'loss_warning_pct':10,'signal_good':-60,'signal_poor':-80,'ccq_good':90,'ccq_poor':50,'snmp_version':'2c','rate_quality_enabled':False,'rate_good_mbps':100,'rate_poor_mbps':10,'internet_latency_warning_ms':1500,'service_alerts':False}
DEFAULT_PROFILE.update(upload_url='',upload_mb=1,speed_gateway='',device_model='',firmware_version='',wan_interface='',wan_counter_verified=False)

def clean_metrics(metrics):
    """Reject invalid units/enums without inventing replacements; retain Counter64 precision."""
    bounds={'gps_latitude':(-90,90),'gps_longitude':(-180,180),'heading_deg':(0,359.9999),'elevation_deg':(-90,90),'signal_chain0_dbm':(-130,0),'signal_chain1_dbm':(-130,0),'signal_dbm':(-130,0),'noise_dbm':(-150,0),'snr_db':(0,150),
            'tx_ccq':(0,100),'rx_ccq':(0,100),'cpu_pct':(0,100),'memory_pct':(0,100),
            'tx_mbps':(0,100000),'rx_mbps':(0,100000),'frequency_mhz':(1,100000),
            'channel_width_mhz':(1,1000),'uptime_s':(0,2**64-1),
            'in_octets':(0,2**64-1),'out_octets':(0,2**64-1),'counter_epoch':(0,2**64-1)}
    out={}
    for name,value in metrics.items():
        if name not in METRICS or not isinstance(value,(int,float)) or isinstance(value,bool):continue
        if isinstance(value,float) and not math.isfinite(value):continue
        if name in ('ethernet_up','wireless_up'):
            if value in (0,1):out[name]=value
        elif name in bounds and bounds[name][0]<=value<=bounds[name][1]:out[name]=value
    return out

def metric_number(value,scale=1):
    # ASN.1 integers and decimal JSON strings must not pass through float first.
    text=str(value)
    number=int(text) if re.fullmatch(r'[+-]?\d+',text) else float(value)
    return number if scale==1 else number*scale

def validate_profile(p):
    if not isinstance(p,dict):raise ValueError('Integration settings must be an object.')
    if set(p)-set(DEFAULT_PROFILE)-{'url','snmp_port','allow_v2c','rate_cap_kbps'}:raise ValueError('Unknown integration setting; secrets belong in the protected credential fields.')
    if p.get('method','none') not in ('none','snmp','https-json'):raise ValueError('Unsupported adapter.')
    if p.get('snmp_version','2c') not in ('1','2c'):raise ValueError('SNMP version must be 1 or 2c.')
    for key in ('rate_quality_enabled','allow_v2c','service_alerts','firmware_verified','wan_verified','wan_counter_verified','automatic_speed'):
        if key in p and not isinstance(p[key],bool):raise ValueError(key+' must be true or false.')
    for key in ('device_model','firmware_version','wan_interface'):
        if key in p and (not isinstance(p[key],str) or len(p[key])>120 or any(ord(c)<32 for c in p[key])):raise ValueError('Invalid '+key)
    if p.get('wan_counter_verified') and not p.get('wan_interface','').strip():raise ValueError('Name the verified WAN counter interface first.')
    if p.get('rate_poor_mbps',10)>=p.get('rate_good_mbps',100):raise ValueError('Good rate must be above poor rate.')
    if p.get('speed_gateway'):
        from .wan_paths import literal
        literal(p['speed_gateway'])
    for key in ('url','internet_url','speed_url','upload_url'):
        if p.get(key):validate_url(p[key],('https',))
    for key,low,high in [('upload_mb',1,16),('poll_seconds',5,3600),('speed_mb',1,64),('speed_seconds',1,30),('daily_mb',1,1024),('speed_interval',900,86400),('snmp_port',1,65535),('rate_cap_kbps',0,1000000),('min_download_mbps',0,100000),('loss_warning_pct',0,100),('signal_good',-120,-1),('signal_poor',-130,-2),('ccq_good',1,100),('ccq_poor',0,99),('rate_good_mbps',0.01,100000),('rate_poor_mbps',0,99999),('internet_latency_warning_ms',1,60000)]:
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
            for part in cfg['path'].split('/'):value=value[int(part)] if isinstance(value,list) else value[part]
            number=metric_number(value,cfg.get('scale',1))
            if isinstance(number,int) or math.isfinite(number):result[name]=number
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):continue
    return clean_metrics(result)

async def snmp_fetch(d,secrets,source=''):
    from pysnmp.hlapi.v3arch.asyncio import SnmpEngine,CommunityData,UdpTransportTarget,Udp6TransportTarget,ContextData,ObjectType,ObjectIdentity,get_cmd
    p=d.integration
    if not p.get('allow_v2c'):raise ValueError('SNMP v1/v2c must be explicitly enabled on a trusted management network; its community travels unencrypted.')
    if not secrets.get('community'):raise ValueError('Save a read-only SNMP community first.')
    engine=SnmpEngine()
    try:
        try:remote=ipaddress.ip_address(d.host)
        except ValueError:remote=None
        local=ipaddress.ip_address(source) if source else None
        if local and (remote is None or local.version!=remote.version or local.is_unspecified or local.is_multicast):raise ValueError('Source-bound SNMP requires literal matching-family device and local IPs.')
        if '%' in d.host or '%' in source:raise ValueError('Scoped IPv6 SNMP is not verified; use a non-scoped management address.')
        cls=Udp6TransportTarget if remote and remote.version==6 else UdpTransportTarget
        target=await cls.create((d.host,int(p.get('snmp_port',161))),timeout=2,retries=0)
        if source:target.set_local_address((source,0))
        values=list(p.get('oids',{}).items())
        if not values:raise ValueError('No firmware-verified OIDs configured.')
        error,status,index,bindings=await get_cmd(engine,CommunityData(secrets['community'],mpModel=0 if p.get('snmp_version','2c')=='1' else 1),target,ContextData(),*[ObjectType(ObjectIdentity(v['path'])) for k,v in values],lookupMib=False)
        if error or status:raise ValueError('SNMP timeout or rejected request; check firmware, network and read-only community.')
        out={}
        for (name,cfg),binding in zip(values,bindings):
            try:
                value=metric_number(binding[1],cfg.get('scale',1))
                if isinstance(value,int) or math.isfinite(value):out[name]=value
            except (TypeError,ValueError,OverflowError):pass
        return clean_metrics(out)
    finally:engine.close_dispatcher()

def fetch_metrics(d,secrets,source=''):
    p=d.integration;method=p.get('method','none')
    if method=='none':return {},'Telemetry unavailable — configure a verified adapter'
    if not p.get('firmware_verified'):return {},'Firmware/profile not verified'
    if method=='snmp':
        return asyncio.run(asyncio.wait_for(snmp_fetch(d,secrets,source),8)), 'SNMP v'+p.get('snmp_version','2c')+' (configured OIDs; '+('source-bound' if source else 'OS route')+')'
    url=p.get('url','');u=validate_url(url,('https',))
    # Saved device credentials are never sent to a different target host.
    if u.hostname.lower()!=d.host.lower():raise ValueError('Telemetry URL host must match the device management host.')
    headers={}
    if secrets.get('password'):headers['Authorization']='Basic '+base64.b64encode((d.username+':'+secrets['password']).encode()).decode()
    code,body=request(url,source,headers=headers,max_bytes=65536)
    if code!=200:raise ValueError('Telemetry request failed; HTTP '+str(code))
    return normalized(json.loads(body),p.get('fields',{})),'HTTPS JSON (configured fields)'

def quality(metrics,p,age=0):
    metrics=clean_metrics(metrics)
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
    if not math.isfinite(elapsed) or elapsed<=0 or not previous or previous.get('counter_epoch')!=current.get('counter_epoch'):return {}
    previous=clean_metrics(previous);current=clean_metrics(current)
    if 'uptime_s' in previous and 'uptime_s' in current and current['uptime_s']<previous['uptime_s']:return {}
    out={}
    for key,name in [('in_octets','download_mbps'),('out_octets','upload_mbps')]:
        if key in previous and key in current and current[key]>=previous[key]:out[name]=(current[key]-previous[key])*8/elapsed/1e6
    return out

def internet_check(p,source):
    if not p.get('wan_verified'):return 'Not independently measurable'
    if not p.get('internet_url') or not p.get('internet_marker'):return 'Unknown — configure HTTPS endpoint and expected response text'
    code,body=request(p['internet_url'],source,max_bytes=4096)
    return 'Online' if code==200 and p['internet_marker'].encode() in body else 'Offline — external check failed'

def speed_test(p,source='',cancel=None,connection_fn=None):
    if not p.get('wan_verified') or not p.get('speed_url'):raise ValueError('Verify the WAN route and configure a controlled HTTPS download endpoint first.')
    limit=int(p.get('speed_mb',1)*1048576);seconds=p.get('speed_seconds',5);cap=p.get('rate_cap_kbps',0)*1024
    c,path=(connection_fn or connection)(p['speed_url'],source,min(5,seconds));total=0;start=time.monotonic()
    try:
        c.request('GET',path,headers={'Range':f'bytes=0-{limit-1}','Accept-Encoding':'identity'});r=c.getresponse()
        if r.status not in (200,206):raise ValueError('Speed endpoint rejected the request.')
        while total<limit and time.monotonic()-start<seconds and not (cancel and cancel.is_set()):
            data=r.read(min(16384,limit-total))
            if not data:break
            total+=len(data)
            if cap:time.sleep(min(.25,max(0,total/cap-(time.monotonic()-start))))
        elapsed=time.monotonic()-start
        if cancel and cancel.is_set():raise ValueError('Download measurement cancelled; no completed throughput result.')
        if not total:raise ValueError('Speed endpoint returned no data.')
        return {'download_mbps':total*8/max(.001,elapsed)/1e6,'bytes':total,'seconds':elapsed,'rate_kind':'Controlled download throughput'+(' (rate capped)' if cap else ''),'upload_note':'Upload test unavailable; router counters can measure upload traffic'}
    finally:c.close()


def upload_test(p,source='',cancel=None,connection_fn=None):
    """Bounded POST; only an exact receiver acknowledgement yields a measurement."""
    if not p.get('wan_verified') or not p.get('upload_url'):raise ValueError('Configure an authorized HTTPS upload receiver first.')
    limit=int(p.get('upload_mb',1)*1048576);seconds=p.get('speed_seconds',5)
    c,path=(connection_fn or connection)(p['upload_url'],source,min(5,seconds))
    start=time.monotonic();sent=0;chunk=b'Z'*16384
    try:
        if cancel and cancel.is_set():raise ValueError('Upload cancelled.')
        c.putrequest('POST',path);c.putheader('Content-Type','application/octet-stream');c.putheader('Content-Length',str(limit));c.endheaders()
        while sent<limit:
            if (cancel and cancel.is_set()) or time.monotonic()-start>=seconds:raise ValueError('Upload cancelled or duration limit reached; no completed result.')
            block=chunk[:min(len(chunk),limit-sent)];c.send(block);sent+=len(block)
        r=c.getresponse();body=r.read(4097)
        if time.monotonic()-start>seconds or (cancel and cancel.is_set()):raise ValueError('Upload acknowledgement outside test deadline.')
        if r.status!=200 or len(body)>4096:raise ValueError('Upload receiver rejected the test.')
        ack=json.loads(body).get('received_bytes')
        if isinstance(ack,bool) or not isinstance(ack,int) or ack!=sent:raise ValueError('Upload receiver did not acknowledge the exact byte count.')
        elapsed=time.monotonic()-start
        return {'upload_mbps':sent*8/max(.001,elapsed)/1e6,'upload_bytes':sent,'upload_seconds':elapsed}
    finally:c.close()


def independent_speed_test(p,source='',cancel=None):
    from .wan_paths import checked_factory,PathUnavailable
    if not p.get('speed_gateway'):raise PathUnavailable('Set this modem Internet gateway in WAN setup. A ping IP alone cannot select its Internet path.')
    evidence=[];factory=checked_factory(p['speed_gateway'],evidence)
    result=speed_test(p,source,cancel,connection_fn=factory)
    result['route_evidence']=evidence;result['path_checked']=True
    if p.get('upload_url'):
        try:
            result.update(upload_test(p,source,cancel,connection_fn=factory));result.pop('upload_note',None)
        except PathUnavailable as e:result['upload_note']=str(e)
        except Exception:result['upload_note']='Upload unavailable: receiver, cancellation, deadline or acknowledgement failed.'
    return result
