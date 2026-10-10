"""Windows current-user DPAPI vault; no portable plaintext fallback."""
import ctypes,json,os,base64,threading
from pathlib import Path

class Blob(ctypes.Structure):
    _fields_=[('size',ctypes.c_uint32),('data',ctypes.POINTER(ctypes.c_ubyte))]

def protect(raw,decrypt=False):
    if os.name!='nt':raise RuntimeError('Saved credentials require Windows DPAPI; no plaintext fallback is available.')
    buf=ctypes.create_string_buffer(raw);src=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));dst=Blob()
    dll=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    fn=dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(Blob)];fn.restype=ctypes.c_int
    if not fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(dst)):raise RuntimeError('Windows credential protection failed for this user/computer.')
    try:return ctypes.string_at(dst.data,dst.size)
    finally:kernel.LocalFree(dst.data)

class Vault:
    def __init__(self,path):self.path=Path(path);self.lock=threading.RLock()
    def _read(self):return json.loads(self.path.read_text()) if self.path.exists() else {}
    def get(self,id):
        with self.lock:
            value=self._read().get(id)
            return json.loads(protect(base64.b64decode(value),True)) if value else {}
    def set(self,id,secrets):
        with self.lock:
            data=self._read();data[id]=base64.b64encode(protect(json.dumps(secrets).encode())).decode();self._write(data)
    def delete(self,id):
        with self.lock:
            data=self._read();data.pop(id,None);self._write(data)
    def _write(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(data));os.replace(tmp,self.path)
