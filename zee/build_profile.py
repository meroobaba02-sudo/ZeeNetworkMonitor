"""Public signed customer build profiles; no private issuer material."""
import base64,json,re,hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .licensing import canonical,PRODUCT
from .entitlements import validate

def verify_profile(document,public):
    if not isinstance(document,dict) or set(document)!={'payload','signature'}:raise ValueError('Malformed build profile.')
    p=document['payload']
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public,validate=True)).verify(base64.b64decode(document['signature'],validate=True),canonical(p))
    if not isinstance(p,dict) or set(p)!={'type','version','product','profile_id','customer_id','package_id','customer','branding','entitlements'} or p['type']!='zee-customer-build' or p['version']!=1 or p['product']!=PRODUCT:raise ValueError('Unsupported customer build profile.')
    for k in ('profile_id','customer_id','package_id'):
        if not isinstance(p[k],str) or not re.fullmatch('[a-f0-9-]{36}',p[k]):raise ValueError('Invalid profile reference.')
    if not isinstance(p['customer'],str) or not 1<=len(p['customer'])<=200:raise ValueError('Invalid customer name.')
    validate(p['entitlements']);b=p['branding']
    if not isinstance(b,dict) or set(b)!={'app_name','watermark','logo_png'}:raise ValueError('Invalid branding.')
    for k,limit in [('app_name',100),('watermark',200)]:
        if not isinstance(b[k],str) or not 1<=len(b[k])<=limit or any(ord(c)<32 for c in b[k]):raise ValueError('Invalid branding text.')
    if not isinstance(b['logo_png'],str) or len(b['logo_png'])>3*1048576:raise ValueError('Logo too large.')
    if b['logo_png']:
        raw=base64.b64decode(b['logo_png'],validate=True)
        import struct
        if len(raw)<24 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':raise ValueError('Invalid PNG logo.')
        width,height=struct.unpack('>II',raw[16:24])
        if not 1<=width<=2048 or not 1<=height<=2048:raise ValueError('Logo dimensions too large.')
        from PySide6.QtGui import QImage
        if QImage.fromData(raw,'PNG').isNull():raise ValueError('Invalid PNG image.')
    return p

def digest(document):return hashlib.sha256(canonical(document)).hexdigest()
