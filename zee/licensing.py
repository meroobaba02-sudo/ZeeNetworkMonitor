"""Offline Ed25519 verification. Production issuer public key must be provisioned by owner."""
import json,hashlib,base64,time,os,sys,uuid,math
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
PRODUCT='ZeeNetworkMonitor'

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
    if payload.get('product')!=PRODUCT or payload.get('version')!=1:raise ValueError('Wrong licence product/version.')
    if payload.get('machine')!=(machine or fingerprint()):raise ValueError('This licence belongs to another PC.')
    if type(payload.get('activations')) is not int or payload['activations']!=1:raise ValueError('Each licence file authorizes exactly one machine.')
    now=time.time() if now is None else now
    if payload.get('expires') is not None and (type(payload['expires']) not in (int,float) or not math.isfinite(payload['expires']) or now>payload['expires']):raise ValueError('Licence expired.')
    if type(payload.get('issued')) not in (int,float) or not math.isfinite(payload['issued']) or now<payload['issued']-86400:raise ValueError('Licence not yet valid; check the clock.')
    return payload

def public_key_path():return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets/issuer-public.json'

def status(data_dir):
    key=public_key_path()
    if not key.exists():return {'valid':True,'edition':'Owner evaluation — issuer not provisioned','production':False}
    try:
        payload=verify(json.loads((Path(data_dir)/'license.json').read_text()),json.loads(key.read_text())['public_key'])
        return payload|{'valid':True,'production':True}
    except FileNotFoundError:return {'valid':False,'production':True,'edition':'Activation required','reason':'Licence file missing.'}
    except ValueError as e:return {'valid':False,'production':True,'edition':'Activation required','reason':str(e)}
    except Exception:return {'valid':False,'production':True,'edition':'Activation required','reason':'Licence signature, issuer key or file is invalid.'}
