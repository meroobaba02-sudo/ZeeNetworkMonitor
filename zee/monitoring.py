"""Two bounded telemetry workers, stale-state handling and capped speed budgets."""
import time,threading
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool,QTimer
from . import telemetry
from .connections import service_check

class Signals(QObject):done=Signal(object,object)
class Task(QRunnable):
    def __init__(self,d,source,secrets,signals,speed,cancel,generation):
        super().__init__();self.d=d;self.source=source;self.secrets=secrets;self.signals=signals;self.speed=speed;self.cancel=cancel;self.generation=generation
    def run(self):
        d=self.d;result={'at':time.time(),'metrics':{}}
        try:
            if self.speed:result.update(telemetry.speed_test(d.integration,self.source,self.cancel))
            else:
                try:
                    metrics,method=telemetry.fetch_metrics(d,self.secrets,self.source);result.update(metrics=metrics,method=method)
                    if 'signal_dbm' in metrics and 'noise_dbm' in metrics:metrics['snr_db']=metrics['signal_dbm']-metrics['noise_dbm']
                except Exception as e:result['telemetry_error']=type(e).__name__+' — verify adapter, credentials and firmware'
                if d.service_url:
                    try:result['service']=service_check(d.service_url,self.source)
                    except Exception:result['service']='Unavailable — timeout, TLS or connection error'
                if d.wan or d.kind.startswith('WAN'):
                    try:
                        started=time.monotonic();result['internet']=telemetry.internet_check(d.integration,self.source)
                        if result['internet']=='Online':result['internet_latency_ms']=(time.monotonic()-started)*1000
                    except Exception:result['internet']='Unknown — TLS, route or external endpoint error'
        except Exception:result['error']='Measurement unavailable — check route, endpoint, credentials and limits'
        self.secrets.clear();self.signals.done.emit((d,self.speed,self.generation),result)

class Measurements(QObject):
    changed=Signal()
    def __init__(self,window,vault):
        super().__init__(window);self.window=window;self.vault=vault;self.pool=QThreadPool(self);self.pool.setMaxThreadCount(2)
        self.pending={};self.due={};self.latest={};self.speed_latest={};self.failures={};self.cancel=threading.Event();self.enabled=False;self.limit=2
        self.signals=Signals();self.signals.done.connect(self.complete)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(1000)
    def submit(self,d,speed=False):
        key=(d.id,speed)
        if self.cancel.is_set() or any(k[0]==d.id for k in self.pending) or len(self.pending)>=self.limit or not d.enabled or not d.host:return False
        page=self.window.page_for_device(d)
        if page is None or page.archived:return False
        if (self.window.monitor_all_enabled or page.interface_hint or page.gateway_hint) and not page.routing_verified:return False
        if self.window.monitor_all_enabled and d.id in self.window.ambiguous_devices:return False
        p=d.integration
        if speed:
            day=time.strftime('%Y-%m-%d');budgetkey='speed-budget:'+d.id+':'+day
            used=self.window.store.setting(budgetkey,0);reservation=int(p.get('speed_mb',1)*1048576)
            if used+reservation>p.get('daily_mb',10)*1048576:raise ValueError('Daily download test budget reached.')
            if not p.get('wan_verified') or not p.get('speed_url'):raise ValueError('Configure and verify a WAN-specific route and HTTPS speed endpoint first.')
            # Reserve the maximum before starting: interrupted/failed tests cannot evade the budget.
            self.window.store.set_setting(budgetkey,used+reservation)
        page=self.window.page_for_device(d)
        source=d.source or page.source_ip
        try:secrets=self.vault.get(d.id)
        except Exception:secrets={}
        self.pending[key]=d;self.due[key]=time.monotonic()+p.get('speed_interval',900) if speed else time.monotonic()+p.get('poll_seconds',30)
        self.pool.start(Task(d,source,secrets,self.signals,speed,self.cancel,self.window.engine.generation));return True
    def complete(self,identity,result):
        d,speed,generation=identity;key=(d.id,speed);self.pending.pop(key,None)
        if self.cancel.is_set() or generation!=self.window.engine.generation:return
        current=next((x for x in self.window.monitor_devices() if x.id==d.id),None)
        if current!=d:return
        if speed:self.speed_latest[d.id]=result
        else:
            old=self.latest.get(d.id,{})
            if d.integration.get('wan_verified'):
                rates=telemetry.counter_rates(old.get('metrics'),result['metrics'],result['at']-old.get('at',result['at']))
                if rates:result.update(rates,rate_kind='WAN interface traffic rate estimate; not available capacity')
            self.latest[d.id]=result
        failed=bool(result.get('error') or result.get('telemetry_error'))
        self.failures[key]=min(5,self.failures.get(key,0)+1) if failed else 0
        self.due[key]=time.monotonic()+min(300,d.integration.get('poll_seconds',30)*2**self.failures[key]) if not speed else self.due[key]
        self.window.store.measurement(d.id,result)
        from .wan import wan_health,fresh
        latest=self.latest.get(d.id,{});speed_row=self.speed_latest.get(d.id,{});now=time.time()
        score,label=telemetry.quality(latest.get('metrics',{}),d.integration,now-latest.get('at',0))
        incidents=['Wireless '+label] if label in ('Poor','Critical') else []
        if d.wan or d.kind.startswith('WAN'):
            state,reason=wan_health(d,self.window.state(d),latest,speed_row,now)
            if state in ('Offline','Degraded'):incidents.append(reason)
        if d.kind.startswith('CCTV') and d.integration.get('service_alerts'):
            from .cctv import camera_health
            service=camera_health(d,latest,now)
            if service.startswith('Service unavailable'):incidents.append(service)
        incident='; '.join(incidents)
        prior=self.window.telemetry_alerted.get(d.id,'')
        if incident and d.alerts:
            self.window.telemetry_alerted[d.id]=incident
            if prior!=incident:self.window.notify(d.id,d.name,incident)
        elif not result.get('error') and not result.get('telemetry_error'):self.window.telemetry_alerted.pop(d.id,None)
        self.changed.emit()
    def tick(self):
        if not self.enabled:return
        for d in self.window.monitor_devices():
            if self.due.get((d.id,False),0)<=time.monotonic():self.submit(d)
            if d.integration.get('automatic_speed') and self.due.get((d.id,True),0)<=time.monotonic():
                try:self.submit(d,True)
                except ValueError:self.due[(d.id,True)]=time.monotonic()+900
    def stop(self):self.enabled=False
    def configure(self,limit=2):
        self.limit=max(1,min(4,int(limit)));self.pool.setMaxThreadCount(self.limit)
    def shutdown(self):self.cancel.set();self.timer.stop();self.pool.clear();self.pool.waitForDone()
