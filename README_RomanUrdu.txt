ZEE NETWORK MONITOR PROFESSIONAL v0.4.14

WINDOWS PAR CHALANA
Successful GitHub Actions run se Setup ya Portable artifact download karen.
Setup EXE desktop/Start Menu shortcut banata hai. Python install nahi karna.
Portable ZIP ko Extract All karen; poora folder aur _internal saath rakhen.
Sirf EXE alag copy karne se Python DLL/runtime error aa sakta hai.

ASAN SHURUAT
1. Manage networks > Add network. Apna network naam den.
2. Map > Add tower > naam > Save.
3. Tower select karen > Add radio. Asal IP, naam aur type dalen.
4. Start monitoring dabayen. Default sirf selected page hai.
   Monitor all networks tick karen to verified active pages ikathay monitor honge.
   Is mode mein page badalne se monitoring nahi rukti.
5. Buzzer ON/OFF awaaz control karta hai; Silence mojooda fault ki awaaz rokta hai.
Naya fault dobara alarm baja sakta hai. No reply confirmed dish/cable fault nahi.

NETWORK AUR METRICS
Network setup / paths > Read laptop IPs / adapters > source IP select karen.
Har row mein apna network naam aur test target IP dalen > Check selected network.
ICMP reply intended WAN/dish ka proof nahi. Asal Windows path verify kar ke
Operator verified tick karen > Save > Start monitoring. Software IP/routes nahi banati.
Same IP alag networks par ho to distinct source IPs aur verified Windows paths chahiye.
Connect tower radios > first/second device > Save link. Zaroorat par upstream tick karen.
Cross-network links aur cycles reject hote hain; existing peer replace se pehle remove karen.
Laptop se har IP reachable hona zaroori hai. App routes nahi banati.
IPv4/IPv6 source settings path verify karne ka substitute nahi.
SNMP/HTTPS adapters maujood hain; OIDs/API asal firmware ke mutabiq verify karen.
WAN traffic estimate aur controlled download link capacity ka guaranteed proof nahi.
Camera service response actual video playback ka proof nahi.

BACKUP / RESTORE
Data: %LOCALAPPDATA%\\ZeeNetworkMonitor
Settings > Backup database. Restore backup and close se verified backup select karen.
Agli launch par backup dobara validate hoti hai; purani DB before-restore.bak mein rehti hai.
Invalid queued backup par startup rukta hai; current DB replace nahi hoti.
Recovery ke liye app band kar ke restore.pending.sqlite3 ko doosri jagah move karen.
Full recovery ke liye poora data folder bhi copy karen: database-only backup mein
credentials, licence aur mobile sidecar files shamil nahi. Credentials isi Windows
account se protected hain. Uninstall data preserve karta hai.
Nayi installation par detailed history 48 hours hai. Purani saved customization preserve hoti hai.
Settings mein hours aur Automatic background cleanup set karen; Save settings dabayen.
Clean expired records now manual cleanup hai. Alerts mein Pin / Unpin selected se event bachayen.
Advanced monitoring / history mein retries, worker limits, refresh, alert retention aur
cleanup se pehle archive ka option hai. Archives extra disk leti hain aur khud delete nahi hotin.
Security/audit, pinned aur unresolved alerts ordinary cleanup se protected hain.
Disk threshold warning hai; fresh records zabardasti delete nahi hote.

ADMIN AUR TEST STATUS
ZeeLicenseManager owner-only limited utility hai; full Admin Studio Phase 8 mein ayega.
Private signing key customer ko kabhi na den. Commercial enforcement ke liye owner
public key ke sath customer build chahiye. Preview mein issuer provisioned nahi.
Windows Server 2022 CI evidence physical Windows 10 laptop ka proof nahi.
Real Rocket M5, five-network routing, Android aur old-laptop testing baqi hai.
Details: docs/PROFESSIONAL_GUIDE.md aur docs/PHASE2_STABILIZATION.md.

PHASE 5 — RADIO / WAN
Secure settings mein asal model aur firmware record karen. Verified OID/JSON mapping
ke baad profile-verification checkbox tick karen; mapping badalne par dobara check chahiye.
SNMP GET ab selected source IP se chalti hai (IPv4 aur non-scoped IPv6).
WAN setup mein counter interface ka asal naam den aur counters verify karen.
Interface traffic aur Internet speed alag hain. Upload capacity test abhi unavailable hai.
Rocket M5 ki asal firmware readings abhi device par test honi hain.
Details: PHASE5_INTELLIGENCE.md.

PHASE 6 — FAULT / INCIDENT
Topology & diagnosis mein mumkin fault location, evidence aur next check dekhen.
Events & alerts > Incident history mein start, last evidence aur recovery dekhen.
Acknowledge se buzzer band ya incident recover nahi hota; awaaz ke liye Silence use karen.
Notes aur Pin se zaroori record bachayen. Missing reading recovery nahi hai.
Close unverified sirf operator closure hai, recovery ka proof nahi.
Schema 4 upgrade se pehle database ki automatic .pre-v0410.bak copy banti hai.
Purana software chalana ho to schema 3 backup bhi restore karna zaroori hai.
Details: PHASE6_INCIDENTS.md.

Phase 7: App khulne par Overview dashboard milega. Internet speeds mein saat modem rows hain. Advanced controls se extra setup options dikhen ge. Settings se Dark/Light theme badal sakte hain. Ctrl+1 Overview, Ctrl+2 Map, Ctrl+3 Devices, Ctrl+4 Internet speeds, Ctrl+F device search. Advanced controls admin permission nahi hain; separate Admin Studio aglay phase mein hai.

Phase 8.1: ZeeAdminStudio-Owner ZIP poori extract karein, phir ZeeAdminStudio.exe chalayein. Local owner username aur 12+ character password banayein. Customers, packages, reviewed profiles aur signed licences kaam karte hain. Planned package limits/custom branding abhi customer EXE par apply nahi hoti; ye Phase 8.2 hai. Purana issuer ho to naya key banane se pehle encrypted recovery PEM import karein. Private keys/passwords kabhi GitHub par na bhejein.

Phase 8.2: nayi v2 licence mein features/device limit enforce hain. Profiles > Prepare signed customer build, phir Builds / releases se owner Windows toolchain select karen. Branding customer EXE/installer mein apply hoti hai. Sirf owner build PC ko Python/PyInstaller chahiye; customer ko nahi. Existing owner records/issuer preserve hain. Online revoke/auto update download nahi; signed offline installer verify kar sakte hain. Details PHASE82_CUSTOMER_BUILDS.md.
