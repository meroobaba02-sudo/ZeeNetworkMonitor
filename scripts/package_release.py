"""Assemble a truthful Windows portable package after frozen smoke success."""
import json
import os
from pathlib import Path
import platform
import shutil
import xml.etree.ElementTree as ET
import zipfile

root=Path(__file__).resolve().parents[1]
out=root/'dist/ZeeNetworkMonitor'
assert (out/'ZeeNetworkMonitor.exe').is_file(), 'Windows EXE missing'
marker=Path(os.environ['RUNNER_TEMP'])/'zee-smoke/smoke-ok.txt'
assert marker.is_file(), 'Frozen smoke success missing'
xml=ET.parse(root/'windows-tests.xml').getroot()
suites=list(xml.iter('testsuite'))
counts={key:sum(int(s.get(key,0)) for s in suites) for key in ['tests','failures','errors','skipped']}
assert not counts['failures'] and not counts['errors'], 'Tests failed'
passed=counts['tests']-counts['skipped']
(out/'README_RomanUrdu.txt').write_text('''ZEE NETWORK MONITOR v0.2.0 — WINDOWS PORTABLE\n\nCHALANE KA TAREEQA\n1. ZIP par right-click > Extract All.\n2. ZeeNetworkMonitor folder kholen.\n3. ZeeNetworkMonitor.exe double-click karen.\n4. Pura folder saath rakhen; _internal ya DLLs delete na karen.\nPython, Git ya VS Code install karne ki zaroorat nahi. Yeh portable app hai,\ninstaller nahi; koi Windows service install nahi hoti.\n\nDEVICES\nAdd device > naam, IP/hostname, type, location > Save.\nPing selected ek test; Ping all now tamam enabled devices ka ek test.\nStart monitoring tamam devices ko interval par check karta hai.\nContinuous selected sirf selected device; Stop monitoring naye checks band.\nSettings > Add 5 unconfigured WAN templates, phir har row Edit karen.\nParent hop assign karne se topology banti hai.\n\nMAP / BUZZER\nApp map view par khulti hai. Marker select: Ping, History, Edit.\nMarker drag karke position save karen; wheel/plus/minus se zoom.\nMap offline schematic hai, accurate satellite/GPS map nahi.\nBuzzer ON/OFF top bar par; setting foran save hoti hai.\nSilence current faults ko mute karta hai; naya fault phir alarm dega.\nRecovery, stale/unknown results ya app close par buzzer ruk jata hai.\nSound laptop ke speakers se aati hai; volume/mute check karen.\nDevice alert threshold Edit mein set karen. Settings mein Test buzzer.\n\nHISTORY / ALERTS\nHistory & uptime mein device aur time range select karen.\nCSV reports export kar sakte hain. Settings mein notification/beep on/off.\nDevice Edit mein latency aur repeated-failure thresholds set karen.\nGreen = reply, red = no reply, amber = warning/unknown, blue = checking.\nNo reply confirmed cable/radio fault nahi. ICMP blocked bhi ho sakta hai.\nSampled uptime/loss continuous uptime ka substitute nahi.\n\nWAN / ROCKET M5 LIMITS\nBasic ping monitoring implemented. Router/SNMP/airOS telemetry, signal, CCQ,\nspeed/throughput aur remote Lahore/Sargodha agents abhi implemented nahi.\nGeneral Internet ping se five independent WANs verify nahi hoti. IPv4 mode\nreachability only hai jab tak external routing separately verify na ho.\nOptional IPv6 source binding ko actual network par verify karna zaroori hai.\n\nDATA / CLEANUP\nSaved devices/history: %LOCALAPPDATA%\\ZeeNetworkMonitor\nSettings > Backup database. Close karne par probes safely finish hote hain.\nRemove: app close karke portable folder delete karen. Data bhi mitana ho to\npehle backup le kar %LOCALAPPDATA%\\ZeeNetworkMonitor delete karen.\nPasswords is release mein collect nahi hote; profile field mein secret na likhen.\n\nTESTING\nWindows runner par EXE build aur startup/shutdown smoke passed.\nAap ke Windows 10 laptop aur actual routers/radios par abhi test nahi hua.\nKoi issue aaye to exact error/screenshot aur kiye huay steps share karen.\n''',encoding='utf-8')
info={'version':'0.2.0','runner':platform.platform(),'python':platform.python_version(),'commit':os.getenv('GITHUB_SHA'),'run_url':f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}",'tests':counts|{'passed':passed},'frozen_smoke':'passed','windows10_hardware_test':'not performed'}
(out/'BUILD_INFO.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
(out/'TEST_REPORT.txt').write_text(f'''Windows build report\n\nVersion: 0.2.0\nHost: {platform.platform()}\nPython: {platform.python_version()}\nCommit: {info['commit']}\nRun: {info['run_url']}\n\nTests: {passed} passed, {counts['skipped']} skipped; 0 errors/failures.\nSyntax compilation: passed.\nPyInstaller Windows portable EXE build: passed.\nFrozen GUI startup / graceful shutdown: passed (offscreen).\nLive loopback: covered by the automated suite when OS ping is available.\n\nNOT TESTED: user's Windows 10 laptop, real LAN/WAN/radio behavior,\nWindows desktop DPI/locale/notification and audible speaker behavior, long-duration monitoring.\nNOT IMPLEMENTED: SNMP/airOS/router telemetry, per-WAN throughput, agents.\n\nThis is a testable initial Windows release, not a claim that every handover\nfeature has been completed. No physical link failure is inferred from ping.\n''',encoding='utf-8')
for name in ['docs/MAP_AND_BUZZER.md','docs/FEATURES.md','docs/ARCHITECTURE.md','docs/THIRD_PARTY.md','LICENSE','config-template.json']:
    shutil.copy(root/name,out/Path(name).name)
shutil.copy(root/'windows-tests.xml',out/'windows-tests.xml')
with zipfile.ZipFile(root/'ZeeNetworkMonitor-Windows-x64.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(out.rglob('*')):
        if p.is_file():z.write(p,str(p.relative_to(out.parent)))
print(json.dumps(info,indent=2))
