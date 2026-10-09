"""Saved UnfoldUnrest scenes: isolated asset store and explicit archive linkage."""
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import struct
import threading
import time

SCHEMA_VERSION=1
UPSTREAM='7a3163c74785d3942603587da6456adf297a90cc'
SAFE_ID=re.compile(r'^[a-zA-Z0-9_-]{1,80}$')
LIMIT=96*1024*1024
QUALITY={'scale':'estimated_from_assumed_camera_height','coordinates':'x_along_ride_y_left_z_up',
         'units':'estimated_metres','detector':'imported_open_vocabulary',
         'limits':['Standing cannot distinguish parking from waiting in a queue.',
                   'Objects are aggregate footprints, not per-frame vehicle trajectories.',
                   'Imported sightlines are unverified estimates; crossing classifications may be false positives.',
                   'No legal-distance verdict or measured traffic delay is established.']}
SPATIAL_INTERFACE={'connected':False,'name':'SpatialScene','schema_version':SCHEMA_VERSION,
                   'import':'python spatial_import.py RUN_DIRECTORY --bindings bindings.json',
                   'live_reconstruction':False}

class SpatialError(ValueError):
    def __init__(self,message='Saved map unavailable.',status=400):super().__init__(message);self.status=status


def ident(value):
    if not isinstance(value,str) or not SAFE_ID.fullmatch(value):raise SpatialError('Invalid scene or asset ID.')
    return value


def number(value):
    if type(value) not in {int,float} or not math.isfinite(value) or abs(value)>1e6:raise SpatialError('Invalid spatial number.')
    return float(value)


def vector(value,n=2):
    if not isinstance(value,list) or len(value)!=n:raise SpatialError('Invalid spatial coordinate.')
    return [number(v) for v in value]


def poly(value):
    if not isinstance(value,list) or len(value)!=4:raise SpatialError('Invalid object footprint.')
    p=[vector(v) for v in value]
    if math.hypot(p[1][0]-p[0][0],p[1][1]-p[0][1])<.001 or math.hypot(p[2][0]-p[1][0],p[2][1]-p[1][1])<.001:raise SpatialError('Degenerate object footprint.')
    return p


def safe_file(root,name):
    if not isinstance(name,str) or '\\' in name:raise SpatialError('Invalid asset path.')
    path=PurePosixPath(name)
    if path.is_absolute() or any(p in {'..','.'} for p in path.parts) or not path.parts:raise SpatialError('Invalid asset path.')
    file=(root/name).resolve()
    if not file.is_relative_to(root.resolve()) or not file.is_file() or file.stat().st_size>32*1024*1024:raise SpatialError('Missing or oversized map asset.')
    return file


def read_json(path):
    if path.stat().st_size>8*1024*1024:raise SpatialError('Map metadata too large.')
    try:return json.loads(path.read_text(),parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except (OSError,UnicodeError,ValueError):raise SpatialError('Invalid map metadata.') from None


class SceneStore:
    def __init__(self,root=None,bucket=None,client=None):
        self.root=Path(root or os.environ.get('STREETTWIN_SPATIAL_DIR',Path.home()/'.local/share/street-twin/spatial'))
        self.bucket=bucket or os.environ.get('STREETTWIN_SPATIAL_BUCKET')
        self._client=client;self._cache=None;self._at=0;self.lock=threading.RLock()
        if self.bucket and (not re.fullmatch(r'team-[0-9]+-street-twin-spatial',self.bucket)):
            raise SpatialError('Use a dedicated StreetTwin map bucket.')

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config
            self._client=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT'],
                aws_access_key_id=os.environ['ACCESS_KEY'],aws_secret_access_key=os.environ['SECRET_KEY'],
                config=Config(signature_version='s3v4',s3={'addressing_style':'path'},connect_timeout=10,read_timeout=30,retries={'max_attempts':2}))
        return self._client

    def ensure_bucket(self):
        if not self.bucket:return
        from botocore.exceptions import ClientError
        try:self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            if error.response.get('Error',{}).get('Code') not in {'404','NoSuchBucket','NotFound'}:raise SpatialError('Map storage unavailable.',503) from None
            try:self.client.create_bucket(Bucket=self.bucket)
            except Exception:raise SpatialError('Cannot create the dedicated map bucket.',503) from None

    def get(self,key):
        if self.bucket:
            try:
                response=self.client.get_object(Bucket=self.bucket,Key=key)
                if response['ContentLength']>LIMIT:raise SpatialError('Map file exceeds size limit.')
                return response['Body'].read()
            except SpatialError:raise
            except Exception:raise SpatialError('Saved map unavailable.',404) from None
        path=self.root/key
        if not path.is_file():raise SpatialError('Saved map unavailable.',404)
        return path.read_bytes()

    def put(self,key,data,mime):
        if self.bucket:
            self.client.put_object(Bucket=self.bucket,Key=key,Body=data,ContentType=mime)
        else:
            path=self.root/key;path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix(path.suffix+'.part');temp.write_bytes(data);temp.replace(path)
        self._cache=None

    def index(self):
        with self.lock:
            if self._cache is not None and time.monotonic()-self._at<10:return self._cache
            try:data=json.loads(self.get('index.json'))
            except SpatialError as e:
                if e.status!=404:raise
                data={'schema_version':SCHEMA_VERSION,'scenes':[]}
            if not isinstance(data,dict) or not isinstance(data.get('scenes'),list):raise SpatialError('Invalid scene index.',503)
            self._cache=data;self._at=time.monotonic();return data

    def scene(self,scene_id):
        ident(scene_id)
        entry=next((s for s in self.index()['scenes'] if s['id']==scene_id),None)
        if entry is None:raise SpatialError('Saved map unavailable.',404)
        data=json.loads(self.get(f'{scene_id}/{entry["hash"]}/scene.json'))
        if data.get('hash')!=entry['hash'] or data.get('schema_version')!=SCHEMA_VERSION:raise SpatialError('Invalid saved map.',503)
        return data

    def asset(self,scene_id,asset_id):
        ident(asset_id);scene=self.scene(scene_id)
        asset=scene['assets'].get(asset_id)
        if asset is None:raise SpatialError('Map asset unavailable.',404)
        body=self.get(f'{scene_id}/{scene["hash"]}/{asset_id}')
        if hashlib.sha256(body).hexdigest()!=asset['sha256']:raise SpatialError('Map asset checksum failed.',503)
        return body,asset['mime'],asset['sha256']

    def version(self,scene_id):return self.scene(scene_id)['hash'] if scene_id else ''

    def publish(self,scene,bodies):
        self.ensure_bucket()
        key=f'{scene["id"]}/{scene["hash"]}'
        for asset_id,body in bodies.items():self.put(key+'/'+asset_id,body,scene['assets'][asset_id]['mime'])
        self.put(key+'/scene.json',json.dumps(scene,allow_nan=False).encode(),'application/json')
        index=self.index();entries=[s for s in index['scenes'] if s['id']!=scene['id']]
        entries.append({k:scene[k] for k in ['id','name','hash','duration','schema_version']})
        entries[-1]['linked']=bool(scene['bindings'])
        self.put('index.json',json.dumps({'schema_version':SCHEMA_VERSION,'scenes':entries}).encode(),'application/json')

    def context(self,scene_id,*,segment_id=None,start=None,end=None,object_id=None):
        scene=self.scene(scene_id);bindings=scene['bindings'];binding=None
        if segment_id:
            binding=next((b for b in bindings if b['segment_id']==segment_id),None)
            if binding is None:raise SpatialError('Clip is not linked to this map.',404)
            start=binding['scene_start_sec'];end=binding['scene_end_sec']
        else:
            start=0 if start is None else number(start);end=scene['duration'] if end is None else number(end)
        if start<0 or end<start or end>scene['duration']+.01:raise SpatialError('Invalid scene interval.')
        objects=[o for o in scene['objects'] if o['t0']<=end and o['t1']>=start and (object_id is None or o['id']==object_id)][:80]
        facts=[]
        for o in objects:
            # Only directly observed aggregates are model facts. Upstream crossing risk
            # predictions/rays remain visual estimates, excluded from policy admission.
            facts.append({'fact_id':hashlib.sha256(f'{scene["hash"]}:{o["id"]}:{segment_id or "unlinked"}'.encode()).hexdigest()[:16],
                'scene_id':scene_id,'scene_hash':scene['hash'],'object_id':o['id'],'segment_id':segment_id,
                'label':o['label'],'group':o['group'],'motion':o['motion'],
                'xy':o['xy'],'footprint':o.get('footprint'),'seen':o['seen'],
                'scene_start_sec':max(start,o['t0']),'scene_end_sec':min(end,o['t1']),
                'basis':'spatial_estimate','units':'estimated_metres','eligible_for_reasoning':bool(binding)})
        return {'scene_id':scene_id,'scene_hash':scene['hash'],'quality':scene['quality'],
                'linked':bool(binding),'binding':binding,'facts':facts,'truncated':len(objects)==80}


def import_bundle(directory,store,*,scene_id=None,bindings=None,vss=None):
    root=Path(directory).resolve();app=root/'app' if (root/'app/ride.json').is_file() else root
    raw=read_json(safe_file(app,'ride.json'))
    if not isinstance(raw,dict):raise SpatialError('Invalid ride document.')
    run=read_json(root/'run.json') if (root/'run.json').is_file() else {}
    if run.get('status','done')!='done':raise SpatialError('Import a completed run.')
    sid=ident(scene_id or str(run.get('id') or root.name));assets={};bodies={};total=0
    def asset(aid,name,*,mime=None):
        nonlocal total
        file=safe_file(app,name)
        if file.suffix.lower() not in {'.jpg','.jpeg','.png','.bin'}:raise SpatialError('Only map images and point binaries can be imported.')
        body=file.read_bytes();total+=len(body)
        if total>LIMIT:raise SpatialError('Map bundle exceeds size limit.')
        bodies[aid]=body;assets[aid]={'sha256':hashlib.sha256(body).hexdigest(),'size':len(body),
            'mime':mime or mimetypes.guess_type(name)[0] or 'application/octet-stream',
            'url':f'api/spatial/scenes/{sid}/assets/{aid}'}
        return body
    asset('ortho',raw.get('ortho','ortho.jpg'))
    cloud=raw.get('cloud')
    if cloud:
        pb=asset('points',cloud['points']);cb=asset('colours',cloud['colours'])
        n=len(pb)//12
        if n<1 or n>1_000_000 or len(pb)!=n*12 or len(cb)!=n*3 or cloud.get('n',n)!=n:raise SpatialError('Invalid point cloud lengths.')
        for xyz in struct.iter_unpack('<fff',pb):
            if any(not math.isfinite(v) or abs(v)>1e6 for v in xyz):raise SpatialError('Invalid point cloud coordinate.')
    E=raw.get('extent',{});extent={k:number(E[k]) for k in ['x0','x1','y0','y1']}
    if extent['x1']<=extent['x0'] or extent['y1']<=extent['y0']:raise SpatialError('Invalid street extent.')
    path=raw.get('path')
    if not isinstance(path,list) or not 2<=len(path)<=50000:raise SpatialError('Invalid rider route.')
    path=[{k:number(p[k]) for k in ['t','x','y','h']} for p in path]
    if path[0]['t']<0 or any(b['t']<=a['t'] for a,b in zip(path,path[1:])):raise SpatialError('Route timestamps must increase.')
    duration=number(raw.get('stats',{}).get('duration',path[-1]['t']))
    if duration<=0 or duration<path[-1]['t'] or duration>3600:raise SpatialError('Invalid scene duration.')
    raw_objects=raw.get('objects',[])
    if not isinstance(raw_objects,list) or len(raw_objects)>1000:raise SpatialError('Too many scene objects.')
    objects=[];known=set()
    for entry in raw_objects:
        oid=ident(str(entry['id']))
        if oid in known:raise SpatialError('Duplicate object ID.')
        known.add(oid);group=str(entry.get('group','unknown'))[:80];seen=int(number(entry.get('seen',0)))
        passed=number(entry.get('passed',0));spread=number(entry.get('spread',0))
        motion='unknown'
        if group=='vehicle' and seen>=3 and passed>=4:
            if entry.get('parked') is True and spread<=1.6:motion='standing'
            elif entry.get('parked') is False and spread>1.6:motion='moving'
        t0=number(entry.get('t0',0));t1=number(entry.get('t1',duration))
        if t0<0 or t1<t0 or t1>duration+.1:raise SpatialError('Invalid object observation interval.')
        o={'id':oid,'group':group,'label':str(entry.get('label') or group)[:100],
            'seen':seen,'xy':vector(entry['xy']),'spread':spread,'motion':motion,'t0':t0,'t1':min(duration,t1)}
        footprint=entry.get('footprint') or entry.get('rect')
        if footprint:o['footprint']=poly(footprint)
        if entry.get('height') is not None:o['height']=number(entry['height'])
        if entry.get('t_pass') is not None:o['t_pass']=number(entry['t_pass'])
        if entry.get('evidence'):
            aid='evidence_'+oid;asset(aid,entry['evidence']);o['evidence_asset']=aid
        aps=[]
        for a in entry.get('approaches',[])[:4]:
            rays=[{'to':vector(r['to']),'clear':r.get('clear') is True} for r in a.get('rays',[])[:200]]
            aps.append({'waiting':vector(a['waiting']),'covered':a.get('covered') is True,'rays':rays})
        if aps:o['approaches']=aps
        objects.append(o)
    normalized=[];manifest=bindings or {}
    if manifest:
        if not isinstance(manifest,dict) or not isinstance(manifest.get('bindings'),list) or not vss:raise SpatialError('Archive bindings need a manifest and VSS verification.')
        vss.archive()
        for b in manifest['bindings']:
            seg=b.get('segment_id','')
            if not re.fullmatch('[a-f0-9]{20}',seg):raise SpatialError('Invalid archive segment ID.')
            try:row=vss.get_segment(seg)
            except Exception:raise SpatialError('Unknown archive segment.') from None
            expected=b.get('original_video') or manifest.get('original_video')
            if not expected or row.get('original_video')!=expected:raise SpatialError('Archive parent does not match binding manifest.')
            start=number(b['scene_start_sec']);end=number(b['scene_end_sec']);offset=number(b.get('clip_start_sec',0))
            length=number(row['segment_end_sec'])-number(row['segment_start_sec'])
            if start<0 or end<=start or end>duration+.01 or offset<0 or offset+end-start>length+.01:raise SpatialError('Invalid scene-to-clip interval.')
            normalized.append({'segment_id':seg,'scene_start_sec':start,'scene_end_sec':end,'clip_start_sec':offset,
                'original_video':expected,'camera_id':row.get('camera_id'),'location':row.get('location')})
        normalized.sort(key=lambda b:b['scene_start_sec'])
        if len({b['segment_id'] for b in normalized})!=len(normalized) or any(b['scene_start_sec']<a['scene_end_sec'] for a,b in zip(normalized,normalized[1:])):raise SpatialError('Bindings overlap or repeat a segment.')
    scene={'schema_version':SCHEMA_VERSION,'id':sid,'name':str(run.get('name') or sid)[:120],
           'viewer_revision':UPSTREAM,'source_revision':str(run.get('code_version') or 'unknown')[:80],'duration':duration,'extent':extent,'path':path,'objects':objects,
           'cam_h':number(raw.get('cam_h',1.1)),'hfov':number(raw.get('hfov',90)),
           'quality':QUALITY,'bindings':normalized,'assets':assets}
    if not 0<scene['cam_h']<10 or not 1<scene['hfov']<180:raise SpatialError('Invalid camera assumptions.')
    scene['hash']=hashlib.sha256(json.dumps(scene,sort_keys=True,allow_nan=False).encode()).hexdigest()
    store.publish(scene,bodies)
    return scene
