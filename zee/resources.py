"""Process-only CPU and working-set estimates without an extra dependency."""
import os,time
from pathlib import Path


def memory_mb():
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);api=ctypes.WinDLL('psapi',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        values=Counters();values.cb=ctypes.sizeof(values)
        if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(values),values.cb):return None
        return values.WorkingSetSize/1048576
    try:
        return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')/1048576
    except (OSError,ValueError,IndexError,AttributeError):return None


class Usage:
    def __init__(self):self.wall=time.monotonic();self.cpu=time.process_time()
    def sample(self):
        wall,cpu=time.monotonic(),time.process_time()
        percent=100*(cpu-self.cpu)/max(.001,wall-self.wall)
        self.wall,self.cpu=wall,cpu
        memory=memory_mb()
        return {'cpu_percent_one_core':round(percent,1),'working_set_mb':round(memory,1) if memory is not None else None}
