"""Package only runtime files and user-facing documentation; never admin keys/source."""
import json,os,platform,shutil,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'dist/ZeeNetworkMonitor';release=root/'release';release.mkdir(exist_ok=True)
assert (out/'ZeeNetworkMonitor.exe').is_file()
assert (out/'_internal/assets/region_map.json.gz').is_file()
assert (Path(os.environ['RUNNER_TEMP'])/'zee-smoke/smoke-ok.txt').is_file()
suites=list(ET.parse(root/'windows-tests.xml').getroot().iter('testsuite'))
counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')};assert counts['failures']==counts['errors']==0
info={'version':'0.4.6','edition':'Professional owner-evaluation preview','commit':os.getenv('GITHUB_SHA'),'run_url':f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}",'runner':platform.platform(),'python':platform.python_version(),'tests':counts,'frozen_smoke':'passed','physical_hardware_test':'not performed','issuer_provisioned':(root/'assets/issuer-public.json').exists()}
(out/'BUILD_INFO.json').write_text(json.dumps(info,indent=2))
for name in ['PROFESSIONAL_GUIDE.md','AUDIT_v040.md','THIRD_PARTY.md','PHASE2_STABILIZATION.md']:shutil.copy(root/'docs'/name,out/name)
shutil.copy(root/'LICENSE',out/'LICENSE.txt')
(out/'README_RomanUrdu.txt').write_text('''ZEE NETWORK MONITOR PROFESSIONAL v0.4.6\nCreated by Zeeshan Rasool\n\nSetup EXE desktop/Start Menu shortcut banata hai. Portable ZIP: Extract All, phir\nZeeNetworkMonitor.exe chalayein. Python/Git install nahi karna. Pura folder saath rakhen.\n\nManage networks > Add network. Sirf selected network monitor hota hai.\nMap > Add tower > naam > Save. Tower select > Add radio.\nDevice double-click se details aur management browser khulta hai.\nWAN / Radio > Configure adapter: verified firmware/OIDs/API ke baad metrics.\nBuzzer ON/OFF aur Silence upar hain. Settings mein backup, licence aur mobile access.\nMobile pehle HTTPS certificate trust/fingerprint verify karta hai, phir pairing code.\n\nYeh owner evaluation preview hai. Commercial customer licence issuer setup required.\nZeeLicenseManager owner-only separate download hai. Private key kabhi customer ko na den.\nReal Rocket M5, five-WAN routing, Android phone aur Windows 10 laptop par test baqi hai.\nNative Android APK, ONVIF, upload throughput test aur concurrent network-page monitoring\nabhi shamil nahi. Full setup aur limits PROFESSIONAL_GUIDE.md mein parhen.\n\nPurana data %LOCALAPPDATA%\\ZeeNetworkMonitor mein preserve hota hai.\nSchema upgrade se pehle automatic backup banta hai. Uninstall data nahi mitata.\n''',encoding='utf-8')
shutil.copy(root/'windows-tests.xml',out/'windows-tests.xml')
for p in out.rglob('*'):
    if p.is_file():
        assert p.suffix.lower() not in ('.py','.pyw'), 'Original source must not ship: '+str(p)
        assert 'issuer-private' not in p.name and 'recovery.pem' not in p.name
with zipfile.ZipFile(release/'ZeeNetworkMonitor-Portable-Windows-v0.4.6.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in out.rglob('*'):
        if p.is_file():z.write(p,str(p.relative_to(out.parent)))
admin=root/'dist/ZeeLicenseManager';assert (admin/'ZeeLicenseManager.exe').is_file()
(admin/'OWNER_README.txt').write_text('Owner only. Run ZeeLicenseManager.exe on your Windows PC. Initialize a local DPAPI-protected issuer key. Export only issuer-public.json into app repository assets/ and rebuild before customer distribution. Private keys are never bundled. See PROFESSIONAL_GUIDE.md licensing section. Keep recovery key/password private.',encoding='utf-8')
shutil.copy(root/'docs/PROFESSIONAL_GUIDE.md',admin/'PROFESSIONAL_GUIDE.md')
with zipfile.ZipFile(release/'ZeeLicenseManager-Admin-v0.4.6.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in admin.rglob('*'):
        if p.is_file():z.write(p,str(p.relative_to(admin.parent)))
print(json.dumps(info,indent=2))
