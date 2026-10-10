"""Domain model, SQLite persistence, topology diagnostics and exports."""
from __future__ import annotations
import csv
import ipaddress
import json
import re
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from .workspaces import WorkspaceStore,NetworkPage
from pathlib import Path

VERSION = '0.4.1'
TYPES = ['WAN / Internet', 'Rocket M5 / wireless radio', 'Router', 'Switch', 'CCTV / NVR / camera', 'Server / monitoring agent', 'Other']


def validate_host(host: str, allow_empty=False) -> str:
    host = host.strip()
    if not host and allow_empty:
        return host
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if re.fullmatch(r'[0-9.]+', host) or ':' in host:
        raise ValueError('Invalid IP address. Example: 192.168.1.20')
    name = host.rstrip('.')
    if not name or len(name) > 253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in name.split('.')):
        raise ValueError('Enter an IP address or hostname only; URLs, spaces and command options are not allowed.')
    return host


@dataclass
class Device:
    id: str = ''
    name: str = ''
    host: str = ''
    kind: str = 'Other'
    location: str = ''
    parent: str = ''
    next_hop: str = ''
    wan: int = 0
    notes: str = ''
    enabled: bool = True
    interval: int = 10
    timeout: int = 2000
    alerts: bool = True
    latency_threshold: int = 150
    failure_threshold: int = 3
    source: str = ''
    profile: str = ''
    station_id: str = ''
    dish_side: str = 'Left'
    page_id: str = 'default'
    management_url: str = ''
    service_url: str = ''
    username: str = ''
    role: str = ''
    peer_id: str = ''
    integration: dict = field(default_factory=dict)
    map_x: float | None = None
    map_y: float | None = None

    def validate(self):
        from .connections import validate_url
        for url,schemes in [(self.management_url,('http','https')),(self.service_url,('http','https','rtsp'))]:
            if url:validate_url(url,schemes)
        from .telemetry import validate_profile
        validate_profile(self.integration)
        if self.dish_side not in ('Left', 'Right'):
            raise ValueError('Dish side must be Left or Right.')
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('Device name is required.')
        self.host = validate_host(self.host, allow_empty=True)
        if self.enabled and not self.host:
            raise ValueError('Enter a host, or disable monitoring for an unconfigured device.')
        if self.kind not in TYPES:
            raise ValueError('Unknown device type.')
        if not 1 <= self.interval <= 3600 or not 100 <= self.timeout <= 10000:
            raise ValueError('Interval must be 1–3600 seconds; timeout 100–10000 ms.')
        if not 0 <= self.wan <= 99 or not 1 <= self.failure_threshold <= 100 or not 1 <= self.latency_threshold <= 60000:
            raise ValueError('Invalid WAN number or alert threshold.')
        if (self.map_x is None) != (self.map_y is None):
            raise ValueError('Both map positions must be set together.')
        if self.map_x is not None and not (0 <= self.map_x <= 1 and 0 <= self.map_y <= 1):
            raise ValueError('Map position must be between 0 and 100 percent.')
        if self.source:
            src=ipaddress.ip_address(self.source)
            try:dst=ipaddress.ip_address(self.host)
            except ValueError:raise ValueError('Source-bound monitoring requires a literal IP target.')
            if src.version!=dst.version:raise ValueError('Source and destination IP families must match.')
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.parent == self.id or self.next_hop == self.id:
            raise ValueError('A device cannot link to itself.')


@dataclass
class Station:
    page_id: str = 'default'
    height: float = 0
    notes: str = ''
    id: str = ''
    name: str = ''
    map_x: float = .5
    map_y: float = .5
    latitude: float | None = None
    longitude: float | None = None

    def validate(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('Tower name is required.')
        if not 0 <= self.map_x <= 1 or not 0 <= self.map_y <= 1:
            raise ValueError('Map position must be 0–100 percent.')
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Enter both GPS coordinates.')
        if self.latitude is not None and not (-85 <= self.latitude <= 85 and -180 <= self.longitude <= 180):
            raise ValueError('Invalid GPS coordinates.')
        if not self.id:
            self.id = str(uuid.uuid4())


class Store(WorkspaceStore):
    """Owned by the GUI/main thread. Workers never touch this connection."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        schema = self.db.execute('PRAGMA user_version').fetchone()[0]
        if schema not in (0, 1, 2, 3):
            self.db.close()
            raise ValueError('Unsupported database schema. Use the matching app version or restore a compatible backup.')
        if schema == 1:
            target = sqlite3.connect(str(self.path)+'.pre-v030.bak')
            try: self.db.backup(target)
            finally: target.close()
        if schema == 2:
            target=sqlite3.connect(str(self.path)+'.pre-v040.bak')
            try:self.db.backup(target)
            finally:target.close()
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS measurements(id INTEGER PRIMARY KEY,device TEXT,at REAL,data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS measurement_device_time ON measurements(device,at);
        CREATE TABLE IF NOT EXISTS stations(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, device TEXT, at REAL, success INTEGER, latency REAL, error TEXT);
        CREATE INDEX IF NOT EXISTS sample_device_time ON samples(device, at);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, device TEXT, at REAL, kind TEXT, message TEXT);
        CREATE INDEX IF NOT EXISTS event_time ON events(at);
        PRAGMA user_version=3;
        ''')
        self.db.commit()

        if not self.pages():self.save_page(NetworkPage())

    def stations(self):
        return [Station(**json.loads(r[0])) for r in self.db.execute('SELECT data FROM stations ORDER BY rowid')]

    def save_station(self, station):
        station.validate()
        if station.page_id not in {p.id for p in self.pages()}:raise ValueError('Network no longer exists.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO stations VALUES(?,?)', (station.id,json.dumps(asdict(station))))
            self.event(station.id,'config','Tower saved: '+station.name)

    def delete_station(self, id):
        with self.db:
            for d in self.devices():
                if d.station_id == id:
                    d.station_id = ''
                    self.db.execute('UPDATE devices SET data=? WHERE id=?',(json.dumps(asdict(d)),d.id))
            self.db.execute('DELETE FROM stations WHERE id=?',(id,))
            self.event(id,'config','Tower removed; radios and history retained')

    def devices(self):
        return [Device(**json.loads(r[0])) for r in self.db.execute('SELECT data FROM devices ORDER BY rowid')]

    def save(self, device):
        device.validate()
        if device.page_id not in {p.id for p in self.pages()}:raise ValueError('Network no longer exists.')
        if device.station_id and any(s.id==device.station_id and s.page_id!=device.page_id for s in self.stations()):raise ValueError('Tower belongs to a different network.')
        if device.station_id and device.station_id not in {s.id for s in self.stations()}:
            raise ValueError('Selected tower no longer exists.')
        devices = {d.id: d for d in self.devices()}
        devices[device.id] = device
        for ref in (device.parent, device.next_hop,device.peer_id):
            if ref and ref not in devices:
                raise ValueError('Linked device no longer exists.')
            if ref and devices[ref].page_id!=device.page_id:raise ValueError('Links must stay within one network page.')
        seen = {device.id}
        cursor = device.parent
        while cursor:
            if cursor in seen:
                raise ValueError('Parent links must not form a cycle.')
            seen.add(cursor)
            cursor = devices[cursor].parent
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO devices VALUES(?,?)', (device.id, json.dumps(asdict(device))))
            self.event(device.id, 'config', 'Device saved: ' + device.name)

    def delete(self, id):
        with self.db:
            self.db.execute('DELETE FROM devices WHERE id=?', (id,))
            for d in self.devices():
                if d.parent == id or d.next_hop == id or d.peer_id == id:
                    d.peer_id = '' if d.peer_id == id else d.peer_id
                    d.parent = '' if d.parent == id else d.parent
                    d.next_hop = '' if d.next_hop == id else d.next_hop
                    self.db.execute('UPDATE devices SET data=? WHERE id=?', (json.dumps(asdict(d)), d.id))
            self.event(id, 'config', 'Device deleted; history retained')

    def event(self, device, kind, message, at=None):
        self.db.execute('INSERT INTO events(device,at,kind,message) VALUES(?,?,?,?)', (device, time.time() if at is None else at, kind, message))
        self.db.commit()

    def record(self, device, result, at=None):
        self.db.execute('INSERT INTO samples(device,at,success,latency,error) VALUES(?,?,?,?,?)', (device, time.time() if at is None else at, int(result.success), result.latency, result.error))
        self.db.commit()

    def samples(self, device, since=0):
        return list(self.db.execute('SELECT * FROM samples WHERE device=? AND at>=? ORDER BY at,id', (device, since)))

    def stats(self, device, since=0):
        r = self.db.execute('SELECT COUNT(*) n, COALESCE(SUM(success),0) ok, AVG(CASE WHEN success=1 THEN latency END) latency, MAX(CASE WHEN success=1 THEN at END) last_ok, MAX(CASE WHEN success=0 THEN at END) last_fail FROM samples WHERE device=? AND at>=?', (device,since)).fetchone()
        return dict(r) | {'loss': 100*(r['n']-r['ok'])/r['n'] if r['n'] else None, 'uptime': 100*r['ok']/r['n'] if r['n'] else None}

    def events(self, device='', since=0, until=float('inf'), search='', limit=1000, scope=None):
        clause='';params=[device,device,since,until,search]
        if scope is not None:
            if not scope:return []
            clause=' AND device IN ('+','.join('?' for _ in scope)+')';params.extend(scope)
        params.append(limit)
        return list(self.db.execute('SELECT * FROM events WHERE (?="" OR device=?) AND at>=? AND at<=? AND instr(lower(message || kind),lower(?))>0'+clause+' ORDER BY at DESC,id DESC LIMIT ?',params))

    def setting(self, key, default=None):
        r = self.db.execute('SELECT data FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set_setting(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key,json.dumps(value)))
        self.db.commit()

    def prune(self, days):
        cutoff = time.time()-days*86400
        with self.db:
            for table in ('events','samples','measurements'):
                self.db.execute(f'DELETE FROM {table} WHERE at<?', (cutoff,))
        self.db.execute('PRAGMA incremental_vacuum')

    def backup(self, path):
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()

    def close(self):
        self.db.close()


def export_csv(path, rows, fields):
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for r in rows:
            # Prevent Excel interpreting user-provided labels as formulas.
            writer.writerow({k: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for k,v in dict(r).items()})


def diagnoses(devices, states):
    lookup = {d.id:d for d in devices}
    output = []
    for d in devices:
        if states.get(d.id) != 'No reply' or states.get(d.parent) == 'No reply':
            continue
        descendants = []
        for candidate in devices:
            cursor, seen = candidate.parent, set()
            while cursor and cursor in lookup and cursor not in seen:
                if cursor == d.id:
                    descendants.append(candidate.name)
                    break
                seen.add(cursor)
                cursor = lookup[cursor].parent
        parent = lookup.get(d.parent)
        output.append({'first_failure':d.name,'last_good':parent.name if parent and states.get(parent.id) in ('Online','Warning') else 'Not observed', 'affected':descendants,'explanation':'Suspected path/segment only. ICMP filtering, host routing and overload remain possible; physical failure is not confirmed.'})
    return output


def outages(rows):
    result, start = [], None
    for row in rows:
        if not row['success'] and start is None:
            start = row['at']
        elif row['success'] and start is not None:
            result.append((start,row['at']))
            start = None
    if start is not None:
        result.append((start,None))
    return result
