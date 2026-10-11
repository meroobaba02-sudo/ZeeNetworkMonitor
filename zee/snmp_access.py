"""Bounded read-only access diagnostics, separate from unverified radio metrics."""
import asyncio
import ipaddress
from dataclasses import dataclass

SYS_DESCR = '1.3.6.1.2.1.1.1.0'

@dataclass(frozen=True)
class AccessResult:
    version: str
    state: str
    detail: str

async def probe(host, community, version='2c', source='', port=161, timeout=2):
    from pysnmp.hlapi.v3arch.asyncio import (SnmpEngine, CommunityData,
        UdpTransportTarget, Udp6TransportTarget, ContextData, ObjectType,
        ObjectIdentity, get_cmd)
    from pysnmp.proto import errind
    remote = ipaddress.ip_address(host)
    if version not in ('1', '2c') or not community or not 1 <= int(port) <= 65535:
        raise ValueError('Choose v1/v2c, a read-only community and valid port.')
    if remote.is_unspecified or remote.is_multicast or '%' in host:
        raise ValueError('Use a literal unicast management IP.')
    if source:
        local = ipaddress.ip_address(source)
        if local.version != remote.version or local.is_unspecified or local.is_multicast or '%' in source:
            raise ValueError('Source must be a matching-family local unicast IP.')
    engine = SnmpEngine()
    try:
        cls = Udp6TransportTarget if remote.version == 6 else UdpTransportTarget
        target = await cls.create((host, int(port)), timeout=timeout, retries=0)
        if source:
            target.set_local_address((source, 0))
        error, status, index, bindings = await get_cmd(engine,
            CommunityData(community, mpModel=0 if version == '1' else 1),
            target, ContextData(), ObjectType(ObjectIdentity(SYS_DESCR)), lookupMib=False)
        if error:
            if isinstance(error, errind.RequestTimedOut):
                return AccessResult(version, 'timeout', 'No matching SNMP reply. Timeout alone cannot identify a community or firmware problem.')
            return AccessResult(version, 'transport_error', 'SNMP transport failed; check local source IP, network access and runtime.')
        if status:
            return AccessResult(version, 'agent_error', 'SNMP agent replied with error code '+str(int(status))+'. Access responded, but the requested system description was rejected.')
        if len(bindings) != 1 or str(bindings[0][0]) != SYS_DESCR:
            return AccessResult(version, 'invalid_reply', 'Reply did not contain the requested system description.')
        from pysnmp.proto.rfc1902 import OctetString
        if not isinstance(bindings[0][1], OctetString):
            return AccessResult(version, 'unsupported_oid', 'SNMP replied, but system description is unavailable. Radio metrics remain unverified.')
        # Do not display device-returned text: it can contain secrets or hostile markup.
        return AccessResult(version, 'ok', 'System description returned. SNMP access works; signal OIDs and units still need firmware verification.')
    finally:
        engine.close_dispatcher()

def diagnose(host, community, source='', port=161):
    async def run():
        results = []
        for version in ('2c', '1'):
            try:
                results.append(await asyncio.wait_for(probe(host, community, version, source, port), 8))
            except asyncio.TimeoutError:
                results.append(AccessResult(version, 'deadline', 'Diagnostic reached its time limit.'))
            except ValueError:
                results.append(AccessResult(version, 'configuration_error', 'Check literal management/source IPs, port and saved community.'))
            except Exception:
                results.append(AccessResult(version, 'runtime_error', 'SNMP runtime or local socket error; no credentials were logged.'))
        return results
    return asyncio.run(run())
