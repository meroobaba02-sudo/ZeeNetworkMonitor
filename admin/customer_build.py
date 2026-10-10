"""Owner Windows build runner. Operates in a disposable checkout; public inputs only."""
import argparse,base64,hashlib,json,os,re,shutil,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zee.build_profile import verify_profile,digest
from zee.core import VERSION
from admin.issuer import write_atomic

BLOCKED={'.git','dist','build','release','__pycache__','.pytest_cache','.venv','venv'}

def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()

def verify_report(report,folder):
    if not isinstance(report,dict) or report.get('type')!='zee-customer-build-result' or report.get('status')!='passed':raise ValueError('Expected a successful build report.')
    verify_profile(report['profile_document'],report['issuer_public']['public_key'])
    if report['profile_id']!=report['profile_document']['payload']['profile_id'] or not re.fullmatch(r'\d+\.\d+\.\d+',report['version']):raise ValueError('Build profile/version mismatch.')
    if report['checks']!={'tests':True,'frozen_launch':True,'content_audit':True}:raise ValueError('Required build checks missing.')
    if not isinstance(report['artifacts'],list) or not 1<=len(report['artifacts'])<=2:raise ValueError('Invalid artifacts.')
    for a in report['artifacts']:
        if set(a)!={'name','sha256','bytes','kind'} or a['kind'] not in ('portable','installer'):raise ValueError('Invalid artifact entry.')
        if not re.fullmatch('[A-Za-z0-9_.-]{1,180}',a['name']) or a['name'] in ('.','..'):raise ValueError('Unsafe artifact filename.')
        path=folder/a['name']
        if path.is_symlink() or path.resolve().parent!=folder.resolve():raise ValueError('Artifact outside selected folder.')
        if type(a['bytes']) is not int or not 0<a['bytes']<=512*1048576 or path.stat().st_size!=a['bytes'] or hash_file(path)!=a['sha256']:raise ValueError('Artifact size/hash mismatch.')
    return report

def run(source,profile_path,public_path,output,iscc=None):
    if os.name!='nt':raise RuntimeError('Customer EXE builds require Windows and the pinned Python/PyInstaller toolchain.')
    source=Path(source).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    if (output/'build-result.json').exists():raise ValueError('Choose a new empty result folder; previous release history must be preserved.')
    for path in (profile_path,public_path):
        if Path(path).stat().st_size>4*1048576:raise ValueError('Build input too large.')
    document=json.loads(Path(profile_path).read_text());public=json.loads(Path(public_path).read_text());profile=verify_profile(document,public['public_key'])
    if iscc and any(c in profile['branding']['app_name'] for c in '<>{};\\/:"|?*'):raise ValueError('Installer app name contains unsupported filename/directive characters.')
    if not (source/'ZeeNetworkMonitor.spec').is_file():raise ValueError('Select the project source folder.')
    report={'type':'zee-customer-build-result','profile_id':profile['profile_id'],'version':VERSION,'status':'failed','profile_document':document,'issuer_public':{'public_key':public['public_key']},'checks':{'tests':False,'frozen_launch':False,'content_audit':False},'artifacts':[],'started':time.time(),'platform':sys.platform,'hardware_test':'Not performed','provenance':'Local runner report; owner imports and attests. Not a remote CI attestation.'}
    log=output/'build.log'
    def command(args,cwd,timeout=600,env=None):
        with log.open('ab') as f:
            result=subprocess.run(args,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,env=env)
        if result.returncode:raise RuntimeError('Build step failed; review build.log.')
    try:
        with tempfile.TemporaryDirectory(prefix='zee-customer-build-') as tmp:
            work=Path(tmp)/'source'
            def ignore(directory,names):
                return [n for n in names if n in BLOCKED or n.endswith(('.pem','.dpapi','.sqlite3','.db','.zas')) or 'issuer-private' in n or Path(directory,n).is_symlink()]
            shutil.copytree(source,work,ignore=ignore)
            allowed_assets={'icon.ico','icon.png','alarm.wav','region_map.json.gz','issuer-public.json','customer-profile.json'}
            for asset in (work/'assets').iterdir():
                if asset.name not in allowed_assets:raise ValueError('Unreviewed build asset: '+asset.name)
            env=os.environ.copy();env['QT_QPA_PLATFORM']='offscreen'
            # Regression tests use the unprovisioned client; customer-specific checks follow below.
            for name in ('issuer-public.json','customer-profile.json'):(work/'assets'/name).unlink(missing_ok=True)
            command([sys.executable,'-m','pytest','-q','--junitxml='+str(output/'tests.xml')],work,env=env);report['checks']['tests']=True
            write_atomic(work/'assets/customer-profile.json',json.dumps(document).encode());write_atomic(work/'assets/issuer-public.json',json.dumps({'public_key':public['public_key']}).encode())
            file=work/'zee/licensing.py';code=file.read_text().replace('REQUIRE_ISSUER=False','REQUIRE_ISSUER=True').replace("EXPECTED_PROFILE_SHA256=''",'EXPECTED_PROFILE_SHA256='+repr(digest(document)));file.write_text(code)
            command([sys.executable,'-m','PyInstaller','--clean','--noconfirm','ZeeNetworkMonitor.spec'],work,env=env)
            dist=work/'dist/ZeeNetworkMonitor';smoke=Path(tmp)/'smoke'
            command([str(dist/'ZeeNetworkMonitor.exe'),'--smoke-test','--data-dir',str(smoke)],work,timeout=60,env=env)
            if not (smoke/'smoke-ok.txt').is_file():raise RuntimeError('Customer frozen launch marker missing.')
            smoke_state=json.loads((smoke/'customer-build-smoke.json').read_text())
            if not smoke_state['require_issuer'] or smoke_state['profile_digest']!=digest(document) or smoke_state['profile_id']!=profile['profile_id'] or smoke_state['branding']!=profile['branding'] or not smoke_state['licence']['production'] or smoke_state['licence']['valid']:raise RuntimeError('Customer profile/activation enforcement smoke failed.')
            report['checks']['frozen_launch']=True
            for p in dist.rglob('*'):
                if p.is_file() and (p.suffix.lower() in ('.py','.pyw','.pem','.dpapi','.sqlite3','.db','.zas') or 'issuer-private' in p.name):raise RuntimeError('Unexpected customer runtime file: '+p.name)
            report['checks']['content_audit']=True
            name='ZeeCustomer-'+profile['profile_id']+'-v'+VERSION+'.zip'
            with zipfile.ZipFile(output/name,'w',zipfile.ZIP_DEFLATED) as z:
                for p in dist.rglob('*'):
                    if p.is_file():z.write(p,str(p.relative_to(dist.parent)))
            artifacts=[('portable',output/name)]
            if iscc:
                compiler=Path(iscc).resolve()
                if not compiler.is_file():raise ValueError('Inno Setup compiler missing.')
                iss=(work/'installer/ZeeNetworkMonitor.iss').read_text()
                title=profile['branding']['app_name']
                for token in ('\n','\r','{','}',';'):
                    if token in title:raise ValueError('Installer app name cannot contain braces or semicolons.')
                iss=iss.replace('A677BBD3-90CC-4BCE-9DBA-A13F709DBB48',profile['profile_id'].upper()).replace('Zee Network Monitor',title).replace('Programs\\ZeeNetworkMonitor','Programs\\ZeeCustomer-'+profile['profile_id'])
                iss=iss.replace('OutputBaseFilename=ZeeNetworkMonitor-Setup-Windows-v'+VERSION,'OutputBaseFilename=ZeeCustomer-'+profile['profile_id']+'-Setup-v'+VERSION)
                (work/'release').mkdir(exist_ok=True);(work/'installer/ZeeNetworkMonitor.iss').write_text(iss,encoding='utf-8-sig');command([str(compiler),str(work/'installer/ZeeNetworkMonitor.iss')],work)
                name='ZeeCustomer-'+profile['profile_id']+'-Setup-v'+VERSION+'.exe';shutil.copy(work/'release'/name,output/name);artifacts.append(('installer',output/name))
            import xml.etree.ElementTree as ET
            suites=list(ET.parse(output/'tests.xml').getroot().iter('testsuite'));report['test_counts']={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
            if report['test_counts']['failures'] or report['test_counts']['errors']:raise RuntimeError('Regression report contains failures.')
            report['artifacts']=[{'name':p.name,'sha256':hash_file(p),'bytes':p.stat().st_size,'kind':kind} for kind,p in artifacts];report['status']='passed'
            verify_report(report,output)
        return report
    finally:
        report['finished']=time.time();write_atomic(output/'build-result.json',json.dumps(report,indent=2).encode())

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True,type=Path);parser.add_argument('--profile',required=True,type=Path);parser.add_argument('--public',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--iscc',type=Path);args=parser.parse_args()
    try:run(args.source,args.profile,args.public,args.output,args.iscc)
    except Exception as e:print(str(e),file=sys.stderr);raise SystemExit(1)
