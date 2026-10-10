# Phase 7 — Customer GUI (v0.4.12)

## Delivered behaviour

The existing PySide6 application, monitoring engines, store/schema, map, ping and buzzer remain the foundation. No device records are replaced and no network routes are modified. The application opens on a new **Overview** while all prior pages retain their existing internal indices and actions.

- Page-scoped operations overview: configured, replying, attention and other/not-checked device counts; network/scope/running status; unresolved incidents and evidence; a bounded device list with detail access.
- Individual WAN cards: modem IP, router ping, independently observed Internet status, fresh verified interface traffic and separately labelled route-checked last-test throughput. Unconfigured/stale/missing values stay Unknown/Unavailable. Cards open the actual corresponding modem in Internet speeds, without starting a bandwidth-consuming test. Seven cards per overview page; additional WANs paginate. The existing seven-row speed panel and selected/all/cancel controls remain available.
- Empty first-network guidance: Add device, Add tower, Start monitoring. No sample IPs, network device records or fabricated rates are created.
- Simple controls by default. Advanced controls reveals routing/network management, history and detailed adapter views. Settings always exposes the real configuration/backup tools. This is a display preference, **not authorization or administrator authentication**. It never clears hidden configuration fields and never changes monitoring scope by itself. If all-network monitoring is already enabled, its control remains visible.
- Device edit starts with the common fields, with a separate advanced-fields expander. Existing hidden source, timeout, URLs, thresholds and coordinates are preserved when changing an ordinary field.
- Device details starts with ping/latency, service, applicable Internet/wireless status and collection age. Complete raw metrics/history/alignment tools remain behind an explicit expander. Long detail and adapter forms scroll; action buttons remain reachable.
- Grouped settings for appearance, alerts/retention and setup/backup/support. Dark/light theme and advanced-control preferences persist immediately; alert/history settings retain their existing explicit Save action. Detailed logs default to 48 hours, and unresolved/pinned incidents remain protected. Advanced retention policies use the existing real Performance dialog.
- Scrollable sidebar and overview, responsive two/three-column WAN cards, wrapped device/event action layouts, consistent typography/focus indicators and readable status text in addition to colours. Light-mode status colours meet a tested 4.5:1 contrast against white; the geographic map and measurement canvases deliberately retain a dark drawing surface.
- Branded, high-DPI-aware startup splash. Default app identity, icon and **Created by Zeeshan Rasool** bottom-right watermark are preserved. Customer-specific branding is reserved for authorized Admin Studio workflows in Phase 8.
- Keyboard: Ctrl+1 Overview, Ctrl+2 Map, Ctrl+3 Devices, Ctrl+4 Internet speeds, Ctrl+F device search. Normal Tab navigation remains supported.

## Files / review

UI implementation: `main.py`, `zee/gui.py`, `zee/customer_dashboard.py`, `zee/customer_view.py`, `zee/customer_theme.py`, `zee/professional.py`, `zee/mapview.py`, `zee/incident_dialog.py`, `zee/seven_wan.py`. Release/version files, the professional guide, Roman Urdu readme and packaging workflow are updated. Functional regression coverage is in `tests/test_phase7_customer.py`; existing regression tests are retained.

All existing tab numbers remain unchanged (Map 0, Devices 1, History 2, Topology 3, Events 4, Settings 5, WAN/Radio 6, Internet speeds 7); Overview is appended at 8. This preserves map/details/history navigation and older integration workflows.

## Acceptance and evidence

- [x] Existing ping/buzzer/page-isolation/retention/recovery/licensing/speed-test regression suite passes locally.
- [x] Functional interaction checks cover real WAN-card selection, keyboard navigation, preference persistence after restart, scope isolation, stale/missing evidence, incident acknowledgement, preservation of hidden advanced settings, pagination and responsive layout.
- [x] Manual offscreen visual review covers dark/light overview, 1360×790 and 980×650 logical windows, device/event/settings/speed/map views and scrollable detail/adapter forms. These are controlled layout fixtures; no customer hardware measurements are invented.
- [x] Application startup/shutdown smoke tests pass, including Qt scale factors 1.25 and 1.5 on the development host.
- [x] Baseline scheduling/cleanup benchmark runs for 10, 50, 100 and 250 simulated devices with the existing eight-ping-worker cap. The new overview does not read individual sample/measurement histories during each refresh; it uses cached observations and a bounded incident query.
- Windows CI additionally runs the native regression suite, frozen application/manager smoke tests and installer/upgrade/uninstall tests. Exact results and build commit appear in packaged `BUILD_INFO.json`, `windows-tests.xml`, `phase3-benchmark-windows.json` and `INSTALLER_TEST_REPORT.txt`.

A local synthetic 250-device run recorded approximately 0.14 seconds window construction, 141 MB cumulative process working set, 51 ms maximum check/cleanup heartbeat gap and 0.03 seconds background cleanup. The previous phase's comparable local cumulative working set was about 114 MB; theme/widgets add memory. These are cloud/development measurements, not a guarantee for the owner's old i5 PC. Benchmarks model short simulated calls, not maximum real network timeouts.

## Not verified / still pending

Physical Windows 10 display/DPI/driver behaviour, the customer's subjective usability acceptance, actual seven-modem WAN counters/routes and Rocket M5 firmware compatibility require the owner's real-network test. No claim of zero lag, confirmed physical fault, guaranteed line capacity or production readiness is made. Code signing and full commercial provisioning remain future work. Separate customer/package/branding administration is **Phase 8**, not the Simple/Advanced checkbox or the existing small licence issuer utility.

## Upgrade / rollback

Use Settings → Backup database before an upgrade and retain the backup separately. No database schema migration is introduced by Phase 7. Close the application before installing v0.4.12. Installer upgrade preserves configuration/data under the existing policy.

Baseline source commit: `5dff76ff4caf24194bbc5758b1ab08cd7e9f1a62` (v0.4.11). Git history preserves the old files; to roll back the application, install the preceding v0.4.11 build after closing v0.4.12. Prior Windows setup: https://github.com/meroobaba02-sudo/ZeeNetworkMonitor/actions/runs/38063694091/artifacts/11674460214 . Restore a backup through the existing verified restore workflow only if needed; theme/control preferences are additive and do not alter device records.

Next proposed phase: **Phase 8 — Zee Admin Studio**, customer/package management, entitlements, branding, licence administration, build profiles and audit controls. Start it only after owner approval.
