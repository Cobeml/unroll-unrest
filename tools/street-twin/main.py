"""StreetTwin: a thin, same-origin interface to the indexed VSS archive."""
import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder=None)

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
