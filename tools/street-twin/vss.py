"""Documented retrieval/login, metadata, dashboard, search and videos patterns."""
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import requests

class UpstreamError(Exception):
    def __init__(self, status=502):
        self.status = status
        super().__init__('Archive request unavailable')

class Cache:
    def __init__(self):
        self.data = {}
        self.lock = threading.RLock()

    def get(self, key, loader, ttl=300):
        with self.lock:
            entry = self.data.get(key)
            if entry and entry[0] > time.monotonic():
                return entry[1]
        value = loader()
        with self.lock:
            if len(self.data) >= 128:
                self.data.pop(next(iter(self.data)))
            self.data[key] = (time.monotonic() + ttl, value)
        return value

class VSS:
    def __init__(self):
        self.base = os.environ.get('VSS_URL', os.environ.get('INGRESS_URL', '')).rstrip('/')
        self.username = os.environ.get('VSS_USERNAME', os.environ.get('USERNAME', ''))
        self.password = os.environ.get('VSS_PASSWORD', os.environ.get('PASSWORD', ''))
        self.token = None
        self.lock = threading.RLock()
        self.cache = Cache()
        self.segments = {}

    def login(self, expired=None):
        with self.lock:
            if self.token and (expired is None or self.token != expired):
                return self.token
            if not self.base or not self.username or not self.password:
                raise UpstreamError(503)
            try:
                r = requests.post(self.base+'/api/v1/auth/login', json={
                    'username': self.username, 'password': self.password}, timeout=(8, 30))
                if r.status_code != 200:
                    raise UpstreamError(503)
                self.token = r.json()['access_token']
                return self.token
            except (requests.RequestException, ValueError, KeyError):
                raise UpstreamError(503) from None

    def request(self, path, *, data=None, params=None, stream=False, range_header=None):
        token = self.login()
        for attempt in range(2):
            headers = {'Authorization': 'Bearer '+token}
            query = dict(params or {})
            if stream:
                query['token'] = token
                if range_header:
                    headers['Range'] = range_header
            try:
                r = requests.request('POST' if data is not None else 'GET',
                    self.base+'/api/v1/'+path, json=data, params=query,
                    headers=headers, timeout=(8, 100 if data else 45), stream=stream)
            except requests.RequestException:
                raise UpstreamError(502) from None
            if r.status_code == 401 and attempt == 0:
                r.close()
                token = self.login(expired=token)
                continue
            if r.status_code >= 400:
                status = r.status_code
                r.close()
                raise UpstreamError(status)
            if stream:
                return r
            try:
                return r.json()
            except ValueError:
                raise UpstreamError(502) from None
            finally:
                r.close()
        raise UpstreamError(503)

    def metadata(self):
        def load():
            schema = self.request('metadata/schema')['schema']
            fields = {}
            for field in schema:
                if field['name'] in {'location', 'camera_id', 'capture_type'}:
                    fields[field['name']] = self.request('metadata/values',
                        params={'field': field['name'], 'limit': 100})['values']
            return fields
        return self.cache.get('metadata', load)

    def stats(self):
        def load():
            x = self.request('dashboard/stats', params={'scope': 'all'})
            return {key: x.get(key, {}) for key in ['overview', 'metadata', 'pipeline_alignment']}
        return self.cache.get('stats', load)

    def archive(self):
        def load():
            first = self.request('videos/explore', params={'scope':'all','limit':100,'offset':0})
            chunks = first.get('chunks', [])
            total = first.get('total', first.get('chunk_total', len(chunks)))
            def page(offset):
                return self.request('videos/explore', params={'scope':'all','limit':100,'offset':offset}).get('chunks', [])
            with ThreadPoolExecutor(max_workers=4) as pool:
                for page_rows in pool.map(page, range(100, int(total), 100)):
                    chunks.extend(page_rows)
            for chunk in chunks:
                for row in chunk.get('timeline', []):
                    self.register({**{k:v for k,v in chunk.items() if k!='timeline'}, **row})
            return chunks
        return self.cache.get('archive', load)

    def register(self, row):
        source = row.get('source', '')
        parsed = urlparse(source)
        if parsed.scheme != 's3' or not parsed.netloc or not parsed.path.endswith('.mp4'):
            return None
        segment_id = hashlib.sha256(source.encode()).hexdigest()[:20]
        with self.lock:
            self.segments[segment_id] = dict(row)
        return normalize(row, segment_id)

    def get_segment(self, segment_id):
        with self.lock:
            row = self.segments.get(segment_id)
        if row is None:
            raise UpstreamError(404)
        return row

    def inspect(self, segment_id):
        def load():
            original = self.get_segment(segment_id)
            row = self.request('videos/metadata', params={'source': original['source']})
            # The indexed row, not a sidecar's historical bucket, owns identity.
            row['source'] = original['source']
            return self.register(row)
        return self.cache.get(('inspect',segment_id), load)

    def detections(self, segment_id):
        def load():
            row = self.get_segment(segment_id)
            try:
                x = self.request('videos/detections', params={'source':row['source']})
            except UpstreamError as e:
                if e.status == 404:
                    return {'available':False,'frames':[]}
                raise
            return {**{k:x.get(k) for k in ['video_shape','fps','frame_count','object_classes','object_counts']},
                    'available':True, 'frames':x.get('frames', []), 'segment_id':segment_id}
        return self.cache.get(('detections',segment_id), load)

    def search(self, query, filters):
        x = self.request('search', data={
            'query':query, 'top_k':30, 'llm_top_n':1, 'min_similarity':0.3,
            'time_filter':filters['time_filter'],
            'metadata_filters':filters['metadata_filters'],
            **{k:v for k,v in filters.items() if k.startswith('custom_')},
            'include_public':True})
        return [self.register(row) for row in x.get('results', []) if row.get('source')]


def decode(value, default):
    if isinstance(value, type(default)):
        return value
    try:
        return json.loads(value or '')
    except (TypeError, ValueError):
        return default


def normalize(row, segment_id):
    counts = decode(row.get('object_counts'), {})
    perception = decode(row.get('perception_json'), {})
    classes = row.get('object_classes', '')
    if isinstance(classes, str):
        classes = [v for v in classes.split(',') if v]
    return {
        'id':segment_id, 'source':row['source'],
        'filename':row.get('filename') or row['source'].rsplit('/',1)[-1],
        'original_video':row.get('original_video'),
        'segment_number':row.get('segment_number'),
        'start_sec':row.get('segment_start_sec',0), 'end_sec':row.get('segment_end_sec',0),
        'duration':row.get('duration') or (row.get('segment_end_sec',0)-row.get('segment_start_sec',0)),
        'camera_id':row.get('camera_id') or 'Unknown camera',
        'location':row.get('location') or 'Unknown location',
        'capture_type':row.get('capture_type'), 'indexed_at':row.get('upload_timestamp'),
        'caption':row.get('reasoning_content') or '',
        'object_classes':classes or [], 'object_counts':counts if isinstance(counts,dict) else {},
        'object_counts_mode':perception.get('object_counts_mode','max_per_frame'),
        'tags':row.get('tags') or [],
        'stream_start_sec':decode(row.get('extra_metadata'),{}).get('stream_position_sec'),
    }
