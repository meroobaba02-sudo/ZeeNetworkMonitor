"""Truthful dashboard summaries and measurement sample statistics."""
import math
from .telemetry import quality

def speed_statistics(rows):
    groups={}
    for row in rows:
        kind=row.get('rate_kind','Unspecified measurement')
        for field,label in [('download_mbps','download'),('upload_mbps','upload')]:
            value=row.get(field)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0:
                groups.setdefault((kind,label),[]).append(value)
    return ' | '.join(f'{kind} {label}: {len(values)} samples, min {min(values):.2f}, avg {sum(values)/len(values):.2f}, max {max(values):.2f} Mbps' for (kind,label),values in groups.items()) or 'Speed unavailable; no measured samples.'

def dashboard_text(devices,states,latest,speeds,towers,alerts,telemetry_alerts,now):
    counts={key:sum(states.get(d.id)==key for d in devices) for key in ('Online','Warning','No reply')}
    wireless={'Good':0,'Fair':0,'Poor':0,'Critical':0,'Unknown':0};wan={'Online':0,'Offline':0,'Unknown':0}
    active=set();last_ok=[]
    for d in devices:
        row=latest.get(d.id,{})
        fresh=now-row.get('at',0)<max(30,d.integration.get('poll_seconds',30)*3)
        if 'wireless radio' in d.kind or d.role or d.peer_id:
            _,label=quality(row.get('metrics',{}),d.integration,now-row.get('at',0));wireless[label if label in wireless else 'Unknown']+=1
        if d.wan:
            status=row.get('internet','Unknown') if fresh else 'Unknown'
            wan['Online' if status=='Online' else 'Offline' if status.startswith('Offline') else 'Unknown']+=1
        if d.enabled and d.alerts:
            if d.id in alerts and states.get(d.id) in ('Warning','No reply'):active.add(d.id)
            if d.id in telemetry_alerts and fresh:active.add(d.id)
        if fresh and not row.get('error') and row: last_ok.append(row['at'])
    unknown=len(devices)-sum(counts.values())
    refreshed=f'{max(0,int(now-max(last_ok)))}s ago' if last_ok else 'No successful telemetry refresh'
    return (f'Devices {len(devices)}  •  Online {counts["Online"]}  •  Warning {counts["Warning"]}  •  No reply {counts["No reply"]}  •  Other / unknown {unknown}  •  Towers {towers}\n'
            f'Wireless: good {wireless["Good"]}, degraded {wireless["Fair"]+wireless["Poor"]}, critical {wireless["Critical"]}, unknown {wireless["Unknown"]}  •  WAN Internet: online {wan["Online"]}, offline {wan["Offline"]}, unknown {wan["Unknown"]}  •  Active device alerts {len(active)}\n'
            f'Last successful telemetry refresh: {refreshed}. Ping reply does not prove wireless or Internet health.')
