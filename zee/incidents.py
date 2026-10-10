"""Persistent incident observations. Gaps, edits and disabled checks never imply recovery."""
import json,time,uuid

SCHEMA='''
CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,page_id TEXT,device TEXT,context TEXT,category TEXT,
 at REAL,last_seen REAL,resolved REAL,status TEXT,acknowledged INTEGER DEFAULT 0,pinned INTEGER DEFAULT 0,
 notes TEXT DEFAULT '',detail TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS incident_active_key ON incidents(page_id,device,context,category) WHERE resolved IS NULL;
CREATE INDEX IF NOT EXISTS incident_page_time ON incidents(page_id,at);
CREATE INDEX IF NOT EXISTS incident_resolution ON incidents(resolved);
'''

class IncidentStore:
    def observe_incidents(self,outcomes):
        transitions=[]
        with self.db:
            active={tuple(r[k] for k in ('page_id','device','context','category')):r for r in self.db.execute('SELECT * FROM incidents WHERE resolved IS NULL')}
            observed=set()
            for item in outcomes:
                key=(item['page_id'],item['device'],item['context'],item['category'])
                observed.add(key);row=active.get(key)
                status=item['status'];at=item['at']
                if status=='active' and row is None:
                    id=str(uuid.uuid4());detail=json.dumps(item|{'opening':dict(item)})
                    self.db.execute('INSERT INTO incidents(id,page_id,device,context,category,at,last_seen,status,detail) VALUES(?,?,?,?,?,?,?,?,?)',(id,*key,min(at,item.get('started',at)),at,'Active',detail))
                    transitions.append(('opened',id,item['device']))
                elif row and status=='healthy' and at>=row['last_seen']:
                    detail=json.loads(row['detail'])|{'recovery':dict(item)}
                    self.db.execute('UPDATE incidents SET resolved=?,last_seen=?,status=?,detail=? WHERE id=?',(at,at,'Recovered',json.dumps(detail),row['id']))
                    transitions.append(('recovered',row['id'],item['device']))
                elif row and status=='active' and at>=row['last_seen']:
                    previous=json.loads(row['detail']);detail=json.dumps(item|{'opening':previous.get('opening',previous)})
                    if detail!=row['detail'] or row['status']!='Active':self.db.execute('UPDATE incidents SET last_seen=?,status=?,detail=? WHERE id=?',(at,'Active',detail,row['id']))
                elif row and status=='unknown' and row['status']!='Unobserved':
                    self.db.execute('UPDATE incidents SET status=? WHERE id=?',('Unobserved',row['id']))
            for key,row in active.items():
                if key not in observed and row['status']!='Unobserved':self.db.execute("UPDATE incidents SET status='Unobserved' WHERE id=?",(row['id'],))
        for action,id,device in transitions:self.event(device,'incident',action.title()+' incident '+id)
        return transitions

    def incident_rows(self,page_id=None,limit=500):
        sql='SELECT * FROM incidents';params=[]
        if page_id is not None:sql+=' WHERE page_id=?';params.append(page_id)
        sql+=' ORDER BY resolved IS NULL DESC,at DESC LIMIT ?';params.append(max(1,min(5000,int(limit))))
        return [dict(r)|{'detail':json.loads(r['detail'])} for r in self.db.execute(sql,params)]

    def edit_incident(self,id,*,notes=None,acknowledged=None,pinned=None,close=False):
        row=self.db.execute('SELECT * FROM incidents WHERE id=?',(id,)).fetchone()
        if row is None:raise ValueError('Incident no longer exists.')
        changes={}
        if notes is not None:
            if not isinstance(notes,str) or len(notes)>2000:raise ValueError('Notes must be at most 2,000 characters.')
            changes['notes']=notes
        if acknowledged is not None:changes['acknowledged']=int(bool(acknowledged))
        if pinned is not None:changes['pinned']=int(bool(pinned))
        if close and row['resolved'] is None:changes.update(resolved=time.time(),status='Closed by operator — recovery unverified')
        if changes:
            with self.db:self.db.execute('UPDATE incidents SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',(*changes.values(),id))
            self.event(row['device'],'audit','Incident updated: '+id)

    def suspend_incidents(self):
        with self.db:self.db.execute("UPDATE incidents SET status='Unobserved' WHERE resolved IS NULL")

