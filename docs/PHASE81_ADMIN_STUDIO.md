# Phase 8.1 — Admin Studio foundation (v0.4.13)

Phase 8 remains open. This release supplies a separate owner Windows application, not a completed customer build/entitlement platform.

## Completed and remaining

| Module | Working behavior | Remaining for 8.2 |
|---|---|---|
| Overview and authentication | First-run owner setup, masked passwords, sign-in/out, read-only viewer, backend owner authorization | Broader account administration |
| Customers | Create, edit, search, archive and restore local records | Customer deployment lifecycle |
| Packages | Validity, planned feature selection and planned device limits saved and reviewed | Actual feature/device enforcement in the customer application |
| Profiles | Customer/package references, branding text and PNG preview, reviewed JSON export | Apply branding and package settings to customer builds |
| Licences | Import activation request, issue signed one-PC licence, export stored document | Provision reviewed public issuer into customer release; entitlement integration |
| Revocation | Reason and local status recorded | Offline copies remain valid; no remote revocation is implemented |
| Audit | Actor/action history, chained digest verification, CSV export | No claim of an immutable log against filesystem administrators |
| Recovery | Encrypted database/key backup, verified restore, pre-restore checkpoint, encrypted signing-key recovery | Cross-machine setup must still use recovery PEM and restored owner credentials |
| Releases and updates | External Windows CI builds/tests downloadable EXEs | Studio build executor, installer/version/update management and build-results console |

## Try the owner EXE

Download `ZeeAdminStudio-Owner`, extract the entire ZIP and run `ZeeAdminStudio/ZeeAdminStudio.exe`. Keep `_internal` beside the EXE. No separately installed Python is required. This first Studio release is portable; a Studio installer is not included. The customer Setup and legacy ZeeLicenseManager are separate artifacts.

Create a local owner username and password of 12–256 characters. There is no default password. Add customers and packages, then optionally associate them through a profile. Labels describe package limits and branding as planned because they do not yet change the customer EXE. Viewer accounts can read records but cannot alter them, issue licences, access signing keys or restore backups.

If you already use a signing issuer, import its password-encrypted recovery PEM **before initializing a new Studio issuer**. Initializing a different issuer does not update existing customer applications. Export only `issuer-public.json` for a reviewed client rebuild. Never upload a private key, recovery PEM, backup or password to GitHub or send it to a customer. Without a provisioned public issuer, the current client remains an owner-evaluation preview.

For a licence, choose an active customer/package, optionally a matching profile, and import that customer's activation request or enter its machine fingerprint. Select the output filename and issue. Canceling the save dialog does not create a licence. If writing the chosen file fails, the signed record remains available for export. Archive preserves record/history and prevents using inactive records for new issuance. Revocation updates only the Studio register; an already exported offline licence continues to verify.

## Storage and security limits

Studio uses `%LOCALAPPDATA%/ZeeAdminStudio`, separate from customer monitor data and legacy issuer storage. Windows DPAPI protection fails closed outside supported Windows. Production signing keys are generated only on the owner's machine, never in CI or shipped in the ZIP.

Passwords use PBKDF2-HMAC-SHA256 with 600,000 iterations and random salts. A separate authentication verifier is stored; it cannot directly decrypt the key wrapper. The signing key is encrypted with AES-GCM using the owner's derived secret, then protected by Windows DPAPI. The unlocked secret exists in the authenticated owner session. Sessions expire after 15 minutes (absolute duration), and five rejected logins trigger a one-minute lock. Authorization is checked in the storage service, not just through disabled buttons.

Customer records are ordinary local SQLite data, not encrypted at rest. Protect the Windows account and disk appropriately. Audit chaining detects inconsistent history but an attacker controlling the filesystem can rewrite/recompute an entire chain; it is not an externally anchored immutable audit. A valid owner login encountering a broken chain opens recovery-only mode; normal operations and viewer access are blocked.

Backups encrypt a consistent SQLite snapshot and the already wrapped issuer file with AES-GCM and a separate backup password. Restore validates decryption, schema, SQLite integrity and audit chaining before replacing current files. A timestamped pre-restore checkpoint is retained and sessions are invalidated. Sign in using the restored account/password. Transferring a backup to another Windows account/machine requires the separate encrypted issuer recovery PEM to rewrap the matching issuer; DPAPI is tied to the original account. Recovery passwords are not recoverable by the application. Checkpoints contain local database records and need the same filesystem protection as current data.

## Verification and performance

Local full suite: 191 passed, 5 Windows-only checks skipped (196 collected), including Studio role/expiry denial, password wrapping, client-side signature verification, wrong-PC rejection, encrypted backup/restore, audit recovery and GUI authorization. Linux protection mocks are test fixtures only; production DPAPI has no plaintext fallback. Windows CI also executes a real-DPAPI Studio signing/backup test, builds the customer/legacy-owner/Studio applications, checks frozen launch markers, audits packaged contents and exercises customer installer/upgrade/uninstall. Consult this build's CI result and `BUILD_INFO.json` for native results.

Visual review covered the locked login, overview and customer list. No physical Windows 10 laptop or customer modem/network was tested. Network polling is unchanged. Record reads are bounded to 1,000 rows and the table renders at most 200 matching rows; this release is intended for a small local customer register. Large-register pagination and background password/backup work remain future performance work.

## Changed files and rollback

New: `admin/studio.py`, `admin/studio_store.py`, `ZeeAdminStudio.spec`, `tests/test_admin_studio.py`, and this guide. Updated: version in `zee/core.py`, packaging script, Windows workflow, customer installer version, READMEs and professional guide. Customer database schema remains 4. Existing monitor behavior and legacy owner utility are preserved.

To roll back code, use Phase 7 commit `f00b2b6d9cdf6dafc471755e854f757f91192177` / v0.4.12 customer package. Keep Studio data and encrypted recovery exports safe; reverting the customer version does not restore or erase the separate Studio database. Test a backup/restore using disposable records before relying on it for real customers.

8.1 exit checklist: local tests pass; Windows native tests and frozen launch pass; owner/customer artifacts stay separate; package audit includes no original Python source or private issuer files; owner can create records, sign/export a licence and restore encrypted backup. Full Phase 8 completion requires 8.2: client entitlements, applied branding, reviewed customer build profiles, release/version/update workflows and their tests.
