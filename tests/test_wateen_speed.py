import threading
import pytest
from zee import telemetry
from zee.core import Store, Device
from zee.gui import Window
from zee.wan_dialog import WanDialog
from test_professional import app

class Response:
    def __init__(self,status=200):self.status=status
    def read(self,n):return b''

class Receiver:
    def __init__(self,status=200):self.status=status;self.sent=0;self.closed=False
    def putrequest(self,*args):pass
    def putheader(self,*args):pass
    def endheaders(self):pass
    def send(self,block):self.sent+=len(block)
    def getresponse(self):return Response(self.status)
    def close(self):self.closed=True

def profile():
    return dict(wan_verified=True,upload_protocol='cloudflare',upload_url='https://speed.cloudflare.com/__up',upload_mb=2,speed_seconds=30)

def test_cloudflare_completion_measures_only_sent_bytes():
    c=Receiver();result=telemetry.upload_test(profile(),connection_fn=lambda *a:(c,'/__up'))
    assert result['upload_bytes']==c.sent==2*1048576 and result['upload_mbps']>0 and c.closed
    assert 'Cloudflare' in result['upload_method']

@pytest.mark.parametrize('url',['http://speed.cloudflare.com/__up','https://evil.test/__up','https://speed.cloudflare.com/__up?x=1'])
def test_cloudflare_protocol_cannot_relax_custom_receiver_checks(url):
    p=profile()|{'upload_url':url}
    with pytest.raises(ValueError):telemetry.validate_profile(p)
    with pytest.raises(ValueError):telemetry.upload_test(p,connection_fn=lambda *a:pytest.fail('Must reject before connection'))

def test_cloudflare_server_rejection_and_cancel_have_no_rate():
    c=Receiver(403)
    with pytest.raises(ValueError,match='rejected'):telemetry.upload_test(profile(),connection_fn=lambda *a:(c,'/__up'))
    assert c.closed
    c=Receiver();cancel=threading.Event();cancel.set()
    with pytest.raises(ValueError,match='cancelled'):telemetry.upload_test(profile(),cancel=cancel,connection_fn=lambda *a:(c,'/__up'))
    assert c.sent==0 and c.closed

def test_wateen_setup_saved_source_and_both_endpoints(app,tmp_path):
    s=Store(tmp_path/'db');d=Device(name='Wateen',host='58.27.163.137',wan=1);s.save(d);w=Window(s)
    try:
        dialog=WanDialog(w,d);dialog.wateen_preset()
        assert dialog.source.text()=='58.27.163.141' and dialog.fields['speed_gateway'].text()=='58.27.163.137'
        assert not dialog.auto.isChecked() and not dialog.verified.isChecked()
        dialog.verified.setChecked(True);saved=dialog.value()
        assert saved.source=='58.27.163.141' and saved.integration['wan_verified']
        assert saved.integration['upload_protocol']=='cloudflare' and saved.integration['speed_mb']==8
        dialog.fields['upload_url'].setText('https://receiver.test/upload')
        assert dialog.upload_protocol=='exact-ack' and not dialog.verified.isChecked()
        dialog.close()
    finally:w.close();s.close()
