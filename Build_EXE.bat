@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo This is a developer build script. For no-Python use, download the Windows portable artifact from GitHub Actions.
  pause
  exit /b 1
)
py -3.11 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pytest -q
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm ZeeNetworkMonitor.spec
if errorlevel 1 goto failed
copy README_RomanUrdu.txt dist\ZeeNetworkMonitor\ >nul
copy config-template.json dist\ZeeNetworkMonitor\ >nul
echo Build created in dist\ZeeNetworkMonitor. Keep the entire folder together.
pause
exit /b 0
:failed
echo Build failed. Read the error above. No successful EXE claim can be made.
pause
exit /b 1
