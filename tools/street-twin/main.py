"""Unfold: a saved crossing-sightline demo and indexed VSS archive."""
import os
import re
import requests
import hashlib
import json
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, request, Response, stream_with_context, render_template_string
from vss import VSS, UpstreamError
from spatial import SPATIAL_INTERFACE, SceneStore, SpatialError
from policy import policy_report
from service import filters_from, sample, BadFilter, analytics, matches, demo
from analysis import AnalysisManager, context_from
from ride_demo import demo_document, scene_document, synthesize_scene, SCENE_ID
from processing import Jobs, discover

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder=None)
app.config['PUBLIC_PATH'] = os.environ.get('STREETTWIN_PUBLIC_PATH', '/')
vss = VSS()
scenes = SceneStore()
jobs = Jobs(scenes,vss)
analyses = AnalysisManager(vss, spatial=scenes)
app.config['MAX_CONTENT_LENGTH'] = 8192

def app_shell(template='ride.html'):
    # Ingress strips /app before Flask sees the request. Resolve the public
    # mount on the server so CSS and scripts also work without inline JS.
    prefix = request.headers.get('X-Forwarded-Prefix') or request.script_root or app.config['PUBLIC_PATH']
    if not re.fullmatch(r'/(?:[A-Za-z0-9._~-]+/)*[A-Za-z0-9._~-]*', prefix) or any(p in {'.', '..'} for p in prefix.split('/')):
        prefix = app.config['PUBLIC_PATH']
    public_path = prefix.rstrip('/') + '/'
    version = hashlib.sha256(b''.join((ROOT / name).read_bytes() for name in ['app.js','style.css','cockpit.js','ride.js','ride.css','discover.js'])).hexdigest()[:12]
    response = Response(render_template_string((ROOT / template).read_text(), public_path=public_path, asset_version=version), mimetype='text/html')
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.errorhandler(UpstreamError)
def upstream_error(error):
    status = error.status if error.status in {404,416} else 503
    return jsonify(error="Clip unavailable" if status == 404 else "Archive temporarily unavailable. Try again."), status

@app.get("/api/metadata")
def metadata():
    fields=vss.metadata()
    streets=[c for c in vss.archive() if c.get('capture_type') in {'streets','traffic'}]
    locations={}
    for chunk in streets:
        camera,location=chunk.get('camera_id'),chunk.get('location')
        if camera and location:
            locations.setdefault(camera,set()).add(location)
    return jsonify({**fields,'camera_id':sorted(locations),
        'location':sorted({v for values in locations.values() for v in values}),
        'camera_locations':{k:sorted(v) for k,v in locations.items()}})

@app.errorhandler(BadFilter)
def bad_filter(error):
    return jsonify(error=str(error)), 400

@app.get('/api/analytics')
def get_analytics():
    filters = filters_from(request.args, vss.metadata())
    return jsonify(sample(vss, filters))

@app.get('/api/demo/<name>')
def get_demo(name):
    return jsonify(demo(vss,name))

@app.get('/api/recommendations')
def get_recommendations():
    job=analyses.start(context_from(request.args.to_dict(),vss.metadata()))
    return jsonify(job),200 if job['status']=='complete' else 202

@app.post('/api/analysis')
def begin_analysis():
    job=analyses.start(context_from(request.get_json(silent=True),vss.metadata()))
    return jsonify(job),200 if job['status']=='complete' else 202

@app.get('/api/analysis/<job_id>')
def analysis_status(job_id):
    if not re.fullmatch(r'[a-f0-9]{16}',job_id):raise UpstreamError(404)
    return jsonify(analyses.get(job_id))

@app.get('/api/policy/<review_id>')
def get_policy(review_id):
    if not re.fullmatch(r'[a-f0-9]{16}',review_id):
        raise UpstreamError(404)
    job=analyses.start(context_from(request.args.to_dict(),vss.metadata()))
    if job['status']!='complete':return jsonify(job),202
    data=analyses.result(job['id'])
    report=policy_report(data,review_id)
    if report is None:
        return jsonify(error='This policy has no supporting clips in this view.'),404
    return jsonify(report)

@app.get('/api/spatial')
def spatial_interface():
    return jsonify({**SPATIAL_INTERFACE,'connected':bool(scenes.index()['scenes'])})

@app.errorhandler(SpatialError)
def spatial_error(error):
    return jsonify(error=str(error)),error.status

@app.get('/api/spatial/scenes')
def spatial_scenes():
    return jsonify(scenes.index())

@app.get('/api/spatial/scenes/<scene_id>')
def spatial_scene(scene_id):
    scene=scenes.scene(scene_id)
    if scene['bindings']:
        vss.archive()
        from vss import normalize
        scene['bindings']=[{**b,'clip':normalize(vss.get_segment(b['segment_id']),b['segment_id'])} for b in scene['bindings']]
    return jsonify(scene)

@app.get('/api/spatial/scenes/<scene_id>/assets/<asset_id>')
def spatial_asset(scene_id,asset_id):
    body,mime,checksum=scenes.asset(scene_id,asset_id)
    response=Response(body,mimetype=mime)
    response.set_etag(checksum)
    response.headers['Cache-Control']='private, max-age=60'
    return response.make_conditional(request)

@app.get('/api/spatial/context')
def spatial_context():
    def time_arg(name):
        try:return float(request.args[name]) if name in request.args else None
        except ValueError:raise SpatialError('Invalid scene interval.') from None
    return jsonify(scenes.context(request.args.get('scene_id',''),segment_id=request.args.get('segment_id'),
        start=time_arg('start'),end=time_arg('end'),object_id=request.args.get('object_id')))

@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    if request.path.startswith('/api/') and not request.path.startswith('/api/stream/'):
        response.headers['Cache-Control']='no-store'
    return response

def segment_id(value):
    if not re.fullmatch(r'[a-f0-9]{20}', value):
        raise UpstreamError(404)
    try:vss.get_segment(value)
    except UpstreamError:
        vss.archive();vss.get_segment(value)
    return value

@app.get('/api/evidence/<clip_id>')
def evidence(clip_id):
    return jsonify(vss.inspect(segment_id(clip_id)))

@app.get('/api/detections/<clip_id>')
def detections(clip_id):
    return jsonify(vss.detections(segment_id(clip_id)))

@app.get('/api/stream/<clip_id>')
def stream(clip_id):
    row = vss.get_segment(segment_id(clip_id))
    return stream_source(row['source'])

def stream_source(source):
    range_header = request.headers.get('Range')
    if range_header and not re.fullmatch(r'bytes=(?:[0-9]+-[0-9]*|-[0-9]+)', range_header):
        return jsonify(error='Unsupported video range'), 416
    upstream = vss.request('videos/stream', params={'source':source},
                           stream=True, range_header=range_header)
    def chunks():
        try:
            yield from upstream.iter_content(chunk_size=65536)
        except requests.RequestException:
            app.logger.warning('Video stream interrupted')
        finally:
            upstream.close()
    headers = {k:upstream.headers[k] for k in ['Content-Length','Content-Range','Accept-Ranges','ETag','Last-Modified'] if k in upstream.headers}
    headers['Content-Type']='video/mp4'
    headers['Cache-Control']='private, max-age=60'
    response = Response(stream_with_context(chunks()), status=upstream.status_code, headers=headers)
    response.call_on_close(upstream.close)
    return response

@app.get('/api/ride')
def ride_data():
    return jsonify(demo_document(scenes,vss))

@app.get('/api/rides/<scene_id>')
def get_ride(scene_id):
    return jsonify(scene_document(scenes,vss,scene_id))

@app.get('/api/rides/<scene_id>/video')
def scene_video(scene_id):
    doc=scene_document(scenes,vss,scene_id)
    return stream_source(doc['clips'][0]['original_video'])

@app.post('/api/rides/<scene_id>/analysis')
def scene_analysis(scene_id):
    doc=scene_document(scenes,vss,scene_id)
    try:
        result=json.loads(scenes.get('analyses/'+scene_id+'.json'))
        if result.get('scene_hash')==doc['scene_hash']:return jsonify(result)
    except SpatialError as e:
        if e.status!=404:raise
    return jsonify(vss.cache.get(('scene-analysis',doc['scene_hash']),lambda:synthesize_scene(doc,vss),ttl=1800))

@app.get('/api/discover')
def risk_clips():
    filters=filters_from(request.args,vss.metadata())
    try:page=int(request.args.get('page',0))
    except ValueError:raise SpatialError('Invalid result page.') from None
    if not 0<=page<=100:raise SpatialError('Invalid result page.')
    candidates=discover(vss,request.args.get('kind','close-call'),filters)
    return jsonify(candidates=candidates[page*4:(page+1)*4],page=page,page_size=4,total=len(candidates),
        label='Danger candidates; a search match does not verify a crash or close call.')

@app.get('/api/runs')
def run_list():
    return jsonify(runs=[jobs.public(j) for j in jobs.list()][:100])

@app.post('/api/runs')
def run_start():
    body=request.get_json(silent=True) or {}
    if not isinstance(body,dict):raise SpatialError('Choose an indexed segment.')
    job=jobs.start(body.get('segment_id'))
    return jsonify(jobs.public(job)),200 if job['status']=='complete' else 202

@app.get('/api/runs/<job_id>')
def run_status(job_id):return jsonify(jobs.public(jobs.get(job_id)))

@app.post('/api/runs/<job_id>/retry')
def run_retry(job_id):return jsonify(jobs.public(jobs.retry(job_id))),202

@app.get('/api/ride/video')
def ride_video():
    from ride_demo import PARENT_FILENAME
    scene=scenes.scene(SCENE_ID)
    if not scene.get('bindings'):raise SpatialError('Demo video is not linked.',503)
    vss.archive()
    row=vss.get_segment(scene['bindings'][0]['segment_id'])
    source=row.get('original_video','')
    if source.rsplit('/',1)[-1]!=PARENT_FILENAME:raise SpatialError('Demo archive source mismatch.',503)
    return stream_source(source)

@app.post('/api/ride/analysis')
def ride_analysis():
    doc=demo_document(scenes,vss)
    row=vss.get_segment(doc['clips'][0]['id'])
    def analyze():
        context={'findings':doc['findings'],'crossing_reviews':[{'object_id':o['id'],'side':e['side'],'review':e.get('review')} for o in doc['objects'] for e in o.get('ends',[]) if e.get('review')]}
        question='Explain the crossing around 16–20 seconds and its maintenance proposal. Separate caption observations from this imported spatial/review JSON: '+json.dumps(context)+'. Distances and speeds are uncalibrated estimates. The right hedge claim is supported by imported frame review; the left spatial claim was rejected. Cite segment numbers and timestamps, and retain this disagreement.'
        system_prompt='Answer the supplied question using the indexed segment captions and the imported context in the question. Write four concise sections: Observed video, Imported spatial evidence, Maintenance proposal, Limits. Label geometry, visibility percentages, speed and stopping distance as imported estimates. Attribute vision-review claims to the imported review, not your own direct observation. Never infer a collision, legal violation, traffic delay or measured safety benefit. Do not replace the question with a generic chronological ride summary.'
        result=vss.request('videos/synthesize',data={'original_video':row['original_video'],'question':question,'system_prompt':system_prompt,'max_segments':6})
        return {'answer':result.get('answer') or result.get('llm_synthesis',{}).get('response') or 'No video synthesis returned.',
            'scope':'demo_parent_and_imported_spatial_context','scene_hash':doc['scene_hash'],'segment_ids':[c['id'] for c in doc['clips']]}
    return jsonify(vss.cache.get(('ride-analysis-v2',doc['scene_hash']),analyze,ttl=1800))

@app.get('/api/search')
def search():
    filters = filters_from(request.args, vss.metadata())
    query = request.args.get('query','').strip()
    if not 3 <= len(query) <= 500:
        raise BadFilter('Describe the scene in 3–500 characters.')
    clips = vss.search(query,filters)
    clips = [c for c in clips if c and matches(c,filters)]
    return jsonify(analytics(clips,filters=filters))

@app.post('/api/reason/<clip_id>')
def reason(clip_id):
    row=vss.get_segment(segment_id(clip_id))
    data=vss.request('agent/ask', data={
        'original_video':row['original_video'], 'top_k':6,
        'question':'Describe visible curb use, cyclist passage and crossing activity in this parent video. Cite segment numbers and times. Distinguish observations from uncertainty. Do not infer legal violations, engine idling, speeds or distances.'})
    return jsonify(answer=data.get('answer','No description available.'),
                   scope='parent_video', segment_id=clip_id)

@app.get("/api/stats")
def stats():
    return jsonify(vss.stats())

@app.get('/')
def index():
    return app_shell('ride.html')

@app.get('/ride')
def ride_page():return app_shell('ride.html')

@app.get('/archive')
def archive_page():
    from flask import redirect
    return redirect(app.config['PUBLIC_PATH'].rstrip('/')+'/discover',code=302)

@app.get('/discover')
@app.get('/runs/<job_id>')
def discovery_page(job_id=None):
    if job_id and not re.fullmatch('[a-f0-9]{24}',job_id):raise SpatialError('Run unavailable.',404)
    return app_shell('discover.html')

@app.get('/rides/<scene_id>')
@app.get('/rides/<scene_id>/recommendations/<finding_id>')
def saved_ride_page(scene_id,finding_id=None):
    from spatial import ident
    ident(scene_id)
    if finding_id and not re.fullmatch(r'crossing-[0-9]{1,8}-(?:left|right)',finding_id):raise SpatialError('Finding unavailable.',404)
    return app_shell('ride.html')

@app.get('/finding/<finding_id>')
def finding_page(finding_id):
    if not re.fullmatch(r'crossing-[0-9]{1,8}-(?:left|right)',finding_id):raise SpatialError('Finding unavailable.',404)
    return app_shell('ride.html')

@app.get('/policy/<review_id>')
def policy_page(review_id):
    if not re.fullmatch(r'[a-f0-9]{16}',review_id):
        return jsonify(error='Policy unavailable'),404
    # The retired archive layout is never rendered. Its evidence API remains
    # available to MCP; current stakeholder pages use scene-specific routes.
    from flask import redirect
    return redirect(app.config['PUBLIC_PATH'].rstrip('/')+'/discover',code=302)

@app.get('/assets/<path:name>')
def asset(name):
    if name in {'vendor/three.module.min.js','vendor/OrbitControls.js'}:
        return send_from_directory(ROOT, name)
    if name not in {'app.js', 'cockpit.js', 'style.css', 'ride.js','ride.css','discover.js','ride-preview.jpg','street-preview.jpg','bottleneck-preview.jpg','traffic-preview.jpg'}:
        return jsonify(error='Asset unavailable'), 404
    return send_from_directory(ROOT, name)

@app.get('/health')
def health():
    return jsonify(status='ok', product='Unfold', demo='Crosswalk sightlines')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8080')))
