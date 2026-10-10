"""Adapt PySNMP's legacy MIB reader to standard Python 3 .pyc headers.
PySNMP 7.1 still assumes an 8-byte header in read(), while its debug loader uses
runpy which requires the standard 16-byte header. Our bundled MIB data uses
standard py_compile files, so both paths can load the same compiled code.
"""
import importlib.util,marshal

def install():
    from pysnmp.smi import builder
    cls=builder.__AbstractMibSource
    if getattr(cls,'_zee_standard_pyc',False):return
    original=cls.read
    def read(self,name):
        try:
            data,path=self._get_data(name+'.pyc','rb')
            if data[:4]==importlib.util.MAGIC_NUMBER and len(data)>=16:
                return marshal.loads(data[16:]),'.pyc'
        except OSError:pass
        return original(self,name)
    cls.read=read;cls._zee_standard_pyc=True
