import json,os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from zee.buzzer import Buzzer
from zee import wan_paths
from zee.core import Store,Device
from zee.gui import Window
from zee.wan_dialog import WanDialog


def test_alarm_delay_short_fault_recovery_and_new_incident():
    app=QApplication.instance() or QApplication([])
    now=[0.0];sounds=[]
    b=Buzzer(sound_fn=sounds.append,delay_seconds=15,clock=lambda:now[0])
    b.update({'a':'No reply'});assert not b.playing
    now[0]=10;b.update({'a':'No reply'});assert not b.playing
    b.update({});now[0]=20;b.refresh();assert not b.playing
    b.update({'a':'No reply'});now[0]=34.9;b.refresh();assert not b.playing
    now[0]=35;b.refresh();assert b.playing and sounds==[True]
    b.silence();assert not b.playing
    now[0]=50;b.update({'a':'No reply'});assert not b.playing
    b.update({});b.update({'a':'No reply'});assert not b.playing
    now[0]=65;b.refresh();assert b.playing
    b.shutdown();assert not b.delay_timer.isActive()


def test_route_selects_matching_interface_and_missing_command(monkeypatch):
    monkeypatch.setattr(wan_paths.os,'name','nt')
    monkeypatch.setattr(wan_paths.subprocess,'CREATE_NO_WINDOW',0,raising=False)
    rows=[{'NextHop':'192.0.2.99','InterfaceIndex':99}, {'IPAddress':'192.0.2.10','InterfaceIndex':2}, {'NextHop':'192.0.2.1','InterfaceIndex':2}]
    monkeypatch.setattr(wan_paths.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(rows)))
    assert wan_paths.find_route('198.51.100.1','192.0.2.10')['gateway']=='192.0.2.1'
    def missing(*a,**k):raise FileNotFoundError('powershell missing')
    monkeypatch.setattr(wan_paths.subprocess,'run',missing)
    import pytest
    with pytest.raises(wan_paths.PathUnavailable,match='unavailable'):wan_paths.find_route('198.51.100.1','192.0.2.10')


def test_download_preset_and_saved_alarm_delay(tmp_path):
    app=QApplication.instance() or QApplication([])
    store=Store(tmp_path/'db');d=Device(name='WAN',host='192.0.2.1',wan=1);store.save(d)
    w=Window(store);w.buzzer.sound_fn=lambda _:None
    assert w.buzzer.delay_seconds==15
    dialog=WanDialog(w,d);dialog.download_preset()
    assert dialog.fields['speed_url'].text()=='https://speed.cloudflare.com/__down?bytes=1048576'
    assert not dialog.verified.isChecked() and not dialog.auto.isChecked()
    assert dialog.fields['upload_url'].text()==''
    w.alarm_delay.setValue(25);w.save_settings()
    assert store.setting('alarm_delay_seconds')==25 and w.buzzer.delay_seconds==25
    dialog.close();w.close()


def test_window_short_ping_outage_cancels_pending_alarm(tmp_path):
    from zee.ping import Result
    app=QApplication.instance() or QApplication([])
    store=Store(tmp_path/'db');d=Device(name='Radio',host='127.0.0.1',failure_threshold=1);store.save(d)
    w=Window(store);now=[0.0];w.buzzer.clock=lambda:now[0];w.buzzer.sound_fn=lambda _:None
    w.result(d.id,d,Result(False,error='No reply'))
    assert d.id in w.buzzer.active and not w.buzzer.playing
    now[0]=10;w.result(d.id,d,Result(True,2));now[0]=20;w.buzzer.refresh()
    assert not w.buzzer.active and not w.buzzer.playing
    w.result(d.id,d,Result(False,error='No reply'));now[0]=35;w.buzzer.refresh()
    assert w.buzzer.playing
    w.close()
