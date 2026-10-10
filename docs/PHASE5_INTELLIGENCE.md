# Phase 5 — device, Rocket M5 and WAN intelligence (v0.4.9)

## Increment delivered
The existing SNMP/HTTPS adapters, gateway ping, external HTTPS checks, quality score, alignment trend and controlled-download budget are preserved. This phase strengthens their evidence boundaries rather than inventing an airOS API or rewriting the application.

- Read-only SNMP v1/v2c GET actually binds to a selected local IPv4 or non-scoped IPv6 address. Matching literal device/source IP families are required. Scoped IPv6 and a source-bound DNS target fail explicitly. There is no default-route fallback, SNMP SET, discovery scan or remote configuration change.
- Secure settings records actual device model and firmware (optional reference fields), with an explicit operator profile-verification checkbox. Mapping/model/firmware/method/version edits clear verification; the operator can recheck after validating the mapping. A successful request is not physical compatibility certification.
- Numeric telemetry rejects nonfinite/out-of-range signal, CCQ, rates and percentages. Link-state enums must already be mapped to 0/1: values such as 2 are not silently interpreted. Unsupported/missing metrics stay unavailable. JSON paths support array indices for explicitly configured station entries; station inventory/discovery is not implemented.
- ASN.1/JSON integer counters preserve Counter64 precision. Negative movement, changed discontinuity marker and declining uptime reset the baseline. Polling uses monotonic completion times and ignores stale baseline gaps. Counter wraps are discarded, not guessed; unexposed reboot/discontinuity cannot be proven.
- WAN traffic needs both WAN path attestation and separate WAN counter-interface attestation/name. An arbitrary management-interface counter is no longer presented as WAN traffic. Old profiles remain usable for reachability/wireless checks, but counters require this additional configuration.
- WAN endpoint/expected marker/source changes clear path attestation. Counter-interface changes clear counter attestation. Host/source edits in the basic device editor also clear verification and cached readings. Saving WAN/adapter settings invalidates old workers, stops monitoring and clears cached measurements. Restart monitoring after saving.
- Cancelled download tests produce an unavailable/error result, not completed Mbps. Maximum data reservation remains charged on interruption/failure. Active upload-capacity testing is unavailable; verified interface counters show traffic usage only.
- Device details records measurement source, model/firmware and profile limitations. Alignment feedback resets when quality data disappears, even if the latest collection timestamp is fresh.

## Simple setup (Roman Urdu)
1. Apne radio ka management page normal login se kholen. Asal model aur firmware version note karen.
2. Device details > Secure settings. Model/firmware record karen, supported method select karen, read-only credentials protected fields mein den.
3. Asal firmware ke verified OIDs/JSON fields aur correct units configure karen. Is verification ke baghair profile checkbox tick na karen. Koi ready-made Rocket M5 OID profile is release mein claim nahi kiya gaya.
4. Mapping verify hone par checkbox tick > Save. Network setup mein existing local source IP aur actual Windows path verify karen. Start monitoring > Refresh / Test connection.
5. WAN setup mein apna controlled HTTPS endpoint aur expected marker den. Intended WAN path khud verify karen, phir checkbox tick karen.
6. Counters use karne hon to actual WAN interface ka naam den aur us interface/OID mapping ko alag verify karen. Download test data consume karta hai; automatic testing default OFF rakhen jab tak zaroorat na ho.

## Quality formula
For each valid available signal/CCQ metric, clamp `10 * (value - poor) / (good - poor)` to 0–10. Optional rate scoring applies the same formula to measured TX/RX rates. Take the lowest available component, rounded to one decimal. Good >=8; Fair >=5; otherwise Poor. An explicitly mapped wireless_up=0 is Critical. No valid scoring components, or data older than max(30 seconds, 3 polling intervals), yields Unknown / insufficient data. A strong signal alone is a partial score, not proof of all aspects of link health. Noise/SNR/frequency/uptime are displayed but not invented score components. Configurable thresholds remain in the integration profile. Peer-map quality still requires both fresh endpoints and takes the worse category.

## Evidence and status
Verified Working against local fixtures: source-bound SNMP v1/v2c IPv4 and IPv6 GET with observed packet source; precise Counter64 values; invalid metric rejection; reboot/discontinuity guards; stale counter gaps; cancelled download result; WAN edit invalidation; profile attestation reset; unavailable alignment reset. Full local suite: 136 passed, 3 Windows-specific skips. Syntax and application startup smoke checks also passed.

Windows acceptance: the release workflow must pass all tests, its synthetic 10/50/100/250-device checks, frozen executable launches and installer/upgrade/uninstall checks before packages are called verified. Expected suite count: 139 without local skips; actual workflow result is authoritative. The synthetic benchmark does not measure radio firmware compatibility or production WAN throughput. No extra worker pools or periodic services were introduced. Local Linux synthetic results (10/50/100/250 devices): all checks 0.133/0.861/1.755/4.669 seconds, maximum UI heartbeat gap 51.1/56.1/88.5/143.4 ms, cumulative process working set 83.2/92.4/102.2/113.2 MB. Peak ping workers remained 8; 25,000 expired-row cleanup used 0.031/0.023/0.024/0.023 worker seconds. Short simulated checks do not model real DNS/TLS/radio timeouts or startup blocking.

Blocked: actual Rocket M5/airOS OIDs/API/firmware compatibility, router-specific WAN counter direction/interface mapping, connected-station enumeration, the user's five independent WAN paths, active upload capacity and physical Windows 10/old-laptop/alignment tests. Their hardware/management access is unavailable here. No guessed model profile, fabricated Mbps, combined connection labeled per-WAN, or ping-only physical-fault conclusion is supplied. Actual user network requests were not performed.

## Official integration reference
PySNMP 7.1 API: https://docs.lextudio.com/pysnmp/v7.1/docs/api-reference — set_local_address sets the local SNMP source, and Udp6TransportTarget supports IPv6. Installed pinned version 7.1.22 source was also inspected and the protocol exercised against a local fixture. This does not certify a Rocket firmware mapping.

## Files and recovery
Runtime: zee/telemetry.py, zee/monitoring.py, zee/professional.py, zee/wan_dialog.py, zee/gui.py. Tests: tests/test_phase5_intelligence.py. Version, package/installer/workflow and user guides updated to 0.4.9. No database schema migration (schema 3), signing-key changes or device configuration writes.

Before upgrading, close the app and back up the entire %LOCALAPPDATA%\ZeeNetworkMonitor data directory. Baseline v0.4.8 commit d70728a587bb8a8afb5d2d493dc4fd859473b295 is recoverable in GitHub history. Keep its installer. For full rollback use that installer plus the saved data directory; reverting code alone does not undo saved profile/settings edits. Credentials remain Windows-account protected. Historical Phase 4 documentation describes v0.4.8; this release supersedes its SNMP-source limitation.

Current phase acceptance: code/fixture checks completed; actual-device acceptance explicitly Blocked. Review final Windows CI evidence and perform field checks before claiming hardware verification. Next proposal is Phase 6 evidence-based fault localization/incidents, after user approval. Full Admin Studio remains Phase 8.
