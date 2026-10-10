"""Frozen panel smoke only: no network fault or physical acceptance is claimed."""
import json,os,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='zee-pilot-runtime-') as folder:
    completed=subprocess.run([str(root/'dist/ZeeNetworkMonitor/ZeeNetworkMonitor.exe'),'--smoke-test','--pilot-smoke-test','--data-dir',folder],timeout=60,env=os.environ.copy())
    assert completed.returncode==0
    report=json.loads((Path(folder)/'pilot-runtime-smoke.json').read_text())
    assert report['format']=='zee-pilot-1' and len(report['results'])==18
    assert all(result['status']=='Not performed' for result in report['results'].values())
    assert not report['review']['commercial_release_approved'] and not report['review']['ready_for_owner_review']
    assert report['capture']['state']=='Not recorded' and not report['privacy']['notes_included']
    print('Frozen field-pilot panel/defaults verified. No hardware acceptance or commercial approval.')
