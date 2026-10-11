import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QPushButton
from zee import licensing
from zee.core import Store,Device
from zee.gui import Window


def test_owner_preview_simplifies_controls_and_preserves_existing_enforcement(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    key=tmp_path/'assets/issuer-public.json'
    monkeypatch.setattr(licensing,'public_key_path',lambda:key)
    licence=tmp_path/'license.json';licence.write_text('old activation record')
    store=Store(tmp_path/'monitor.sqlite3');device=Device(name='Saved Radio',host='127.0.0.1');store.save(device)
    w=Window(store)
    try:
        assert w.monitoring_preview and w.license_timer.isActive() and w.start_button.isEnabled()
        texts={b.text() for b in w.findChildren(QPushButton)}
        assert 'Licence / activation' not in texts and 'Verify offline installer update' not in texts
        assert w.policy.allows('wan') and w.permit_device(device)
        w.check_licence()
        assert licence.read_text()=='old activation record' and store.devices()[0].id==device.id
    finally:w.close()


def test_provisioned_invalid_licence_keeps_activation_controls_and_blocks_monitoring(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    assets=tmp_path/'assets';assets.mkdir();key=assets/'issuer-public.json';key.write_text('invalid issuer fixture')
    monkeypatch.setattr(licensing,'public_key_path',lambda:key)
    store=Store(tmp_path/'monitor.sqlite3');store.save(Device(name='Radio',host='127.0.0.1'))
    w=Window(store)
    try:
        assert not w.monitoring_preview and w.license_timer.isActive() and not w.start_button.isEnabled()
        texts={b.text() for b in w.findChildren(QPushButton)}
        assert 'Licence / activation' in texts and not w.policy.valid
        assert not licensing.status(tmp_path)['valid']
    finally:w.close()
