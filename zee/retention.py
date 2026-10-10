"""Bounded background cleanup using a private SQLite connection."""
from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
import json, logging, re, sqlite3, threading, time
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


@dataclass(frozen=True)
class Policy:
    hours: int = 48
    incident_days: int = 90
    disk_warning_mb: int = 250
    archive: bool = False

    def __post_init__(self):
        if not 1 <= self.hours <= 87600 or not 0 <= self.incident_days <= 3650:
            raise ValueError('Retention outside supported range.')
        if not 0 <= self.disk_warning_mb <= 100000:
            raise ValueError('Invalid disk warning threshold.')


def history_hours(store):
    saved = store.setting('detail_hours',None)
    # Preserve an explicitly saved old customization; fresh installs default to 48h.
    return int(saved if saved is not None else store.setting('retention',2)*24)


def trim_diagnostics(base, cutoff):
    """Keep multiline log records together; synchronize with our active file handler."""
    path=Path(base)/'diagnostic.log'
    handlers=[h for h in logging.getLogger().handlers if getattr(h,'baseFilename',None)==str(path.resolve())]
    for h in handlers:h.acquire();h.flush()
    try:
        for p in [path]+[Path(str(path)+'.'+str(i)) for i in range(1,4)]:
            if not p.exists():continue
            lines=p.read_text(encoding='utf-8',errors='replace').splitlines(keepends=True)
            keep=p.stat().st_mtime>=cutoff;retained=[]
            for line in lines:
                match=re.match(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)',line)
                if match:
                    try:keep=time.mktime(time.strptime(match[1],'%Y-%m-%d %H:%M:%S'))>=cutoff
                    except ValueError:pass
                if keep:retained.append(line)
            if len(retained)!=len(lines):
                # Append-mode logging handles remain attached to the same file.
                p.write_text(''.join(retained),encoding='utf-8')
    finally:
        for h in reversed(handlers):h.release()


def cleanup(path, policy, cancel=None, now=None, budget=5):
    cancel=cancel or threading.Event();now=time.time() if now is None else now
    started=time.monotonic();path=Path(path);deleted=0;more=False;archive=''
    with closing(sqlite3.connect(path,timeout=.25)) as db:
        db.execute('PRAGMA busy_timeout=250')
        if policy.archive:
            folder=path.parent/'archives';folder.mkdir(exist_ok=True)
            target=folder/('history-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())+'.sqlite3')
            try:
                with closing(sqlite3.connect(target)) as dest:
                    def progress(*args):
                        if cancel.is_set():raise InterruptedError('Archive cancelled')
                        if time.monotonic()-started>30:raise InterruptedError('Archive deadline exceeded')
                    db.backup(dest,pages=128,progress=progress,sleep=.05)
                archive=str(target)
            except Exception:
                target.unlink(missing_ok=True);raise
            started=time.monotonic()
        active=db.execute('SELECT data FROM settings WHERE key="active_incident_devices"').fetchone()
        active=json.loads(active[0]) if active else []
        # A temporary table avoids SQLite variable-count limits on larger installations.
        db.execute('CREATE TEMP TABLE active_devices(id TEXT PRIMARY KEY)')
        db.executemany('INSERT OR IGNORE INTO active_devices VALUES(?)',[(x,) for x in active]);db.commit()
        pinned='id NOT IN (SELECT event_id FROM event_pins)'
        ordinary="kind NOT IN ('alert','alert_control','incident','security','audit','licence','license','licensing')"
        plans=[('samples','at<?',(now-policy.hours*3600,)),('measurements','at<?',(now-policy.hours*3600,)),('events',f'at<? AND {ordinary} AND {pinned}',(now-policy.hours*3600,))]
        if policy.incident_days:
            plans.append(('events',f"at<? AND kind IN ('alert','alert_control','incident') AND {pinned} AND device NOT IN (SELECT id FROM active_devices)",(now-policy.incident_days*86400,)))
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='incidents'").fetchone():
                plans.append(('incidents','resolved IS NOT NULL AND resolved<? AND pinned=0',(now-policy.incident_days*86400,)))
        for table,where,params in plans:
            while not cancel.is_set():
                if time.monotonic()-started>=budget:more=True;break
                with db:
                    n=db.execute(f'DELETE FROM {table} WHERE id IN (SELECT id FROM {table} WHERE {where} ORDER BY at LIMIT 500)',params).rowcount
                deleted+=n
                if n<500:break
            if more or cancel.is_set():break
        with db:db.execute('DELETE FROM event_pins WHERE event_id NOT IN (SELECT id FROM events)')
        # No full VACUUM or forced WAL truncate: never block the GUI's readers/writer.
        used=(db.execute('PRAGMA page_count').fetchone()[0]-db.execute('PRAGMA freelist_count').fetchone()[0])*db.execute('PRAGMA page_size').fetchone()[0]
    if not cancel.is_set():trim_diagnostics(path.parent,now-policy.hours*3600)
    physical=sum(p.stat().st_size for p in [path,Path(str(path)+'-wal'),Path(str(path)+'-shm')] if p.exists())
    return {'at':now,'deleted':deleted,'more':more,'cancelled':cancel.is_set(),'archive':archive,'logical_mb':round(used/1048576,2),'physical_mb':round(physical/1048576,2),'disk_warning':bool(policy.disk_warning_mb and physical>policy.disk_warning_mb*1048576),'seconds':round(time.monotonic()-started,3)}


class Signals(QObject):
    done=Signal(object)


class Job(QRunnable):
    def __init__(self,path,policy,cancel,signals):
        super().__init__();self.path=path;self.policy=policy;self.cancel=cancel;self.signals=signals
    def run(self):
        try:result=cleanup(self.path,self.policy,self.cancel)
        except (sqlite3.Error,OSError,ValueError,InterruptedError):
            result={'error':'Cleanup/archive unavailable: database busy, invalid data or file access denied. Retry later.'}
        except Exception:
            result={'error':'Cleanup stopped unexpectedly. Some expired records may already be removed; check the data folder and retry.'}
        self.signals.done.emit(result)


class Cleaner(QObject):
    finished=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.signals=Signals(self);self.signals.done.connect(self.complete)
        self.running=False;self.cancel=threading.Event()
    def start(self,path,policy):
        if self.running or self.cancel.is_set():return False
        self.running=True;self.pool.start(Job(path,policy,self.cancel,self.signals));return True
    def complete(self,result):
        self.running=False
        if not self.cancel.is_set():self.finished.emit(result)
    def shutdown(self):
        self.cancel.set();self.pool.waitForDone()
