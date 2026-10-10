"""Offline Ed25519 verification. Production issuer public key must be provisioned by owner."""
import json,hashlib,base64,time,os,sys,uuid,math
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
PRODUCT='ZeeNetworkMonitor'
REQUIRE_ISSUER=False
EXPECTED_PROFILE_SHA256='' # Pinned into compiled customer builds by owner build runner.

def fingerprint():
    if os.name=='nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Cryptography',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:value=winreg.QueryValueEx(key,'MachineGuid')[0]
    else:value='development-'+str(uuid.getnode())
    return hashlib.sha256((PRODUCT+'|'+value).encode()).hexdigest()

def canonical(payload):return json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def verify(document,public_key,machine=None,now=None):
    if not isinstance(document,dict) or set(document)!={'payload','signature'} or not isinstance(document['payload'],dict):raise ValueError('Malformed licence document.')
    payload=document['payload'];signature=base64.b64decode(document['signature'],validate=True)
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key,validate=True)).verify(signature,canonical(payload))
    if payload.get('product')!=PRODUCT or payload.get('version') not in (1,2):raise ValueError('Wrong licence product/version.')
    if payload.get('machine')!=(machine or fingerprint()):raise ValueError('This licence belongs to another PC.')
    if type(payload.get('activations')) is not int or payload['activations']!=1:raise ValueError('Each licence file authorizes exactly one machine.')
    now=time.time() if now is None else now
    if payload.get('expires') is not None and (type(payload['expires']) not in (int,float) or not math.isfinite(payload['expires']) or now>payload['expires']):raise ValueError('Licence expired.')
    if type(payload.get('issued')) not in (int,float) or not math.isfinite(payload['issued']) or now<payload['issued']-86400:raise ValueError('Licence not yet valid; check the clock.')
    if payload['version']==2:
        from .entitlements import validate
        validate(payload.get('entitlements'))
        if not isinstance(payload.get('customer_id'),str) or not isinstance(payload.get('profile_id'),str):raise ValueError('Invalid licence binding.')
    return payload

def public_key_path():return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets/issuer-public.json'

def customer_profile():
    from .build_profile import verify_profile,digest
    path=public_key_path().with_name('customer-profile.json')
    if not path.exists():
        if EXPECTED_PROFILE_SHA256:raise ValueError('Customer build profile missing.')
        return None
    document=json.loads(path.read_text())
    if EXPECTED_PROFILE_SHA256 and digest(document)!=EXPECTED_PROFILE_SHA256:raise ValueError('Customer build profile changed.')
    return verify_profile(document,json.loads(public_key_path().read_text())['public_key'])

def branding():
    p=customer_profile()
    return p['branding'] if p else {'app_name':'Zee Network Monitor','watermark':'Created by Zeeshan Rasool','logo_png':''}

def status(data_dir):
    key=public_key_path()
    if not key.exists() and not REQUIRE_ISSUER and not EXPECTED_PROFILE_SHA256 and not key.with_name('customer-profile.json').exists():return {'valid':True,'edition':'Owner evaluation — issuer not provisioned','production':False}
    try:
        profile=customer_profile()
        payload=verify(json.loads((Path(data_dir)/'license.json').read_text()),json.loads(key.read_text())['public_key'])
        if profile and (payload.get('version')!=2 or payload.get('customer_id')!=profile['customer_id'] or payload.get('profile_id')!=profile['profile_id']):raise ValueError('Licence belongs to a different customer build profile.')
        return payload|{'valid':True,'production':True}
    except FileNotFoundError:return {'valid':False,'production':True,'edition':'Activation required','reason':'Licence file missing.'}
    except ValueError as e:return {'valid':False,'production':True,'edition':'Activation required','reason':str(e)}
    except Exception:return {'valid':False,'production':True,'edition':'Activation required','reason':'Licence signature, issuer key or file is invalid.'}
