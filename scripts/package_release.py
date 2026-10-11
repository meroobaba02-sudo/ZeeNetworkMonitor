"""Package only runtime files and user-facing documentation; never admin keys/source."""
import json,os,platform,shutil,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'dist/ZeeNetworkMonitor';release=root/'release';release.mkdir(exist_ok=True)
assert (out/'ZeeNetworkMonitor.exe').is_file()
assert (out/'_internal/assets/region_map.json.gz').is_file()
assert not (out/'_internal/assets/issuer-public.json').exists()
assert not (out/'_internal/assets/customer-profile.json').exists()
assert (Path(os.environ['RUNNER_TEMP'])/'zee-smoke/smoke-ok.txt').is_file()
suites=list(ET.parse(root/'windows-tests.xml').getroot().iter('testsuite'))
counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')};assert counts['failures']==counts['errors']==0
info={'version':'0.5.3','edition':'Monitoring development — existing owner preview','commit':os.getenv('GITHUB_SHA'),'run_url':f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}",'runner':platform.platform(),'python':platform.python_version(),'tests':counts,'frozen_smoke':'passed','physical_hardware_test':'not performed','monitoring_only_delivery':True,'licence_enforcement_unchanged':True,'activation_required':False,'admin_tools_packaged':False}
(out/'BUILD_INFO.json').write_text(json.dumps(info,indent=2))
for name in ['PROFESSIONAL_GUIDE.md','AUDIT_v040.md','THIRD_PARTY.md','PHASE2_STABILIZATION.md','PHASE3_PERFORMANCE.md','PHASE4_NETWORKS.md','PHASE5_INTELLIGENCE.md','PHASE6_INCIDENTS.md','PHASE61_SEVEN_WANS.md','PHASE7_CUSTOMER_GUI.md','PHASE9_INSTALL_RECOVERY_MOBILE.md','PHASE10_REAL_NETWORK_PILOT.md','WAN_ALARM_FIX.md','MONITORING_ONLY.md','NOC_GUI_v050.md','DISCOVERY_ALIGNMENT_v051.md','DISCOVERY_ALL_NETWORKS_v052.md','WATEEN_SPEED_v053.md']:shutil.copy(root/'docs'/name,out/name)
shutil.copy(root/'LICENSE',out/'LICENSE.txt')
shutil.copy(root/'README_RomanUrdu.txt',out/'README_RomanUrdu.txt')
shutil.copy(root/'phase3-benchmark-windows.json',out/'phase3-benchmark-windows.json')
shutil.copy(root/'phase10-benchmark-windows.json',out/'phase10-benchmark-windows.json')
shutil.copy(root/'windows-tests.xml',out/'windows-tests.xml')
for p in out.rglob('*'):
    if p.is_file():
        assert p.suffix.lower() not in ('.py','.pyw'), 'Original source must not ship: '+str(p)
        assert 'issuer-private' not in p.name and 'recovery.pem' not in p.name
with zipfile.ZipFile(release/'ZeeNetworkMonitor-Portable-Windows-v0.5.3.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in out.rglob('*'):
        if p.is_file():z.write(p,str(p.relative_to(out.parent)))
print(json.dumps(info,indent=2))
