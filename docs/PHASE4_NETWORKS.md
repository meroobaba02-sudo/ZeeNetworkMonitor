# Phase 4 — multi-network topology (v0.4.8)

## Delivered behavior
- **Network setup / paths** provides editable network rows (at least five initial rows), laptop source IP selection, adapter identity from real Windows inventory, optional gateway reference, literal test target and an explicit Operator verified checkbox.
- **Read laptop IPs / adapters** invokes the fixed read-only Windows Get-NetIPAddress command in a background worker. It selects existing addresses; it does not assign addresses or modify adapters. The non-Windows development fixture lists loopback only and is not a Windows-laptop inventory.
- **Check selected network** selects an OS route, sends one requested ICMP check and reads Windows adapter/route tables. The report records actual source/reachability observations. A reply never automatically marks the page verified or proves the intended WAN/dish. Changed-input results are ignored.
- **Monitor all networks** is optional and saved. Start checks active pages together under the existing shared pool limits (default 8 ping / 2 telemetry), rather than multiplying pools per page. All-network mode requires an operator-verified path for every checked page.
- In all-network mode changing the visible page retains monitoring/results on other pages. Map, towers, history, device table and links still display only the selected page. In default selected-page mode changing pages retains the previous stop/reset behavior.
- The source/route decision is captured on the GUI thread before each ping worker is submitted. Telemetry uses the device's own page source, not whichever page is currently visible. Page/path configuration edits invalidate older generations and stop monitoring.
- Background-page faults reach the buzzer/notifications and persist protection from ordinary retention. Mobile shows actual all-network fresh results when all-network mode is selected; other pages remain Not monitored in selected mode.
- Same target across pages is blocked in all-network mode if sources are missing/shared or any related page lacks operator verification. Distinct sources and operator attestation still do not establish WAN independence.
- **Connect tower radios** saves reciprocal peer IDs, optionally sets the second radio's upstream parent, and rejects cross-page links, self-links, replacement of existing peers without removal and parent cycles. Both peer records update together. Remove clears that pair and its direct parent relation, preserving unrelated parent links.
- Map peer links avoid drawing the same reciprocal pair twice. Radio-pair quality uses both fresh endpoints, takes the worse measured category, and remains Unknown if either is missing/stale. Reachability warnings at either endpoint make the line dashed; wireless quality remains separate from ICMP evidence.

## Simple user path (Roman Urdu)
1. Network setup / paths kholen. Har row ka apna network naam den.
2. Read laptop IPs / adapters dabayen. Us network ke liye existing laptop source IP select karen. Automatic sirf verified OS routing ke sath use karen.
3. Apna real target IP dalen aur Check selected network dabayen.
4. Windows interface/route aur intended remote endpoint ko khud verify kar ke Operator verified tick karen. Software ka successful ping akela proof nahi.
5. Save. Har page par apne towers/devices add karen.
6. Monitor all networks tick karen, phir Start monitoring. Pages ko dekhne ke liye switch kar sakte hain.
7. Connect tower radios mein dono endpoints select karen; optional upstream direction choose kar ke Save link.

The wizard creates named pages, not default devices, invented customer IPs or automatic connections. Saved existing page names/towers/devices remain intact.

## Routing boundaries
The software contains no internal router and applies no routes, NIC addresses, VLANs, VPNs, forwarding, firewall or radio configuration. Source binding is real where implemented: Windows IPv4 ICMP, IPv6 system ping and supported HTTP/TCP paths. IP/adapter selection alone is not proof of a specific gateway.

A laptop must already reach each management subnet through Windows/router/VPN configuration or suitable physically connected adapters. For overlapping IP networks, an unmanaged switch and a software checkbox do not create separation. Distinct source bindings still require correct OS path configuration and endpoint verification. Agents are not implemented.

SNMP source binding remains explicitly unsupported; a configured source makes that adapter unavailable instead of silently using another path. Use separately verified non-overlapping management routing or a supported HTTPS adapter. Firmware metrics/real WAN validation belong to Phase 5 and the pilot.

## Tests and evidence
Focused tests cover:
- Real-payload interface parsing and an actual Windows inventory check on Windows.
- Immutable source/verification snapshots and IP-family rejection.
- Duplicate-target ambiguity and distinct per-page sources.
- Five simultaneous pages with identical test targets, bounded shared workers, source capture, view switches and isolated history/towers.
- Unverified paths cannot become Online or create fake packet-loss samples.
- Background-page buzzer, cleanup protection, mobile status and telemetry source/result continuity.
- Atomic multi-page validation/save and wizard selection behavior.
- Stale route-check rejection and the absence of automatic verification.
- Reciprocal peer links, persistence, same-page guards and atomic cycle rejection.

Existing ping/buzzer/map/licence/mobile/retention regressions remain mandatory. Run pytest and compileall; the Windows workflow also records the existing 10/50/100/250 synthetic benchmark, launches frozen applications and checks installer/upgrade/uninstall behavior.

These tests prove the implemented isolation/scheduling behavior against fixtures and CI, not reachability of the user's five real networks. The user's interface addresses, gateway paths, Rocket firmware and physical Windows 10 laptop are not available in this environment. They remain field checks.

## Recovery and acceptance
Keep baseline v0.4.7 at commit 77301221050d8753dddefefd8df4c71dd317306a and its packages. Back up the full data directory before upgrades. SQLite schema remains version 3 and existing records are preserved.

Require focused and existing regressions, syntax/startup, synthetic load checks and a successful v0.4.8 Windows workflow. Do not label operator attestation as software-proven routing. The limited owner License Manager is still not full Admin Studio.

Next approved phase: Phase 5 device/Rocket M5/WAN intelligence. Actual unavailable hardware/API/firmware checks must be marked Blocked rather than guessed. Full Admin Studio's first test increment remains Phase 8.

