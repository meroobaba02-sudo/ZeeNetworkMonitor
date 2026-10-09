# Portable folder build: fewer extraction/AV issues than a one-file Qt bundle.
from pathlib import Path
root=Path(SPECPATH)
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=[],datas=[(str(root/'assets'),'assets')],hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQml','PySide6.QtQuick','PySide6.QtNetwork','PySide6.QtMultimedia','PySide6.Qt3DCore'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ZeeNetworkMonitor',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon=str(root/'assets'/'icon.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ZeeNetworkMonitor')
