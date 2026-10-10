"""Pure, conservative correlation: observations support possibilities, not physical proof."""
import hashlib,json
from .telemetry import quality

def context(device,page=None):
    values=[device.host,device.source,device.page_id,device.parent,device.peer_id,device.service_url,
            device.interval,device.timeout,device.latency_threshold,device.failure_threshold,device.integration,
            getattr(page,'source_ip',''),getattr(page,'gateway_hint',''),getattr(page,'routing_verified',False)]
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()[:24]

def fresh(row,now,seconds):
    return bool(row) and isinstance(row.get('at'),(int,float)) and 0<=now-row['at']<=seconds

def service_responding(row):
    return row.get('service','').startswith(('HTTP service responding','Authentication required','HTTP error (','RTSP service responding','RTSP authentication required'))

def evaluate(devices,pings,states,latest,streaks,now,pages=None,minimum_interval=1,correlate=True):
    """Return per-check outcomes and grouped possible locations; Unknown never heals."""
    pages=pages or {};lookup={d.id:d for d in devices};outcomes=[];failures={};ping_good=set()
    for d in devices:
        row=pings.get(d.id,{});tele=latest.get(d.id,{})
        identity=context(d,pages.get(d.page_id))
        ping_fresh=d.enabled and fresh(row,now,max(30,max(d.interval,minimum_interval)*3)) and states.get(d.id)!='Probe error' and row.get('context',identity)==identity
        tele_fresh=d.enabled and fresh(tele,now,max(30,d.integration.get('poll_seconds',30)*3)) and tele.get('context',identity)==identity
        def add(category,status,title,evidence,confidence='Low',step='Check the configured path and device management interface.',at=None):
            outcomes.append({'device':d.id,'page_id':d.page_id,'context':identity,'category':category,'status':status,'title':title,
                             'name':d.name,'host':d.host,'source':d.source or getattr(pages.get(d.page_id),'source_ip','') or 'Automatic (OS route)',
                             'evidence':evidence,'confidence':confidence,'next_step':step,'at':at if at is not None else max(row.get('at',0),tele.get('at',0))})
        if ping_fresh and row.get('success') is True:
            ping_good.add(d.id);add('reachability','healthy','ICMP reply received',['Fresh ICMP reply'],at=row['at'])
        elif ping_fresh and row.get('success') is False and streaks.get(d.id,0)>=d.failure_threshold:
            alternative=tele_fresh and service_responding(tele)
            failures[d.id]={'device':d,'at':row['at'],'alternative':alternative}
            add('reachability','active','ICMP unavailable; service responds' if alternative else 'Endpoint / path possibly unavailable',
                ['Fresh ICMP failures reached the configured threshold']+(['Fresh application response: '+tele['service'],'A responding service contradicts complete device unreachability'] if alternative else ['No fresh alternative response proves reachability']),
                'Medium' if alternative else 'Low','Check ICMP policy / rate limits and service health.' if alternative else 'Try the management service; check power, route and previous hop without assuming a physical failure.',at=row['at'])
            outcomes[-1]['started']=row.get('failure_since',row['at'])
        else:add('reachability','unknown','Insufficient reachability evidence',['Missing/stale/disabled/probe error or threshold not reached'])
        if ping_fresh and row.get('success') is True:
            add('ping_performance','active' if states.get(d.id)=='Warning' else 'healthy' if states.get(d.id)=='Online' else 'unknown',
                'Observed latency / packet loss warning' if states.get(d.id)=='Warning' else 'ICMP performance within configured limits',
                ['Fresh successful ICMP observation; configured warning thresholds applied'],'Medium','Compare latency/loss history and load; do not assume a physical link failure.',at=row['at'])
        else:add('ping_performance','unknown','ICMP performance not observed',['No fresh successful ping'])
        if d.service_url:
            service=tele.get('service','') if tele_fresh else ''
            if service.startswith(('HTTP service responding','RTSP service responding')):
                add('service','healthy','Configured service responds',[service],at=tele['at'])
            elif service.startswith(('Unavailable','HTTP error','RTSP response not accepted')):
                add('service','active','Configured service unavailable / error',[service],'Low','Check this configured service, authentication and TLS. This does not prove device power failure or a failed video stream.',at=tele['at'])
            else:add('service','unknown','Service health insufficient',['No fresh accepted service response; authentication-only response proves reachability, not service access'])
        if d.wan or d.kind.startswith('WAN'):
            internet=tele.get('internet','') if tele_fresh and d.integration.get('wan_verified') else ''
            if internet=='Online':add('internet','healthy','External expected response received',['Fresh configured HTTPS response'],at=tele['at'])
            elif internet.startswith('Offline'):
                add('internet','active','External Internet check failed; router responds' if d.id in ping_good else 'External Internet check failed',
                    ['Configured external endpoint did not return the expected response']+(['Router ICMP reply received'] if d.id in ping_good else []),
                    'Medium' if d.id in ping_good else 'Low','Check another authorized external endpoint and the specific WAN route. Endpoint failure is not proof of a whole-Internet outage.',at=tele['at'])
            else:add('internet','unknown','Insufficient independent WAN evidence',['WAN path unverified or external result missing/stale/error'])
        score,label=quality(tele.get('metrics',{}),d.integration,now-tele.get('at',0)) if tele_fresh else (None,'Unknown')
        if label in ('Poor','Critical'):
            add('wireless','active','Measured wireless '+label.lower(),['Fresh configured metric quality: '+label+f' ({score}/10)'],
                'Medium','Inspect signal/CCQ trends and both peer radios; validate firmware mapping before physical diagnosis.',at=tele['at'])
        elif label in ('Good','Fair'):add('wireless','healthy','Wireless measurements recovered',['Fresh quality '+label],at=tele['at'])
        else:add('wireless','unknown','Insufficient wireless evidence',['No fresh valid scoring metrics'])
    if not correlate:return outcomes,[]
    findings=[]
    for id,failed in failures.items():
        d=failed['device'];cursor=d.parent;seen={id};ancestor=False
        while cursor in lookup and cursor not in seen and lookup[cursor].page_id==d.page_id:
            seen.add(cursor)
            if cursor in failures and abs(failures[cursor]['at']-failed['at'])<=60 and not failures[cursor]['alternative'] and not failed['alternative']:ancestor=True;break
            cursor=lookup[cursor].parent
        if ancestor:continue
        affected=[];healthy=[]
        for child in devices:
            if child.id==id or child.page_id!=d.page_id:continue
            cursor=child.parent;seen=set()
            while cursor in lookup and cursor not in seen:
                if cursor==id:
                    if child.id in failures and not failures[child.id]['alternative'] and abs(failures[child.id]['at']-failed['at'])<=60:affected.append(child.name)
                    elif child.id in ping_good:healthy.append(child.name)
                    break
                seen.add(cursor);cursor=lookup[cursor].parent
        correlated=len(affected)>=2 and not healthy and not failed['alternative']
        parent=lookup.get(d.parent)
        findings.append({'device':d.id,'correlated':correlated,'first_failure':d.name,'last_good':parent.name if parent and parent.id in ping_good else 'Not observed',
                         'affected':affected,'confidence':'Medium' if correlated or failed['alternative'] else 'Low',
                         'title':'Possible common upstream path near '+d.name if correlated else ('ICMP policy / endpoint issue at '+d.name if failed['alternative'] else 'Possible endpoint or path issue at '+d.name),
                         'explanation':('At least two downstream endpoints also have recent threshold failures.' if correlated else 'Evidence does not establish a common upstream fault.')+
                           (' Fresh service responds despite ICMP failure.' if failed['alternative'] else '')+(' Some downstream endpoints still reply.' if healthy else '')+' Physical failure is not confirmed.',
                         'next_step':'Verify the last responding hop, management service and route; inspect the intermediate segment only after alternative checks.'})
    return outcomes,findings

