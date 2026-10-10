"""Signed package bounds shared by storage, workers and customer UI."""
from dataclasses import dataclass
FEATURES=('monitoring','map','wan','wireless','cctv','mobile','reports')

def validate(value):
    if not isinstance(value,dict) or set(value)!={'features','max_devices'}:raise ValueError('Invalid package permissions.')
    features=value['features'];limit=value['max_devices']
    if not isinstance(features,list) or any(type(x) is not str or x not in FEATURES for x in features) or len(set(features))!=len(features):raise ValueError('Invalid package features.')
    if type(limit) is not int or not 1<=limit<=10000:raise ValueError('Device limit must be 1–10000.')
    return {'features':list(features),'max_devices':limit}

def category(device):
    if device.wan or device.kind.startswith('WAN'):return 'wan'
    if device.kind.startswith('Rocket'):return 'wireless'
    if device.kind.startswith('CCTV'):return 'cctv'
    return 'monitoring'

@dataclass(frozen=True)
class Policy:
    features:frozenset=frozenset(FEATURES)
    max_devices:int=10000
    valid:bool=True
    def allows(self,feature):return self.valid and feature in self.features
    def require(self,feature):
        if not self.allows(feature):raise ValueError('This package does not permit '+feature+'. Check Licence / activation.')
    def selected(self,devices):return {d.id for d in devices[:self.max_devices]} if self.valid else set()
    def permits(self,device,devices):return self.allows('monitoring') and self.allows(category(device)) and device.id in self.selected(devices)

def from_status(state,profile=None):
    if not state.get('valid'):return Policy(frozenset(),0,False)
    ceiling=validate(profile['entitlements']) if profile else {'features':list(FEATURES),'max_devices':10000}
    grant=validate(state['entitlements']) if state.get('version')==2 else ceiling
    return Policy(frozenset(ceiling['features']) & frozenset(grant['features']),min(ceiling['max_devices'],grant['max_devices']))
