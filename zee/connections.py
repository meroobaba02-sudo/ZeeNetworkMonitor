"""Strict URL validation, bounded HTTP(S)/RTSP service checks, no web auto-login."""
import http.client,socket,ssl,urllib.parse,time

def validate_url(url,schemes=('http','https')):
    u=urllib.parse.urlsplit(url)
    if u.scheme not in schemes or not u.hostname or u.username or u.password or u.fragment or any(ord(c)<32 for c in url):raise ValueError('Use an HTTP/HTTPS (or supported RTSP) URL without embedded credentials or fragments.')
    try:port=u.port
    except ValueError:raise ValueError('Invalid port.')
    if port is not None and not 1<=port<=65535:raise ValueError('Invalid port.')
    return u

def connection(url,source='',timeout=5):
    u=validate_url(url);kwargs={'timeout':timeout}
    if source:kwargs['source_address']=(source,0)
    cls=http.client.HTTPSConnection if u.scheme=='https' else http.client.HTTPConnection
    return cls(u.hostname,u.port,**kwargs),u.path+('?' + u.query if u.query else '') or '/'

def request(url,source='',method='GET',headers=None,max_bytes=4096,timeout=5):
    c,path=connection(url,source,timeout)
    try:
        c.request(method,path,headers=headers or {});r=c.getresponse();body=r.read(max_bytes+1)
        return r.status,body[:max_bytes]
    finally:c.close()

def service_check(url,source=''):
    u=validate_url(url,('http','https','rtsp'))
    if u.scheme=='rtsp':
        with socket.create_connection((u.hostname,u.port or 554),timeout=4,source_address=(source,0) if source else None) as s:
            s.sendall(('OPTIONS '+url+' RTSP/1.0\r\nCSeq: 1\r\n\r\n').encode());reply=s.recv(4096)
            line=reply.split(b'\r\n',1)[0]
            if line.startswith(b'RTSP/1.0 200'):return 'RTSP service responding (video not tested)'
            if line.startswith(b'RTSP/1.0 401'):return 'RTSP authentication required (video not tested)'
            return 'RTSP response not accepted'
    code,_=request(url,source)
    if 200<=code<400:return f'HTTP service responding ({code})'
    if code in (401,403):return f'Authentication required ({code})'
    return f'HTTP error ({code})'

def management_url(d):
    if d.management_url:return d.management_url
    if not d.host:raise ValueError('Configure the device host first.')
    return 'http://'+('['+d.host+']' if ':' in d.host else d.host)+'/'
