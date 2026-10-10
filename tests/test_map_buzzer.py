import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
import pytest
from PySide6.QtWidgets import QApplication
from zee.buzzer import Buzzer
from zee.core import Store,Device
from zee.gui import Window
from zee.ping import Result

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])

def test_buzzer_off_silence_recovery_new_fault(app):
    sounds=[];b=Buzzer(sound_fn=sounds.append)
    b.update({'a':'No reply'})
    assert b.playing and sounds==[True]
    b.silence();assert not b.playing
    b.update({'a':'No reply'});assert not b.playing
    b.update({'a':'No reply','b':'High latency'});assert b.playing
    b.set_enabled(False);assert not b.playing
    b.set_enabled(True);assert b.playing
    b.update({});assert not b.playing and not b.acknowledged
    b.update({'a':'No reply'});assert b.playing
    b.shutdown();assert not b.playing


def test_silenced_warning_upgrades_to_outage(app):
    b=Buzzer(sound_fn=lambda x:None)
    b.update({'a':'High latency'});b.silence()
    b.update({'a':'No reply'});assert b.playing
    b.shutdown()


def test_map_position_persistence_old_config_compatible(app,tmp_path):
    s=Store(tmp_path/'db')
    a=Device(name='Lahore radio',host='127.0.0.1',location='Lahore')
    s.save(a)
    w=Window(s);w.buzzer.sound_fn=lambda x:None
    w.map_page.select(a.id)
    assert w.map_page.device().id==a.id
    w.map_page.move(a.id,.33,.44)
    saved=w.store.devices()[0]
    assert saved.map_x==.33 and saved.map_y==.44
    # Moving a marker must not throw away a valid in-flight probe.
    w.result(a.id,a,Result(True,2))
    assert s.stats(a.id)['n']==1
    w.map_page.history();assert w.tabs.currentIndex()==2
    w.map_page.canvas.grab()
    w.close()
    s=Store(tmp_path/'db');assert s.devices()[0].map_y==.44;s.close()


def test_fault_threshold_mute_saved_and_restart(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('alarm_delay_seconds',0);d=Device(name='Radio',host='127.0.0.1',failure_threshold=2);s.save(d)
    w=Window(s);sounds=[];w.buzzer.sound_fn=sounds.append
    w.result(d.id,d,Result(False,error='No reply'));assert not w.buzzer.playing
    w.result(d.id,d,Result(False,error='No reply'));assert w.buzzer.playing
    w.buzzer_button.setChecked(False);assert not w.buzzer.playing
    assert s.setting('buzzer_enabled') is False
    w.buzzer_button.setChecked(True);assert w.buzzer.playing
    w.silence_buzzer();assert not w.buzzer.playing
    w.result(d.id,d,Result(True,4));assert not w.buzzer.active
    w.result(d.id,d,Result(False));w.result(d.id,d,Result(False));assert w.buzzer.playing
    w.buzzer_button.setChecked(False);w.close()
    s=Store(tmp_path/'db');w=Window(s);assert not w.buzzer.enabled;w.close()


def test_invalid_map_position():
    with pytest.raises(ValueError):Device(name='bad',host='localhost',map_x=1.5,map_y=.2).validate()
    with pytest.raises(ValueError):Device(name='bad',host='localhost',map_x=.5).validate()


def test_stale_or_disabled_device_stops_alarm(app,tmp_path):
    import time
    s=Store(tmp_path/'db');s.set_setting('alarm_delay_seconds',0);d=Device(name='Radio',host='127.0.0.1',failure_threshold=1);s.save(d)
    w=Window(s);w.buzzer.sound_fn=lambda x:None
    w.result(d.id,d,Result(False));assert w.buzzer.playing
    w.latest[d.id]['at']=time.time()-200;w.refresh_states()
    assert not w.buzzer.playing
    w.result(d.id,d,Result(False));assert w.buzzer.playing
    s.save(replace(d,enabled=False));w.reload();assert not w.buzzer.playing
    w.close()
