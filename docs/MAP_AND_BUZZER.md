# v0.2.1 — map dashboard and fault buzzer

The desktop now opens on the map. The design follows the approved dark navy/emerald preview with left navigation, four health cards, colored device markers/parent links, a selected-device panel, measured history, a WAN list and recent events.

The background is an **offline illustrative schematic**, not satellite imagery or a GPS map. There are no default city/station names. Only user-added devices are labeled, and the user can drag a marker to save a custom position. Map X/Y fields are percentages, not latitude/longitude. Roads/river are decorative; actual radio hops are user-defined parent links. No example devices, IPs or live results are seeded. Additional sites and devices work without Internet map requests or API keys.

Click a marker for Ping, History and Edit. Wheel or +/− zoom; drag empty space to pan; Reset restores the view. Map position changes preserve in-flight probe results. Existing schema-v1 devices remain compatible: absent position fields default to automatic layout.

**Buzzer ON/OFF** is always visible in the header and saved immediately. Windows plays a bundled WAV asynchronously in a loop through the laptop sound output. A repeated no-reply threshold or high-latency alert starts the alarm when per-device alerts are enabled. Silence acknowledges the current incident(s). A new device fault, a warning becoming an outage, or a new failure after recovery sounds again. Recovery, disabled/deleted devices, stale/unknown observations and application close stop the alarm. Stop monitoring silences current incidents. Buzzer OFF mutes all alarm audio without removing the visual device state. Settings includes a 1-second sound test. Windows audio output, physical speakers/headphones, mute and volume still need testing on the user's laptop; CI tests verify control logic, not audible sound from hardware.

No-reply is not a confirmed physical fault. Remote agents, router/radio telemetry and independent five-WAN performance remain outside this release.

Tower icons are built-in: select Rocket M5 / wireless radio as the device type. No image upload/download is needed. WAN templates have no default location. Existing user-entered location labels are retained and editable.
