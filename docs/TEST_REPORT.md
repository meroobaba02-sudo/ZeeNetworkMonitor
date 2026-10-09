# Test report — Zee Network Monitor 0.1.0

Date: 2026-10-09. Test/build host: Linux x86_64; Python 3.12.14. GUI: PySide6 6.8.3, Qt offscreen platform. Packaging: PyInstaller 6.12.0, hooks-contrib 2025.1. Windows workflow targets Python 3.11 x64 on Windows Server 2022, but was not run in this session.

## Executed results

| Check | Result |
|---|---|
| Dependency installation | Passed; pinned runtime/build packages resolved on Linux |
| Syntax/static bytecode compilation | Passed: `python -m compileall -q main.py zee tests` |
| Unit / integration / GUI suite | **41 passed, 1 skipped**; last run 0.47 seconds |
| Parser fixtures | Passed: Windows/Linux echo, sub-ms, decimal comma, selected localized timings, IPv6, timeout, unreachable, TTL expiry |
| Host validation | Passed: IPv4/IPv6/ASCII names accepted; malformed IP, URL, whitespace and command-like input rejected |
| Save/load/restart and backup | Passed: devices/settings/history retained, SQLite backup matches, incompatible schema rejected |
| CSV export | Passed: event export readable, user strings guarded against spreadsheet formula evaluation |
| Retention / event filtering | Passed: age-based deletion, device/date/search filtering |
| Multi-device / overlapping jobs | Passed: concurrent Qt workers, duplicate suppression, GUI-main-thread results, 12-device manual queue |
| Shutdown/stop | Passed with injected bounded probe; stops new periodic work and drains running jobs safely |
| Edit/delete during work | Obsolete edited-device snapshot ignored; parent references cleared after deletion |
| Alerts | Passed: repeated-failure threshold, duplicate suppression, recovery event |
| Unknown/stale status | Passed: persisted success does not become fresh Online after restart; stale state becomes Unknown |
| Infrastructure error handling | Passed: missing executable/DNS/permission issues do not count as device outage samples |
| GUI editor/table/filter/topology | Startup/editor roundtrip, 12-row dashboard, search, topology render and close exercised |
| Source GUI smoke | Passed: start, display and graceful close; explicit success marker |
| Linux portable frozen build | Passed with the supplied PyInstaller spec |
| Linux frozen GUI smoke | Passed: frozen executable launch and graceful close, explicit success marker |
| GUI visual inspection | Offscreen rendered dashboard inspected; preview included in `docs/GUI_preview.png` |
| Workflow YAML structural validation | Passed parser checks; not an executed Windows CI result |

Automated probe tests use injected results to test scheduling and state transitions. Those tests are not evidence of live radio/WAN connectivity. The delivered GUI preview is an actual empty application screenshot, not fake network health.

## Skipped / not tested

- **Live loopback ICMP test skipped:** no OS `ping` executable on this Linux host. The suite includes a live loopback test that runs where `ping` is available, including the future Windows runner. Actual device/WAN ping is not tested.
- **Windows EXE build: not performed.** No Windows executable is present in the source ZIP. Linux build success is not Windows build success. The included GitHub Actions workflow must be run before an EXE can be downloaded.
- **Windows frozen launch / missing DLL checks: not performed.** The workflow includes these checks but has not been executed.
- **Windows 10 laptop compatibility, real DPI/locale behavior and notifications/beep: not tested.** An offscreen Linux test cannot establish those behaviors.
- **WAN-specific IPv6 binding / externally verified IPv4 routing: not tested on live network hardware.** Command construction is tested only; independent WAN performance is not established.
- **SNMP, airOS, router APIs, radio telemetry and agents:** not implemented and not tested. No claims of secure agent communication, service installation or secret storage are made.
- **Long-duration soak, large-device scaling, disk-full recovery, real power-loss and service behavior:** not tested. Store operations/report generation on large retained data remain a scaling limitation.

## Packaging notes

The Linux build warning list contains expected optional/platform-specific imports such as `_winapi`, `winreg`, `msvcrt`, Java/VMS and optional Windows logging modules. Excluded unused QtNetwork is optional here. No failed import was observed in the Linux frozen GUI smoke. Windows DLL dependencies remain unverified until the Windows workflow runs. Source ZIP excludes Linux binaries, build cache and dependency installs; the Linux executable is not presented as a Windows deliverable.

Machine-readable results, last Linux build log, PyInstaller warning file and smoke markers are included under `docs/test_evidence/`. Test durations can vary on rerun.

## References used for build/worker design

- Qt background thread signals: https://doc.qt.io/qtforpython-6/examples/example_widgets_thread_signals.html
- Qt QThreadPool: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThreadPool.html
- PyInstaller platform-specific build requirement: https://pyinstaller.org/en/latest/
