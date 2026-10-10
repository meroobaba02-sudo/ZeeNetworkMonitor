"""Read-only Windows next-hop checks on the actual TLS socket used by a test."""
import ipaddress,json,os,subprocess
from .connections import connection

class PathUnavailable(ValueError):pass

def literal(value):
    ip=ipaddress.ip_address(value)
    if '%' in value or ip.is_unspecified or ip.is_multicast:raise PathUnavailable('Use a non-scoped, literal gateway/source IP.')
    return str(ip)

def find_route(remote,local):
    remote,local=literal(remote),literal(local)
    if os.name!='nt':raise PathUnavailable('Independent speed-path verification requires Windows.')
    command=f"$ErrorActionPreference='Stop'; Find-NetRoute -RemoteIPAddress '{remote}' -LocalIPAddress '{local}' | Select-Object IPAddress,NextHop,InterfaceIndex,InterfaceAlias | ConvertTo-Json -Compress"
    try:
        r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,errors='replace',timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode:raise PathUnavailable('Windows could not verify this Internet route.')
        rows=json.loads(r.stdout.lstrip('\ufeff'));rows=rows if isinstance(rows,list) else [rows]
        address=next(x for x in rows if x.get('IPAddress'))
        route=next(x for x in rows if x.get('NextHop'))
        if literal(address['IPAddress'])!=local or address['InterfaceIndex']!=route['InterfaceIndex']:raise PathUnavailable('Windows source/interface does not match the connected socket.')
        return {'source':local,'remote':remote,'gateway':str(ipaddress.ip_address(route['NextHop'])),'interface':route['InterfaceIndex']}
    except (subprocess.TimeoutExpired,KeyError,StopIteration,json.JSONDecodeError) as e:raise PathUnavailable('Windows route check unavailable; no speed payload sent.') from e

def checked_factory(gateway,evidence):
    gateway=literal(gateway)
    def connect(url,source,timeout):
        c,path=connection(url,source,timeout)
        try:
            c.connect()
            row=find_route(c.sock.getpeername()[0],c.sock.getsockname()[0])
            if row['gateway']!=gateway:raise PathUnavailable('Wrong Internet gateway: Windows selected '+row['gateway']+'; this modem requires '+gateway+'.')
            c.auto_open=0  # Never silently reconnect after checking this socket.
            evidence.append(row)
            return c,path
        except Exception:
            c.close();raise
    return connect
