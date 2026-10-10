"""Short synthetic pilot recorder overhead measurement, not hardware acceptance."""
import json,os,sys,tempfile,time,statistics,platform
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen');sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from zee.core import Store,Device
from zee.gui import Window
from zee.pilot_dialog import PilotCapture

def run(count):
    with tempfile.TemporaryDirectory(prefix='zee-pilot-overhead-') as folder:
        s=Store(Path(folder)/'monitor.sqlite3');s.set_setting('auto_cleanup',False)
        for index in range(count):s.save(Device(id=str(index),name='Synthetic fixture',host='127.0.0.1',alerts=False))
        w=Window(s);w.latest={d.id:{'at':time.time()} for d in w.monitor_devices()};w.engine.running=True
        capture=PilotCapture(w);w.pilot_capture=capture
        try:
            capture.start();times=[]
            for _ in range(10):
                started=time.perf_counter();capture.collect();times.append(1000*(time.perf_counter()-started))
            capture.stop();data=capture.session.document
            return {'devices':count,'stored_snapshot_devices':len(data['capture']['devices']),'snapshot_truncated':data['capture']['devices_truncated'],'collect_save_median_ms':round(statistics.median(times),3),'collect_save_max_ms':round(max(times),3),'file_bytes':capture.session.path.stat().st_size,'samples':data['capture']['total_samples'],'field_acceptance':False}
        finally:w.close()

if __name__=='__main__':
    app=QApplication([]);report={'kind':'Synthetic source-run snapshots, real local file writes. No live network requests, sustained laptop run or field acceptance.','platform':platform.platform(),'rows':[run(count) for count in (10,100,250)],'limits':'10 rapid captures per scenario; normal sampling is 30 seconds. No threshold certifies an old laptop.'}
    path=Path(sys.argv[1]);path.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
