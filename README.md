# Zee Network Monitor

Windows desktop network monitor for towers, radios, WAN links and camera services. Current customer GUI release: **0.5.2**, monitoring development owner preview; existing licence enforcement unchanged.

Download the setup or portable package from a successful [Windows Actions run](https://github.com/meroobaba02-sudo/ZeeNetworkMonitor/actions). No Python is needed on the customer's laptop. Keep the entire portable folder together.

Existing features include saved network pages, grouped tower maps, background ping, buzzer controls, history, configurable SNMP/HTTPS telemetry, WAN checks, paired read-only mobile access and an offline licence issuer. Firmware metrics require verified configuration and real-device testing. Selected-page monitoring is the default; optional all-network monitoring uses shared worker limits and operator-verified paths. The app does not create routes.

The separate ZeeLicenseManager utility issues licences. Separate Zee Admin Studio now provides the Phase 8.1/8.2 local owner workflow. Customer licensing enforcement requires an owner public key in the customer build. Never distribute the private signing key.

Windows CI tests packaging on Windows Server 2022. Physical Windows 10, real five-network routing, Rocket M5 readings, Android and old-laptop performance remain unverified.

Start with README_RomanUrdu.txt and docs/PROFESSIONAL_GUIDE.md. Current stabilization details: docs/PHASE2_STABILIZATION.md. Older audit/test documents describe their original versions and are historical evidence.

Phase 3 adds bounded configurable checks, coalesced refresh, device pagination, process CPU/RAM display, background 48-hour detail cleanup, protected/pinned alerts and archive controls. See docs/PHASE3_PERFORMANCE.md for policy and synthetic measurements.

Phase 4: Network setup / paths reads real Windows source addresses, checks reachability asynchronously, and keeps page-specific snapshots/history isolated. Connect tower radios creates explicit peer/upstream links with cycle/page guards. See docs/PHASE4_NETWORKS.md.

Phase 5: real source-bound SNMP GET, model/firmware records and explicit profile attestation, validated wireless metrics, precise Counter64/reboot guards, verified WAN counter-interface selection and changed-endpoint invalidation. Hardware compatibility is blocked until actual device evidence is available. See docs/PHASE5_INTELLIGENCE.md.

Phase 6: evidence-based possible upstream/endpoint fault correlation, ICMP/service contradictions, independent WAN failures, persistent incident start/evidence/recovery, acknowledgement/notes/pins/CSV, cautious downstream notification reduction and protected retention. Schema 4 upgrade backs up schema 3 automatically. See docs/PHASE6_INCIDENTS.md.

Phase 6.1: a dedicated Internet speeds panel separates per-modem WAN interface traffic from sequential, next-hop-checked HTTPS download/upload tests. See [setup and limits](docs/PHASE61_SEVEN_WANS.md). Seven shared-LAN IPs alone cannot select seven Internet paths.

Phase 7: customer overview, responsive WAN cards, simple/advanced display controls, persistent dark/light themes, keyboard shortcuts and scrollable configuration/detail forms. See [customer GUI guide and acceptance evidence](docs/PHASE7_CUSTOMER_GUI.md). Admin Studio remains Phase 8.

Phase 8.1 adds a separate ZeeAdminStudio.exe owner/viewer application with local authentication, customer/package/profile records, protected signing, audit checks and encrypted backups. [Scope and remaining Phase 8.2 work](docs/PHASE81_ADMIN_STUDIO.md). Existing customer monitoring and the legacy issuer utility remain available.

Phase 8.2: signed v2 package permissions/device caps, customer branding and pinned profiles, owner Windows customer build runner, artifact-verified release history and signed offline installer verification. [Owner workflow, toolchain requirements and remaining online work](docs/PHASE82_CUSTOMER_BUILDS.md). Default download remains owner evaluation until your own public issuer/profile is provisioned.

Phase 9 adds a separate Admin Studio Windows installer, validated previous-licence recovery, safer mobile certificate/pairing lifecycle and native customer installer acceptance. See [Phase 9 guide](docs/PHASE9_INSTALL_RECOVERY_MOBILE.md). Physical network and phone testing belongs to the Phase 10 pilot.

Phase 10.1 delivers Settings > Real-network pilot / support report, 18 operator-recorded scenarios, opt-in CPU/RAM/storage/heartbeat capture, privacy-safe JSON export and an explicit commercial-release review gate. Actual hardware acceptance has not been performed. See [field pilot guide](docs/PHASE10_REAL_NETWORK_PILOT.md).

Internet route inspection and delayed buzzer fixes: [route/alarm fix guide](docs/WAN_ALARM_FIX.md).

Admin Studio/licence work is paused. Current CI builds and publishes only Network Monitor. See [monitoring-only guide](docs/MONITORING_ONLY.md). Historical owner tools remain in source for later work.

NOC GUI redesign: [screens, verified behavior and limitations](docs/NOC_GUI_v050.md).

Discovery and measured alignment v0.5.1: [beginner launch, controls, authorization and limits](docs/DISCOVERY_ALIGNMENT_v051.md).

Discovery across connected networks v0.5.2: [controls, separate results and limits](docs/DISCOVERY_ALL_NETWORKS_v052.md).
