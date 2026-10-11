import asyncio
import socket
import threading
from types import SimpleNamespace
import pytest
from pyasn1.codec.ber import decoder, encoder
from pysnmp.proto.api import v1, v2c
from zee.snmp_access import probe, SYS_DESCR, AccessResult

@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    yield app

@pytest.mark.parametrize('version', ['1', '2c'])
@pytest.mark.parametrize('mode,expected', [('ok','ok'), ('agent_error','agent_error'), ('silence','timeout')])
def test_real_udp_access_with_source_binding(version, mode, expected):
    api = v1 if version == '1' else v2c
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.settimeout(3)
    failures=[]
    def serve():
        try:
            raw,addr=sock.recvfrom(65535)
            assert addr[0]=='127.0.0.1'
            request,rest=decoder.decode(raw,asn1Spec=api.Message());assert not rest
            assert str(api.apiMessage.get_community(request))=='fixture-private'
            request_pdu=api.apiMessage.get_pdu(request)
            assert request_pdu.tagSet==api.GetRequestPDU.tagSet
            assert str(api.apiPDU.get_varbinds(request_pdu)[0][0])==SYS_DESCR
            if mode=='silence':return
            reply=api.apiMessage.get_response(request);pdu=api.apiMessage.get_pdu(reply)
            api.apiPDU.set_varbinds(pdu,[(SYS_DESCR,api.OctetString('fixture-private'))])
            if mode=='agent_error':api.apiPDU.set_error_status(pdu,2)
            sock.sendto(encoder.encode(reply),addr)
        except Exception as e:failures.append(e)
    thread=threading.Thread(target=serve);thread.start()
    try:
        result=asyncio.run(probe('127.0.0.1','fixture-private',version,'127.0.0.1',sock.getsockname()[1],.1))
        assert result.state==expected
        assert 'fixture-private' not in result.detail
    finally:thread.join();sock.close()
    assert not failures

@pytest.mark.parametrize('host,source',[('0.0.0.0',''),('224.0.0.1',''),('127.0.0.1','::1'),('127.0.0.1','0.0.0.0')])
def test_invalid_targets_rejected_without_send(host,source):
    with pytest.raises(ValueError):asyncio.run(probe(host,'fixture-private',source=source))

@pytest.mark.parametrize('version',[0,1])
@pytest.mark.parametrize('length',[9,16,64])
def test_powershell_diagnostic_packet_structure(version,length):
    # Same bytes as the field script; no hardware reading is represented by this fixture.
    community=b'x'*length
    packet=bytes([48,32+length,2,1,version,4,length])+community+bytes([160,25,2,1,1,2,1,0,2,1,0,48,14,48,12,6,8,43,6,1,2,1,1,1,0,5,0])
    api=v1 if version==0 else v2c
    message,rest=decoder.decode(packet,asn1Spec=api.Message())
    assert not rest and bytes(api.apiMessage.get_community(message))==community
    pdu=api.apiMessage.get_pdu(message)
    assert pdu.tagSet==api.GetRequestPDU.tagSet
    assert str(api.apiPDU.get_varbinds(pdu)[0][0])==SYS_DESCR

def test_access_dialog_runs_in_background_and_does_not_verify_profile(qapp,monkeypatch):
    import time
    from zee import snmp_access_dialog as module
    release=threading.Event()
    def diagnostic(*args):
        assert args==('127.0.0.1','fixture-private','127.0.0.1',161)
        release.wait(2)
        return [AccessResult('2c','ok','Access only')]
    monkeypatch.setattr(module,'diagnose',diagnostic)
    dialog=module.AccessDialog(None,'127.0.0.1','fixture-private','127.0.0.1')
    dialog.show();dialog.begin();qapp.processEvents()
    assert dialog.task is not None and not dialog.start.isEnabled()
    dialog.reject();assert dialog.isVisible()
    release.set();deadline=time.monotonic()+3
    while dialog.task and time.monotonic()<deadline:qapp.processEvents();time.sleep(.01)
    assert dialog.task is None and dialog.start.isEnabled()
    assert 'Access only' in dialog.result.text()
    dialog.reject();assert dialog.community==''

def test_unverified_integration_can_test_without_save(qapp,monkeypatch):
    from PySide6.QtWidgets import QWidget
    from zee.core import Device
    from zee.professional import IntegrationDialog
    from zee import snmp_access_dialog
    window=QWidget();window.permit_device=lambda d:True
    window.vault=SimpleNamespace(get=lambda id:{'community':'fixture-private'})
    window.current_page=lambda:SimpleNamespace(id='default',source_ip='127.0.0.1')
    device=Device(host='127.0.0.1',integration={'allow_v2c':True,'firmware_verified':False})
    calls=[]
    class FakeDialog:
        def __init__(self,*args):calls.append(args)
        def exec(self):return 0
    monkeypatch.setattr(snmp_access_dialog,'AccessDialog',FakeDialog)
    dialog=IntegrationDialog(window,device);dialog.test_snmp_access()
    assert calls and calls[0][1:]==('127.0.0.1','fixture-private','127.0.0.1',161)
    assert not device.integration['firmware_verified'] and not dialog.profile_verified.isChecked()
    dialog.reject();window.close()
