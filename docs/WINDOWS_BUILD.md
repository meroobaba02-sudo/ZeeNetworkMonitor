# Windows build and download

The existing v0.4.5 Windows build succeeded at [run 38052485552](https://github.com/meroobaba02-sudo/ZeeNetworkMonitor/actions/runs/38052485552). The Phase 2 update is v0.4.6: inspect its own run before calling its packages verified.

1. Open the repository Actions tab and select **Build and test Professional Windows packages**.
2. Open a successful run for the required commit/version.
3. Download **ZeeNetworkMonitor-Setup-Windows** for the installer, or **ZeeNetworkMonitor-Portable-Windows** for the portable ZIP. Extract the downloaded artifact first.
4. Run the setup EXE, or Extract All the enclosed portable ZIP and run ZeeNetworkMonitor.exe. Keep its entire folder and _internal together. Python/Git are not required on the customer's PC.
5. **ZeeLicenseManager-Admin** is a separate owner-only licence utility, not full Admin Studio. Do not give it or private signing keys to customers.

The workflow uses Python 3.11 x64, pinned dependencies, unit/GUI/security tests, both PyInstaller specifications, frozen startup including SNMP engine construction, runtime-content audit, Inno Setup, and install/launch/reinstall/uninstall checks. Windows Server 2022 CI does not prove physical Windows 10, real-device compatibility or performance. The application is not Authenticode signed.

A push to main triggers this workflow; workflow_dispatch supports manual runs. If a step fails, inspect the failed step and Windows-build-diagnostics. Artifacts expire after 30 days and can be rebuilt. Never mix runtime DLLs from different versions.

Developer local Windows build: Build_EXE.bat with Python 3.11 builds the customer portable folder. It does not run the full CI installer/owner packaging checks. Use the workflow for full release evidence.

Before upgrade, close the app and back up the entire user-data folder plus a database backup. Data remains under %LOCALAPPDATA%\\ZeeNetworkMonitor after normal uninstall.
