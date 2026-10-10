import json
import sqlite3
from dataclasses import replace
import pytest
from zee.core import Store,Device,Station
from zee import regionmap


def test_v1_upgrade_backs_up_existing_device_and_history(tmp_path):
    path=tmp_path/'old.db';db=sqlite3.connect(path)
    db.executescript('CREATE TABLE devices(id TEXT PRIMARY KEY,data TEXT NOT NULL); PRAGMA user_version=1;')
    db.execute('INSERT INTO devices VALUES(?,?)',('old',json.dumps({'id':'old','name':'Old radio','host':'127.0.0.1'})));db.commit();db.close()
    store=Store(path)
    assert store.devices()[0].station_id==''
    assert Path(str(path)+'.pre-v030.bak').exists()
    tower=Station(name='My tower');store.save_station(tower)
    store.save(replace(store.devices()[0],station_id=tower.id))
    store.close();store=Store(path)
    assert store.devices()[0].station_id==tower.id
    store.delete_station(tower.id)
    assert store.devices()[0].station_id==''
    assert not store.stations();store.close()

from pathlib import Path

def test_unlimited_radios_and_valid_tower(tmp_path):
    store=Store(tmp_path/'db');tower=Station(name='Tower');store.save_station(tower)
    for i in range(4):store.save(Device(name=f'Radio {i}',host='localhost',station_id=tower.id,dish_side='Right' if i%2 else 'Left'))
    store.save(Device(name='Fifth',host='localhost',station_id=tower.id))
    assert len(store.devices())==5
    with pytest.raises(ValueError):store.save(Device(name='Missing',host='localhost',station_id='missing'))
    store.save(replace(store.devices()[0],name='Edited'))
    store.close()

def test_map_gps_roundtrip_and_bounded_import(tmp_path):
    x,y=regionmap.position(31.773901,69.349685)
    lat,lon=regionmap.coordinates(x,y)
    assert lat==pytest.approx(31.773901) and lon==pytest.approx(69.349685)
    data={'format':'zee-vector-1','bbox':list(regionmap.BBOX),'features':[{'kind':'road','name':'fixture','points':[[31.34,69.44],[31.35,69.45]]}]}
    path=tmp_path/'map.json';regionmap.save(path,data);assert regionmap.load(path)==data
    data['features'][0]['points'][0][0]=float('nan')
    with pytest.raises(ValueError):regionmap.save(path,data)
    assert regionmap.load(path)['features'][0]['points'][0][0]==31.34

def test_tower_canvas_group_selection_and_persistence(tmp_path):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from zee.gui import Window
    app=QApplication.instance() or QApplication([])
    store=Store(tmp_path/'db');tower=Station(name='Tower A');store.save_station(tower)
    radios=[]
    for i in range(4):
        d=Device(name=f'R{i}',host='localhost',station_id=tower.id,dish_side='Left' if i<2 else 'Right');store.save(d);radios.append(d)
    w=Window(store);w.buzzer.sound_fn=lambda x:None;w.show();app.processEvents()
    w.map_page.select(tower.id);w.map_page.canvas.grab()
    canvas=w.map_page.canvas
    assert len(canvas.station_boxes)==1 and len(canvas.dish_boxes)==4 and not canvas.boxes
    assert w.map_page.radios.count()==4
    w.map_page.select(radios[3].id);assert w.map_page.device().id==radios[3].id
    w.map_page.move(tower.id,.3,.4)
    saved=store.stations()[0];assert saved.latitude is not None
    x,y=regionmap.position(saved.latitude,saved.longitude)
    assert x==pytest.approx(.3) and y==pytest.approx(.4)
    w.close()
