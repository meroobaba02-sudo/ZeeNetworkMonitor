"""Compile PySNMP's runtime MIB data using its documented-in-code loader format.
PySNMP 7.1 builder reads magic + 32-bit mtime + marshalled code, not the
standard Python 3.7+ 16-byte .pyc header. Keep this isolated from normal modules.
"""
from pathlib import Path
import importlib.util,marshal,struct

def compile_mibs(entries,folder):
    result=[]
    for dest,src,kind in entries:
        if dest.replace('\\','/').startswith('pysnmp/smi/mibs/') and dest.endswith('.py'):
            output=Path(folder)/(dest+'c');output.parent.mkdir(parents=True,exist_ok=True)
            code=compile(Path(src).read_text(encoding='utf-8-sig'),dest,'exec')
            output.write_bytes(importlib.util.MAGIC_NUMBER+struct.pack('<I',int(Path(src).stat().st_mtime))+marshal.dumps(code))
            result.append((dest+'c',str(output),kind))
        else:result.append((dest,src,kind))
    return result
