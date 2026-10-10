# Phase 2 stabilization — v0.4.6

Scope: preserve existing features; correct source-path wording, reconcile current user guides, and strengthen database recovery regression checks. Full Admin Studio, 48-hour retention and performance-engine changes belong to their later phases.

## Changes
- Source-bound labels now cover IPv4, IPv6 and network-page source settings without falsely calling every address IPv6.
- Queued restores are revalidated at startup before touching the active database or safety backup. Unsupported schemas, corrupted SQLite files and missing device tables are rejected. A rejected queue remains available for inspection; move restore.pending.sqlite3 away while the application is closed to resume the original database.
- Successful restores retain before-restore.bak and preserve credential/licence/mobile sidecars. These sidecars are not included in a database-only backup.
- Root README, Roman Urdu guide and Windows build guide describe the current artifacts and actual feature limits.
- Focused tests cover source labels and valid/invalid recovery. Existing ping, buzzer, map and telemetry tests remain regression gates.

## Baseline and rollback
Recover the previous release using commit aca5eede34f7486c0ce85d96f9a40b0cc5ac12ee and v0.4.5 packages. Back up the complete data folder before upgrades. This stabilization does not change SQLite schema version 3. Use matching versions for future schema changes.

## Acceptance
Run pytest with QT_QPA_PLATFORM=offscreen and compileall. Require the Windows workflow to pass frozen startup, runtime packaging and installer checks for this commit. Real Windows 10, live Rocket metrics, speaker playback and old-laptop performance remain field checks.

## Usability and next phase
Customer and owner workflows must stay simple: everyday controls visible, expert settings separate. The full Admin Studio test executable is planned after the first small Phase 8 increment, with customer/package setup before branding/licence/build expansion. Phase 3 next addresses configurable monitoring limits, responsiveness and 48-hour detailed-record retention with separate incident policy; user approval is required before that phase.
