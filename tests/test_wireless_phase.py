import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from zee.telemetry import validate_profile,quality
from zee.core import Store,Device
from zee.gui import Window
from zee.professional import IntegrationDialog,DeviceDetails

def test_snmp_version_validation_and_rate_quality():
    for version in ('1','2c'):validate_profile({'snmp_version':version})
    with pytest.raises(ValueError):validate_profile({'snmp_version':'3'})
    m={'signal_dbm':-50,'tx_mbps':10,'rx_mbps':100}
    assert quality(m,{})[1]=='Good'
    assert quality(m,{'rate_quality_enabled':True})[1]=='Poor'
    assert quality(m,{'rate_quality_enabled':True},1000)[1]=='Unknown'

def test_adapter_controls_and_alignment_graph(tmp_path):
    app=QApplication.instance() or QApplication([])
    store=Store(tmp_path/'test.db');d=Device(name='Fixture',host='127.0.0.1',integration={'method':'snmp','snmp_version':'1','poll_seconds':60,'allow_v2c':True});store.save(d);w=Window(store)
    try:
        adapter=IntegrationDialog(w,d)
        assert adapter.snmp_version.currentText()=='1' and adapter.poll_seconds.value()==60 and adapter.trusted.isChecked()
        w.measurements.latest[d.id]={'at':time.time(),'metrics':{'signal_dbm':-65,'noise_dbm':-90,'snr_db':25}}
        store.measurement(d.id,{'metrics':{'signal_dbm':-65}})
        details=DeviceDetails(w,d);details.trend_metric.setCurrentIndex(1);details.refresh()
        assert details.graph.values==[-65]
        assert 'Best last-hour Signal (dBm): -65.0' in details.text.text()
        details.feedback.setChecked(True);w.measurements.latest[d.id]['at']=time.time()-1000;details.refresh()
        assert details.previous is None and 'feedback paused' in details.text.text()
        details.close();adapter.close()
    finally:w.close();store.db.close()
