# Monitoring-only development build — v0.4.18

Admin Studio and licensing work is paused at the owner's request. Current CI builds/publishes only Zee Network Monitor Setup and portable runtime. No Admin Studio or licence manager package is produced.

The existing unprovisioned owner-preview runtime already needs no activation. This release hides its Licence / activation and signed-customer updater controls. Licence status validation, package permissions, startup activation gates and periodic licence timer remain unchanged. If an issuer/profile is provisioned, activation controls and enforcement remain available. Existing licence/Studio files are preserved. Monitoring, map, WAN, wireless, CCTV, mobile and reports remain available. Credentials still use Windows DPAPI. No Windows routes/firewalls are changed.

This mode applies to the normal unbound monitoring development build. Existing signed customer packages with compiled issuer/profile requirements continue their original signature/activation checks. These historical packages are not current deliverables. No licence bypass is added.

Upgrade uses the same app ID and normal LOCALAPPDATA/ZeeNetworkMonitor data folder. A separately branded customer profile uses a different folder: this build does not automatically import that folder. Back up the complete data folder before upgrading. The database schema is unchanged. Roll back by reinstalling v0.4.17 with the complete backup; do not delete licence/Studio records.

First checks: ping and 15-second buzzer delay; WAN external-route inspection/download setup; monitor refresh and CPU/RAM behavior. A correct per-modem Windows route remains necessary. Upload capacity requires an authorized receiver. Cloudflare preset measures bounded download throughput only.

The scheduler/heartbeat/storage benchmarks use simulated probes on CI hardware. They do not prove performance on your laptop or actual seven-WAN/radio network. Send the exact error text/screenshot and exported pilot report for physical issues.
