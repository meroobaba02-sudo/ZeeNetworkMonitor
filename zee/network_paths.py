"""Read-only adapter inventory, source snapshots and ambiguity checks."""
from dataclasses import replace
import ipaddress,json,os,socket,subprocess
from .ping import probe,Result


def normalize_interfaces(payload):
    rows=payload if isinstance(payload,list) else [payload]
    result=[]
    for row in rows:
        try:
            ip=ipaddress.ip_address(row['IPAddress'])
            if ip.is_unspecified or ip.is_multicast:continue
            index=int(row.get('InterfaceIndex',0));address=str(ip)
            if ip.version==6 and ip.is_link_local and not ip.scope_id and index>0:address+='%' + str(index)
            result.append({'ip':address,'name':str(row.get('InterfaceAlias',''))[:120],'index':index,'prefix':int(row.get('PrefixLength',0))})
        except (ValueError,TypeError,KeyError):continue
    return sorted(result,key=lambda r:(r['index'],r['ip']))


def interfaces():
    if os.name=='nt':
        command="Get-NetIPAddress | Select-Object IPAddress,InterfaceAlias,InterfaceIndex,PrefixLength | ConvertTo-Json -Compress"
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,errors='replace',timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:raise ValueError('Windows adapter inventory unavailable. Enter a local IP manually.')
        return normalize_interfaces(json.loads(result.stdout.lstrip('\ufeff')))
    # Development fixture only; do not invent an inventory of the Windows laptop.
    return [{'ip':'127.0.0.1','name':'Loopback (development host)','index':0,'prefix':8},{'ip':'::1','name':'Loopback (development host)','index':0,'prefix':128}]


def ambiguous_hosts(devices,pages):
    def key(address):
        if not address:return ''
        try:
            ip=ipaddress.ip_address(address);canonical=str(ip)
            if ip.version==6 and ip.scope_id and ip.scope_id.isdigit():canonical=canonical.rsplit('%',1)[0]+'%'+str(int(ip.scope_id))
            return canonical
        except ValueError:return address.casefold().rstrip('.')
    groups={}
    for d in devices:
        if d.enabled and d.host:groups.setdefault(key(d.host),[]).append(d)
    blocked=set()
    for group in groups.values():
        if len({d.page_id for d in group})<2:continue
        by_page={}
        for d in group:by_page.setdefault(d.page_id,set()).add(key(d.source or pages[d.page_id].source_ip))
        sources=list(by_page.values())
        conflict=any(a & b for i,a in enumerate(sources) for b in sources[i+1:])
        if any('' in s for s in sources) or conflict or not all(pages[d.page_id].routing_verified for d in group):blocked.update(d.id for d in group)
    return blocked


def prepare_probe(device,page,fn,require_verified=False,ambiguous=False):
    if page is None or page.archived:
        return lambda d:Result(False,error='Network is archived or unavailable.',infrastructure_error=True)
    if ambiguous:
        return lambda d:Result(False,error='Same target exists on multiple networks: configure distinct source IPs and verify each Windows path.',infrastructure_error=True)
    if (require_verified or page.interface_hint or page.gateway_hint) and not page.routing_verified:
        return lambda d:Result(False,error='Network path not operator-verified; checks paused.',infrastructure_error=True)
    source=device.source or page.source_ip
    try:
        if source and ipaddress.ip_address(source).version!=ipaddress.ip_address(device.host).version:raise ValueError()
    except ValueError:
        return lambda d:Result(False,error='Source-bound checks require matching literal IP versions.',infrastructure_error=True)
    snapshot=replace(device,source=source)
    return lambda d:fn(snapshot)


def peer_quality(first,second,latest,now):
    from .telemetry import quality
    labels=[]
    for d in (first,second):
        row=latest.get(d.id,{})
        labels.append(quality(row.get('metrics',{}),d.integration,now-row.get('at',0))[1])
    rank={'Good':0,'Fair':1,'Poor':2,'Critical':3}
    combined='Unknown' if 'Unknown' in labels else max(labels,key=rank.get)
    return combined,labels


def inspect_path(target,source=''):
    ip=ipaddress.ip_address(target)
    if source and ipaddress.ip_address(source).version!=ip.version:raise ValueError('Source and target IP versions must match.')
    sock=socket.socket(socket.AF_INET6 if ip.version==6 else socket.AF_INET,socket.SOCK_DGRAM)
    try:
        if source:sock.bind((source,0))
        sock.connect((str(ip),161));selected=sock.getsockname()[0]
    finally:sock.close()
    # Explicit user-requested test sends one ICMP echo, never alters a route/device.
    from .core import Device
    result=probe(Device(name='Network path test',host=str(ip),source=source,timeout=1500))
    outcome='ICMP reply received' if result.success else ('Probe unavailable' if result.infrastructure_error else 'No ICMP reply')
    from .wan import route_report
    inventory=route_report(str(ip),source)
    return {'source':selected,'target':str(ip),'reply':result.success,'at':__import__('time').time(),'text':f'{outcome}\nTarget: {ip}\nConfigured source: {source or "Automatic"}\nOS-selected local source: {selected}\n'+(result.error+'\n' if result.error else '')+'This is reachability evidence, not proof of the intended dish, WAN gateway or Internet path. One ICMP test was requested. No adapter, route, firewall or remote-device settings were changed.\n\nRead-only route inventory (no UDP data sent):\n'+inventory}
