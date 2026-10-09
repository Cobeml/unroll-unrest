import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis import AnalysisManager, context_from
from service import BadFilter
from vss import UpstreamError
from test_bottlenecks import fixture,proposal


class Archive:
    def __init__(self):
        self.clips=fixture();self.calls=[];self.fail=False
    def metadata(self):return {'location':['new_york'],'camera_id':['nyc_bike_gopro-1']}
    def archive(self):
        c=self.clips[0]
        return [{**c,'filename':'20261008_074847_GX050001_chunk_0005.mp4','timeline':self.clips}]
    def register(self,row):return dict(row)
    def search(self,query,filters,**kwargs):
        self.calls.append(('search',kwargs));return self.clips
    def request(self,path,**kwargs):
        if self.fail:raise UpstreamError(503)
        self.calls.append((path,kwargs))
        return {'answer':json.dumps(proposal(self.clips))}
    def detections(self,segment_id):return {'available':False,'frames':[]}


class AnalysisTests(unittest.TestCase):
    def manager(self,archive=None,**kwargs):
        m=AnalysisManager(archive or Archive(),**kwargs)
        self.addCleanup(m.pool.shutdown,wait=True)
        return m

    def test_pipeline_expands_demo_and_generates_real_paired_reports(self):
        archive=Archive();manager=self.manager(archive)
        data=manager.analyze({'demo':'bottleneck'})
        self.assertEqual(len(data['clips']),6)
        self.assertEqual(len(data['bottlenecks']),1)
        self.assertEqual(len(data['recommendations']),2)
        self.assertEqual(data['recommendations'][0]['metrics']['detection_clips'],0)
        self.assertFalse(any(c[0]=='search' for c in archive.calls))
        self.assertEqual(archive.calls[0][1]['data']['max_segments'],6)

    def test_targeted_search_obeys_filters_and_zero_synthesis(self):
        archive=Archive();manager=self.manager(archive)
        data=manager.analyze({'camera_id':'nyc_bike_gopro-1'})
        searches=[c for c in archive.calls if c[0]=='search']
        self.assertEqual(len(searches),3)
        self.assertTrue(all(c[1]=={'top_k':8,'llm_top_n':0} for c in searches))
        self.assertEqual(data['analyzed_parent_count'],1)

    def test_no_movement_means_no_recommendation_or_model_call(self):
        archive=Archive()
        for c in archive.clips:c['caption']='A car is parked at the curb. Traffic flows normally.'
        data=self.manager(archive).analyze({'demo':'bottleneck'})
        self.assertEqual(data['recommendations'],[])
        self.assertEqual(data['reasoned_parent_count'],0)

    def test_model_timeout_does_not_create_a_canned_recommendation(self):
        archive=Archive();archive.fail=True
        with self.assertRaises(UpstreamError):self.manager(archive).analyze({'demo':'bottleneck'})

    def test_one_invalid_response_retries_but_two_fail_closed(self):
        archive=Archive();manager=self.manager(archive)
        with patch.object(archive,'request',side_effect=[{'answer':'bad JSON'},{'answer':json.dumps(proposal(archive.clips))}]) as request:
            self.assertEqual(len(manager.analyze({'demo':'bottleneck'})['recommendations']),2)
            self.assertEqual(request.call_count,2)
        with patch.object(archive,'request',return_value={'answer':'{"findings":[{"action":"Fine the driver"}]}'}):
            with self.assertRaises(UpstreamError):manager.analyze({'demo':'bottleneck'})

    def test_deduplication_expiry_failure_retry_and_no_detection_payload(self):
        now=[10];manager=self.manager(clock=lambda:now[0],ttl=30)
        manager._run=lambda job_id:None
        first=manager.start({'demo':'bottleneck'})
        self.assertEqual(manager.start({'demo':'bottleneck'})['id'],first['id'])
        manager._update(first['id'],status='complete',result={'recommendations':[],'detections':{'private':'large sidecar'}})
        self.assertNotIn('detections',manager.get(first['id']))
        now[0]=41
        with self.assertRaises(UpstreamError):manager.get(first['id'])
        second=manager.start({'demo':'bottleneck'})
        self.assertNotEqual(first['id'],second['id'])
        manager._update(second['id'],status='failed')
        self.assertNotEqual(manager.start({'demo':'bottleneck'})['id'],second['id'])

    def test_invalid_scope_and_pending_report(self):
        metadata=Archive().metadata()
        for args in [None,[],{'demo':'made-up'},{'query':'x'},{'camera_id':'wrong'},{'location':[]}]:
            with self.assertRaises(BadFilter):context_from(args,metadata)
        from main import app
        job={'id':'a'*16,'status':'running','phase':'Reading sequence 1'}
        with patch('main.vss.metadata',return_value=metadata),patch('main.analyses.start',return_value=job),patch('main.analyses.get',return_value=job):
            with app.test_client() as client:
                self.assertEqual(client.post('/api/analysis',json={'demo':'bottleneck'}).status_code,202)
                self.assertEqual(client.get('/api/analysis/'+'a'*16).json['status'],'running')
                self.assertEqual(client.get('/api/policy/'+'b'*16+'?demo=bottleneck').status_code,202)
                self.assertEqual(client.post('/api/analysis',json={'camera_id':'wrong'}).status_code,400)
                self.assertEqual(client.get('/api/analysis/not-an-id').status_code,404)

    def test_search_compatibility_keeps_only_hits_and_remembers_minimum(self):
        from vss import VSS
        v=VSS()
        with patch.object(v,'request',side_effect=[UpstreamError(422),{'results':[]},{'results':[]}]) as request:
            v.search('obstruction',{'metadata_filters':{},'time_filter':'all'},top_k=8)
            v.search('other obstruction',{'metadata_filters':{},'time_filter':'all'},top_k=8)
            self.assertEqual(request.call_count,3)
            self.assertEqual(request.call_args.kwargs['data']['llm_top_n'],1)


if __name__=='__main__':unittest.main()
