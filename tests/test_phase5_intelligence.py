import asyncio,socket,threading,time,math
from dataclasses import replace
import pytest
from zee.core import Device,Store
from zee import telemetry

@pytest.mark.parametrize('version',['1','2c'])
@pytest.mark.parametrize('ipv6',[False,True])
def test_real_snmp_get_uses_requested_source_and_preserves_counter64(version,ipv6):
    from pyasn1.codec.ber import decoder,encoder
    from pysnmp.proto.api import v1,v2c
    protocol=v1 if version=='1' else v2c
    host='::1' if ipv6 else '127.0.0.1';source='::1' if ipv6 else '127.0.0.2'
    sock=socket.socket(socket.AF_INET6 if ipv6 else socket.AF_INET,socket.SOCK_DGRAM)
    try:sock.bind((host,0))
    except OSError:
        sock.close();pytest.skip('IPv6 loopback unavailable')
    sock.settimeout(5);seen=[];errors=[];counter=2**60+123
    def serve():
        try:
            raw,addr=sock.recvfrom(65535);seen.append(addr[0])
            msg,_=decoder.decode(raw,asn1Spec=protocol.Message())
            assert protocol.apiMessage.get_pdu(msg).isSameTypeWith(protocol.GetRequestPDU())
            reply=protocol.apiMessage.get_response(msg);pdu=protocol.apiMessage.get_pdu(reply)
            value=protocol.Counter(123) if version=='1' else protocol.Counter64(counter)
            protocol.apiPDU.set_varbinds(pdu,[('1.3.6.1.2.1.2.2.1.10.1',value)])
            sock.sendto(encoder.encode(reply),addr)
        except Exception as e:errors.append(e)
    thread=threading.Thread(target=serve);thread.start()
    d=Device(host=host,integration={'method':'snmp','firmware_verified':True,'allow_v2c':True,'snmp_version':version,'snmp_port':sock.getsockname()[1],'oids':{'in_octets':{'path':'1.3.6.1.2.1.2.2.1.10.1'}}})
    try:
        metrics,method=telemetry.fetch_metrics(d,{'community':'fixture-only'},source)
        assert metrics['in_octets']==(123 if version=='1' else counter)
        assert isinstance(metrics['in_octets'],int) and 'source-bound' in method
    finally:thread.join();sock.close()
    assert not errors and seen==[source]

def test_snmp_mismatched_family_has_no_default_route_fallback():
    d=Device(host='127.0.0.1',integration={'method':'snmp','firmware_verified':True,'allow_v2c':True,'oids':{'signal_dbm':{'path':'1.3.6.1.2.1.1.3.0'}}})
    with pytest.raises(ValueError,match='matching-family'):telemetry.fetch_metrics(d,{'community':'fixture-only'},'::1')

def test_invalid_wireless_values_cannot_create_quality_or_enum_fault():
    assert telemetry.quality({'signal_dbm':50,'tx_ccq':101,'wireless_up':2},{})==(None,'Unknown')
    assert telemetry.clean_metrics({'noise_dbm':math.nan,'tx_mbps':-1,'ethernet_up':2,'signal_dbm':-65})=={'signal_dbm':-65}
    assert telemetry.normalized({'stations':[{'signal':'-67'}]}, {'signal_dbm':{'path':'stations/0/signal'},'noise_dbm':{'path':'stations/8/noise'}})=={'signal_dbm':-67}

def test_counter_precision_reboot_discontinuity_and_bad_elapsed():
    huge=2**60+123
    assert telemetry.normalized({'bytes':str(huge)},{'in_octets':{'path':'bytes'}})['in_octets']==huge
    assert telemetry.counter_rates({'in_octets':huge},{'in_octets':huge+100},1)['download_mbps']==.0008
    assert telemetry.counter_rates({'in_octets':100,'uptime_s':500},{'in_octets':200,'uptime_s':1},1)=={}
    assert telemetry.counter_rates({'in_octets':100,'counter_epoch':1},{'in_octets':200,'counter_epoch':2},1)=={}
    assert telemetry.counter_rates({'in_octets':100},{'in_octets':200},math.nan)=={}

def test_cancelled_speed_never_becomes_completed_measurement(monkeypatch):
    class Cancel:
        def is_set(self):return True
    class Response:status=200
    class Connection:
        closed=False
        def request(self,*a,**k):pass
        def getresponse(self):return Response()
        def close(self):self.closed=True
    c=Connection();monkeypatch.setattr(telemetry,'connection',lambda *a:(c,'/fixture'))
    with pytest.raises(ValueError,match='cancelled'):telemetry.speed_test({'wan_verified':True,'speed_url':'https://fixture.example/'},cancel=Cancel())
    assert c.closed

def test_wan_edits_clear_attestation_and_stop_stale_workers(tmp_path):
    from PySide6.QtWidgets import QApplication
    from zee.gui import Window
    from zee.wan_dialog import WanDialog
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'wan.db')
    d=Device(name='WAN fixture',host='127.0.0.1',wan=1,integration={'wan_verified':True,'internet_url':'https://example.com/','internet_marker':'fixture','wan_interface':'wan1','wan_counter_verified':True})
    store.save(d);w=Window(store)
    try:
        dlg=WanDialog(w,d);dlg.fields['internet_marker'].setText('changed')
        assert not dlg.verified.isChecked()
        dlg.counter_interface.setText('wan2');assert not dlg.counter_verified.isChecked()
        generation=w.engine.generation;w.engine.running=True;w.measurements.enabled=True
        dlg.accept();assert w.engine.generation!=generation and not w.engine.running and not w.measurements.enabled
        w.measurements.complete((d,False,generation),{'at':time.time(),'metrics':{},'internet':'Online'})
        assert d.id not in w.measurements.latest
    finally:w.close();store.close()

def test_wan_counter_requires_own_interface_and_fresh_monotonic_baseline(tmp_path):
    from PySide6.QtWidgets import QApplication
    from zee.gui import Window
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'counter.db')
    d=Device(name='WAN fixture',host='127.0.0.1',wan=1,integration={'wan_verified':True})
    store.save(d);w=Window(store)
    try:
        base={'at':time.time(),'monotonic_at':100,'metrics':{'in_octets':100}}
        row={'at':time.time(),'monotonic_at':101,'metrics':{'in_octets':200}}
        w.measurements.latest[d.id]=base;w.measurements.complete((d,False,w.engine.generation),dict(row))
        assert 'download_mbps' not in w.measurements.latest[d.id]
        d=replace(d,integration=d.integration|{'wan_counter_verified':True,'wan_interface':'wan1'});store.save(d);w.reload()
        w.measurements.latest[d.id]=base;w.measurements.complete((d,False,w.engine.generation),dict(row))
        assert w.measurements.latest[d.id]['download_mbps']==.0008
        w.measurements.latest[d.id]=base;w.measurements.complete((d,False,w.engine.generation),row|{'monotonic_at':500})
        assert 'download_mbps' not in w.measurements.latest[d.id]
    finally:w.close();store.close()

def test_invalid_verification_settings_are_rejected():
    with pytest.raises(ValueError):telemetry.validate_profile({'firmware_verified':'yes'})
    with pytest.raises(ValueError):telemetry.validate_profile({'wan_counter_verified':True})
    with pytest.raises(ValueError):telemetry.validate_profile({'device_model':'x\nsecret'})

def test_adapter_edit_requires_new_attestation_and_alignment_resets_on_missing_data(tmp_path):
    from PySide6.QtWidgets import QApplication
    from zee.gui import Window
    from zee.professional import IntegrationDialog,DeviceDetails
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'radio.db')
    d=Device(name='Radio fixture',host='127.0.0.1',integration={'firmware_verified':True,'device_model':'Fixture radio'})
    store.save(d);w=Window(store)
    try:
        dlg=IntegrationDialog(w,d);assert dlg.profile_verified.isChecked()
        dlg.firmware.setText('different');assert not dlg.profile_verified.isChecked()
        dlg.accept();assert not store.devices()[0].integration['firmware_verified']
        details=DeviceDetails(w,store.devices()[0]);details.previous=8;details.previous_at=1
        w.measurements.latest[d.id]={'at':time.time(),'metrics':{}}
        details.refresh();assert details.previous is None and 'feedback paused' in details.text.text()
        details.close()
    finally:w.close();store.close()

@pytest.mark.parametrize('field,value',[('host','127.0.0.2'),('source','127.0.0.1')])
def test_basic_device_editor_cannot_carry_wan_verification_to_changed_path(field,value):
    from PySide6.QtWidgets import QApplication
    from zee.gui import DeviceDialog
    app=QApplication.instance() or QApplication([])
    d=Device(name='Verified fixture',host='127.0.0.1',integration={'firmware_verified':True,'wan_verified':True,'wan_counter_verified':True,'wan_interface':'wan1'})
    dlg=DeviceDialog([d],d);dlg.fields[field].setText(value);updated=dlg.device()
    assert not updated.integration['wan_verified'] and not updated.integration['wan_counter_verified']
    if field=='host':assert not updated.integration['firmware_verified']
    dlg.close()
