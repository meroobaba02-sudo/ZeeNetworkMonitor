import csv
import sqlite3
import pytest
from zee.core import Device,Store,validate_host,export_csv,diagnoses,outages,TYPES
from zee.ping import Result,parse_ping,command,probe

@pytest.mark.parametrize('host',['192.168.1.3','::1','router.local','WAN-gateway','example.com.'])
def test_valid_host(host):
    assert validate_host(host)==host

@pytest.mark.parametrize('host',['','999.1.2.3','1.2.3','-n','host name','https://example.com','a;whoami','host_1','fe80:::1'])
def test_invalid_host(host):
    with pytest.raises(ValueError): validate_host(host)

@pytest.mark.parametrize('text,code,ok,ms',[
    ('Reply from 192.168.1.1: bytes=32 time=15ms TTL=64',0,True,15),
    ('Reply from 127.0.0.1: bytes=32 time<1ms TTL=128',0,True,.5),
    ('64 bytes from host: icmp_seq=1 ttl=64 time=2.31 ms',0,True,2.31),
    ('Antwort: Bytes=32 Zeit=4ms TTL=128',0,True,4),
    ('ttl=64 temps=1,2 ms',0,True,1.2),
    ('Request timed out.',1,False,None),
    ('Reply from 1.1.1.1: Destination host unreachable.',0,False,None),
    ('TTL expired in transit.',1,False,None),
    ('Reply from ::1: time<1ms',0,True,.5),
    ('ttl=64 time=1ms',1,False,None),
])
def test_parsing(text,code,ok,ms):
    r=parse_ping(text,code)
    assert r.success==ok and r.latency==ms


def test_store_restart_export_backup(tmp_path):
    path=tmp_path/'state.db'
    s=Store(path)
    d=Device(name='=WAN test',host='127.0.0.1')
    s.save(d)
    s.record(d.id,Result(True,5),10)
    s.record(d.id,Result(False,error='No reply'),20)
    s.set_setting('beep',True)
    s.backup(tmp_path/'backup.db')
    s.close()
    s=Store(path)
    assert s.devices()[0]==d
    assert s.setting('beep') is True
    assert s.stats(d.id)['loss']==50
    assert s.stats(d.id)['latency']==5
    export_csv(tmp_path/'events.csv',s.events(),['device','at','kind','message'])
    assert len(list(csv.DictReader((tmp_path/'events.csv').open(encoding='utf-8-sig'))))==1
    export_csv(tmp_path/'safe.csv',[{'name':d.name}],['name'])
    assert "'=WAN" in (tmp_path/'safe.csv').read_text(encoding='utf-8-sig')
    backup=Store(tmp_path/'backup.db')
    assert backup.stats(d.id)['n']==2
    backup.close()
    s.close()


def test_topology_cycle_and_delete(tmp_path):
    s=Store(tmp_path/'db')
    a=Device(name='Lahore',host='127.0.0.1');s.save(a)
    b=Device(name='Hop',host='127.0.0.2',parent=a.id);s.save(b)
    c=Device(name='Sargodha',host='127.0.0.3',parent=b.id);s.save(c)
    a.parent=c.id
    with pytest.raises(ValueError):s.save(a)
    diagnosis=diagnoses(s.devices(),{a.id:'Online',b.id:'No reply',c.id:'No reply'})
    assert len(diagnosis)==1 and diagnosis[0]['affected']==['Sargodha'] and diagnosis[0]['last_good']=='Lahore'
    s.delete(b.id)
    assert next(d for d in s.devices() if d.id==c.id).parent==''
    s.close()


def test_prune_and_filter(tmp_path):
    import time
    s=Store(tmp_path/'db')
    s.event('a','status','Old',1)
    s.event('b','alert','New')
    s.prune(1)
    assert len(s.events())==1
    assert len(s.events(device='b',search='NEW'))==1
    assert not s.events(until=time.time()-100)
    s.close()


def test_outages():
    rows=[{'at':1,'success':True},{'at':2,'success':False},{'at':3,'success':False},{'at':5,'success':True},{'at':9,'success':False}]
    assert outages(rows)==[(2,5),(9,None)]


def test_command_and_source_validation():
    d=Device(name='test',host='::1',source='::1')
    d.validate()
    args=command(d,'Windows')
    assert args==['ping','-n','1','-w','2000','-6','-S','::1','::1']
    d.source='192.168.1.1'
    with pytest.raises(ValueError): d.validate()


def test_missing_ping(monkeypatch):
    import zee.ping as module
    def missing(*a,**kw): raise FileNotFoundError()
    monkeypatch.setattr(module.subprocess,'run',missing)
    assert probe(Device(host='127.0.0.1')).infrastructure_error


def test_timeout(monkeypatch):
    import subprocess
    import zee.ping as module
    def timeout(*a,**kw): raise subprocess.TimeoutExpired('ping',2)
    monkeypatch.setattr(module.subprocess,'run',timeout)
    r=probe(Device(host='127.0.0.1'))
    assert not r.success and not r.infrastructure_error


def test_live_loopback_if_system_ping_available():
    import shutil
    if not shutil.which('ping'):
        pytest.skip('System ping executable unavailable on this test host')
    d=Device(name='Loopback',host='127.0.0.1')
    r=probe(d)
    assert r.success, r.error


@pytest.mark.parametrize('message',['Ping request could not find host wrong.local.','ping: wrong.local: Name or service not known','ping: socket: Operation not permitted'])
def test_probe_environment_errors(message):
    r=parse_ping(message,2)
    assert not r.success and r.infrastructure_error


def test_unknown_schema_rejected(tmp_path):
    path=tmp_path/'new.db'
    c=sqlite3.connect(path);c.execute('PRAGMA user_version=99');c.close()
    with pytest.raises(ValueError,match='schema'):Store(path)
    c=sqlite3.connect(path)
    assert c.execute('PRAGMA user_version').fetchone()[0]==99
    c.close()
