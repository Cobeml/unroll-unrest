"""Bounded asynchronous retrieval → reasoning → evidence → intervention pipeline."""
import hashlib
import json
import logging
import secrets
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from bottlenecks import VERSION, SYSTEM_PROMPT, allowed_claims, validate_findings
from recommendations import build_recommendations
from service import filters_from, matches, sample, demo, DEMO_ANCHORS, BadFilter
from vss import UpstreamError
from spatial import SpatialError
from spatial_reasoning import enrich

QUERIES = [
    'Parked vehicle blocks a lane and a cyclist or camera vehicle maneuvers around it',
    'Truck and construction barrier narrow the street and obstruct passage',
    'Physical obstruction forces a cyclist or camera vehicle to divert around it',
]
LOG=logging.getLogger(__name__)


def context_from(args, metadata):
    if not isinstance(args,dict):raise BadFilter('Choose a valid street view.')
    if any(not isinstance(args.get(k,''),str) for k in ['location','camera_id','start','end','query','demo','scene_id']):
        raise BadFilter('Choose a valid street view.')
    context={k:args[k].strip() for k in ['location','camera_id','start','end','query','demo','scene_id'] if args.get(k,'').strip()}
    filters_from(context,metadata)
    if context.get('demo') and context['demo'] not in DEMO_ANCHORS:raise BadFilter('Choose an existing demo preset.')
    if context.get('query') and not 3<=len(context['query'])<=500:raise BadFilter('Describe the scene in 3–500 characters.')
    if context.get('scene_id') and not __import__('re').fullmatch(r'[A-Za-z0-9_-]{1,80}',context['scene_id']):raise BadFilter('Choose a valid saved map.')
    return context


class AnalysisManager:
    def __init__(self, vss, *, spatial=None, ttl=1800, clock=time.monotonic):
        self.vss=vss;self.spatial=spatial;self.ttl=ttl;self.clock=clock
        self.lock=threading.RLock();self.jobs=OrderedDict();self.scopes={}
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='street-analysis')

    def _prune(self):
        for job_id,job in list(self.jobs.items()):
            if job['status'] in {'complete','failed'} and job['expires']<=self.clock():
                self.jobs.pop(job_id);self.scopes.pop(job['key'],None)

    def start(self, context):
        spatial_hash=self.spatial.version(context.get('scene_id')) if self.spatial else ''
        key=hashlib.sha256((VERSION+spatial_hash+json.dumps(context,sort_keys=True)).encode()).hexdigest()
        with self.lock:
            self._prune()
            existing=self.jobs.get(self.scopes.get(key))
            if existing and existing['status']!='failed':return self._public(existing)
            if existing:
                self.jobs.pop(existing['id']);self.scopes.pop(key,None)
            active=sum(j['status'] not in {'complete','failed'} for j in self.jobs.values())
            if active>=8:raise UpstreamError(503)
            while len(self.jobs)>=32:
                oldest=next((i for i,j in self.jobs.items() if j['status'] in {'complete','failed'}),None)
                if oldest is None:raise UpstreamError(503)
                old=self.jobs.pop(oldest);self.scopes.pop(old['key'],None)
            job_id=secrets.token_hex(8)
            job={'id':job_id,'key':key,'scope':dict(context),'status':'queued','phase':'Queued',
                 'warnings':[],'result':None,'spatial_hash':spatial_hash,'expires':self.clock()+self.ttl}
            self.jobs[job_id]=job;self.scopes[key]=job_id
            self.pool.submit(self._run,job_id)
            return self._public(job)

    def _public(self, job):
        result={k:job[k] for k in ['id','scope','status','phase','warnings']}
        result['analysis_version']=VERSION
        if job['status']=='complete':
            result.update({k:v for k,v in job['result'].items() if k!='detections'})
        if job['status']=='failed':result['error']='Analysis unavailable. Retry; street footage remains available.'
        return result

    def get(self, job_id):
        with self.lock:
            self._prune()
            if job_id not in self.jobs:raise UpstreamError(404)
            return self._public(self.jobs[job_id])

    def result(self, job_id):
        with self.lock:
            job=self.jobs.get(job_id)
            return job.get('result') if job and job['status']=='complete' else None

    def _update(self, job_id, **values):
        with self.lock:self.jobs[job_id].update(values)

    def _run(self, job_id):
        try:
            self._update(job_id,status='running',phase='Finding obstructions')
            with self.lock:context=dict(self.jobs[job_id]['scope'])
            data=self.analyze(context,lambda phase:self._update(job_id,phase=phase))
            if self.spatial and self.spatial.version(context.get('scene_id'))!=self.jobs[job_id]['spatial_hash']:
                raise SpatialError('Map changed during analysis. Retry.')
            self._update(job_id,status='complete',phase='Analysis complete',result=data,
                         warnings=data['warnings'],expires=self.clock()+self.ttl)
        except Exception as error:
            # Never stringify upstream errors: URLs/headers can contain runtime secrets.
            LOG.warning('Street analysis failed: %s',type(error).__name__)
            self._update(job_id,status='failed',phase='Analysis unavailable',expires=self.clock()+30)

    def analyze(self, context, progress=lambda phase:None):
        deadline=self.clock()+300
        def budget():
            if self.clock()>deadline:raise UpstreamError(503)
        vss=self.vss;warnings=[];filters=filters_from(context,vss.metadata())
        if context.get('demo'):
            initial=demo(vss,context['demo']);candidates=initial['clips']
        else:
            initial=sample(vss,filters)
            candidates=list(initial['clips'])
            queries=QUERIES+([context['query']] if context.get('query') else [])
            with ThreadPoolExecutor(max_workers=3) as search_pool:
                futures=[search_pool.submit(vss.search,q,filters,top_k=8,llm_top_n=0) for q in queries]
                for future in futures:
                    try:candidates.extend(c for c in future.result() if c and matches(c,filters))
                    except UpstreamError:warnings.append('Some retrieval results were unavailable.')
                    budget()
        candidates=list({c['id']:c for c in candidates}.values())
        # Rank movement evidence first; density and object co-occurrence never qualify.
        ranked=sorted(candidates,key=lambda c:(not bool(allowed_claims([c])['movement_effect']),
                                               not bool(allowed_claims([c])['obstruction']),c['filename']))
        parent_seeds={}
        for c in ranked:
            if any(allowed_claims([c]).values()) and c['original_video'] not in parent_seeds:
                parent_seeds[c['original_video']]=c
            if len(parent_seeds)>=3:break
        chunks={c['original_video']:c for c in vss.archive() if c.get('original_video')}
        clips=[];events=[];detections={};attempted=0;failed=0
        for parent,seed in parent_seeds.items():
            budget()
            chunk=chunks.get(parent)
            if not chunk:continue
            rows=[vss.register({**{k:v for k,v in chunk.items() if k!='timeline'},**r}) for r in chunk.get('timeline',[])]
            rows=[c for c in rows if c and matches(c,filters)]
            rows=sorted(sorted(rows,key=lambda c:abs(c['start_sec']-seed['start_sec']))[:6],key=lambda c:c['start_sec'])
            clips.extend(rows)
            allowed=allowed_claims(rows)
            if not all(allowed.values()):continue
            attempted+=1;progress(f'Reading sequence {attempted}')
            try:
                # Synthesis consumes indexed captions, not a new ingest or raw video upload.
                for attempt in range(2):
                    budget()
                    response=vss.request('videos/synthesize',data={'original_video':parent,'max_segments':6,
                        'system_prompt':SYSTEM_PROMPT,
                        'question':('Diagnose a local obstruction with an observed avoidance maneuver. '
                                    +('The prior response did not pass validation. Return the exact schema and unchanged allowed quotation objects. ' if attempt else '')
                                    +'Select only these allowed quotations: '+json.dumps(allowed))})
                    try:
                        admitted=validate_findings(response.get('answer',''),rows)
                        break
                    except (ValueError,TypeError):
                        LOG.warning('Sequence diagnosis rejected by evidence validator (attempt %s)',attempt+1)
                        if attempt:raise
            except (UpstreamError,ValueError,TypeError) as error:
                LOG.warning('Sequence unavailable: %s',type(error).__name__)
                failed+=1;warnings.append('A sequence could not produce a validated diagnosis.');continue
            events.extend(admitted)
        progress('Checking detections and citations')
        support={q['segment_id'] for e in events for q in e['claims']}
        for clip_id in sorted(support):
            budget()
            try:detections[clip_id]=vss.detections(clip_id)
            except UpstreamError:warnings.append('Some frame detections were unavailable.')
        if attempted and failed==attempted:raise UpstreamError(503)
        budget()
        generated=datetime.now(timezone.utc).isoformat()
        recommendations=build_recommendations(clips,events,detections,generated)
        recommendations,spatial_contexts,spatial_warnings=enrich(vss,self.spatial,context.get('scene_id'),recommendations,progress=progress,budget=budget) if self.spatial else (recommendations,[],[])
        warnings.extend(spatial_warnings)
        return {'clips':clips,'bottlenecks':events,'recommendations':recommendations,'spatial_contexts':spatial_contexts,
                'detections':detections,'generated_at':generated,'filters':filters,'demo':initial.get('demo'),
                'analyzed_parent_count':len(parent_seeds),'reasoned_parent_count':attempted,
                'warnings':list(dict.fromkeys(warnings))}
