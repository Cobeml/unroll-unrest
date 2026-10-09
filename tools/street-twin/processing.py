"""Durable archive-to-remote-GPU jobs. No VSS upload or pipeline modification."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from urllib.parse import urlparse

import requests
from ride_sync import pull, token, service_url
from spatial import SpatialError, import_bundle, read_json
from vss import normalize

VERSION = 'unfold-vm-1'
CHUNK = 64 * 1024 * 1024
CLIP_MAX = 4 * 1024**3
ACTIVE = {'queued', 'transferring', 'processing', 'importing', 'waiting'}
QUERIES = {
    'close-call': 'Bicyclist narrowly avoids a vehicle, sudden braking or swerving around an obstruction in the riding path',
    'collision': 'Bicycle collision with a vehicle or pedestrian, visible contact or a cyclist falling',
    'crash': 'Bicycle crash, rider falls or loses control in street traffic',
}


class RideService:
    def __init__(self, base=None, access_token=None, session=None):
        self.base = (base or service_url()).rstrip('/')
        p = urlparse(self.base)
        if p.scheme not in {'http', 'https'} or not p.netloc or p.username or p.password or p.query or p.fragment:
            raise SpatialError('The reconstruction service is not configured.', 503)
        self.token = token() if access_token is None else access_token
        if not self.token:
            raise SpatialError('The reconstruction service token is not configured.', 503)
        self.session = session or requests.Session()

    def request(self, method, path, **kwargs):
        try:
            r = self.session.request(method, self.base + path,
                headers={'Authorization': 'Bearer ' + self.token}, timeout=(10, 90),
                allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise SpatialError('Reconstruction service unreachable. Processing will resume when it returns.', 503) from None
        if r.status_code >= 400:
            status = r.status_code
            r.close()
            raise SpatialError('Reconstruction access denied.' if status in {401,403} else 'Reconstruction request unavailable.', 503)
        if kwargs.get('stream'):
            return r
        try:
            return r.json()
        except ValueError:
            raise SpatialError('Invalid reconstruction response.', 503) from None
        finally:
            r.close()

    def offset(self, rid):
        # Closing a streamed GET reads only headers, never another copy of the clip.
        try:
            r = self.session.get(self.base + '/runs/' + rid + '/clip.mp4',
                headers={'Authorization': 'Bearer ' + self.token}, timeout=(10,30),
                stream=True, allow_redirects=False)
        except requests.RequestException:
            raise SpatialError('Reconstruction service unreachable.', 503) from None
        try:
            if r.status_code == 404: return 0
            if r.status_code != 200: raise SpatialError('Cannot inspect transfer progress.',503)
            n = int(r.headers['Content-Length'])
            if not 0 <= n <= CLIP_MAX: raise ValueError()
            return n
        except (KeyError, ValueError):
            raise SpatialError('Invalid transfer progress.',503) from None
        finally:
            r.close()


class Jobs:
    """One API process + one Recreate worker. Only the worker changes active jobs."""
    def __init__(self, store, vss, remote_factory=RideService):
        self.store, self.vss, self.remote_factory = store, vss, remote_factory
        self.lock = threading.RLock()

    def get(self, jid):
        if not re.fullmatch('[a-f0-9]{24}', jid): raise SpatialError('Run unavailable.',404)
        try: return json.loads(self.store.get('jobs/' + jid + '.json'))
        except SpatialError: raise
        except (ValueError, UnicodeError): raise SpatialError('Run record unavailable.',503) from None

    def save(self, job):
        job['updated_at'] = time.time()
        self.store.put('jobs/' + job['id'] + '.json', json.dumps(job, allow_nan=False).encode(), 'application/json')

    def list(self):
        if self.store.bucket:
            keys = []
            params = {'Bucket':self.store.bucket, 'Prefix':self.store.prefix + 'jobs/'}
            while True:
                page = self.store.client.list_objects_v2(**params)
                keys += [x['Key'][len(self.store.prefix):] for x in page.get('Contents',[]) if x['Key'].endswith('.json')]
                if not page.get('IsTruncated'): break
                params['ContinuationToken'] = page['NextContinuationToken']
        else:
            keys = ['jobs/' + p.name for p in (self.store.root / 'jobs').glob('*.json')]
        return sorted([self.get(Path(k).stem) for k in keys], key=lambda j:j['created_at'], reverse=True)

    def public(self, job):
        return {k:job.get(k) for k in ['id','status','stage','message','created_at','updated_at','source_filename',
            'camera_id','location','selected_segment_id','highlight_sec','remote_run_id','scene_id','result_url',
            'uploaded_bytes','source_bytes','source_sha256','service_version','pipeline_version','summary','analysis_status']}

    def start(self, segment_id):
        if not isinstance(segment_id,str) or not re.fullmatch('[a-f0-9]{20}',segment_id):
            raise SpatialError('Choose an indexed segment.')
        self.vss.archive()
        row = self.vss.get_segment(segment_id)
        if row.get('capture_type') not in {'streets','traffic'} or not row.get('original_video'):
            raise SpatialError('Choose an indexed street or traffic clip.')
        remote = self.remote_factory()
        version = str(remote.request('GET','/health').get('code_version','unknown'))[:80]
        jid = hashlib.sha256((row['original_video'] + ':' + VERSION + ':' + version).encode()).hexdigest()[:24]
        with self.lock:
            try: return self.get(jid)
            except SpatialError as e:
                if e.status != 404: raise
            job = {'id':jid,'status':'queued','stage':'queued','created_at':time.time(),
                'source_filename':row['original_video'].rsplit('/',1)[-1], 'original_video':row['original_video'],
                'camera_id':row.get('camera_id'), 'location':row.get('location'),
                'selected_segment_id':segment_id, 'highlight_sec':float(row.get('segment_start_sec',0)),
                'pipeline_version':VERSION,'service_version':version,'uploaded_bytes':0,
                'message':'Full parent chunk queued for reconstruction.'}
            self.save(job)
            return job

    def retry(self, jid):
        with self.lock:
            job = self.get(jid)
            if job['status'] != 'failed': return job
            job.update(status='queued', retry_remote=True, message='Retry requested.')
            self.save(job)
            return job

    def advance(self, job):
        remote = self.remote_factory()
        # Recover a response lost after POST without submitting the video twice.
        if not job.get('remote_run_id'):
            runs = remote.request('GET','/api/runs')
            existing = next((r for r in runs if r.get('source',{}).get('vm_job_id') == job['id']),None)
            rec = existing or remote.request('POST','/api/runs', json={
                'name':'archive-' + job['id'][:12], 'filename':'clip.mp4',
                'source':{'kind':'vss_indexed_parent','vm_job_id':job['id'],
                    'archive_filename':job['source_filename'],'segment_id':job['selected_segment_id'],
                    'camera_id':job['camera_id'],'location':job['location'],'offset_sec':0}})
            rid = rec.get('id','')
            if not re.fullmatch('[A-Za-z0-9_-]{1,80}',rid): raise SpatialError('Invalid reconstruction run ID.',503)
            job['remote_run_id'] = rid
            self.save(job)
        rid = job['remote_run_id']
        rec = remote.request('GET','/api/runs/' + rid)
        if rec['status'] == 'failed':
            if job.pop('retry_remote',False):
                rec = remote.request('POST','/api/runs/' + rid + '/rerun', params={'start':rec.get('stage') or 'frames'})
            else:
                job.update(status='failed',stage=rec.get('stage'),message='Remote reconstruction failed. Retry or inspect the GPU service log.')
                self.save(job)
                return
        if rec['status'] == 'uploading':
            self.transfer(job, remote)
            rec = remote.request('POST','/api/runs/' + rid + '/start')
        if rec['status'] in {'running','queued'}:
            job.update(status='processing',stage=rec.get('stage') or 'queued', message='Reconstructing the full parent chunk.')
            self.save(job)
            return
        if rec['status'] != 'done': raise SpatialError('Unexpected reconstruction state.',503)
        if rec.get('source',{}).get('vm_job_id') != job['id']:
            raise SpatialError('Reconstruction source provenance mismatch.')
        job.update(status='importing',stage='import',message='Verifying and importing the saved map.')
        self.save(job)
        with tempfile.TemporaryDirectory(prefix='unfold-map-') as root:
            directory = pull(remote.base,root,run_id=rid,access_token=remote.token)
            raw = read_json(directory / 'app/ride.json')
            duration = max(float(raw.get('stats',{}).get('duration',0)),float(raw['path'][-1]['t']))
            bindings = self.bindings(job,duration)
            scene = import_bundle(directory,self.store,bindings=bindings,vss=self.vss)
        from ride_demo import scene_document
        doc = scene_document(self.store,self.vss,scene['id'])
        # Cosmos reads indexed captions alongside the same imported map/reviews.
        # Failure here leaves the already verified geometry and findings usable.
        try:
            from ride_demo import synthesize_scene
            analysis = synthesize_scene(doc,self.vss)
            self.store.put('analyses/' + scene['id'] + '.json',json.dumps(analysis).encode(),'application/json')
            job['analysis_status'] = 'complete'
        except Exception:
            job['analysis_status'] = 'unavailable'
        job.update(status='complete',stage='complete',scene_id=scene['id'],
            result_url='rides/' + scene['id'] + '?t=' + str(job['highlight_sec']),
            summary={'objects':len(scene['objects']),'recommendations':len(doc['findings']),
                'crossings_assessed':doc['stats'].get('crossings_judged',0),
                'result':'review_ready' if doc['findings'] else 'limited_no_supported_action'},
            message='Map and evidence ready.' if doc['findings'] else 'Map ready. No supported maintenance action was found.')
        self.save(job)

    def transfer(self, job, remote):
        job.update(status='transferring',stage='transfer',message='Transferring the indexed parent to the reconstruction service.')
        self.save(job)
        # Source is looked up again in VSS; never accept a caller-supplied URL.
        self.vss.archive()
        row = self.vss.get_segment(job['selected_segment_id'])
        if row.get('original_video') != job['original_video']: raise SpatialError('Archive source changed.')
        with tempfile.TemporaryFile() as file:
            response = self.vss.request('videos/stream',params={'source':row['original_video']},stream=True)
            n = 0; digest = hashlib.sha256()
            try:
                for block in response.iter_content(1024*1024):
                    n += len(block)
                    if n > CLIP_MAX: raise SpatialError('Parent chunk exceeds the remote 4 GiB limit.')
                    digest.update(block); file.write(block)
                if n == 0 or response.headers.get('Content-Length') and n != int(response.headers['Content-Length']):
                    raise SpatialError('Archive download incomplete.',503)
            finally: response.close()
            checksum = digest.hexdigest()
            if job.get('source_sha256') and job['source_sha256'] != checksum: raise SpatialError('Archive bytes changed during a retry.')
            job.update(source_sha256=checksum,source_bytes=n)
            self.save(job)
            offset = remote.offset(job['remote_run_id'])
            if offset > n: raise SpatialError('Remote transfer exceeds source length.')
            file.seek(offset)
            while offset < n:
                block = file.read(CHUNK)
                result = remote.request('PUT','/api/runs/' + job['remote_run_id'] + '/clip',params={'offset':offset},data=block)
                if result.get('size') != offset + len(block): raise SpatialError('Unexpected transfer offset.',503)
                offset += len(block)
                job['uploaded_bytes'] = offset
                self.save(job)
            manifest = remote.request('GET','/api/manifest',params={'all':1})
            entry = manifest.get('runs',{}).get(job['remote_run_id'],{})
            files = entry.get('files',{})
            info = files.get('runs/' + job['remote_run_id'] + '/clip.mp4') or files.get('clip.mp4') or {}
            if info.get('size') != n or info.get('sha256') != checksum:
                raise SpatialError('Transferred source checksum mismatch.')
            job['transfer_verified'] = True
            self.save(job)

    def bindings(self, job, duration):
        if not job.get('transfer_verified') or not job.get('source_sha256'):
            raise SpatialError('Source transfer was not verified.')
        self.vss.archive()
        clips = [normalize(r,sid) for sid,r in self.vss.segments.items() if r.get('original_video') == job['original_video']]
        intervals = [{'segment_id':c['id'],'scene_start_sec':c['start_sec'],
            'scene_end_sec':min(duration,c['end_sec']),'clip_start_sec':0}
            for c in sorted(clips,key=lambda c:c['start_sec']) if c['start_sec'] < duration]
        indexed_end=max((c['end_sec'] for c in clips),default=0)
        # VSS indexes whole 5-second segments; a decoded last frame can extend
        # beyond them. Permit one 5fps frame plus timestamp rounding, while
        # retaining the uncaptioned tail and never extending clip citations.
        if not intervals or duration > indexed_end + .25:
            raise SpatialError('Map duration does not match the indexed parent.')
        return {'original_video':job['original_video'],'bindings':intervals,
            'verification':{'method':'authenticated_transfer_sha256','archive_filename':job['source_filename'],
                'source_sha256':job['source_sha256'],'source_bytes':job['source_bytes'],
                'remote_run_id':job['remote_run_id'],'offset_sec':0,
                'indexed_end_sec':indexed_end,'uncaptioned_tail_sec':max(0,duration-indexed_end)}}

    def tick(self):
        jobs = [j for j in self.list() if j['status'] in ACTIVE]
        if not jobs: return False
        job = min(jobs,key=lambda j:j['created_at'])
        try: self.advance(job)
        except SpatialError as e:
            job.update(status='waiting' if e.status >= 500 else 'failed',message=str(e))
            self.save(job)
        except Exception:
            job.update(status='waiting',message='Processing temporarily unavailable. The worker will retry; existing pages remain available.')
            self.save(job)
        return True


def discover(vss, kind, filters):
    if kind not in QUERIES: raise SpatialError('Choose collision, close call or crash.')
    from service import matches
    def load():
        clips = vss.search(QUERIES[kind],filters,top_k=100)
        parents = {}
        for clip in clips:
            if clip and matches(clip,filters) and clip.get('original_video'):
                parents.setdefault(clip['original_video'],clip)
        return list(parents.values())
    return vss.cache.get(('danger-candidates',kind,json.dumps(filters,sort_keys=True)),load,ttl=300)


if __name__ == '__main__':
    from spatial import SceneStore
    from vss import VSS
    jobs = Jobs(SceneStore(),VSS())
    print('Unfold worker started; one reconstruction job at a time.',flush=True)
    while True:
        try: jobs.tick()
        except Exception: print('Job storage unavailable; retrying.',flush=True)
        time.sleep(10)
