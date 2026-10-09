# v0.1.0 feature status

| Feature | Status and limits |
|---|---|
| Professional desktop GUI | Implemented; rendered and startup tested on Linux/offscreen, Windows UI not tested |
| Device add/edit/delete, types, notes, locations, IDs | Implemented; validation and persistence tested |
| Parent links / next-hop field | Parent tree editable with cycle prevention; next hop is annotation only |
| Dashboard/filter/search/manual refresh | Implemented; live aggregate counts, sampled failures and latest average latency |
| Single/all/selected continuous/periodic ping | Implemented; bounded background workers, no duplicate jobs, queue for batches larger than 8 |
| Timeouts/graceful shutdown | Implemented; in-flight probes finish within bounded subprocess deadlines |
| Host validation | IPv4/IPv6/ASCII hostnames supported; internationalized names must be entered as ASCII/punycode |
| Persistence / backup | SQLite WAL, online backup; schema v1 only, no future migration implemented |
| History / graphs / outages / uptime | Implemented as retained samples, not continuous true uptime; latency graph latest 1,000 samples |
| CSV events/samples/summary | Implemented with filters and formula-safe strings |
| Alerts | Repeated-failure threshold, latency threshold, deduplication, recovery, optional beep/tray notifications; Windows delivery untested |
| Five WAN templates | Implemented, disabled/unconfigured until user supplies hosts |
| Independent WAN tests | Partial: optional Windows IPv6 source binding; IPv4 is reachability only unless external routing is verified. No per-WAN speed/throughput |
| Rocket M5 | Basic ping only; airOS/SNMP/SSH/signal/noise/SNR/CCQ/uptime/firmware not implemented |
| Router WAN adapter | Typed read-only extension interface only; no concrete integration registered |
| Fault isolation | Probable first failing parent segment and downstream list; not physical failure confirmation |
| Agent heartbeat / secure remote reporting / services | Not implemented. Architecture notes only, no agent results or credentials collected |
| Credential storage | Not needed for current ping-only release; profile reference is reserved, not a secrets field |
| Retention / logs | Age-based history deletion and rotated diagnostic log; DB space can be reused but automatic file compaction absent |
| Windows package | Spec/BAT/GitHub Actions supplied; Windows EXE not built or tested in this session |
| Linux frozen package | Build and startup tested for packaging validation; not delivered as a Windows substitute |
| Windows 10 compatibility | Target only; real Windows 10 launch, live ICMP, DLL and notification checks still required |

No hard-coded user network addresses, synthetic live results, credentials or device write commands are included. Five-WAN reachability does not claim five independent Internet paths.
