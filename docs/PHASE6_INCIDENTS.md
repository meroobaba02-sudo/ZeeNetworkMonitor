# Phase 6 — evidence-based fault localization and incidents (v0.4.10)

## Delivered
Existing ping, buzzer, telemetry, topology, alerts, source selection, retention and installer flows are preserved. New modules separate pure evidence evaluation from GUI-owned incident persistence.

- Topology & diagnosis counts only enabled devices with fresh threshold-reaching ICMP failures. Unknown, stale, disabled and infrastructure probe errors do not become physical fault evidence. Fresh service responses contradict total device unreachability despite ICMP failure.
- A possible common upstream issue needs an observed failing hop plus at least two recently failing descendants (within 60 seconds of that hop), with no fresh replying descendants. Mixed branches and isolated endpoints retain low-confidence possibilities. Missing children are not listed as affected. Parent links are configured dependencies, not discovered physical facts. Cross-page data is never grouped.
- Each displayed possibility includes evidence, qualitative confidence and a suggested next check. Confidence is Low or Medium; it is not a calibrated probability. ICMP evidence never confirms power/cable/dish failure. Check a management service/route and the intermediate segment before physical diagnosis.
- Separate persistent categories: reachability, successful-ICMP latency/loss warnings, configured service errors, external WAN check failures and measured wireless degradation. A router reply with failed external check is separate from an unreachable router. Authentication responses support reachability but cannot heal a service-access incident. Failure of one HTTPS endpoint does not prove a whole-Internet outage.
- Opening-fault evidence is retained separately from the recovery observation. Incident records contain first observed consecutive failure time (once threshold is reached), last evidence time, recovery observation, status, elapsed duration, evidence, confidence, next step, acknowledgement, notes and pin. Wireless/service/WAN start is the first recorded failing collection. Monitoring gaps are not proven downtime.
- Missing/stale results, disabled checks, unverified paths, edits and page changes never imply recovery. Configuration fingerprints bind recovery to the original monitored device/path/profile. Old-context incidents remain unresolved/Unobserved until manually closed or their original configuration is observed again. Restart marks all unresolved incidents Unobserved; new healthy evidence is required to recover them.
- Events & alerts > Incident history offers current-page history, explicit all-network history, acknowledgement, notes, pin/unpin, operator closure and CSV of the latest 500 displayed rows. Removed-device/network rows remain historical. Acknowledge neither silences the buzzer nor marks recovery. Operator closure is labeled recovery unverified; a still-observed fault may immediately create a new incident.
- Optional downstream notification reduction uses a fresh correlated common-upstream possibility. Individual device incident records and buzzer tracking are retained. Notifications issued before enough correlated evidence arrives are not retracted. Recovery messages and separate wireless/WAN issues are preserved. Disable reduction in Incident history if individual desktop notifications are preferred.
- Background retention protects unresolved and pinned incident rows. Resolved unpinned incidents use incident retention days measured from resolution; 0 keeps them indefinitely. Their evidence/notes survive ordinary 48-hour detail cleanup. Audit updates remain protected.

## Simple steps (Roman Urdu)
1. Asal parent/previous-hop links configure karen. Start monitoring.
2. Topology & diagnosis mein mumkin location, confidence, evidence aur next check dekhen.
3. Events & alerts > Incident history. Current page ke records default hain; zaroorat par all-network history tick karen.
4. Acknowledge = dekha gaya; Notes = technician ka update; Pin = cleanup se bachana. Buzzer awaaz ke liye existing Silence use karen.
5. Unobserved ka matlab nayi reliable reading nahi. Isay recovery ya continuously confirmed downtime na samjhen.
6. Asal healthy reading par incident Recovered hota hai. Evidence ke baghair closure chahiye to Close unverified use karen.

## Data safety / rollback
Schema 4 adds an incidents table and indexes. Before migrating an existing schema 3 database, Store creates `monitor.sqlite3.pre-v0410.bak` (or the equivalent database filename plus suffix). Existing devices/pages/history/settings remain. Schema 1/2 migration backups also remain. Database backup/restore accepts schema 4; existing restoration tests run against current schema.

Before upgrading, close the app and back up the full `%LOCALAPPDATA%\ZeeNetworkMonitor` directory, including credentials/licence/mobile sidecars. Baseline v0.4.9 is commit 8e898ae62080f022c3e5c7d7b166cf94b6050133. Old software rejects schema 4: rollback requires its installer AND the saved schema 3/full-data backup. Do not simply replace the EXE against the upgraded database. A later restore of the pre-upgrade backup loses changes made after that backup; keep the upgraded directory separately if needed.

## Tests and performance
Controlled local fixtures cover upstream+multiple downstream failures, isolated/mixed branches, HTTP/RTSP response with failed ICMP, stale/probe-error evidence, independent WAN failure, wireless freshness, service authentication uncertainty, performance-warning recovery, duplicate incident suppression, restart/gap preservation, acknowledgement/notes/pins, recurrence, changed-context/disabled checks, operator closure, protected retention, schema 3 backup/migration and schema 4 restore compatibility. GUI fault injection exercises actual result handlers, notification suppression, recovery, page history and acknowledgement/pin controls. Existing ping/buzzer/telemetry/map/retention/installer regressions remain mandatory.

Full local suite: 153 passed, 3 Windows-only skips. Compileall and real application startup/shutdown smoke passed. Incident dialog rendered and inspected at 1050x680; this is offscreen Linux evidence, not physical Windows DPI testing. Final Windows workflow must pass before delivering packages; expected Windows suite 156 without local skips, with actual workflow result authoritative.

Synthetic 10/50/100/250-device benchmark: all checks 0.150/0.854/1.715/4.538 seconds; max UI heartbeat gap 60.4/57.9/78.5/138.3 ms; cumulative process working set 84.4/93.1/102.9/114.1 MB; peak ping workers 8. Cleanup of 25,000 expired rows used 0.027/0.024/0.023/0.026 worker seconds. Incident observations use one indexed active-row query and no per-outcome lookup queries; unchanged evidence causes no update. Network work remains background/bounded. SQLite persistence and some history queries still run on the GUI thread; old-laptop/large-active-history performance is not guaranteed by this short synthetic run.

Changed runtime: zee/faults.py, zee/incidents.py, zee/incident_dialog.py, zee/core.py, zee/gui.py, zee/monitoring.py, zee/recovery.py, zee/retention.py. New tests: tests/test_phase6_incidents.py. Version/build/installer/user guides updated; PHASE6_INCIDENTS.md ships in the portable package.

## Limits / acceptance
Verified: implemented classifications/lifecycle against controlled fixtures and regression tests. Blocked/not performed: real multi-hop outages, actual Rocket/airOS metrics, five real WAN paths, physical Windows 10/speakers/DPI, long-duration pilot and calibrated false-positive/negative confidence. No remote agent, physical-fault confirmation, general Internet certification or guessed metrics. Historic topology-only diagnoses are superseded in the runtime GUI by fresh-evidence evaluation.

Current phase acceptance: software tests, migration/retention and documented limitations complete; final Windows artifacts require successful workflow. Next proposed phase is Phase 7 customer GUI polish/workflow review, after user approval. Full Admin Studio first increment remains Phase 8.
