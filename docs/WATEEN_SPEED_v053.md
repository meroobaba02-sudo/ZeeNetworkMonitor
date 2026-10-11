# In-app download and upload speed tests — v0.5.3

Internet Monitor already had independent route-checked throughput workers, but upload required a custom receiver returning JSON `received_bytes`. The new ready setup supports Cloudflare's documented speed-test POST endpoint without weakening custom receiver acknowledgement checks.

## Wateen setup

1. Open Internet Monitor. Add/edit your Wateen modem if absent (name Wateen; gateway/ping IP 58.27.163.137).
2. Open its Setup / Details and choose **Wateen setup: laptop 58.27.163.141 / gateway 58.27.163.137**.
3. Confirm the WAN source/gateway checkbox only if this matches your connected laptop adapter, then Save.
4. Choose **Start Test**. Download and upload run in background; Stop Test cancels. Results and measured history appear in the app. No PowerShell commands, browser speed test or custom upload server are required.

The preset fills app settings only; it never changes Windows IP addresses or routes. It uses up to 8 MiB download + 2 MiB upload per test, 30 seconds per transfer, a 200 MiB daily test budget and no read-rate cap. Automatic tests remain off. Other WANs can use the generic download + upload setup with their own laptop source/gateway.

## Evidence and limits

- Each actual TLS socket verifies its Windows source/interface/next hop before sending a speed payload. A wrong gateway produces an error, not a reading attributed to Wateen. If the source is not locally assigned the connection fails.
- Results are single-connection HTTPS throughput to Cloudflare, including response/transfer time. They are not Ookla's algorithm or a guarantee of maximum ISP capacity. Small transfers may underestimate fast connections. Background traffic and server/network conditions affect measurements.
- Public endpoint failures, timeouts, cancellation or rejected responses yield unavailable results. Upload failure after successful download retains download with an upload explanation.
- This is an active test, not continuous passive traffic. Interface traffic and test throughput remain separate fields. Automatic intervals have a 15-minute minimum and consume data.
- Custom upload URLs retain the exact-byte JSON acknowledgement requirement; only the exact `https://speed.cloudflare.com/__up` URL permits Cloudflare completion semantics. Firmware/SNMP settings are unrelated and unchanged.
- Unit/GUI tests use fixtures; Windows CI tests packaging and launch. These do not prove the user's physical Wateen speed. No measured Wateen value is included in this build.

Primary API documentation: https://github.com/cloudflare/speedtest and https://github.com/cloudflare/worker-speedtest-template (POST response after receipt of the complete body).
