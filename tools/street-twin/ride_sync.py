"""Pull completed map exports over the teammate's tunnel, using GET requests only."""
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shlex
from urllib.parse import quote,urlparse
import requests
from spatial import SceneStore,SpatialError,import_bundle,read_json,LIMIT
from vss import VSS


def configured(keys,env_file=None):
    for key in keys:
        value=os.environ.get(key)
        if value and value.strip():return value.strip()
    path=Path('/config/ride.token')
    if 'SERVICE_TOKEN' in keys and path.is_file():return path.read_text().strip()
    path=Path(env_file) if env_file else Path(__file__).resolve().parents[2]/'.env'
    values={}
    if path.is_file():
        for line in path.read_text().splitlines():
            key,sep,value=line.strip().removeprefix('export ').partition('=')
            if sep and key.strip() in keys:
                try:parts=shlex.split(value,comments=True)
                except ValueError:raise SpatialError('Invalid token entry in the environment file.') from None
                if len(parts)==1:values[key.strip()]=parts[0]
    return next((values[k] for k in keys if values.get(k)),'')

def token(env_file=None):return configured(('RIDE_TOKEN','SERVICE_TOKEN'),env_file)

def service_url():return configured(('RIDE_URL',))


def pull(base,destination,*,run_id=None,access_token=None,session=None):
    parsed=urlparse(base)
    if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:raise SpatialError('Choose a valid ride service URL.')
    session=session or requests.Session();headers={'Authorization':'Bearer '+access_token} if access_token else {}
    def get(path,*,stream=False):
        try:r=session.get(base.rstrip('/')+path,headers=headers,timeout=(10,40),stream=stream,allow_redirects=False)
        except requests.RequestException:raise SpatialError('Ride service unavailable. Existing maps remain available.',503) from None
        if r.status_code in {401,403}:
            r.close();raise SpatialError('Ride service needs read-only access or a token in /config/ride.token.',401)
        if r.status_code!=200:r.close();raise SpatialError('Ride export unavailable.',503)
        return r
    response=get('/api/manifest')
    try:manifest=response.json()
    except ValueError:raise SpatialError('Invalid ride manifest.') from None
    finally:response.close()
    runs=manifest.get('runs',{})
    eligible=[(rid,entry) for rid,entry in runs.items() if entry.get('run',{}).get('status')=='done' and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',rid)]
    if run_id:eligible=[v for v in eligible if v[0]==run_id]
    eligible.sort(key=lambda v:str(v[1].get('run',{}).get('created','')),reverse=True)
    if not eligible:raise SpatialError('No completed map run available.',404)
    rid,entry=eligible[0];target=Path(destination)/rid;target.mkdir(parents=True,exist_ok=True);total=0;count=0
    for name,info in entry.get('files',{}).items():
        # Upstream manifests use service-root paths; older exports used run-relative paths.
        if name.startswith('runs/'):
            prefix='runs/'+rid+'/'
            if not name.startswith(prefix):raise SpatialError('Manifest asset belongs to another run.')
            name=name[len(prefix):]
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:raise SpatialError('Invalid manifest asset path.')
        # Explicitly exclude videos, logs, model files, geometry npz and service configuration.
        if name!='run.json' and not (name.startswith('app/') and (name=='app/ride.json' or path.suffix.lower() in {'.bin','.jpg','.jpeg','.png'})):continue
        size=info.get('size');checksum=info.get('sha256','')
        if type(size) is not int or not 0<=size<=32*1024*1024 or not re.fullmatch('[a-f0-9]{64}',checksum):raise SpatialError('Invalid manifest checksum or size.')
        total+=size;count+=1
        if total>LIMIT or count>128:raise SpatialError('Ride export exceeds map limits.')
        file=target/name;file.parent.mkdir(parents=True,exist_ok=True)
        if not file.resolve().is_relative_to(target.resolve()):raise SpatialError('Invalid mirror path.')
        if file.is_file() and file.stat().st_size==size and hashlib.sha256(file.read_bytes()).hexdigest()==checksum:continue
        r=get('/runs/'+quote(rid,safe='')+'/'+quote(name,safe='/'),stream=True);temp=file.with_suffix(file.suffix+'.part');digest=hashlib.sha256();received=0
        try:
            with temp.open('wb') as output:
                for chunk in r.iter_content(65536):
                    received+=len(chunk)
                    if received>size:raise SpatialError('Export length mismatch.')
                    output.write(chunk);digest.update(chunk)
            if received!=size or digest.hexdigest()!=checksum:raise SpatialError('Export checksum mismatch.')
            temp.replace(file)
        finally:
            r.close()
            if temp.exists():temp.unlink()
    if not (target/'app/ride.json').is_file():raise SpatialError('Run has no saved viewer export.',404)
    # The manifest records completion even when run.json is absent from the file listing.
    if not (target/'run.json').is_file():(target/'run.json').write_text(json.dumps(entry['run']))
    return target


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',default=os.environ.get('RIDE_URL'))
    p.add_argument('--destination',type=Path,default=Path.home()/'.local/share/street-twin/ride-mirror')
    p.add_argument('--run');p.add_argument('--bindings',type=Path);p.add_argument('--s3',action='store_true')
    p.add_argument('--local',type=Path);args=p.parse_args()
    if not args.url:p.error('Set RIDE_URL or pass --url.')
    if args.s3 and not os.environ.get('STREETTWIN_SPATIAL_BUCKET'):p.error('Set the dedicated STREETTWIN_SPATIAL_BUCKET.')
    if args.s3 and args.local:p.error('Choose local or S3 storage.')
    try:
        directory=pull(args.url,args.destination,run_id=args.run,access_token=token())
        store=SceneStore(root=args.local)
        if not args.s3:store.bucket=None
        bindings=read_json(args.bindings) if args.bindings else None
        scene=import_bundle(directory,store,bindings=bindings,vss=VSS() if bindings else None)
        print(f'Imported {scene["id"]}: {len(scene["objects"])} objects. Video files were excluded.')
    except Exception as e:
        print(str(e) if isinstance(e,SpatialError) else 'Map sync failed; existing imported maps remain available.')
        raise SystemExit(1) from None

if __name__=='__main__':main()
