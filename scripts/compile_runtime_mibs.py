"""Compile third-party runtime MIB data using standard Python bytecode."""
from pathlib import Path
import py_compile

def compile_mibs(entries,folder):
    result=[]
    for dest,src,kind in entries:
        if dest.replace('\\','/').startswith('pysnmp/smi/mibs/') and dest.endswith('.py'):
            output=Path(folder)/(dest+'c');output.parent.mkdir(parents=True,exist_ok=True)
            py_compile.compile(src,cfile=str(output),dfile=dest,doraise=True)
            result.append((dest+'c',str(output),kind))
        else:result.append((dest,src,kind))
    return result
