"""Qt workers use signals; store/UI writes are performed in the main thread."""
import time
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from .ping import probe, Result

class WorkerSignals(QObject):
    done = Signal(str, object, object)

class Worker(QRunnable):
    def __init__(self, device, probe_fn):
        super().__init__()
        self.device, self.probe_fn = device, probe_fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.probe_fn(self.device)
        except Exception:
            result = Result(False,error='Unexpected probe error; see application diagnostics.',infrastructure_error=True)
        self.signals.done.emit(self.device.id,self.device,result)

class Engine(QObject):
    result = Signal(str, object, object)
    busy_changed = Signal()

    def __init__(self, parent=None, probe_fn=probe):
        super().__init__(parent)
        self.probe_fn = probe_fn
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(8)
        self.pending = {}
        self.due = {}
        self.devices = []
        self.generation = 0
        self.running = False
        self.closing = False
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def submit(self, d):
        if self.closing or not d.enabled or not d.host or d.id in self.pending or len(self.pending)>=8:
            return False
        worker = Worker(d,self.probe_fn)
        worker.generation=self.generation
        worker.signals.done.connect(self.complete)
        self.pending[d.id] = worker
        self.due[d.id] = time.monotonic()+d.interval
        self.pool.start(worker)
        self.busy_changed.emit()
        return True

    @Slot(str,object,object)
    def complete(self,id,device,result):
        worker=self.pending.pop(id,None)
        if not self.closing and worker and worker.generation==self.generation:
            self.result.emit(id,device,result)
        self.busy_changed.emit()

    def tick(self):
        if self.running:
            for d in self.devices:
                if self.due.get(d.id,0)<=time.monotonic():
                    self.submit(d)

    def start(self):
        self.running = True
        self.due.clear()
        self.tick()

    def invalidate(self):
        self.generation+=1
        self.stop()

    def stop(self):
        self.running = False
        # Already running subprocesses finish within their deadline; no new periodic work.

    def shutdown(self):
        self.closing = True
        self.running = False
        self.timer.stop()
        self.pool.clear()
        self.pool.waitForDone()
        self.pending.clear()
