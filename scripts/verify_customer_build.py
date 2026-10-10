"""CI-only disposable signing fixture; never publishes fixture customer packages or keys."""
import base64,json,os,subprocess,sys,tempfile,uuid,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from admin.customer_build import run,verify_report
from admin.issuer import issue_document
from zee.licensing import canonical,fingerprint
from zee.build_profile import digest
from zee.core import VERSION

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='zee-ci-customer-') as temp:
    folder=Path(temp);key=Ed25519PrivateKey.generate();public=base64.b64encode(key.public_key().public_bytes_raw()).decode()
    payload={'type':'zee-customer-build','version':1,'product':'ZeeNetworkMonitor','profile_id':str(uuid.uuid4()),'customer_id':str(uuid.uuid4()),'package_id':str(uuid.uuid4()),'customer':'CI fixture only','branding':{'app_name':'CI Fixture Network','watermark':'CI fixture — not a customer release','logo_png':''},'entitlements':{'features':['monitoring','map'],'max_devices':2}}
    profile={'payload':payload,'signature':base64.b64encode(key.sign(canonical(payload))).decode()};profile_path=folder/'profile.json';profile_path.write_text(json.dumps(profile));public_path=folder/'public.json';public_path.write_text(json.dumps({'public_key':public}));out=folder/'results'
    compiler=Path(r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')
    if not compiler.is_file():raise RuntimeError('Install Inno Setup before the customer build integration step.')
    try:
        result=run(root,profile_path,public_path,out,compiler);verify_report(result,out)
        portable=next(a for a in result['artifacts'] if a['kind']=='portable')
        with zipfile.ZipFile(out/portable['name']) as z:z.extractall(folder/'runtime')
        runtime=folder/'runtime/ZeeNetworkMonitor';data=folder/'activated';data.mkdir()
        licence=issue_document(key,fingerprint(),'CI fixture','Test package','ci-only',entitlements=payload['entitlements'],customer_id=payload['customer_id'],profile_id=payload['profile_id']);(data/'license.json').write_text(json.dumps(licence))
        env=os.environ.copy();env['QT_QPA_PLATFORM']='offscreen'
        def launch(path):return subprocess.run([str(runtime/'ZeeNetworkMonitor.exe'),'--smoke-test','--data-dir',str(path)],timeout=60,env=env).returncode
        assert launch(data)==0
        state=json.loads((data/'customer-build-smoke.json').read_text());assert state['licence']['valid'] and state['require_issuer'] and state['device_limit']==2 and state['features']==['map','monitoring'] and state['profile_digest']==digest(profile) and state['title'].startswith(payload['branding']['app_name'])
        # Resource deletion cannot switch a compiled customer build back to owner evaluation.
        asset=runtime/'_internal/assets/customer-profile.json';raw=asset.read_bytes();asset.unlink();assert launch(folder/'missing-profile')!=0;asset.write_bytes(raw)
        asset=runtime/'_internal/assets/issuer-public.json';asset.unlink();assert launch(folder/'missing-issuer')!=0
        (root/'release/CUSTOMER_BUILD_TEST_REPORT.txt').write_text('Disposable owner build: signed profile, full regression suite, portable + customer installer, frozen activation/branding/permissions, deleted profile/issuer fail-closed, and artifact hashes passed. Fixture private key was held in memory only; no fixture package is released. Physical Windows 10/hardware and customer-specific installer upgrade are untested.\n',encoding='utf-8')
    except Exception:
        if (out/'build.log').exists():(root/'release/CUSTOMER_BUILD_FAILURE.log').write_bytes((out/'build.log').read_bytes())
        raise
