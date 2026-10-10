"""Persistent network scopes. Export/import never contains credential vault data."""
from dataclasses import dataclass,asdict,replace
import json,uuid,ipaddress

@dataclass
class NetworkPage:
    id:str='default'
    name:str='My Network'
    archived:bool=False
    order:int=0
    source_ip:str=''
    interface_hint:str=''
    gateway_hint:str=''
    routing_verified:bool=False
    notes:str=''
    def validate(self):
        self.name=self.name.strip()
        if not self.name:raise ValueError('Network name is required.')
        if self.source_ip:ipaddress.ip_address(self.source_ip)
        if self.gateway_hint:ipaddress.ip_address(self.gateway_hint)
        if not self.id:self.id=str(uuid.uuid4())

class WorkspaceStore:
    def pages(self):
        return sorted([NetworkPage(**json.loads(r[0])) for r in self.db.execute('SELECT data FROM pages')],key=lambda p:(p.order,p.name))
    def save_page(self,p):
        p.validate()
        self.db.execute('INSERT OR REPLACE INTO pages VALUES(?,?)',(p.id,json.dumps(asdict(p))));self.db.commit()
    def save_pages(self,pages):
        for p in pages:p.validate()
        if len({p.id for p in pages})!=len(pages):raise ValueError('Duplicate network identifiers.')
        with self.db:
            for p in pages:self.db.execute('INSERT OR REPLACE INTO pages VALUES(?,?)',(p.id,json.dumps(asdict(p))))
    def export_page(self,id):
        p=next(p for p in self.pages() if p.id==id)
        devices=[]
        for d in self.devices():
            if d.page_id==id:
                data=asdict(d)
                # Integration profiles only contain OIDs/metric names, never secrets.
                devices.append(data)
        return {'format':'zee-page-1','page':asdict(p),'stations':[asdict(s) for s in self.stations() if s.page_id==id],'devices':devices}
    def import_page(self,data,name=None):
        from .core import Device,Station
        if data.get('format')!='zee-page-1':raise ValueError('Unsupported network file.')
        if len(data.get('devices',[]))>10000 or len(data.get('stations',[]))>10000:raise ValueError('Import too large.')
        p=NetworkPage(**data['page']);p.id=str(uuid.uuid4());p.name=name or p.name+' (imported)';p.archived=False;p.routing_verified=False;p.order=len(self.pages());p.validate()
        remap={d['id']:str(uuid.uuid4()) for d in data['devices']}
        towers={s['id']:str(uuid.uuid4()) for s in data['stations']}
        newstations=[Station(**(s|{'id':towers[s['id']],'page_id':p.id})) for s in data['stations']]
        newdevices=[]
        for item in data['devices']:
            d=Device(**(item|{'id':remap[item['id']],'page_id':p.id,'station_id':towers.get(item.get('station_id'),''),'parent':remap.get(item.get('parent'),''),'next_hop':remap.get(item.get('next_hop'),''),'peer_id':remap.get(item.get('peer_id'),''),'enabled':False}))
            d.validate();newdevices.append(d)
        for s in newstations:s.validate()
        # Validate first; one atomic write, no history or secrets copied.
        with self.db:
            self.db.execute('INSERT INTO pages VALUES(?,?)',(p.id,json.dumps(asdict(p))))
            for s in newstations:self.db.execute('INSERT INTO stations VALUES(?,?)',(s.id,json.dumps(asdict(s))))
            for d in newdevices:self.db.execute('INSERT INTO devices VALUES(?,?)',(d.id,json.dumps(asdict(d))))
        return p
    def delete_page(self,id):
        if len(self.pages())<=1:raise ValueError('Keep at least one network page.')
        ids=[d.id for d in self.devices() if d.page_id==id]
        with self.db:
            for did in ids:self.db.execute('DELETE FROM devices WHERE id=?',(did,))
            for s in self.stations():
                if s.page_id==id:self.db.execute('DELETE FROM stations WHERE id=?',(s.id,))
            self.db.execute('DELETE FROM pages WHERE id=?',(id,))
        return ids
    def measurement(self,id,payload):
        import time
        self.db.execute('INSERT INTO measurements(device,at,data) VALUES(?,?,?)',(id,time.time(),json.dumps(payload,allow_nan=False)));self.db.commit()
    def measurements(self,id,since=0,limit=1000):
        return [{'at':r['at'],**json.loads(r['data'])} for r in reversed(list(self.db.execute('SELECT at,data FROM measurements WHERE device=? AND at>=? ORDER BY id DESC LIMIT ?',(id,since,limit))))]
