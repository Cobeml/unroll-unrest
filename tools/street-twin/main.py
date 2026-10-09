"""StreetTwin: a thin, same-origin interface to the indexed VSS archive."""
import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, request
from vss import VSS, UpstreamError
from service import filters_from, sample, BadFilter

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder=None)
vss = VSS()

@app.errorhandler(UpstreamError)
def upstream_error(error):
    status = 404 if error.status == 404 else 503
    return jsonify(error="Clip unavailable" if status == 404 else "Archive temporarily unavailable. Try again."), status

@app.get("/api/metadata")
def metadata():
    return jsonify(vss.metadata())

@app.errorhandler(BadFilter)
def bad_filter(error):
    return jsonify(error=str(error)), 400

@app.get('/api/analytics')
def get_analytics():
    filters = filters_from(request.args, vss.metadata())
    return jsonify(sample(vss, filters))

@app.get("/api/stats")
def stats():
    return jsonify(vss.stats())

@app.get('/')
def index():
    return send_from_directory(ROOT, 'index.html')

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
