ZEE NETWORK MONITOR v0.5.3 — MONITORING TEST BUILD

Filhal Admin Studio aur licence ka kaam paused hai. Normal owner preview ko pehle se activation ki zaroorat nahi. Existing signed builds ki licence protection unchanged hai. Sirf Network Monitor Setup install karen.

Purane towers/devices/settings isi Windows account ke data folder mein rehte hain. Setup se pehle Settings > Backup database aur complete data folder ka backup kar len. Licence/Studio records delete nahi kiye jate.

PING / ALARM
Settings > Alerts & detailed history > Buzzer delay: default 15 seconds. Save karen. Chhota fault recover ho jaye to buzzer cancel hota hai. Status/history ab bhi foran update hote hain.

INTERNET / SPEED
WAN setup > Use Cloudflare download-test setup. Inspect Internet route. Gateway Internet ka actual next hop ho, source laptop ki IP ho. WAN path verify kar ke Save, phir monitoring restart karen. Har modem ki alag speed ke liye Windows routes/interfaces sahi hone chahiye. Upload test ke liye authorized receiver chahiye.

PERFORMANCE
Advanced monitoring / history se worker limits aur intervals adjust ho sakte hain. Real-network pilot / support report se CPU/RAM recording aur fault evidence export karen. Asal hardware results abhi verify nahi hue.

Details: MONITORING_ONLY.md, WAN_ALARM_FIX.md, PHASE10_REAL_NETWORK_PILOT.md.

NOC GUI v0.5.1: Dashboard, Internet Monitor, Discovery, Network Map, Rocket M5 Monitor, Dish Alignment, Alerts & History, Device Manager, Settings.
Discovery sirf Start Scan se chalti hai, subnet max 1,024 addresses. Add Selected Devices se pehle backup hota hai; duplicates skip hote hain.
Dish Alignment signal se andazay ki direction nahin batata; manual adjustment tags aur measured sweeps chahiye. Saved results database backup mein shamil hain.
Network Map configured Lahore–Sargodha schematic aur purana offline geographic map dono rakhta hai. Apne station/links configure karen; sample topology add nahin hoti.
Details NOC_GUI_v050.md.

v0.5.1: Discovery mein pehle apna adapter/range select karein aur authorization tick karein; remote range ke liye confirmation zaroori hai. TCP, DNS, CSV export, remote stations aur session rediscovery optional hain. Alignment mein verified telemetry set karein, Test telemetry dabayein, baseline ke 3 samples lein, phir chhota manual adjustment record karein. RSSI akela perfect alignment ka saboot nahin. Details: DISCOVERY_ALIGNMENT_v051.md.

v0.5.3: Network Discovery > Scan all connected networks. IP select kiye baghair detected connected IPv4 subnets/source list confirm karein. Found now, Identified only aur All checked alag tabs hain; source/subnet ke sath Add Selected aur CSV export hain. Bari ranges skipped dikhengi; remote ranges alag permission se scan hongi. Details: DISCOVERY_ALL_NETWORKS_v052.md.

v0.5.3: Internet Monitor > Wateen modem > Setup / Details > Wateen setup. Source 58.27.163.141 aur gateway 58.27.163.137 confirm kar ke Save, phir Start Test. Download/upload app ke andar; Windows IP/route change nahi hota. Details: WATEEN_SPEED_v053.md.
