# Phase 8.2 — signed packages and customer build workflow (v0.4.14)

This release implements the offline/local Phase 8.2 workflow. It does not implement a hosted activation/revocation service, automatic downloads, code-signing certificates or remotely attested build results. The default downloadable monitor remains an owner-evaluation preview; real customer releases need the owner's own issuer and signed profile.

## Working modules

| Area | Actual behavior |
|---|---|
| Packages | Studio issues version-2 Ed25519 licences containing features, device cap, customer ID and optional profile ID |
| Client enforcement | Signed licence grants intersect with signed build ceilings; cap is the smaller limit. Invalid/expired licences deny workers. Saves, atomic network imports, ping submission, telemetry/speed submission, report export and mobile startup are guarded |
| Existing records | Records are retained. At most the first saved records within the global cap are eligible; disabled/archived records still count. Disallowed device types and over-limit records show Package restricted. Deleting records releases slots |
| Branding | Profile signature is verified against the bundled owner public key. App title, desktop header/logo, splash, tray name, footer watermark and customer installer names use profile branding |
| Customer build | Studio prepares signed public inputs, starts a separate Windows runner with a selected trusted source checkout/toolchain, and records results after artifact verification. Runner uses a disposable copy, runs regressions, builds and launches EXE, audits runtime files, produces portable ZIP and optional Inno Setup installer |
| Release/version history | Successful build-result reports are imported only by owners after verifying profile signature, current issuer, customer association, artifact filenames, sizes and SHA-256 hashes. Read-only viewers can inspect history |
| Offline updates | Studio signs an installer manifest for a recorded installer release. Activated customer app verifies issuer signature, exact profile, newer semantic version and installer hash/size; operator closes the app and runs the installer manually |
| Separation | Customer installer AppId/install folder and default data folder are derived from profile ID. Studio keys/database remain separate. Client builds contain only public verification material |

Feature identifiers: monitoring (required for all device checks), map, wan, wireless, cctv, mobile and reports. WAN/radio/CCTV monitoring permissions follow configured device category; they do not attest physical device identity. Generic monitoring includes basic reachability/service checks. The product is not a tamper-proof billing system against a user who can modify executable code or impersonate a device category. No perfect anti-copy protection is promised.

## Simple owner workflow

1. Extract the complete `ZeeAdminStudio-Owner` ZIP, including any nested ZIP. Run the EXE with `_internal` beside it. Existing owner data and credentials are preserved.
2. If upgrading an existing issuer, import its encrypted recovery PEM before initializing a different issuer. Keep all private keys/backups/passwords private.
3. Create/edit customer, package and profile. Set features, device limit, app name, watermark and optional PNG logo.
4. Select profile → **Prepare signed customer build** → choose a new empty input folder. Studio writes public signed `customer-profile.json` and `issuer-public.json` plus instructions. These files contain customer identity/branding but no signing secret.
5. **Builds / releases → Run Windows customer build**. Choose the trusted source checkout, prepared inputs, empty output folder, Python interpreter with pinned dependencies, and optionally Inno Setup's ISCC.exe. Selecting source/interpreter explicitly authorizes executing that local build toolchain. Source must match the current runner release. Never select an untrusted checkout/interpreter.
6. Review `build.log`, `tests.xml`, `build-result.json`, portable ZIP and optional installer. Successful results are recorded automatically while owner session remains valid. If the 15-minute session expired, sign in and use **Import verified build result**; output files must stay beside the report.
7. Customer exports their activation request. Issue a licence with that same profile selected, then send installer and licence to that customer yourself. A profile-bound customer build rejects legacy v1 licences, another customer's licence and licences without its matching profile ID.

Only the owner build computer needs Python/build tools. The customer runtime and Studio EXE require no manual Python installation. This phase does not bundle a compiler or silently install development tools. On an owner Windows build PC with Python 3.11 x64, from the downloaded source checkout:

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

Select `.venv\Scripts\python.exe` in Studio. Install Inno Setup 6 separately only if an installer is needed. Cancel the optional compiler picker for a portable-only build. No installer-update manifest can be generated from a portable-only result. Source download: GitHub repository → Code → Download ZIP → extract.

A CLI equivalent is available in `admin/customer_build.py`; run with that interpreter and arguments `--source`, `--profile`, `--public`, `--output`, and optionally `--iscc`. No shell interpolation or private key is involved. Build steps have timeouts and the UI runs the runner through QProcess. Studio cannot close during an active build; wait for completion. Runtime package audit rejects source/private-key/database files and unreviewed assets.

## Activation, ceilings and recovery

New v2 licences work with this v0.4.14 client. Older v0.4.13 clients reject v2, so keep the old utility/v1 issuance for legacy clients until upgrading them. Unprofiled owner/public-key builds still accept v1 licences with their previous broad permissions. Do not treat a legacy licence as a package-limited commercial entitlement.

A package increase requires both an appropriate licence grant and a customer rebuild with an increased ceiling. Editing an existing Studio package does not change a delivered EXE or issued licence. Keep the same profile ID across versions for upgrades; a different profile gets separate installation/data identity. Moving owner-evaluation data into a profile-specific build requires a reviewed backup/restore and the matching licence; data is not silently migrated or erased.

Customer runner pins REQUIRE_ISSUER and the exact profile digest into compiled code. Deleting/replacing public profile/issuer assets cannot fall back to evaluation in that compiled customer release. This is a practical resource-integrity guard, not protection against executable patching. The signing private key is generated/protected on the owner Windows PC and never copied to the runner/customer package. Offline revocation remains a local record only, and deleting a licence does not revoke exported copies. Machine binding continues to use Windows MachineGuid; OS reinstall can require owner reissue.

Offline update manifests prove owner signature and file integrity, not Microsoft Authenticode trust. There is no automatic network download, execution, rollback or remote update server. Installer packages remain unsigned without an owner-supplied code-signing certificate. A forged local build-results report could claim tests passed; imports check files and owner associations but are **owner attestations**, not independent remote CI attestations. Review provenance/logs before distributing a release. Customer-specific Inno installer compilation is automated; generic customer installer install/upgrade/uninstall is tested. Customer-specific installer upgrade/uninstall still needs a field pilot.

## Verification, performance and rollback

Local regression suite before the last added logo/mobile/report case: 198 passed, 5 Windows-only skipped. The additional case verifies applied PNG branding and rejects report export/mobile startup before files/network work. Native CI runs the full final suite plus a disposable customer build: regression tests, signed profile, portable and Inno installer generation, activated frozen client permissions/title, and deletion of profile/public-key assets failing closed. CI fixture signing key exists only in memory; fixture customer installers are deleted and never uploaded for customer use. Check the successful run and BUILD_INFO for final counts.

GUI review covers default owner monitor and Studio Builds/releases. No physical laptop, modem/Rocket firmware, production issuer, phone or customer network has been tested. Existing live ping/buzzer regression coverage remains in the full suite. Worker permission checks use cached eligible IDs; cryptographic licence refresh occurs once per minute, not every ping. Build work runs in a child process. Local hash verification, password derivation and backup operations can briefly block dialogs; no zero-lag claim is made.

Changed/new code: `zee/entitlements.py`, `zee/build_profile.py`, `zee/updates.py`, licensing/client entry/UI/storage/import/workers/mobile-dialog integration, `admin/issuer.py`, `admin/studio_store.py`, `admin/studio.py`, `admin/customer_build.py`, Windows verification script/tests/workflow, version/installer/packaging and guides. Customer database schema stays 4; Studio adds an additive builds table, preserving existing records.

Rollback source baseline: `d6090b704d43f7a9434219ec5447bd05fd5c1668` (v0.4.13). Preserve encrypted Studio backup and issuer recovery PEM before changing real customer records. Restore an appropriate licence/client pair: v0.4.13 cannot validate v2 licences. Studio history/key files remain in the existing owner data folder; profile client data folders are separate from the old generic monitor directory.

Acceptance: signed entitlements verified; storage/worker denials tested; records retained; branding applied; owner-only build/release/sign actions; no private customer bundle material; Windows frozen custom activation and missing-resource checks; release hashes and manual signed update verification. Pending beyond this local workflow: hosted online activation/revocation, automatic downloads/installer rollout, trusted remote build attestations, certificate signing and real hardware/customer pilot. Phase 9 should address installer/licensing/mobile acceptance and deployment recovery; Phase 10 is real-network pilot.
