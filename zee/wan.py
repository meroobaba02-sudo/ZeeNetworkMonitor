"""Independent Internet health and read-only local routing diagnostics."""
import ipaddress,socket,subprocess,os

def fresh(row,seconds,now):
    return bool(row) and now-row.get('at',0)<=seconds

def wan_health(device,ping,row,speed,now):
    if not device.enabled:return 'Unknown','Monitoring disabled'
    if not device.integration.get('wan_verified'):return 'Unknown','WAN path not independently verified'
    if not fresh(row,max(30,device.integration.get('poll_seconds',30)*3),now):return 'Unknown','Internet result missing or stale'
    internet=row.get('internet','Unknown')
    if internet.startswith('Offline'):return 'Offline','External endpoint check failed'
    if internet!='Online':return 'Unknown',internet
    issues=[]
    if ping in ('Warning','No reply','Probe error'):issues.append('Router ping '+ping.lower())
    if row.get('internet_latency_ms',0)>device.integration.get('internet_latency_warning_ms',1500):issues.append('External HTTPS latency high')
    if fresh(speed,max(60,device.integration.get('speed_interval',900)),now) and 'download_mbps' in speed and speed['download_mbps']<device.integration.get('min_download_mbps',0):issues.append('Measured download below threshold')
    return ('Degraded','; '.join(issues)) if issues else ('Online','Expected external response received through configured path')

def route_report(target,source=''):
    """No probe data sent; UDP connect selects an OS route without send()."""
    ip=ipaddress.ip_address(target)
    if source and ipaddress.ip_address(source).version!=ip.version:raise ValueError('Source and target IP versions must match.')
    sock=socket.socket(socket.AF_INET6 if ip.version==6 else socket.AF_INET,socket.SOCK_DGRAM)
    try:
        if source:sock.bind((source,0))
        sock.connect((str(ip),161));selected=sock.getsockname()[0]
    finally:sock.close()
    lines=[f'Target: {ip}',f'Configured source: {source or "Automatic"}',f'OS-selected local source: {selected}',
           'Source selection is not proof of a particular WAN gateway. Verify the interface, next hop and external endpoint path.',
           'No routes, firewall rules or adapter settings were changed. No UDP data was sent.']
    if os.name=='nt':
        for cmd in (['ipconfig'],['route','print','-6' if ip.version==6 else '-4']):
            try:
                r=subprocess.run(cmd,capture_output=True,text=True,errors='replace',timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
                lines.extend([' '.join(cmd),r.stdout[:16000] if r.returncode==0 else 'Windows command failed.'])
            except (OSError,subprocess.TimeoutExpired):lines.append('Windows diagnostics unavailable or timed out.')
    else:lines.append('Windows adapter and route inventory is available in the Windows build.')
    return '\n\n'.join(lines)
