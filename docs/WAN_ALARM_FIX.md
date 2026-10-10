# v0.4.17 — Internet setup and delayed buzzer

Settings > Alerts & detailed history > Buzzer delay after confirmed fault: default 15 seconds; adjustable 0–300 seconds. Save alert / history settings. A fault must stay active through the delay before sounding. Recovery cancels the pending sound. Silence acknowledges the current incident. Consecutive ping failures still apply before the buzzer countdown. Status/history and desktop notifications continue to show faults immediately; this setting delays audible alarms only.

WAN setup > Use Cloudflare download-test setup supplies a bounded 1 MiB HTTPS download endpoint and Internet check. This is a single-connection throughput sample, not an Ookla capacity test; automatic tests remain off. Existing custom endpoints are changed only when this button is pressed. Upload requires your authorized receiver and its byte-count acknowledgement; this preset does not supply upload capacity measurement.

Inspect Internet route / adapters now inspects the external test endpoint instead of the modem management IP. Enter its displayed Internet next hop as the gateway only if it is the intended modem. Source IP must belong to this laptop. Verify the WAN-specific path and save before testing. Windows route parsing matches the selected source interface; missing PowerShell fails clearly.

Seven modems sharing a switch do not become separately routable just by entering seven ping IPs. If Windows selects another gateway, configure the intended Windows route/interface or ask your network administrator. The application does not alter Windows routing and never labels another modem's test as this modem's result.

Actual gateway/IP information and the exact user error are still needed to diagnose this physical network if the new route check reports a mismatch. Windows CI tests do not prove seven-WAN hardware operation.

Rollback: back up the complete app data folder, then reinstall v0.4.16. No database schema change is made. The old version ignores alarm_delay_seconds and returns to its prior immediate audible-alarm behavior.
