# Phase 10.1 — real-network pilot package (v0.4.16)

**Status: tooling and automated verification only. Actual user-network pilot NOT PERFORMED. Commercial launch NOT APPROVED.**

Phase 10 in the approved plan requires actual hardware evidence first, then documentation and commercial review. This delivery is Phase 10.1: a usable field-test package. Phase 10.2 will review the operator's real report, fix observed defects, repeat failed cases and decide release readiness. CI results cannot replace the user's Windows laptop, Rocket radios, seven modems or phone/VPN tests.

## Delivered files and behavior

`zee/pilot.py` owns validated local evidence, atomic persistence, privacy-safe export and review blockers. `zee/pilot_dialog.py` adds a simple scrollable checklist with results/notes/delays/false-alert counts, opt-in CPU/RAM/storage/GUI-heartbeat capture and export. Settings > **Real-network pilot / support report** opens it. Existing monitoring, topology, licence and device controls remain in place. `main.py` provides a separate CI-only frozen-panel smoke option; `scripts/verify_pilot_runtime.py` checks it. `scripts/benchmark_phase10.py` measures short synthetic recording overhead. `tests/test_phase10_pilot.py` tests recovery, privacy, evidence validation, blockers, bounded snapshots and injected fault/recovery fixtures. Packaging/CI includes this guide and the Windows synthetic benchmark. DB schema remains 4; Studio schema remains 1.

## Easy field workflow

1. Back up the full application data folder and make a separate database backup. Keep private issuer recovery/passwords separate. Confirm actual Windows interface/route paths. Start with one or two spare/test endpoints before scheduling outages that affect live users.
2. Configure actual devices and verified firmware adapters, then **Start monitoring**. Open Settings > Real-network pilot / support report > **Start performance capture**. Capture does not start network probes, change routes, reboot/disconnect devices, create load tests or run speed tests. Normal monitoring continues.
3. Choose a test from the dropdown. Perform the controlled action on your own network, compare against independently observed ground truth, choose Pass/Fail/Blocked, record a specific evidence note and save. Do not mark a case Pass because ping alone is green. Missing hardware is Not performed or Blocked.
4. Detection delay is seconds from the independently recorded fault start to the first relevant application alert. Recovery delay is seconds from independently confirmed recovery to the application recovery indication. False positive is an alert when the condition did not actually occur; false negative is a missed real fault. Keep timestamps/evidence so a reviewer can reconstruct these numbers. Use Not measured when unknown; enter zero only when measured zero. Fault cases need counts and detection/recovery measurements before owner review readiness.
5. Keep the PC awake and the app/normal monitoring running for 4–6 hours initially. Read the **Fresh monitoring** counter: at least four hours is the initial readiness requirement. The operator's extended-run case still needs a real note and evidence; a counter alone does not validate reliability. Continue longer if the actual network needs it. Closing the pilot panel does not stop capture; stopping the main app saves it. Crash/restart marks a previously running capture Interrupted rather than pretending it ran continuously.
6. **Stop & save capture**, then **Export support / pilot report**. Save `zee-pilot-report.json` and send it yourself for review. Notes are excluded by default; include them only after removing passwords, keys, phone codes or identifying customer information. For note-free exports supply sanitized test explanations separately. No upload/email/remote support session happens automatically.
7. A new session archives the old evidence locally before clearing the checklist. Old-version evidence remains readable but cannot qualify the new release. A stopped/interrupted capture is not silently resumed or combined into a continuous run. Preserve archives for comparison.

## Controlled cases and acceptance evidence

| Case | Expected distinction / ground truth |
| --- | --- |
| Endpoint outage | Specific endpoint loses service/reply; unaffected peers remain checked. Record delay and physical/service confirmation. |
| Gateway outage | Gateway reachability and downstream correlation are shown as evidence-based possibilities. Verify the actual path. |
| Upstream/intermediate tower | Check multiple hops and independent peers; no confirmed cable/power diagnosis from ping alone. |
| Internet fails, router replies | Local management remains reachable while a verified external check fails. |
| One WAN fails | Independently verified alternate WAN continues working. A shared switch/shared subnet alone does not prove path independence. |
| Rocket management unreachable | Distinguish management response from wireless forwarding/link quality. |
| Actual Rocket metrics | Compare model/firmware and real OIDs/API values with the device UI at the same time. Missing values stay Unknown. |
| ICMP filtered | Another actual service continues responding; do not diagnose a physical failure from ICMP alone. |
| Recovery | Restore the real condition and compare app recovery time against independent confirmation. |
| Many simultaneous faults | Record scope/correlation, unexpected alerts, bounded workers, GUI delay and recovery. |
| Extended run | Four or more captured fresh monitoring hours initially, CPU/RAM/storage growth and UI heartbeat observations. Expand duration as required. |
| Retention cleanup | Expired eligible history is removed; pinned/unresolved/protected records and current configuration remain. |
| Restart | Settings, pages, towers, licence and protected credentials remain. Interrupted monitoring gaps are not fake recovery. |
| Backup/restore | Restored configuration matches backup; safety copy matches pre-restore state; licence/credentials remain local. |
| Windows installation | Clean supported physical Windows 10/11 x64 install, shortcuts, launch, update and uninstall preserving data. CI Server 2022 is separate evidence. |
| Five networks | Confirm Windows interfaces/routes, intended sources and page isolation, especially overlapping IP networks. |
| Seven modems | Verify every actual modem/Internet path before comparing independent traffic/download throughput. Shared-address management ping is insufficient. |
| Phone LAN/VPN | Verify certificate fingerprint, pair two phones, revoke one/all, logout, stop/restart and real VPN reachability. No hosted relay is included. |

## What the report measures

Capture is off until explicitly started. A one-second GUI timer measures maximum heartbeat gap; every 30 seconds it samples process CPU (100% = one core), current working-set RAM, database/WAL/SHM byte sizes and rotated diagnostic-log sizes. It stores selected permitted-device counts, fresh ping counts and the latest numeric measurement snapshot. Traffic download/upload and controlled download throughput have separate fields; upload capacity testing remains unavailable. Stale measurements stay unavailable. CPU above 100% can mean more than one core is in use.

Fresh-monitoring duration is a sampled estimate: it counts intervals with monitoring active and recent ping observations from the latest capture; intervals longer than five seconds are excluded. It is not proof that every endpoint was continuously probed, all WANs were independent or faults were correctly classified. Compare all claims with actual operator ground truth.

Raw performance history is capped at 1,440 samples (about the latest 12 hours at normal cadence). Total/observed counts, elapsed duration and maximum heartbeat gap cover the session. Only the latest snapshot of up to 200 permitted selected devices is included; larger scopes are explicitly marked truncated. Report does not include raw logs/events, database content, IPs/hostnames, network/device names, URLs, credentials, licence/fingerprint/key documents or pairing tokens. Device aliases are pseudonymous hashes of IDs. Local notes are capped at 2,000 characters; notes can contain anything the operator types, so inclusion is explicit. Local evidence is capped at 2 MiB on read. Archives are preserved and require manual housekeeping.

## Review gate and launch checklist

The report always says `commercial_release_approved: false`. Readiness for **owner review** requires all cases operator-reported Pass with evidence notes, required delay/count fields, zero unexplained false alerts, a completed continuous capture with at least four fresh monitoring hours and 480 fresh observation samples, actual Windows metadata and current app version. Failed/blocked/missing cases remain visible. The JSON is local operator evidence, not a cryptographically attested independent field audit; its contents can be edited by the local user. Owner must verify ground truth and evidence, not trust a checkbox or imported file automatically. Existing Studio build/licence tools remain available for testing; their successful build status is not commercial pilot approval.

Before launch the owner must:

- Review actual hardware/firmware/routing and controlled outage/recovery evidence; record sign-off and release-blocking issue resolution.
- Review sustained resource/storage measurements on the actual laptop and configure retention/archive housekeeping.
- Repeat affected acceptance cases after fixes; keep baseline reports and rollback backups.
- Verify production issuer, customer profile/feature ceilings, one-PC binding and encrypted issuer recovery. Keep private material out of customers/packages/GitHub.
- Review clean-machine installation and same-profile upgrades, backup/restore, phone trust/VPN requirements and unsigned-installer handling.
- Publish known limits, supported versions, support contact/hours and a concrete bug-report procedure. No invented support email is provided here.

Support procedure: operator exports the redacted report, gives version/OS, case ID, exact observed-versus-expected behavior and sanitized timing evidence. Owner assigns issue severity, reproduces with a controlled fixture where possible, patches/retests and repeats the user's failed field case. Do not request private keys, passwords, full databases or unredacted logs as the first diagnostic step.

## Verification, performance and rollback

Automated regression and injected fault fixtures verify the software flow; they are not real outage acceptance. Frozen smoke opens the actual packaged pilot panel with all cases Not performed and no capture/approval. Native Windows setup/customer activation/upgrade/recovery tests remain in CI. `phase10-benchmark-windows.json` contains short synthetic collection/save measurements for 10/100/250 fixtures; it does not certify sustained old-laptop performance. Actual CPU/RAM/GUI/storage measurements must come from the exported field session. No additional network requests are introduced by pilot capture.

Rollback baseline: **v0.4.15**, commit `83c288212a283b2079e50ce5790ead19b6f2dc82`. Stop capture and both applications; copy full customer/Studio data folders plus pilot evidence/archives; install the reviewed prior package with the same customer profile/issuer. Existing SQLite schemas remain compatible. Older apps ignore new pilot JSON files. Database-only restore does not back up pilot sidecars, credentials or licences. Same Windows account/PC is needed for DPAPI credentials.

**Phase 10.1 acceptance:** panel works, statuses default unperformed, evidence survives restart/archive, bad files/writes cannot silently replace valid saved results, export excludes private configuration, CPU/storage sampling and caps are verified, frozen/native builds pass, field guide/support/rollback procedures supplied. **Phase 10.2 blocker:** actual user-device access and completed pilot report/ground-truth evidence are not yet available. Commercial readiness cannot be declared until those are reviewed and critical defects are resolved.
