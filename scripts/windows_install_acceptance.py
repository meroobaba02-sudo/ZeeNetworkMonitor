"""Native per-user Inno acceptance helpers. Run only on the disposable Windows CI runner."""
import ctypes,json,os,shutil,subprocess,base64
from pathlib import Path

def known_folder(identifier):
    buffer=ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None,identifier,None,0,buffer):raise OSError('Cannot locate Windows shortcut folder')
    return Path(buffer.value)

def execute(exe,*arguments):
    result=subprocess.run([str(exe),*map(str,arguments)],timeout=120,env=os.environ.copy())
    if result.returncode:raise RuntimeError(f'{Path(exe).name} exited {result.returncode}')

def installer_process(exe,*arguments):
    # Inno can launch a child bootstrap/uninstall process. Wait for the full tree,
    # as Start-Process -Wait does, rather than only the initial subprocess handle.
    path=str(Path(exe).resolve()).replace("'","''")
    flags=' '.join(arguments).replace("'","''")
    command="$p=Start-Process -FilePath '"+path+"' -ArgumentList '"+flags+"' -Wait -PassThru; exit $p.ExitCode"
    encoded=base64.b64encode(command.encode('utf-16-le')).decode()
    execute('powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded)

def install(setup):installer_process(setup,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-')

def shortcuts(app_name):
    assert (known_folder(16)/(app_name+'.lnk')).is_file(),'Desktop shortcut missing'
    assert (known_folder(2)/app_name/(app_name+'.lnk')).is_file(),'Start Menu shortcut missing'

def uninstall(folder):
    installer_process(folder/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART')


def studio_acceptance(root):
    setup=root/'release/ZeeAdminStudio-Setup-Windows-v0.4.16.exe'
    runtime=Path(os.environ['LOCALAPPDATA'])/'Programs/ZeeAdminStudio'
    data=Path(os.environ['LOCALAPPDATA'])/'ZeeAdminStudio'
    data.mkdir(parents=True,exist_ok=True);marker=data/'installer-preserve.txt';marker.write_text('CI fixture')
    try:
        install(setup);shortcuts('Zee Admin Studio');execute(runtime/'ZeeAdminStudio.exe','--smoke-test')
        assert (data/'studio-smoke-ok.txt').is_file()
        install(setup);execute(runtime/'ZeeAdminStudio.exe','--smoke-test')
        uninstall(runtime);assert marker.read_text()=='CI fixture' and (data/'studio.sqlite3').is_file()
        assert not (runtime/'ZeeAdminStudio.exe').exists()
        (root/'release/STUDIO_INSTALLER_TEST_REPORT.txt').write_text('Windows Server 2022: per-user install, desktop/Start Menu, frozen login startup, same-version reinstall, uninstall preserving Studio database passed. No owner account or production signing key provisioned. Physical Windows 10/11 untested.\n')
    except Exception as error:
        print('Studio installer acceptance failed: '+str(error),flush=True);raise
    finally:
        if (runtime/'unins000.exe').exists():uninstall(runtime)

if __name__=='__main__':studio_acceptance(Path(__file__).resolve().parents[1])
