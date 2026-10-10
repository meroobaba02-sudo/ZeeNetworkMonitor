"""Owner-only licence creation helpers; no bundled keys or remote services."""
import base64,time,uuid,re,json,os
from pathlib import Path
from zee.licensing import PRODUCT,canonical

def activation_request(machine):
    if not isinstance(machine,str) or not re.fullmatch('[a-f0-9]{64}',machine):raise ValueError('Invalid PC fingerprint.')
    return {'type':'zee-activation-request','version':1,'product':PRODUCT,'machine':machine}

def read_request(document):
    if not isinstance(document,dict) or document.get('type')!='zee-activation-request' or document.get('version')!=1 or document.get('product')!=PRODUCT:raise ValueError('Not a Zee activation request.')
    return activation_request(document.get('machine'))['machine']

def issue_document(key,machine,customer,edition,reference,days=365,expires=None,now=None,entitlements=None,customer_id='',profile_id=''):
    activation_request(machine);now=time.time() if now is None else now
    if isinstance(days,bool) or not isinstance(days,int) or not 0<=days<=36500:raise ValueError('Days must be 0–36500.')
    if expires is not None and (not isinstance(expires,(int,float)) or not now<expires<=now+36500*86400):raise ValueError('Expiry must be in the future within 100 years.')
    for value in (customer,edition,reference):
        if not isinstance(value,str) or len(value)>200:raise ValueError('Labels must be at most 200 characters.')
    if not customer.strip() or not edition.strip():raise ValueError('Customer and edition are required.')
    payload={'version':1,'product':PRODUCT,'machine':machine,'customer':customer.strip(),'edition':edition.strip(),'reference':reference.strip() or str(uuid.uuid4()),'activations':1,'issued':now,'expires':expires if expires is not None else now+days*86400 if days else None}
    if entitlements is not None:
        from zee.entitlements import validate
        payload.update(version=2,entitlements=validate(entitlements),customer_id=customer_id,profile_id=profile_id)
    return {'payload':payload,'signature':base64.b64encode(key.sign(canonical(payload))).decode()}

def write_atomic(path,data):
    path=Path(path);temp=path.with_name(path.name+'.new')
    try:
        with temp.open('wb') as file:file.write(data);file.flush();os.fsync(file.fileno())
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)
