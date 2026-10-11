# Discovery v0.5.2 — all connected IPv4 networks and separate results

The existing Python/PySide6 application, ping, device records, SNMP access diagnostic, settings, monitoring and Windows credential vault remain in place. No database schema changes or example measurements are introduced. Existing version backup and pre-import database backup remain enabled.

## Use

1. Open Network Discovery. Choose **Scan all connected networks** without selecting an IP or subnet. The app refreshes connected IPv4 adapter detection in the background.
2. Review the detected adapter/subnet/source list and confirm that you own/administer every listed network or have permission. Denying confirmation sends no discovery probes. Remote ranges are not guessed or included automatically.
3. Every eligible connected subnet is scanned through its own detected local source IP. Subnets on the same interface are processed in sequence with at most four workers and the selected 1–20 host starts/second. Existing ICMP, interface-scoped ARP/neighbour evidence, optional DNS identity and optional safe TCP-connect methods are reused. Settings and routes are not changed.
4. **Found now** contains devices with response evidence at their check time. **Identified only** contains DNS/cache identities whose current reachability is unconfirmed. **All checked** also includes nonresponding/probe-error addresses; those remain unknown, not automatically offline. Finishing a scan opens Found now, even if its count is zero.
5. Tables include IP, timestamp, evidence method, subnet, adapter and source IP. Identical target IPs reached through different source IPs remain separate. Repeated evidence for the same IP/source updates its existing row. Filtering applies to all three views. CSV exports the active filtered view and escapes spreadsheet formulas.
6. Select results in the desired tab and **Add Selected Devices**. Import preserves the row's source IP, skips existing IP/source pairs, retains the current network page and makes the existing pre-import database backup. It never assigns physical topology or vendor type from an IP.
7. Stop cancels new starts, waits for bounded in-flight checks and retains completed observations. Revoking the permission checkbox also cancels. **Rescan** after an all-networks scan redetects networks and repeats the exact-plan confirmation. Manual subnet/range scan and its session-only timed rediscovery remain available. Timed rediscovery is disabled for all-networks mode; use explicit Rescan.

## Limits

- Connected subnets only: no complete Internet scan, guessed remote-station networks, internal routing or VLAN enumeration. A Windows/VPN route and separately authorized remote range are still needed for routed stations. IPv6 discovery is not included.
- Each subnet is limited to 1,024 total addresses and the combined plan to 8,192 host checks. Larger or invalid ranges are explicitly listed as **skipped / not scanned** before confirmation and after completion; the application never silently truncates them. Narrow a large subnet in manual mode.
- Identical CIDRs on the same interface are scanned once. Identical CIDRs on different interfaces retain their distinct sources. Overlapping networks that cannot be distinguished by source IP still require proper Windows routing/interface separation; this update cannot make them independent automatically.
- MAC addresses across routers, blocked ICMP/TCP, stale DNS/ARP and absent vendor assignments remain limitations. Found now is a timestamped observation, not a guarantee the device is still online later. Optional DNS/TCP increases scan time. Tests and CI are not physical acceptance of the user's laptop or radio.

## Validation

Tests exercise detection of multiple IP aliases/subnets, duplicate-subnet elimination, visible large-range skips, source/interface propagation, bounded cancellation before later networks, permission denial, background scanning without IP selection, progress, separate result views, per-source deduplication/import/backup, and active filtered CSV export. The existing discovery/alignment and application regression suites are retained. Windows CI additionally builds and tests the installer/portable runtime, installed startup, upgrade and data preservation.
