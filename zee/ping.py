"""Bounded system-ping adapter. No shell invocation, no device mutations."""
from dataclasses import dataclass
import platform
import re
import subprocess

@dataclass(frozen=True)
class Result:
    success: bool
    latency: float | None = None
    error: str = ''
    infrastructure_error: bool = False


def parse_ping(output, returncode):
    # TTL/hlim identifies an echo reply rather than an ICMP unreachable error.
    reply = re.search(r'(?:ttl|hlim)\s*[=:]\s*\d+', output, re.I)
    timing = re.search(r'(?:time|temps|zeit|tiempo|tempo|время|时间)\s*([=<])\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:ms|мс|毫秒)',output,re.I)
    if returncode == 0 and (reply or timing):
        latency = float(timing[2].replace(',','.')) if timing else None
        if timing and timing[1] == '<':
            latency /= 2
        return Result(True,latency)
    if re.search(r'could not find host|name or service not known|temporary failure in name resolution|unknown host',output,re.I):
        return Result(False,error='Hostname could not be resolved. Check the name and DNS settings.',infrastructure_error=True)
    if re.search(r'operation not permitted|permission denied',output,re.I):
        return Result(False,error='System denied permission to run ICMP probes.',infrastructure_error=True)
    return Result(False,error='No ping reply (ICMP filtering or routing may be involved)')


def command(device, system=None):
    system = system or platform.system()
    if system == 'Windows':
        args = ['ping','-n','1','-w',str(device.timeout)]
        if device.source:
            args += ['-6','-S',device.source]
        return args+[device.host]
    args = ['ping','-n','-c','1','-W',str(max(1,(device.timeout+999)//1000))]
    if device.source:
        args += ['-6','-I',device.source]
    return args+[device.host]


def probe(device):
    if device.source and ':' not in device.source:
        from .windows_ping import echo
        return echo(device.host,device.source,device.timeout)
    try:
        run = subprocess.run(command(device),capture_output=True,text=True,errors='replace',timeout=device.timeout/1000+4,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return parse_ping(run.stdout,run.returncode)
    except FileNotFoundError:
        return Result(False,error='System ping executable is missing.',infrastructure_error=True)
    except subprocess.TimeoutExpired:
        return Result(False,error='Probe/DNS deadline expired; no reply observed.')
    except OSError as e:
        return Result(False,error='Probe could not run: '+str(e),infrastructure_error=True)
