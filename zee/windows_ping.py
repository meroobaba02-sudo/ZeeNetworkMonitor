"""Native IPv4 source-bound echo (IcmpSendEcho2Ex); no route mutation."""
import ctypes,socket,struct,os
from .ping import Result

def echo(host,source,timeout):
    if os.name!='nt':return Result(False,error='IPv4 source-bound ICMP requires Windows.',infrastructure_error=True)
    from ctypes import wintypes as w
    class Options(ctypes.Structure):_fields_=[('ttl',ctypes.c_ubyte),('tos',ctypes.c_ubyte),('flags',ctypes.c_ubyte),('size',ctypes.c_ubyte),('data',ctypes.c_void_p)]
    class Reply(ctypes.Structure):_fields_=[('address',w.ULONG),('status',w.ULONG),('rtt',w.ULONG),('size',w.WORD),('reserved',w.WORD),('data',ctypes.c_void_p),('options',Options)]
    api=ctypes.WinDLL('iphlpapi',use_last_error=True)
    api.IcmpCreateFile.restype=w.HANDLE;api.IcmpCloseHandle.argtypes=[w.HANDLE]
    fn=api.IcmpSendEcho2Ex;fn.restype=w.DWORD
    fn.argtypes=[w.HANDLE,w.HANDLE,ctypes.c_void_p,ctypes.c_void_p,w.ULONG,w.ULONG,ctypes.c_void_p,w.WORD,ctypes.c_void_p,ctypes.c_void_p,w.DWORD,w.DWORD]
    handle=api.IcmpCreateFile()
    if handle==ctypes.c_void_p(-1).value:return Result(False,error='Windows ICMP handle unavailable',infrastructure_error=True)
    try:
        payload=ctypes.create_string_buffer(b'ZeeMonitor');buf=ctypes.create_string_buffer(ctypes.sizeof(Reply)+64)
        addr=lambda s:struct.unpack('<I',socket.inet_aton(s))[0]
        count=fn(handle,None,None,None,addr(source),addr(host),payload,10,None,buf,len(buf),timeout)
        if count:
            reply=Reply.from_buffer(buf)
            if reply.status==0:return Result(True,float(reply.rtt))
            return Result(False,error='No reply on the selected source path (ICMP status '+str(reply.status)+')')
        error=ctypes.get_last_error()
        return Result(False,error='Source-bound ICMP failed (Windows code '+str(error)+')',infrastructure_error=error not in (11010,11003,11002))
    finally:api.IcmpCloseHandle(handle)
