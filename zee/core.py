"""Domain model, SQLite persistence, topology diagnostics and exports."""
from __future__ import annotations
import csv
import ipaddress
import json
import re
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

VERSION = '0.2.0'
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
    map_x: float | None = None
    map_y: float | None = None

    def validate(self):
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
            if ipaddress.ip_address(self.source).version != 6:
                raise ValueError('Windows ping source binding supports IPv6 only. For IPv4 use verified OS routing or a future agent.')
            if ':' not in self.host:
                raise ValueError('Source-bound mode requires a literal IPv6 target.')
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.parent == self.id or self.next_hop == self.id:
            raise ValueError('A device cannot link to itself.')


class Store:
    """Owned by the GUI/main thread. Workers never touch this connection."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        schema = self.db.execute('PRAGMA user_version').fetchone()[0]
        if schema not in (0, 1):
            self.db.close()
            raise ValueError('Unsupported database schema. Restore a v1 backup or use the matching app version.')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, device TEXT, at REAL, success INTEGER, latency REAL, error TEXT);
        CREATE INDEX IF NOT EXISTS sample_device_time ON samples(device, at);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, device TEXT, at REAL, kind TEXT, message TEXT);
        CREATE INDEX IF NOT EXISTS event_time ON events(at);
        PRAGMA user_version=1;
        ''')
        self.db.commit()

    def devices(self):
        return [Device(**json.loads(r[0])) for r in self.db.execute('SELECT data FROM devices ORDER BY rowid')]

    def save(self, device):
        device.validate()
        devices = {d.id: d for d in self.devices()}
        devices[device.id] = device
        for ref in (device.parent, device.next_hop):
            if ref and ref not in devices:
                raise ValueError('Linked device no longer exists.')
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
                if d.parent == id or d.next_hop == id:
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

    def events(self, device='', since=0, until=float('inf'), search='', limit=1000):
        return list(self.db.execute('SELECT * FROM events WHERE (?="" OR device=?) AND at>=? AND at<=? AND instr(lower(message || kind),lower(?))>0 ORDER BY at DESC,id DESC LIMIT ?', (device,device,since,until,search,limit)))

    def setting(self, key, default=None):
        r = self.db.execute('SELECT data FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set_setting(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key,json.dumps(value)))
        self.db.commit()

    def prune(self, days):
        cutoff = time.time()-days*86400
        with self.db:
            for table in ('events','samples'):
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
