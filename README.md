# Zee Network Monitor

Windows desktop network monitor for towers, radios, WAN links and camera services. Current device/WAN release: **0.4.9**, owner-evaluation preview.

Download the setup or portable package from a successful [Windows Actions run](https://github.com/meroobaba02-sudo/ZeeNetworkMonitor/actions). No Python is needed on the customer's laptop. Keep the entire portable folder together.

Existing features include saved network pages, grouped tower maps, background ping, buzzer controls, history, configurable SNMP/HTTPS telemetry, WAN checks, paired read-only mobile access and an offline licence issuer. Firmware metrics require verified configuration and real-device testing. Selected-page monitoring is the default; optional all-network monitoring uses shared worker limits and operator-verified paths. The app does not create routes.

The separate ZeeLicenseManager utility issues licences. Full Zee Admin Studio is planned for Phase 8; it is not included yet. Customer licensing enforcement requires an owner public key in the customer build. Never distribute the private signing key.

Windows CI tests packaging on Windows Server 2022. Physical Windows 10, real five-network routing, Rocket M5 readings, Android and old-laptop performance remain unverified.

Start with README_RomanUrdu.txt and docs/PROFESSIONAL_GUIDE.md. Current stabilization details: docs/PHASE2_STABILIZATION.md. Older audit/test documents describe their original versions and are historical evidence.

Phase 3 adds bounded configurable checks, coalesced refresh, device pagination, process CPU/RAM display, background 48-hour detail cleanup, protected/pinned alerts and archive controls. See docs/PHASE3_PERFORMANCE.md for policy and synthetic measurements.

Phase 4: Network setup / paths reads real Windows source addresses, checks reachability asynchronously, and keeps page-specific snapshots/history isolated. Connect tower radios creates explicit peer/upstream links with cycle/page guards. See docs/PHASE4_NETWORKS.md.

Phase 5: real source-bound SNMP GET, model/firmware records and explicit profile attestation, validated wireless metrics, precise Counter64/reboot guards, verified WAN counter-interface selection and changed-endpoint invalidation. Hardware compatibility is blocked until actual device evidence is available. See docs/PHASE5_INTELLIGENCE.md.
