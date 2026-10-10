"""Offline owner-signed installer verification; never downloads or executes automatically."""
import base64,hashlib,re
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .licensing import canonical,PRODUCT

def verify_update(document,public,profile_id,current,installer):
    if not isinstance(document,dict) or set(document)!={'payload','signature'}:raise ValueError('Malformed update manifest.')
    p=document['payload'];Ed25519PublicKey.from_public_bytes(base64.b64decode(public,validate=True)).verify(base64.b64decode(document['signature'],validate=True),canonical(p))
    if set(p)!={'type','version','product','profile_id','app_version','filename','sha256','bytes'} or p['type']!='zee-offline-update' or p['version']!=1 or p['product']!=PRODUCT or p['profile_id']!=profile_id:raise ValueError('Update belongs to another customer profile.')
    if not re.fullmatch(r'\d+\.\d+\.\d+',p['app_version']) or tuple(map(int,p['app_version'].split('.')))<=tuple(map(int,current.split('.'))):raise ValueError('Update is not newer than this application.')
    path=Path(installer)
    if not re.fullmatch('[A-Za-z0-9_.-]{1,180}',p['filename']) or path.name!=p['filename'] or path.suffix.lower()!='.exe':raise ValueError('Select the matching installer EXE.')
    if type(p['bytes']) is not int or not 0<p['bytes']<=512*1048576 or path.stat().st_size!=p['bytes']:raise ValueError('Installer size mismatch.')
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    if h.hexdigest()!=p['sha256']:raise ValueError('Installer integrity check failed.')
    return p
