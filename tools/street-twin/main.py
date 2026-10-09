"""StreetTwin: a thin, same-origin interface to the indexed VSS archive."""
import os
import re
import requests
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, request, Response, stream_with_context
from vss import VSS, UpstreamError
from spatial import SPATIAL_INTERFACE
from policy import policy_report
from service import filters_from, sample, BadFilter, analytics, matches, demo

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder=None)
vss = VSS()

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
    filters=filters_from(request.args,vss.metadata())
    return jsonify(recommendations=sample(vss,filters)['recommendations'])

@app.get('/api/policy/<review_id>')
def get_policy(review_id):
    if not re.fullmatch(r'[a-f0-9]{16}',review_id):
        raise UpstreamError(404)
    if request.args.get('demo'):
        data=demo(vss,request.args['demo'])
    else:
        filters=filters_from(request.args,vss.metadata())
        query=request.args.get('query','').strip()
        if query:
            if not 3<=len(query)<=500:
                raise BadFilter('Describe the scene in 3–500 characters.')
            clips=[c for c in vss.search(query,filters) if c and matches(c,filters)]
            data=analytics(clips,filters=filters)
        else:
            data=sample(vss,filters)
    report=policy_report(data,review_id)
    if report is None:
        return jsonify(error='This policy has no supporting clips in this view.'),404
    return jsonify(report)

@app.get('/api/spatial')
def spatial_interface():
    return jsonify(SPATIAL_INTERFACE)

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
    range_header = request.headers.get('Range')
    if range_header and not re.fullmatch(r'bytes=(?:[0-9]+-[0-9]*|-[0-9]+)', range_header):
        return jsonify(error='Unsupported video range'), 416
    upstream = vss.request('videos/stream', params={'source':row['source']},
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
    return send_from_directory(ROOT, 'index.html')

@app.get('/policy/<review_id>')
def policy_page(review_id):
    if not re.fullmatch(r'[a-f0-9]{16}',review_id):
        return jsonify(error='Policy unavailable'),404
    return send_from_directory(ROOT,'index.html')

@app.get('/assets/<path:name>')
def asset(name):
    if name not in {'app.js', 'style.css'}:
        return jsonify(error='Asset unavailable'), 404
    return send_from_directory(ROOT, name)

@app.get('/health')
def health():
    return jsonify(status='ok', product='StreetTwin')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8080')))
