# Zee Network Monitor Professional 0.4.0 — owner evaluation preview

Created by Zeeshan Rasool

## Install and first run (Roman Urdu)

Setup EXE double-click karen. Desktop aur Start Menu shortcut banenge. Admin/Python/Git install karna zaroori nahi. Purana app pehle close karen. Data %LOCALAPPDATA%\ZeeNetworkMonitor mein rehta hai; upgrade/uninstall ise delete nahi karta. Portable ZIP alternative hai: Extract All, phir ZeeNetworkMonitor.exe; poora folder saath rakhen.

1. Manage networks → Add network. Apna naam den. Har network ka alag page ban sakta hai. Sirf selected page monitor hota hai; page badalne par Start monitoring dobara dabayen.
2. Router: Add device → naam/IP/type Router. Management URL optional, jaise http://device-ip/ (apna IP dalen). Double-click se browser aur details khulte hain. Browser login manually karen.
3. Tower: Add tower → naam → Save. Har naya tower alag position par aata hai. Name box drag karen. Tower button se rename/GPS/notes. Map options → Remove selected tower radios ko standalone rakhta hai.
4. Rocket M5: tower select → Add radio. IP, left/right dish side, role aur wireless peer configure karen. Ping aur wireless quality alag hain. Gray quality ka matlab telemetry Unknown hai. Double-click → Secure settings se password/read-only SNMP community save karen.
5. Camera: device type CCTV, service URL HTTP/HTTPS ya RTSP. Service status alag nazar aata hai. Open stream compatible external player kholta hai; continuous previews nahi.
6. WAN / Radio page par device select → Configure adapter. Neeche profile instructions parhen. Test Speed Now manual test hai. Automatic speed default OFF hai.
7. Phone: Settings → Mobile HTTPS dashboard. PC LAN IP enter → Enable → local certificate/fingerprint verify aur phone par trust setup → New pairing code. Phone browser mein displayed HTTPS URL kholen aur code enter karen. Yeh responsive web dashboard hai, native APK nahi.
8. Data: Settings → Backup database. Restore backup and close aglay launch par restore karta hai, safety backup rakhta hai. Secret vault doosre Windows account/PC par portable nahi. Page Export/Import secrets aur history transfer nahi karta. Imported/duplicated devices disabled aate hain.

## Pages and routing

Add/edit/rename/reorder/duplicate/archive/restore/delete/export/import pages are implemented. Radio/tower/parent/peer references are scoped to their page. Deleting a page deletes its inventory and saved credentials after confirmation, while measurement history is retained in the database. Unarchive through Manage networks. Do not delete your last active page.

A page is not a network isolation boundary. Source IP binds Windows IPv4 ICMP via IcmpSendEcho2Ex, IPv6 system ping, and HTTP/TCP sockets. It must be an address assigned to the laptop. Literal matching-family targets are required for source-bound ICMP. Adapter name/gateway are notes: Windows routes are not modified. When adapter/gateway is entered but not verified, new probes are blocked. Overlapping subnets require a correctly configured route/VPN or separate agents (agents not included). SNMP source binding is not supported and is explicitly blocked if a source IP is selected. Do not merge separate production networks on an unmanaged switch merely to monitor them.

Only selected page is polled; other mobile pages say Not monitored. Schedules are per device; current page can be manually checked or started/stopped. Concurrent monitoring of different pages is not implemented. Existing ping and buzzer controls are preserved. Ping no-reply does not prove a physical fault.

## Wireless adapters and alignment

Supported integration methods: none, snmp (read-only SNMPv2c GET), https-json (read-only GET). Both require firmware_verified=true. There is NO bundled claim of an airOS-specific firmware profile or automatic discovery/login. Obtain and verify the actual device firmware's documented OIDs/API first. Unsupported fields remain unavailable. No SSH commands, reboot, router configuration or SNMP SET.

SNMP: store community in the masked protected field; set allow_v2c=true only for a trusted management network (v2c transmits community unencrypted). Numeric OIDs in oids: metric → {"path":"numeric OID","scale":1}. Use the device's read-only community. SNMPv3 is not implemented.

HTTPS JSON: url must use HTTPS and match device.host exactly. The password is sent only to that configured host, using Basic authentication when supplied. System certificate validation remains enabled; no global bypass and no redirects. fields: metric → {"path":"nested/key","scale":1}. API mapping must match a documented compatible endpoint. This is an integration adapter, not a ready-made universal airOS login.

Metrics: signal_dbm, noise_dbm, snr_db, tx_ccq, rx_ccq, tx_mbps, rx_mbps, frequency_mhz, channel_width_mhz, uptime_s, ethernet_up, wireless_up, cpu_pct, memory_pct, in_octets, out_octets, counter_epoch. Map exposed enum values to 0/1 only if the firmware matches those meanings; arbitrary SNMP interface state enums need a compatible adapter conversion. Unknown fields are rejected.

Quality 0–10 is the minimum available normalized signal/CCQ component, with configurable good/poor thresholds. It is explicitly a partial-metric assessment when only one component exists. No metric → Unknown; confirmed wireless_up=0 → Critical; stale → Unknown. Data-rate and packet-loss contributions to the score are not implemented. Ping status is separate. Detail graph shows recorded quality history, best recent score, optional improvement beep, local/peer names and valid GPS distance/bearing. Elevation/terrain guidance is unavailable. Technician physically adjusts dish.

## WAN measurements

Router ping, external HTTPS test, traffic rate and controlled throughput are separate observations. wan_verified must be true only after verifying that source/OS routing selects the intended WAN. The application cannot independently prove a load-balanced router's policy. No verification → Not independently measurable.

External check: configure internet_url (HTTPS) and internet_marker (expected response text). Exact 200 plus matching text means this configured external check passed; router ping alone does not prove Internet. Timeout/TLS errors remain Unknown instead of manufacturing an outage reason.

Counters: map verified WAN in_octets/out_octets and preferably counter_epoch (reset/discontinuity indicator). Two valid increasing samples yield Mbps. Counter reset/wrap/epoch change resets baseline. In/out direction depends on selected router interface. This measures traffic usage, NOT available speed/capacity. It does not consume a download test's data allowance.

Controlled download: configure speed_url to an authorized fixed test file on the intended path. Defaults speed_mb=1, speed_seconds=5, daily_mb=10, automatic_speed=false, speed_interval=900. Requests have bounded size/duration/socket timeout; total includes connection overhead. Optional rate_cap_kbps is a local download-read throttle, not a router traffic shaper (TCP buffering can briefly exceed it). Failed/interrupted tests conservatively reserve their full maximum bytes from the daily budget. DNS/system/TLS delays can extend total elapsed time beyond the transfer duration. Measurements are bounded throughput estimates, not a standardized ISP benchmark. Controlled upload tests are not implemented; upload traffic is available from configured counters.

Profile min_download_mbps triggers a warning only for controlled download results; loss_warning_pct uses up to 30 ping samples in the last five minutes. Warning colours/alerts are available; latest controlled downloads are ranked with a same-method/limits comparison note; session counter-byte totals are not implemented. Graph/statistics show up to 1,000 measurements from the last 24 hours and can include differing methods; inspect the method label before comparing.

## Credentials and exports

Windows current-user DPAPI encrypts password/community values in credentials.dpapi.json. No plaintext fallback on other systems. Editing a password blank preserves it; Delete all saved credentials removes it. Passwords are never included in device/page JSON, CSV, diagnostics or customer builds. URLs must not contain user:password syntax. Do not paste API tokens into URL queries, notes or profile mappings. Device web pages open without injected credentials. Authentication failures are reported without raw credentials or response bodies.

## Owner licensing setup (required before commercial distribution)

This build is an owner evaluation: no issuer key has been provisioned and existing monitoring remains usable. It is NOT an already locked customer product. The verification/enforcement path is implemented and signature/tamper/expiry/wrong-PC rejection are tested with temporary test keys.

1. On your Windows owner PC, open the separately supplied ZeeLicenseManager.exe.
2. Initialize owner key. It is generated locally and protected using that Windows account's DPAPI. No private key is generated in GitHub Actions, committed or included in any distributed artifact.
3. Export issuer-public.json. Upload ONLY that public file to repository assets/issuer-public.json and build again. The customer build then requires a valid signed licence at startup. Public key file is distributed with the compiled app; it is not an anti-tamper root of trust against a skilled local attacker. Production hardening/code signing remains necessary.
4. Customer Settings → License shows hashed machine fingerprint. It is not transmitted automatically. Copy it to owner manually. Generate one-PC licence with customer, edition, days (0 perpetual), reference. Import the signed JSON on customer PC. A supplied public key must match this owner key.
5. Export encrypted recovery PEM from manager using a strong password you enter locally. Keep PEM and password separately and privately. DPAPI key otherwise cannot be recovered after owner Windows reinstallation.
6. Deactivate deletes the local licence. Transfer/recovery is a manual owner decision and signed reissue. Offline deletion cannot revoke a copied licence on an old offline PC. Exact global one-PC-at-a-time transfer enforcement needs an activation/revocation service, not included. Current fingerprint survives ordinary RAM/network changes but changes after Windows reinstall; owner must reissue.

Admin tool is separate and useless for forging another issuer's licences without its private key. Do not send it/recovery material to customers. The repository remains public under its existing licence; practical packaging is not absolute copy protection. No Authenticode certificate is available: installer/EXEs are unsigned and Windows may show SmartScreen prompts. There is no online activation service or clock rollback hardening.

## Mobile security and limits

The opt-in PC service uses HTTPS/TLS 1.2+, random one-time five-minute pairing codes, rate limiting, authenticated Secure/HttpOnly/SameSite cookies, hashed persistent revocable tokens (30 days) and read-only endpoints. No device passwords are sent to the phone. Pairing is required to see network data. Stop the service or revoke all paired phones from desktop. Notifications are desktop only; no mobile push/native Android APK, per-device token revocation UI or remote configuration/reboot controls.

The local self-signed certificate needs explicit trust and fingerprint verification on your phone. Certificate is valid for the configured IP at generation time. Changing IP may require reissuing that local certificate. A production trusted certificate/reverse proxy or VPN certificate setup is deployment work. Remote access is VPN-only architecture: configure your own VPN outside the app, explicitly bind to the PC VPN address and retain authentication/TLS. VPN installation, relay hosting, automatic public access and firewall/port forwarding are not included. No automatic external telemetry or identifier transmission.

## Tests and remaining commissioning

Automated coverage: baseline ping/buzzer/persistence, multiple tower placement, page isolation/import IDs, secret omission, source-family validation, URL rejection, quality and counter reset logic, signature tampering/expiry/wrong PC, actual local HTTPS pairing/auth/replay/expiry/revocation, HTTP service check separation, obsolete worker generations, local UDP SNMP protocol fixture, controlled HTTPS download and external endpoint checks, compiled MIB runtime loader. Windows-only tests cover DPAPI roundtrip and IPv4 source-bound loopback. CI builds and starts both frozen apps, runs the installer silently, verifies desktop/Start Menu shortcuts and uninstall/config preservation. Check BUILD_INFO.json and the Actions run for actual success.

Not performed: user's Windows 10 hardware/DPI/speakers, real Rocket M5/airOS firmware or radio metrics, actual five-WAN routing/performance, real camera RTSP stream/ONVIF, physical alignment, Android browser trust/pairing, long-duration or thousands-of-devices load test. ONVIF is not implemented. Large histories still have some synchronous SQLite queries; practical scale depends on machine/resources. This preview is testable but does not satisfy all final acceptance criteria of the complete master specification.


## v0.4.1 usability phase
Dashboard now shows selected-page ping, wireless, WAN Internet and alert counts. Stale telemetry stays unknown. Alerts count affected devices, not separate incident types. Settings > Help / About explains first-run setup. Event filtering includes tower, device, date and search before the display limit. WAN history shows local-calendar-day and application-session measured sample min/mean/max, keeping traffic estimates separate from controlled tests. These are sample statistics, not time-weighted averages or transferred-byte totals. Daily graph displays the latest 1,000 samples.


## v0.4.2 wireless preparation
SNMP v1 and v2c are selectable; existing profiles keep v2c. airOS 8 official guide documents v1. Both communities are unencrypted; explicit trusted-network consent required. Adapter dialog has method/version/poll controls overriding those JSON fields. Firmware-verified numeric OIDs still required; Prism 5AC XC.v8.7.11 and AF-5XHD v1.4.0 are identified from owner screenshots but no live protocol compatibility or metric OIDs are verified. No firmware/configuration changes are sent to radios. Optional rate_quality_enabled adds measured TX/RX rates to quality with configurable rate_good_mbps/rate_poor_mbps; default OFF. Alignment graph can select quality, signal, SNR or CCQ; stale readings suppress feedback. Last-hour best values are sampled records, not physical dish alignment.


## v0.4.3 WAN controls
WAN / Radio > select a WAN > WAN setup / routing provides check endpoints, source IP, polling interval, test size/duration, daily budget, read cap, automatic-test switch and warning thresholds. Route inspection runs asynchronously and displays ipconfig and route print plus OS-selected local source; it changes no routes and sends no UDP data. This does not prove WAN independence: verify actual interface/gateway and external path. Source changes clear WAN path attestation; save and reverify. External endpoint requires HTTPS and expected response text. HTTPS response latency includes connection/TLS/server time, not pure ICMP latency. WAN status independently uses external result; router ping and low fresh throughput/HTTPS latency can degrade an otherwise online WAN. A successful speed test does not clear an existing external-Internet incident. Daily history selector separates controlled downloads from traffic estimates; capped tests excluded from fastest/slowest ranking. Upload remains verified interface traffic estimate only, not an active upload capacity test. Physical five-WAN routing and firmware tests remain pending.
