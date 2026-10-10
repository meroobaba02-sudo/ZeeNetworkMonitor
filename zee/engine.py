"""Qt workers use signals; store/UI writes are performed in the main thread."""
import time
import threading
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from .ping import probe, Result

class WorkerSignals(QObject):
    done = Signal(str, object, object)

class Worker(QRunnable):
    def __init__(self, device, probe_fn, retries=0, retry_delay=1):
        super().__init__()
        self.device, self.probe_fn = device, probe_fn
        self.signals = WorkerSignals()
        self.retries, self.retry_delay = retries, retry_delay
        self.cancel = threading.Event()

    @Slot()
    def run(self):
        try:
            for attempt in range(self.retries+1):
                result = self.probe_fn(self.device)
                if result.success or result.infrastructure_error or attempt==self.retries:
                    break
                if self.cancel.wait(self.retry_delay):
                    break
        except Exception:
            result = Result(False,error='Unexpected probe error; see application diagnostics.',infrastructure_error=True)
        self.signals.done.emit(self.device.id,self.device,result)

class Engine(QObject):
    result = Signal(str, object, object)
    busy_changed = Signal()

    def __init__(self, parent=None, probe_fn=probe):
        super().__init__(parent)
        self.probe_fn = probe_fn
        self.prepare_probe = None
        self.permit = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(8)
        self.pending = {}
        self.due = {}
        self.devices = []
        self.generation = 0
        self.running = False
        self.closing = False
        self.limit, self.retries, self.retry_delay = 8, 0, 1
        self.minimum_interval = 1
        self.failures = {}
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def submit(self, d):
        if self.permit and not self.permit(d):return False
        if self.closing or not d.enabled or not d.host or d.id in self.pending or len(self.pending)>=self.limit:
            return False
        fn=self.prepare_probe(d,self.probe_fn) if self.prepare_probe else self.probe_fn
        worker = Worker(d,fn,self.retries,self.retry_delay)
        worker.generation=self.generation
        worker.signals.done.connect(self.complete)
        self.pending[d.id] = worker
        self.due[d.id] = time.monotonic()+max(d.interval,self.minimum_interval)
        self.pool.start(worker)
        self.busy_changed.emit()
        return True

    @Slot(str,object,object)
    def complete(self,id,device,result):
        worker=self.pending.pop(id,None)
        if not self.closing and worker and worker.generation==self.generation:
            self.failures[id] = 0 if result.success else min(5,self.failures.get(id,0)+1)
            interval=max(device.interval,self.minimum_interval)
            self.due[id]=time.monotonic()+max(interval,min(300,interval*2**self.failures[id]))
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

    def configure(self, limit=8, retries=0, retry_delay=1, minimum_interval=1):
        self.limit=max(1,min(16,int(limit)))
        self.retries=max(0,min(3,int(retries)))
        self.retry_delay=max(.1,min(10,float(retry_delay)))
        self.minimum_interval=max(1,min(3600,int(minimum_interval)))
        self.pool.setMaxThreadCount(self.limit)

    def invalidate(self):
        self.generation+=1
        self.stop()

    def stop(self):
        self.running = False
        for worker in self.pending.values():worker.cancel.set()
        # Already running subprocesses finish within their deadline; no new periodic work.

    def shutdown(self):
        self.closing = True
        self.stop()
        self.timer.stop()
        self.pool.clear()
        self.pool.waitForDone()
        self.pending.clear()
