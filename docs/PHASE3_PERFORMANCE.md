# Phase 3 — bounded monitoring and retention (v0.4.7)

## Scope delivered
Existing ping, buzzer, map, page management, telemetry, mobile and licence features remain in place. The customer interface keeps daily controls visible and puts technical tuning in a separate Advanced dialog.

- Ping pool: 1–16 concurrent jobs, default 8. Service/telemetry pool: 1–4, default 2.
- Optional 0–3 extra ping retries, 1–10 second delay; default no extra retries. Successful or infrastructure-error results do not retry. Stop interrupts retry waits; an in-flight network call retains its existing bounded timeout. Failed periodic checks back off up to five minutes without shortening longer configured intervals.
- The same device cannot run overlapping ordinary/speed telemetry jobs. ICMP reachability and service telemetry remain separate probe families.
- Minimum ping interval: 1–3,600 seconds; per-device intervals continue above that floor. Screen refresh: 1–30 seconds, default 2.
- Probe callbacks update records/alarm immediately, then coalesce view redraws. Hidden WAN tables do not poll/redraw continuously.
- Device-table pagination: 200 rows. History graph/outage list: newest 1,000 samples. WAN day/session view: newest 5,000 measurements, explicitly labelled. Full retained exports remain available.
- CPU/RAM status shows this process, with 100% CPU equal to one core. It is not total PC utilization.
- Minimize continues monitoring by default. Optional pause remembers/resumes the prior periodic scope; changing network clears deferred resume.

## Retention policy
New installations default to **48 hours** for samples, telemetry measurements, ordinary events and diagnostic log records. An explicitly saved legacy day setting is converted to hours and preserved. The saved setting survives restart.

Background cleanup runs at startup and every ten minutes when enabled; expiry is therefore scheduled, not exact-to-the-second deletion. A separate worker owns its SQLite connection. Time indexes and 500-row transactions bound database work; each normal pass has a five-second database budget, with continuation if necessary. Lock/file errors are reported in Settings and automatic retry waits one minute.

Alert history has its own default **90-day** policy; zero keeps it indefinitely. Security/audit/licence event kinds, user-pinned events and persisted unresolved-device alerts are exempt. Existing events/alerts provide these protections; formal incident lifecycle/confidence belongs to Phase 6. Persisted unresolved alerts stay protected across pages/restarts until fresh state clears them.

Settings exposes hours, automatic cleanup, manual cleanup and last result/error. Alerts provides Pin/Unpin selected. Advanced exposes incident days and archive-before-cleanup. Archives are full SQLite snapshots under the data folder's archives directory; they exclude external credentials/licence/mobile sidecars, use additional disk, and remain until manually removed. Export/history and database backup remain available.

The configurable database disk threshold is a **warning, not a hard limit**. Fresh/protected records are never deleted merely to reach it. Database pages are reused; physical file size need not shrink after deletion. No full VACUUM or forced WAL truncation is run on the GUI thread. Diagnostic records keep traceback continuations together and are trimmed under the active log handler lock; the existing rotating file count/size cap remains.

## Verification
The suite covers legacy/new retention persistence, expiry boundaries, active/security/pinned preservation, unpinning, archive-before-delete, cancellation/bounded continuation, diagnostic traceback expiry, GUI/background database access, controlled lock failure, optional retry/backoff/cancellation, infrastructure-error behavior, pool bounds, pagination, auto-off/manual cleanup, redraw coalescing with immediate alarm, minimized monitoring and process resource readings. Existing regressions remain required.

Local source tests and syntax/startup checks are run before publication. Windows CI additionally runs the full tests, this phase's benchmark, both frozen executable smoke checks and installer/upgrade/uninstall tests. Windows success must be checked for the v0.4.7 commit, not inferred from v0.4.6.

## Recorded synthetic measurements
Source evidence: docs/test_evidence/phase3-benchmark-linux.json.
Fixture: 100 retained rows/device, 25,000 expired rows, 8 ping workers; quarter of targets return a slower simulated failure. No physical network requests.

| Devices | All fixture checks (s) | Cleanup worker (s) | Largest heartbeat gap (ms) | Process RAM (MB) |
|---|---:|---:|---:|---:|
| 10 | 0.146 | 0.023 | 52.2 | 81.6 |
| 50 | 0.845 | 0.027 | 54.8 | 90.8 |
| 100 | 1.731 | 0.024 | 66.3 | 100.5 |
| 250 | 4.526 | 0.026 | 131.3 | 111.4 |

Recorded startup: 0.088–0.157 seconds; measured idle-worker closure: 0.002–0.003 seconds. These are Linux cloud measurements, not guaranteed Windows/network timings. RAM is process-wide and cumulative across scenarios. CPU is measured over the short startup/check/cleanup scenario; it is not idle usage. Heartbeats cover checks/cleanup, not synchronous startup. The Windows CI benchmark is separately bundled as phase3-benchmark-windows.json.

## Limits and remaining field checks
The simulated delays are 3/20 milliseconds, so they do not establish behavior under maximum DNS, ICMP, SNMP, HTTPS or camera timeouts. Closing waits for already running bounded network calls; this is not an instantaneous cancellation guarantee. Large archive backup has a cancellation/deadline check. Archive growth is user-managed, and the disk threshold does not enforce a hard storage cap. ICMP and telemetry can run simultaneously for one device because they collect separate observations. Native radio, five-network routing, Android and physical old-i5 Windows 10 tests remain in the pilot phase. Do not claim “zero lag.”

## Acceptance and next phase
Require passing relevant regressions, startup, background cleanup/protections and recorded resource/UI measurements; then require a successful Windows release workflow. Preserve v0.4.6 commit 79be7a1086977a219364c052d1797804e51416d8 and its packages for recovery. Schema version remains 3 with additive time indexes and an event-pins table, preserving older readers.

Phase 4 next covers the five-network setup and topology with honest reachability/path validation. Start it only after the user's approval. Full Admin Studio's first test executable remains scheduled for the first small Phase 8 increment.

