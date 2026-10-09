# Windows build and download

**Current status: Windows EXE has not been built in this session.** This workflow is supplied, not claimed to have run. The intended release is a portable folder containing the EXE plus runtime DLLs; the EXE alone is not portable.

## Free browser-only GitHub Actions path

1. Sign in to [GitHub](https://github.com), choose **New repository**, name it `ZeeNetworkMonitor`, select **Private**, initialize with a README, then create it. No token or password needs to be sent in chat.
2. Extract the source ZIP. Open its `ZeeNetworkMonitor` folder. Upload its **contents** into the repository root using **Add file → Upload files**. In particular `main.py`, `requirements.txt`, `requirements-build.txt`, `ZeeNetworkMonitor.spec`, `pytest.ini`, `zee`, `tests`, `assets`, `docs`, and `README_RomanUrdu.txt` must be at the root. Do not upload the outer folder as another nested folder. Do not merely upload the ZIP.
3. Ensure `.github/workflows/windows-build.yml` is present. Windows may hide dot-prefixed folders. If the workflow did not upload, choose **Add file → Create new file**, set the filename to `.github/workflows/windows-build.yml`, copy the entire included YAML file into it, and commit. This is file copying, not writing new code.
4. Open the repository **Actions** tab. Enable workflows if prompted. Choose **Build Windows portable application → Run workflow → Run workflow**. A push to `main` or `master` also triggers it.
5. Wait for the run to finish. **A green check means its build, unit tests and frozen GUI smoke checks succeeded on Windows Server 2022**. It does not establish Windows 10 hardware compatibility, real router behavior or radio telemetry.
6. Open the successful run. Under **Artifacts**, click **ZeeNetworkMonitor-Windows-x64**. GitHub requires sign-in for artifact download. Unzip the artifact download and then its enclosed `ZeeNetworkMonitor-Windows-x64.zip`.
7. Open the resulting `ZeeNetworkMonitor` portable folder and run `ZeeNetworkMonitor.exe`. Keep `_internal` and every runtime file with it. The user laptop does not need Python, Git or VS Code.
8. If any job is red, open its failed step. Download **Windows-build-diagnostics** if available and send the log file for repair. An app artifact is uploaded only after smoke success. Artifacts are retained for 30 days; rerun the workflow if expired.

The runner uses Python 3.11 x64, PySide6 6.8.3 and PyInstaller 6.12.0. Windows 10 x64 is the target; a separate test on the user's laptop is still required. The package is not code-signed. Actual hardware, locale, DPI, firewall, OS edition and notification behavior remain to be checked.

## Developer local build

On a Windows development machine with Python 3.11 x64, run `Build_EXE.bat`. The build resolves pinned dependencies, runs the test suite and emits `dist/ZeeNetworkMonitor`. GitHub Actions additionally launches the frozen application and checks its success marker. This script is not the beginner no-Python route.

## No invented link

No repository or Windows run was created in this session, so there is no verified online EXE download URL yet. The supplied source ZIP is the verified deliverable. Once uploaded, the artifact is available on the user's actual repository Actions run; its URL cannot be specified before that run exists.
