import sqlite3
import pytest
from zee.core import Store, Device
from zee.recovery import restore_pending


def database(path, name):
    store = Store(path)
    store.save(Device(name=name, host='127.0.0.1'))
    store.close()


def names(path):
    store = Store(path)
    try:
        return [d.name for d in store.devices()]
    finally:
        store.close()


def test_restore_preserves_original_and_leaves_sidecars_alone(tmp_path):
    database(tmp_path/'monitor.sqlite3', 'Original')
    database(tmp_path/'restore.pending.sqlite3', 'Restored')
    (tmp_path/'credentials.bin').write_bytes(b'unchanged')
    assert restore_pending(tmp_path)
    assert names(tmp_path/'monitor.sqlite3') == ['Restored']
    assert names(tmp_path/'before-restore.bak') == ['Original']
    assert (tmp_path/'credentials.bin').read_bytes() == b'unchanged'
    assert not (tmp_path/'restore.pending.sqlite3').exists()
    assert restore_pending(tmp_path) is False


@pytest.mark.parametrize('invalid', ['corrupt', 'future-schema', 'missing-tables'])
def test_invalid_queued_restore_cannot_replace_live_data(tmp_path, invalid):
    database(tmp_path/'monitor.sqlite3', 'Original')
    pending = tmp_path/'restore.pending.sqlite3'
    if invalid == 'corrupt':
        pending.write_bytes(b'not a SQLite backup')
    else:
        with sqlite3.connect(pending) as connection:
            connection.execute('PRAGMA user_version=' + ('99' if invalid == 'future-schema' else '3'))
    with pytest.raises((ValueError, sqlite3.Error)):
        restore_pending(tmp_path)
    assert names(tmp_path/'monitor.sqlite3') == ['Original']
    assert pending.exists()
    assert not (tmp_path/'before-restore.bak').exists()


def test_restore_into_new_data_directory(tmp_path):
    database(tmp_path/'restore.pending.sqlite3', 'Recovered')
    assert restore_pending(tmp_path)
    assert names(tmp_path/'monitor.sqlite3') == ['Recovered']
