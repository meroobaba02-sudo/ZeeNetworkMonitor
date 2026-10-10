"""Validate a database before restoring it; preserve the previous database."""
from pathlib import Path
from contextlib import closing
import sqlite3,json


def open_backup(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Invalid database backup.')
        if connection.execute('PRAGMA user_version').fetchone()[0] not in (1, 2, 3, 4):
            raise ValueError('Unsupported backup schema.')
        # Integrity alone does not guarantee configuration can be loaded by the app.
        from .core import Device,Station
        from .workspaces import NetworkPage
        tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table,model in [('devices',Device),('stations',Station),('pages',NetworkPage)]:
            if table not in tables:
                if table=='devices':raise ValueError('Backup has no device table.')
                continue # Older supported schemas gain these tables during migration.
            for identifier,raw in connection.execute('SELECT id,data FROM '+table):
                try:
                    item=model(**json.loads(raw));item.validate()
                    if item.id!=identifier:raise ValueError('Configuration identifier mismatch.')
                except Exception as error:
                    raise ValueError('Invalid '+table+' configuration in backup.') from error
        if 'settings' in tables:
            for raw, in connection.execute('SELECT data FROM settings'):json.loads(raw)
        return connection
    except Exception:
        connection.close()
        raise


def restore_pending(base):
    base = Path(base)
    pending = base / 'restore.pending.sqlite3'
    if not pending.exists():
        return False
    # Validate again at startup: the queued file may have changed since selection.
    source = open_backup(pending)
    try:
        active = base / 'monitor.sqlite3'
        if active.exists():
            with closing(sqlite3.connect(active)) as old, closing(sqlite3.connect(base / 'before-restore.bak')) as safety:
                old.backup(safety)
        with closing(sqlite3.connect(active)) as destination:
            source.backup(destination)
    finally:
        source.close()
    pending.unlink()
    return True
