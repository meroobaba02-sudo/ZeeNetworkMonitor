"""Validate a database before restoring it; preserve the previous database."""
from pathlib import Path
from contextlib import closing
import sqlite3


def open_backup(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Invalid database backup.')
        if connection.execute('PRAGMA user_version').fetchone()[0] not in (1, 2, 3):
            raise ValueError('Unsupported backup schema.')
        connection.execute('SELECT data FROM devices LIMIT 1')
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
