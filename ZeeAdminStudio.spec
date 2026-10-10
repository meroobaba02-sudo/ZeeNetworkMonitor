from pathlib import Path
root=Path(SPECPATH)
a=Analysis([str(root/'admin/studio.py')],pathex=[str(root)],binaries=[],datas=[],hiddenimports=[],excludes=['PySide6.QtWebEngineCore','PySide6.QtQml','PySide6.QtQuick','PySide6.QtNetwork'],noarchive=False)
import sys
sys.path.insert(0,str(root/'scripts'))
from compile_runtime_mibs import compile_mibs
a.datas=compile_mibs(a.datas,root/'build/studio_mib_bytecode')
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ZeeAdminStudio',console=False,icon=str(root/'assets/icon.ico'))
coll=COLLECT(exe,a.binaries,a.datas,name='ZeeAdminStudio')
