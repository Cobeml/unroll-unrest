import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from processing import Jobs, CHUNK, discover
from spatial import SceneStore, SpatialError
from vss import Cache


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=SceneStore(self.tmp.name);self.store.bucket=None
        self.sid='a'*20
        self.row={'source':'s3://segments/one.mp4','original_video':'s3://archive/parent.mp4',
            'capture_type':'streets','segment_start_sec':0,'segment_end_sec':5,'camera_id':'bike','location':'city'}
        self.vss=SimpleNamespace(archive=lambda:[],get_segment=lambda sid:self.row,segments={self.sid:self.row},cache=Cache())
        self.remote=Mock();self.remote.request.return_value={'code_version':'v1'}
        self.jobs=Jobs(self.store,self.vss,lambda:self.remote)
    def tearDown(self):self.tmp.cleanup()
    def test_submission_is_durable_and_reuses_parent_and_version(self):
        a=self.jobs.start(self.sid)
        b=Jobs(self.store,self.vss,lambda:self.remote).start(self.sid)
        self.assertEqual(a['id'],b['id']);self.assertEqual(len(self.jobs.list()),1)
        self.assertNotIn('original_video',self.jobs.public(a))
        self.remote.request.return_value={'code_version':'v2'}
        self.assertNotEqual(a['id'],self.jobs.start(self.sid)['id'])
    def test_public_api_requires_canonical_input_and_persists_restart_status(self):
        from main import app
        with patch('main.jobs',self.jobs),app.test_client() as client:
            self.assertEqual(client.post('/api/runs',json={'url':'https://example.com/video.mp4'}).status_code,400)
            self.assertEqual(client.post('/api/runs',json=['invalid']).status_code,400)
            result=client.post('/api/runs',json={'segment_id':self.sid})
            self.assertEqual(result.status_code,202)
            self.assertNotIn('original_video',result.json)
            self.assertEqual(client.get('/api/runs/'+result.json['id']).json['status'],'queued')
            self.assertEqual(len(client.get('/api/runs').json['runs']),1)
            self.assertEqual(client.get('/api/runs/not-a-run').status_code,404)
    def test_unindexed_or_nonstreet_input_is_not_transferred(self):
        with self.assertRaises(SpatialError):self.jobs.start('https://example.com/video')
        self.row['capture_type']='warehouse'
        with self.assertRaises(SpatialError):self.jobs.start(self.sid)
        self.remote.request.assert_not_called()
    def test_interrupted_upload_resumes_and_requires_exact_source_checksum(self):
        payload=b'indexed-archive-bytes'
        job=self.jobs.start(self.sid);job['remote_run_id']='run1'
        response=Mock(headers={'Content-Length':str(len(payload))})
        response.iter_content.return_value=[payload]
        self.vss.request=Mock(return_value=response)
        self.remote.offset.return_value=8
        def remote(method,path,**kw):
            if method=='PUT':
                self.assertEqual(kw['params']['offset'],8)
                self.assertEqual(kw['data'],payload[8:])
                return {'size':len(payload)}
            return {'runs':{'run1':{'files':{'runs/run1/clip.mp4':{'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}}}}}
        self.remote.request.side_effect=remote
        self.jobs.transfer(job,self.remote)
        self.assertTrue(self.jobs.get(job['id'])['transfer_verified'])
        self.assertEqual(CHUNK,64*1024*1024)
        job['source_sha256']='0'*64
        with self.assertRaisesRegex(SpatialError,'bytes changed'):self.jobs.transfer(job,self.remote)
    def test_map_cannot_be_bound_before_transfer_verification(self):
        job=self.jobs.start(self.sid)
        with self.assertRaisesRegex(SpatialError,'not verified'):self.jobs.bindings(job,5)
        job.update(transfer_verified=True,source_sha256='1'*64,source_bytes=42,remote_run_id='run1')
        manifest=self.jobs.bindings(job,4.8)
        self.assertEqual(manifest['bindings'][0]['scene_end_sec'],4.8)
        self.assertEqual(manifest['verification']['method'],'authenticated_transfer_sha256')
        with self.assertRaisesRegex(SpatialError,'duration'):self.jobs.bindings(job,6)
    def test_outage_preserves_job_and_resumes_same_remote_id(self):
        job=self.jobs.start(self.sid);job['remote_run_id']='existing';self.jobs.save(job)
        self.remote.request.side_effect=SpatialError('Tunnel unavailable.',503)
        self.jobs.tick()
        restored=self.jobs.get(job['id'])
        self.assertEqual(restored['status'],'waiting');self.assertEqual(restored['remote_run_id'],'existing')
        self.remote.request.side_effect=None;self.remote.request.return_value={'status':'running','stage':'geometry'}
        self.jobs.tick();self.assertEqual(self.jobs.get(job['id'])['stage'],'geometry')
    def test_failed_remote_job_requires_explicit_retry(self):
        job=self.jobs.start(self.sid);job['remote_run_id']='existing';self.jobs.save(job)
        self.remote.request.return_value={'status':'failed','stage':'detect'}
        self.jobs.tick();self.assertEqual(self.jobs.get(job['id'])['status'],'failed')
        self.remote.request.reset_mock();self.assertFalse(self.jobs.tick());self.remote.request.assert_not_called()
    def test_candidates_are_deduplicated_and_do_not_invent_crash_verdicts(self):
        self.vss.search=Mock(return_value=[{'id':self.sid,'capture_type':'streets','original_video':'parent'},
            {'id':'b'*20,'capture_type':'streets','original_video':'parent'},
            {'id':'c'*20,'capture_type':'warehouse','original_video':'other'}])
        result=discover(self.vss,'close-call',{'time_filter':'all','metadata_filters':{}})
        self.assertEqual(len(result),1);self.assertNotIn('verified',result[0])

    def test_completed_run_imports_verified_provenance_and_structured_action(self):
        from test_spatial import make_bundle
        from test_ride_demo import crossing_export
        job=self.jobs.start(self.sid)
        self.row['segment_end_sec']=10
        job.update(remote_run_id='run1',transfer_verified=True,source_sha256='1'*64,source_bytes=42)
        self.jobs.save(job)
        run,raw=make_bundle(Path(self.tmp.name)/'export')
        crossing_export(raw)
        (run/'app/ride.json').write_text(json.dumps(raw))
        (run/'run.json').write_text(json.dumps({'id':'run1','status':'done','code_version':'v1'}))
        self.remote.base='https://service.example';self.remote.token='unused-test-token'
        self.remote.request.return_value={'id':'run1','status':'done','source':{'vm_job_id':job['id']}}
        self.vss.request=Mock(return_value={'answer':'Indexed footage and imported review support a hedge inspection.'})
        with patch('processing.pull',return_value=run):self.jobs.advance(job)
        saved=self.jobs.get(job['id'])
        self.assertEqual(saved['status'],'complete');self.assertEqual(saved['analysis_status'],'complete')
        self.assertEqual(saved['summary']['recommendations'],1)
        self.assertEqual(self.store.scene('run1')['source_verification']['source_sha256'],'1'*64)
        analysis=json.loads(self.store.get('analyses/run1.json'))
        self.assertEqual(analysis['segment_ids'],[self.sid])
        self.assertIn('rejected',self.vss.request.call_args.kwargs['data']['question'])
        self.remote.request.return_value={'status':'done','source':{'vm_job_id':'different'}}
        with self.assertRaisesRegex(SpatialError,'provenance mismatch'):self.jobs.advance(job)

if __name__=='__main__':unittest.main()
