"""Verify frozen monitoring edition starts and preserves old licence files."""
import json,os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=Path(os.environ['RUNNER_TEMP'])/'zee-smoke';folder.mkdir(parents=True,exist_ok=True)
licence=folder/'license.json';previous=folder/'license.previous.json'
licence.write_text('old activation fixture — must not be read or modified',encoding='utf-8')
previous.write_text('old recovery fixture',encoding='utf-8')
before={p:p.read_bytes() for p in (licence,previous)}
result=subprocess.run([str(root/'dist/ZeeNetworkMonitor/ZeeNetworkMonitor.exe'),'--smoke-test','--noc-smoke-test','--data-dir',str(folder)],timeout=60,env=os.environ.copy())
assert result.returncode==0 and (folder/'smoke-ok.txt').is_file()
state=json.loads((folder/'customer-build-smoke.json').read_text())
assert state['monitoring_preview'] and state['licence']['valid'] and not state['licence']['production']
assert state['licence_timer_active'] and not state['activation_controls_present']
assert set(state['features'])=={'monitoring','map','wan','wireless','cctv','mobile','reports'}
assert all(p.read_bytes()==value for p,value in before.items())
noc=json.loads((folder/'noc-runtime-smoke.json').read_text());assert len(noc['routes'])==9 and noc['devices']==0 and not noc['discovery_running'] and noc['alignment_state']=='Ready' and noc['wan_cards']==7 and noc['configured_cards']==0 and noc['size']==[980,650]
print('Frozen NOC routes/defaults and monitoring startup: existing owner preview needs no activation, controls hidden, licence enforcement unchanged, old licence records preserved.')
