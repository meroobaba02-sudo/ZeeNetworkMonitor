"""Bounded, read-only discovery evidence; DNS/cache entries are not liveness proof."""
import csv,ipaddress,json,os,re,socket,subprocess,time,threading
from pathlib import Path
from .network_paths import interfaces


_inventory_lock=threading.Lock()
_inventory_cache=None

def ipv4_inventory(force=False):
    global _inventory_cache
    with _inventory_lock:
        if not force and _inventory_cache and time.monotonic()-_inventory_cache[0]<60:return [dict(r) for r in _inventory_cache[1]]
        raw=interfaces(connected_only=True)
        rows=_ipv4_rows(raw);_inventory_cache=(time.monotonic(),rows);return rows

def _ipv4_rows(raw):
    rows=[]
    for item in raw:
        try:
            ip=ipaddress.ip_address(item['ip']);prefix=item['prefix']
            if ip.version!=4 or not 0<=prefix<=32:continue
            network=ipaddress.ip_network(f'{ip}/{prefix}',strict=False)
            rows.append(item|{'subnet':str(network),'mask':str(network.netmask)})
        except (ValueError,KeyError,TypeError):continue
    return rows


def targets(value):
    value=value.strip()
    if '-' in value:
        start,end=(ipaddress.IPv4Address(v.strip()) for v in value.split('-',1))
        if int(end)<int(start) or int(end)-int(start)>=1024:raise ValueError('Use an ordered range of at most 1,024 addresses.')
        values=[str(ipaddress.IPv4Address(i)) for i in range(int(start),int(end)+1)]
    else:
        network=ipaddress.ip_network(value,strict=False)
        if network.version!=4 or network.num_addresses>1024:raise ValueError('Use an IPv4 subnet with at most 1,024 addresses or a start-end range.')
        values=list(map(str,network.hosts()))
    if not values or any(ipaddress.ip_address(v).is_multicast or ipaddress.ip_address(v).is_unspecified or v=='255.255.255.255' for v in values):raise ValueError('Use unicast IPv4 targets.')
    return values


def local_scope(hosts,source,inventory):
    # A public/third-party range always needs the explicit remote authorization.
    if not all(ipaddress.ip_address(h).is_private for h in hosts):return False
    for row in inventory:
        if source!=row['ip']:continue
        network=ipaddress.ip_network(row['subnet'])
        if all(ipaddress.ip_address(h) in network for h in hosts):return True
    return False


def ports(value):
    if not value.strip():return []
    try:result=sorted(set(int(v.strip()) for v in value.split(',')))
    except ValueError:raise ValueError('Use comma-separated TCP ports.') from None
    if len(result)>3 or any(not 1<=v<=65535 for v in result):raise ValueError('Choose at most 3 TCP ports from 1 to 65535.')
    return result


def tcp_check(host,source,port,timeout):
    """Connect/close only: no authentication, banner read or payload."""
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM);sock.settimeout(timeout/1000)
    started=time.monotonic()
    try:
        if source:sock.bind((source,0))
        code=sock.connect_ex((host,port))
        return (code==0,(time.monotonic()-started)*1000 if code==0 else None)
    finally:sock.close()


def neighbour_snapshot():
    if os.name!='nt':return []
    command="$live=@(Get-NetNeighbor -AddressFamily IPv4 -State Reachable | ForEach-Object { $_.InterfaceIndex.ToString()+':'+$_.IPAddress }); Get-NetNeighbor -AddressFamily IPv4 | Select-Object IPAddress,LinkLayerAddress,InterfaceIndex,@{Name='Reachable';Expression={ ($_.InterfaceIndex.ToString()+':'+$_.IPAddress) -in $live }} | ConvertTo-Json -Compress"
    try:
        r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=3,creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode or not r.stdout.strip():return []
        raw=json.loads(r.stdout.lstrip('\ufeff'));raw=raw if isinstance(raw,list) else [raw];rows=[]
        for item in raw:
            host=str(ipaddress.IPv4Address(item['IPAddress']));mac=item.get('LinkLayerAddress','').upper().replace('-',':')
            if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}',mac) or mac in ('00:00:00:00:00:00','FF:FF:FF:FF:FF:FF'):continue
            rows.append({'ip':host,'mac':mac,'index':int(item.get('InterfaceIndex',0)),'reachable':item.get('Reachable') is True})
        return rows
    except (OSError,subprocess.TimeoutExpired,ValueError,TypeError,KeyError):return []


def neighbour_for(host,snapshot,index=None):
    matches=[r for r in snapshot if r['ip']==host and index is not None and r['index']==index]
    if len({r['mac'] for r in matches})!=1:return None
    return {'mac':matches[0]['mac'],'reachable':any(r['reachable'] for r in matches)}


def load_vendors(path):
    """Operator-supplied IEEE-style CSV only; never fetch or guess vendors."""
    if not path:return {}
    path=Path(path)
    if path.stat().st_size>8*1024*1024:raise ValueError('Vendor CSV exceeds 8 MB.')
    result={}
    with path.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            assignment=row.get('Assignment',row.get('prefix','')).upper().replace(':','').replace('-','')
            vendor=row.get('Organization Name',row.get('vendor','')).strip()[:200]
            if len(assignment) in (6,7,9) and re.fullmatch('[0-9A-F]+',assignment) and vendor:result[assignment]=vendor
    if not result:raise ValueError('Use Assignment / Organization Name or prefix / vendor CSV columns.')
    return result


def vendor_name(mac,vendors):
    key=mac.replace(':','').replace('-','').upper()
    if len(key)!=12:return 'Unavailable'
    if int(key[:2],16)&2:return 'Unavailable (locally administered MAC)'
    return next((vendors[key[:n]] for n in (9,7,6) if key[:n] in vendors),'Unavailable')
