import copy
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from spatial_reasoning import select_facts,enrich,validate_spatial_refs
from spatial import SpatialError
from test_bottlenecks import fixture,proposal
from bottlenecks import validate_findings
from recommendations import build_recommendations,validate_recommendation
from analysis import AnalysisManager


class SpatialReasoningTests(unittest.TestCase):
    def setUp(self):
        self.clips=fixture();self.items=build_recommendations(self.clips,validate_findings(json.dumps(proposal(self.clips)),self.clips))
        self.seg=self.items[0]['segment_refs'][0]['segment_id']
        self.fact={'fact_id':'f'*16,'scene_id':'map','scene_hash':'h','object_id':'1','segment_id':self.seg,
            'eligible_for_reasoning':True,'label':'car','motion':'standing','basis':'spatial_estimate'}
        self.context={'facts':[self.fact]}
    def test_model_can_select_only_linked_registered_facts(self):
        answer=json.dumps({'spatial_fact_ids':['f'*16]})
        self.assertEqual(select_facts(answer,[self.fact]),[self.fact])
        for value in [{'spatial_fact_ids':['invented']},{'spatial_fact_ids':['f'*16]*2},{'spatial_fact_ids':['f'*16],'delay':20}]:
            with self.assertRaises(ValueError):select_facts(json.dumps(value),[self.fact])
        with self.assertRaises(ValueError):select_facts(answer,[{**self.fact,'eligible_for_reasoning':False}])
    def test_shared_selection_and_spatial_tampering_cannot_alter_policy(self):
        calls=[]
        vss=SimpleNamespace(request=lambda *a,**kw:(calls.append(kw) or {'answer':json.dumps({'spatial_fact_ids':['f'*16]})}))
        def context(scene_id,segment_id):
            if segment_id!=self.seg:raise SpatialError('Not linked',404)
            return self.context
        store=SimpleNamespace(context=context)
        items,contexts,warnings=enrich(vss,store,'map',self.items)
        self.assertEqual(len(calls),1);self.assertFalse(warnings)
        for item in items:
            self.assertTrue(validate_recommendation(item,self.clips,spatial_contexts=contexts))
            bad=copy.deepcopy(item);bad['spatial_refs'][0]['label']='fabrication'
            self.assertFalse(validate_recommendation(bad,self.clips,spatial_contexts=contexts))
            bad=copy.deepcopy(item);bad['action']='Fine all standing cars'
            self.assertFalse(validate_recommendation(bad,self.clips,spatial_contexts=contexts))
    def test_unlinked_map_and_model_failure_leave_video_actions_intact(self):
        def missing(*a,**kw):raise SpatialError('Not linked',404)
        items,contexts,warnings=enrich(None,SimpleNamespace(context=missing),'map',self.items)
        self.assertEqual(items,self.items);self.assertFalse(contexts)
        def failed(*a,**kw):raise RuntimeError('private failure')
        items,contexts,warnings=enrich(SimpleNamespace(request=failed),SimpleNamespace(context=lambda *a,**kw:self.context),'map',self.items)
        self.assertTrue(warnings);self.assertEqual(items[0]['spatial_refs'],[])
    def test_scene_version_participates_in_analysis_cache_key(self):
        store=SimpleNamespace(version=lambda _:store.current,current='one')
        manager=AnalysisManager(None,spatial=store);manager.pool.shutdown(wait=True)
        class Pool:
            def submit(self,*a):pass
        manager.pool=Pool();first=manager.start({'scene_id':'map'});second=manager.start({'scene_id':'map'})
        self.assertEqual(first['id'],second['id']);store.current='two';third=manager.start({'scene_id':'map'})
        self.assertNotEqual(first['id'],third['id'])

if __name__=='__main__':unittest.main()
