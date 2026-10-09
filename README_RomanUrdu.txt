ZEE NETWORK MONITOR v0.1.0
Windows 10 x64 target — Source + Windows build workflow

ZAROORI BAAT
Is source ZIP mein Windows EXE abhi nahi hai. App Linux environment mein
banayi/test ki gayi hai. Windows build workflow tayyar hai, lekin is session
mein Windows runner ya aap ke Windows 10 laptop par nahi chalaya gaya.
Sirf successful GitHub Actions artifact mein ready-to-run EXE milegi.
Advanced SNMP/airOS/router telemetry aur remote agents abhi implemented nahi.

BINA PYTHON INSTALL KIYE WINDOWS PACKAGE HASIL KARNA
1. docs/WINDOWS_BUILD.md kholen. GitHub par free private repository banayen.
2. Source upload karen aur included .github/workflows/windows-build.yml lagayen.
3. Actions > Build Windows portable application > Run workflow.
4. Green successful run > Artifacts > ZeeNetworkMonitor-Windows-x64 download.
5. Download unzip karen; andar ki portable ZIP bhi unzip karen.
6. ZeeNetworkMonitor folder ke andar ZeeNetworkMonitor.exe double-click karen.
   Pura folder saath rakhen. _internal ko delete ya move na karen.
Aap ke laptop par Python, Git ya VS Code ki zaroorat nahi hogi. Build GitHub
ke Windows runner par hoga. Failed workflow ki artifact ko successful build
na samjhen. README mein screenshots nahi, step-by-step text guide hai.

PEHLA ISTEMAAL
- Add device: naam, IP/hostname, type aur location enter karen.
- Apni actual IPs GUI mein enter karen. Default koi user IP set nahi hai.
- Host khali rakhna hai to Enable monitoring untick karen.
- Ping selected: ek test. Ping all now: tamam enabled devices ka ek test.
- Continuous selected: selected device ko bar bar check karega.
- Start monitoring: tamam enabled devices intervals par check honge.
- Stop monitoring: naye periodic checks band. Chal rahe probes deadline tak
  finish honge. App close karne par shutdown chand seconds le sakta hai.
- Parent / previous hop topology ki direction define karta hai. Next hop
  annotation hai; diagnosis parent tree se hoti hai. Cycles allowed nahi.
- Edit/Delete ke liye table ki row select karen.
- Disabled device par ping nahi chalega. Enable karne ke liye Edit use karen.

STATUS
Green Online = reply. Red No reply = ICMP reply nahi mili.
Amber Warning = latency threshold se zyada. Amber Unknown = fresh result nahi.
Blue Checking = probe chal raha hai. Disabled/Unconfigured = monitoring band.
No reply ka matlab confirmed radio/cable failure nahi. ICMP firewall mein
blocked ho sakta hai; route, host ya monitoring PC ka issue bhi ho sakta hai.
Stale results (~max 30 seconds / 3 intervals) Unknown ho jate hain. App restart
par previous-session result ko fresh Online nahi dikhaya jata.

5 WAN CONNECTIONS
Settings > Add 5 unconfigured WAN templates: Lahore WAN-1 ... WAN-5.
Har WAN ki row Edit karen. General 8.8.8.8 ping se load-balanced PC par
5 independent WANs measure nahi hongi. Is release ka IPv4 mode reachability
only hai. Windows routing ko aap ke network engineer ko separately verify
karna hoga. App routes nahi banati. Optional literal IPv6 source + IPv6 target
supported hain; actual egress path phir bhi verify karna hai. Router telemetry,
speed aur bandwidth measurements unavailable hain. Numbers invent nahi hote.

HISTORY / ALERTS
History & uptime mein device aur time range select karen. Graph actual measured
latency show karta hai; red ticks no reply hain. Sampled availability true
continuous uptime ka substitute nahi. App band hone ka waqt unknown hai.
Events & alerts mein date range/device/search filter hai. CSV export Excel mein
khul sakti hai. Exports mein epoch timestamp UTC hota hai; GUI local time hai.
Per-device latency/failure threshold Edit mein set karen. Settings mein beep,
notification aur recovery on/off. Duplicate incident alerts suppress hote hain.
Loss sample-based estimate hai; old samples retention ke baad delete hote hain.

DATA / BACKUP
Windows data: %LOCALAPPDATA%\ZeeNetworkMonitor\monitor.sqlite3
Settings aur devices automatically save hote hain; IP dobara nahi dalni parti.
Settings > Backup database. Restore: app band karen, active data folder ko pehle
copy karen, monitor.sqlite3 aur us ke old -wal/-shm companions hata kar verified
backup ko monitor.sqlite3 naam se copy karen. Sirf same schema v1 backup use karen.
Credentials/passwords is release mein collect ya store nahi hote. Profile field
future adapter reference ke liye reserved hai; us mein password mat likhen.
Diagnostic log rotate hota hai (1 MB x 4 files), default history 90 days.
Database file deleted pages reuse kar sakti hai; retention ke baad physical
file foran chhoti hona lazmi nahi. Long term file growth/disk usage monitor karen.

UNINSTALL / CLEANUP
App close karen; portable folder delete karen. Settings/history bhi mitani hain
 to %LOCALAPPDATA%\ZeeNetworkMonitor delete karen (pehle backup le len).
Koi service, startup registration ya router configuration install nahi hoti.

DEVELOPER ONLY
Python 3.11 x64 installed Windows par Build_EXE.bat build script hai. End-user
ke liye isay chalana zaroori nahi. Source: main.py, zee/, tests/, .github/.
Details: docs/FEATURES.md, docs/TEST_REPORT.md, docs/ARCHITECTURE.md.
