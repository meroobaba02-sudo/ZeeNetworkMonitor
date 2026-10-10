"""Presentation helpers: unavailable/stale evidence is never converted into healthy data."""
import math

def rate(row,key):
    value=row.get(key)
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0:return f'{value:.2f}'
    return 'Unavailable'

def wan_view(d,state,metrics,test,now):
    live=0<=now-metrics.get('at',0)<=max(30,d.integration.get('poll_seconds',30)*3)
    checked=test.get('path_checked') is True and not test.get('error')
    age=now-test.get('at',0)
    current_test=checked and 0<=age<=max(60,d.integration.get('speed_interval',900))
    status=metrics.get('internet','Not configured') if live else 'Unknown / no fresh check'
    return {'name':d.name,'host':d.host or 'IP not configured','router':state,'internet':status,
            'download':rate(metrics,'download_mbps') if live else 'Unavailable',
            'upload':rate(metrics,'upload_mbps') if live else 'Unavailable',
            'test_download':rate(test,'download_mbps') if current_test else 'Unavailable',
            'test_upload':rate(test,'upload_mbps') if current_test else 'Unavailable',
            'test_age':f'{int(age)}s ago'+(' • old result' if not current_test else '') if test.get('at') and age>=0 else 'Not tested',
            'test_note':test.get('error',test.get('upload_note','Route-checked HTTPS test' if checked else 'Independent path not measured'))}

def device_counts(devices,states):
    online=sum(states.get(d.id)=='Online' for d in devices)
    attention=sum(states.get(d.id) in ('Warning','No reply','Probe error') for d in devices)
    return {'devices':len(devices),'online':online,'attention':attention,'other':len(devices)-online-attention}
