# Phase 6.1 — Seven Internet modems (v0.4.11)

Open **Internet speeds**. Seven empty slots are visible; Add modem creates a real configurable WAN device on the selected network page. More than seven connections are supported. No sample IP addresses or copied default-route speeds are supplied.

## Simple setup

1. Add each modem: give it a name and its real LAN management IP. Ping checks confirm management reachability only.
2. Counter adapter: configure the modem's supported read-only SNMP or HTTPS JSON profile. Record the actual model/firmware, verify the mapping, map `in_octets` and `out_octets` to the actual WAN interface (not its LAN switch port), and preferably map uptime/discontinuity counters. WAN setup names and verifies that interface. Start monitoring; two fresh samples yield independent live download/upload **usage** in Mbps. Unsupported modem counters show Unavailable.
3. WAN setup: set an authorized HTTPS download endpoint, optional authorized upload receiver, data/time limits, daily budget, local source address where applicable, and the actual modem **Internet gateway IP**. Verify the existing Windows path. No route, adapter or default gateway is changed by the application.
4. Test selected or Test all. All tests run sequentially. Cancel stops further queued tests and requests cancellation of the current transfer. HTTPS socket operations can take up to the configured timeout to stop. Failed/cancelled tests retain their full reserved budget.

The modem models, LAN addresses and laptop routing are not yet supplied, so production hardware/counter compatibility and all seven Internet paths remain unverified.

## One switch / one subnet

Seven modem management IPs on one switch do **not** give a laptop seven independently selectable Internet paths. Binding a laptop source IP alone does not choose a different modem next hop. Existing correctly configured Windows routing/interfaces or a supported per-WAN router/agent are needed. Most ordinary setups select one default Internet gateway; tests for the other six will be blocked rather than report that default connection seven times.

Each test connects using certificate-validated TLS, reads the actual socket's local and remote IPs, then calls Windows `Find-NetRoute` read-only for those exact addresses. Its next hop must equal the configured modem gateway before any test payload is sent. The checked socket cannot silently reconnect. Upload opens and checks its own socket too. This records the OS route at test start; it cannot prove a path beyond an upstream load balancer or prevent routing changes during transfer. Linux independent tests are unavailable. No commercial Ookla executable or unofficial FAST API is bundled.

## Live usage versus speed tests

Live rates use verified WAN interface byte deltas / monotonic time, with reset/reboot/stale baseline checks. They represent current total interface traffic, not maximum purchased Internet capacity. Two matching samples are necessary. Missing/stale values remain Unavailable.

Manual rates are end-to-end controlled HTTPS throughput to the chosen server. Small capped transfers, server load and connection/TLS time affect the result. A read-rate cap constrains the download measurement; it is not a guaranteed wire-bandwidth cap. The last successful route-checked test remains visible with its time and age; it is not represented as live traffic. Test rows and live rows are separate. Browser FAST/Ookla buttons use the laptop's current connection; no browser result is attributed to a modem.

## Authorized upload receiver contract

Configure only an endpoint you operate or have permission to use for speed-test uploads. It must accept an `application/octet-stream` POST with a Content-Length (1–16 MiB limit), consume the full body, then return HTTP 200 and JSON such as `{"received_bytes":1048576}` for a 1 MiB test. The integer must equal the actual full byte count. Redirects, rejection, malformed/incorrect acknowledgements, deadline expiry and cancellation produce no upload Mbps. No device credentials are sent to this receiver. Download + optional upload maximum bytes are reserved together against the modem's daily test budget before a worker starts; protocol overhead is outside the application payload budget. Automatic tests stay off by default.

## Validation

Local automated coverage includes real TLS upload/acknowledgement fixtures, wrong-gateway rejection before payload, checked-socket reuse, independent display cells, sequential batch/cancellation, combined data-budget limits and stale live readings. Windows CI also runs the actual read-only Find-NetRoute loopback API, existing interface inventory and installer/upgrade/uninstall checks. These checks do not substitute for the owner's seven-modem physical network test.
