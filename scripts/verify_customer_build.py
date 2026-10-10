"""CI-only disposable signing fixture; never publishes fixture customer packages or keys."""
import base64,json,os,subprocess,sys,tempfile,uuid,zipfile,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from admin.customer_build import run,verify_report
from admin.issuer import issue_document
from zee.licensing import canonical,fingerprint
from zee.build_profile import digest
from zee.core import VERSION,Store,Device
from zee.recovery import restore_pending
from zee.licensing import import_licence
from scripts.windows_install_acceptance import install,shortcuts,uninstall,execute

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
        # Build the actual previous released source with the SAME signed profile/public key.
        # No private signing material is written into either source checkout or runtime.
        baseline_sha='b890bb63d12aef75dd20ea9b4b6c6358cc3e5fa2'
        baseline=folder/'baseline';baseline.mkdir()
        execute('git','init',baseline)
        execute('git','-C',baseline,'fetch','--depth=1','https://github.com/meroobaba02-sudo/ZeeNetworkMonitor.git',baseline_sha)
        execute('git','-C',baseline,'checkout','--detach','FETCH_HEAD')
        actual=subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip();assert actual==baseline_sha
        previous_out=folder/'previous-results'
        subprocess.run([sys.executable,str(baseline/'admin/customer_build.py'),'--source',str(baseline),'--profile',str(profile_path),'--public',str(public_path),'--output',str(previous_out),'--iscc',str(compiler)],cwd=baseline,env=env,timeout=1800,check=True)
        previous_report=json.loads((previous_out/'build-result.json').read_text());assert previous_report['version']=='0.4.14' and previous_report['status']=='passed'
        previous_setup=previous_out/next(a['name'] for a in previous_report['artifacts'] if a['kind']=='installer')
        # Exercise the actual customer-specific Inno package in the default per-profile folders.
        setup=out/next(a['name'] for a in result['artifacts'] if a['kind']=='installer')
        installed=Path(os.environ['LOCALAPPDATA'])/'Programs'/('ZeeCustomer-'+payload['profile_id'])
        installed_data=Path(os.environ['LOCALAPPDATA'])/('ZeeCustomer-'+payload['profile_id'])
        try:
            install(previous_setup);shortcuts(payload['branding']['app_name'])
            execute(installed/'ZeeNetworkMonitor.exe','--smoke-test')
            inactive=json.loads((installed_data/'customer-build-smoke.json').read_text());assert not inactive['licence']['valid'] and inactive['require_issuer'] and inactive['title'].endswith('0.4.14')
            # The same import service used by the desktop activation dialog; issuer paths scoped to fixture only.
            from zee import licensing
            old_path=licensing.public_key_path;old_digest=licensing.EXPECTED_PROFILE_SHA256;old_required=licensing.REQUIRE_ISSUER
            licensing.public_key_path=lambda:installed/'_internal/assets/issuer-public.json';licensing.EXPECTED_PROFILE_SHA256=digest(profile);licensing.REQUIRE_ISSUER=True
            incoming=folder/'signed-activation.json';incoming.write_text(json.dumps(licence))
            try:import_licence(installed_data,incoming)
            finally:licensing.public_key_path=old_path;licensing.EXPECTED_PROFILE_SHA256=old_digest;licensing.REQUIRE_ISSUER=old_required
            execute(installed/'ZeeNetworkMonitor.exe','--smoke-test')
            activated=json.loads((installed_data/'customer-build-smoke.json').read_text());assert activated['licence']['valid'] and activated['device_limit']==2
            store=Store(installed_data/'monitor.sqlite3');store.save(Device(name='Preserve during reinstall',host='127.0.0.1'));store.backup(installed_data/'accepted-backup.sqlite3');store.close()
            from zee.credentials import Vault
            vault_path=installed_data/'credentials.dpapi.json';vault=Vault(vault_path);vault.set('ci-only',{'password':'CI disposable credential'})
            license_before=(installed_data/'license.json').read_bytes();vault_before=vault_path.read_bytes()
            install(setup);execute(installed/'ZeeNetworkMonitor.exe','--smoke-test')
            upgraded=json.loads((installed_data/'customer-build-smoke.json').read_text());assert upgraded['title'].endswith(VERSION) and upgraded['licence']['valid']
            assert (installed_data/'license.json').read_bytes()==license_before and vault_path.read_bytes()==vault_before
            assert Vault(vault_path).get('ci-only')['password']=='CI disposable credential'
            store=Store(installed_data/'monitor.sqlite3');assert store.devices()[0].name=='Preserve during reinstall';store.save(Device(name='Changed after backup',host='127.0.0.2'));store.close()
            shutil.copyfile(installed_data/'accepted-backup.sqlite3',installed_data/'restore.pending.sqlite3')
            execute(installed/'ZeeNetworkMonitor.exe','--smoke-test')
            store=Store(installed_data/'monitor.sqlite3');assert len(store.devices())==1;store.close()
            store=Store(installed_data/'before-restore.bak');assert len(store.devices())==2;store.close()
            assert (installed_data/'license.json').read_bytes()==license_before and vault_path.read_bytes()==vault_before
            uninstall(installed);assert not (installed/'ZeeNetworkMonitor.exe').exists()
            assert (installed_data/'monitor.sqlite3').is_file() and (installed_data/'license.json').read_bytes()==license_before and vault_path.read_bytes()==vault_before
        finally:
            if (installed/'unins000.exe').exists():uninstall(installed)
            shutil.rmtree(installed_data,ignore_errors=True)
        # Resource deletion cannot switch a compiled customer build back to owner evaluation.
        asset=runtime/'_internal/assets/customer-profile.json';raw=asset.read_bytes();asset.unlink();assert launch(folder/'missing-profile')!=0;asset.write_bytes(raw)
        asset=runtime/'_internal/assets/issuer-public.json';asset.unlink();assert launch(folder/'missing-issuer')!=0
        (root/'release/CUSTOMER_BUILD_TEST_REPORT.txt').write_text('Disposable owner build: signed profile, full regression suite, portable + customer installer, frozen activation/branding/permissions, deleted profile/issuer fail-closed, and artifact hashes passed. Fixture private key was held in memory only; no fixture package is released. Native customer install/shortcuts, activation import, released v0.4.14-to-v0.4.15 binary upgrade preserving configuration/DPAPI credentials/licence, queued recovery with safety backup, uninstall preserving user data passed on Windows Server 2022. Physical Windows 10/11 and phone/VPN/hardware are untested.\n',encoding='utf-8')
    except Exception:
        if (out/'build.log').exists():(root/'release/CUSTOMER_BUILD_FAILURE.log').write_bytes((out/'build.log').read_bytes())
        raise
