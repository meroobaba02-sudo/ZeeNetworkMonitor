"""Small, explicit vector map downloads. No tile scraping or automatic requests."""
import json
import gzip
import math
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

BBOX = (31.25, 69.15, 31.90, 69.65)  # south, west, north, east
ENDPOINT = 'https://overpass-api.de/api/interpreter'
LIMIT = 12_000_000
ATTRIBUTION = '© OpenStreetMap contributors • ODbL 1.0'

def mercator(lat):
    return math.log(math.tan(math.pi/4 + math.radians(lat)/2))

def position(lat, lon, bbox=BBOX):
    south,west,north,east=bbox
    return (lon-west)/(east-west),(mercator(north)-mercator(lat))/(mercator(north)-mercator(south))

def coordinates(x,y,bbox=BBOX):
    south,west,north,east=bbox
    m=mercator(north)-y*(mercator(north)-mercator(south))
    return math.degrees(2*math.atan(math.exp(m))-math.pi/2),west+x*(east-west)

def validate(data):
    if not isinstance(data,dict) or data.get('format') != 'zee-vector-1':
        raise ValueError('Select a Zee vector map JSON exported by this app.')
    bbox=data.get('bbox',[])
    if len(bbox)!=4 or not all(isinstance(n,(int,float)) and math.isfinite(n) for n in bbox):
        raise ValueError('Invalid map bounds.')
    s,w,n,e=bbox
    if not (-85 <= s < n <= 85 and -180 <= w < e <= 180 and n-s<=2 and e-w<=2):
        raise ValueError('Map must be a local area, at most 2° wide/high.')
    features=data.get('features')
    if not isinstance(features,list) or not features or len(features)>30000:
        raise ValueError('Map contains no features or is too large.')
    points=0
    for f in features:
        if not isinstance(f,dict):raise ValueError('Invalid map feature.')
        if f.get('kind') not in ('road','water','place') or not isinstance(f.get('name',''),str):
            raise ValueError('Invalid map feature.')
        geom=f.get('points')
        if not isinstance(geom,list) or len(geom)>20000:
            raise ValueError('Invalid map geometry.')
        points+=len(geom)
        if points>300000: raise ValueError('Too many map points.')
        for xy in geom:
            if not isinstance(xy,list) or len(xy)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in xy) or not -85<=xy[0]<=85 or not -180<=xy[1]<=180:
                raise ValueError('Invalid geographic coordinate.')
    return data

def load(path):
    if Path(path).stat().st_size > LIMIT: raise ValueError('Map file exceeds 12 MB.')
    if str(path).endswith('.gz'):
        with gzip.open(path,'rb') as f: raw=f.read(LIMIT+1)
        if len(raw)>LIMIT: raise ValueError('Map exceeds 12 MB when decompressed.')
        return validate(json.loads(raw))
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))

def save(path,data):
    validate(data)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    os.replace(tmp,path)

def download(bbox=BBOX,endpoint=ENDPOINT):
    parsed=urllib.parse.urlparse(endpoint)
    if parsed.scheme!='https' or not parsed.hostname:
        raise ValueError('Map endpoint must be an HTTPS Overpass interpreter URL.')
    b=','.join(str(v) for v in bbox)
    query=f'[out:json][timeout:25][maxsize:67108864];(way[highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service)$"]({b});way[waterway~"^(river|stream)$"]({b});node[place~"^(city|town|village|hamlet)$"]({b}););out geom;'
    request=urllib.request.Request(endpoint,data=urllib.parse.urlencode({'data':query}).encode(),headers={'User-Agent':'ZeeNetworkMonitor/0.3 (+https://github.com/meroobaba02-sudo/ZeeNetworkMonitor)','Accept':'application/json'})
    start=time.monotonic()
    with urllib.request.urlopen(request,timeout=35) as response:
        chunks=[];size=0
        while True:
            chunk=response.read(65536)
            if not chunk:break
            size+=len(chunk)
            if size>LIMIT or time.monotonic()-start>55: raise ValueError('Map download exceeded size/time limit.')
            chunks.append(chunk)
    raw=json.loads(b''.join(chunks))
    if raw.get('remark'):raise ValueError('Map server could not complete the request. Try later.')
    features=[]
    for e in raw.get('elements',[]):
        tags=e.get('tags',{});name=tags.get('name:en',tags.get('name',''))
        if e.get('type')=='node' and 'place' in tags:
            features.append({'kind':'place','name':name,'points':[[e['lat'],e['lon']]]})
        elif e.get('type')=='way':
            geom=[[g['lat'],g['lon']] for g in e.get('geometry',[]) if 'lat' in g and 'lon' in g]
            if len(geom)>1:features.append({'kind':'road' if 'highway' in tags else 'water','name':name,'class':tags.get('highway',''),'points':geom})
    return validate({'format':'zee-vector-1','bbox':list(bbox),'attribution':ATTRIBUTION,'downloaded_at':time.time(),'features':features})
