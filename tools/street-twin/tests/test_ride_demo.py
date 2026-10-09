import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ride_demo import viewer_export,crossing_findings,demo_document,PARENT_FILENAME,SCENE_ID
from spatial import SceneStore,SpatialError,import_bundle
from test_spatial import make_bundle


def crossing_export(raw):
    raw['objects'][0].update(group='hedge',label='hedge')
    raw.update(frame_size=[1280,720],fps=.2,overlays={'0':[[1,20,20,100,100]],'1':[]},
        rules={'clear':.9,'window_m':10.5,'react_s':1.5,'decel':3,'target_h':1},
        stats={'duration':10,'distance':10,'crosswalks':1,'crossings_judged':1,'stopped':0})
    end={'side':'right','area':[[7,0],[8,0],[8,1],[7,1]],'covered':True,'seen_at_stop':.03,
         'needed_m':10,'speed_kmh':16.1,'clear_from_m':5.3,'stop_d':10.2,'stop_t':4,'stop_k':0,'clear_k':1,
         'blockers':[{'id':1,'n':12,'before_m':5.4,'in_20ft':True}],
         'frames':[{'k':0,'d':10.2,'seen':.03,'counted':True,'poly':[[0,0]]*8},{'k':1,'d':0,'seen':1,'counted':True}],
         'review':{'claim':'confirmed','reason':'A hedge screens the waiting area.','model':'imported-review'}}
    left=copy.deepcopy(end);left.update(side='left',seen_at_stop=.7,review={'claim':'rejected','reason':'The area is visible.','model':'imported-review'})
    raw['objects'].append({'id':2,'group':'crosswalk','label':'crosswalk','seen':4,'xy':[8,0],'edge':[7,0],
        'rect':[[7,-2],[9,-2],[9,2],[7,2]],'t0':0,'t1':10,'t_pass':8,'ends':[end,left]})


class RideDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.run,self.raw=make_bundle(self.root)
        crossing_export(self.raw)
        (self.run/'run.json').write_text(json.dumps({'id':SCENE_ID,'status':'done'}))
        self.write();self.store=SceneStore(self.root/'store');self.store.bucket=None
        self.rows={'a'*20:{'source':'s3://segments/one.mp4','original_video':'s3://archive/'+PARENT_FILENAME,'segment_start_sec':0,'segment_end_sec':5,'camera_id':'camera','location':'street'},
                   'b'*20:{'source':'s3://segments/two.mp4','original_video':'s3://archive/'+PARENT_FILENAME,'segment_start_sec':5,'segment_end_sec':10,'camera_id':'camera','location':'street'}}
        self.vss=SimpleNamespace(archive=lambda:[],get_segment=lambda key:self.rows[key])
        self.bindings={'original_video':'s3://archive/'+PARENT_FILENAME,'bindings':[{'segment_id':key,'scene_start_sec':row['segment_start_sec'],'scene_end_sec':row['segment_end_sec']} for key,row in self.rows.items()]}
    def tearDown(self):self.tmp.cleanup()
    def write(self):(self.run/'app/ride.json').write_text(json.dumps(self.raw))
    def test_saved_review_disagreement_and_crossing_stats_are_preserved(self):
        s=import_bundle(self.run,self.store,bindings=self.bindings,vss=self.vss)
        self.assertIn('viewer',s['assets'])
        doc=demo_document(self.store,self.vss)
        self.assertEqual(doc['video'],'api/ride/video');self.assertEqual(doc['stats']['crosswalks'],1)
        self.assertEqual(doc['objects'][1]['ends'][1]['review']['claim'],'rejected')
        self.assertEqual(len(doc['findings']),1)
        f=doc['findings'][0]
        self.assertEqual(f['title'],'Trim the hedge at crossing 1');self.assertEqual(f['metrics']['hidden_fraction'],.97)
        self.assertEqual(len(f['segment_refs']),2);self.assertEqual(f['segment_refs'][0]['start_sec'],4)
        self.assertEqual(f['segment_refs'][1]['end_sec'],9)
    def test_unknown_overlay_object_and_nonfinite_estimate_are_rejected(self):
        original=copy.deepcopy(self.raw)
        self.raw['overlays']['0'][0][0]=999;self.write()
        with self.assertRaisesRegex(SpatialError,'object box'):import_bundle(self.run,self.store)
        self.assertEqual(self.store.index()['scenes'],[])
        self.raw=original;self.raw['objects'][1]['ends'][0]['needed_m']=float('nan');self.write()
        with self.assertRaises(SpatialError):import_bundle(self.run,self.store)
    def test_unlinked_and_wrong_archive_sources_cannot_enter_demo(self):
        import_bundle(self.run,self.store)
        with self.assertRaisesRegex(SpatialError,'verified archive bindings'):demo_document(self.store,self.vss)
        import_bundle(self.run,self.store,bindings=self.bindings,vss=self.vss)
        self.rows['a'*20]['original_video']='s3://archive/unrelated.mp4'
        with self.assertRaisesRegex(SpatialError,'source does not match'):demo_document(self.store,self.vss)
    def test_rejected_review_never_makes_a_maintenance_proposal(self):
        import_bundle(self.run,self.store,bindings=self.bindings,vss=self.vss)
        doc=demo_document(self.store,self.vss)
        for o in doc['objects']:
            for e in o.get('ends',[]):e['review']['claim']='rejected'
        self.assertEqual(crossing_findings(doc,doc['clips']),[])
    def test_demo_routes_use_same_origin_assets_and_validate_range(self):
        from main import app
        import_bundle(self.run,self.store,bindings=self.bindings,vss=self.vss)
        with patch('main.scenes',self.store),patch('main.vss',self.vss),patch.dict(app.config,{'PUBLIC_PATH':'/app/'}),app.test_client() as client:
            self.assertEqual(client.get('/api/ride').status_code,200)
            page=client.get('/')
            self.assertIn('<base href="/app/">',page.text);self.assertIn('assets/ride.js?v=',page.text)
            self.assertNotIn('cdn.jsdelivr',page.text);self.assertIn('Unfold',page.text)
            self.assertEqual(client.get('/api/ride/video',headers={'Range':'bytes=0-1,4-5'}).status_code,416)
            self.assertEqual(client.get('/finding/crossing-2-right').status_code,200)
            self.assertEqual(client.get('/finding/not-a-finding').status_code,404)
    def test_cosmos_receives_both_reviews_and_does_not_replace_structured_findings(self):
        from main import app
        from vss import Cache
        import_bundle(self.run,self.store,bindings=self.bindings,vss=self.vss)
        self.vss.cache=Cache();self.vss.request=lambda *a,**kw:{'answer':'Separate imported estimates from caption observations.'}
        with patch('main.scenes',self.store),patch('main.vss',self.vss),patch.object(self.vss,'request',wraps=self.vss.request) as request,app.test_client() as client:
            response=client.post('/api/ride/analysis');self.assertEqual(response.status_code,200)
            sent=request.call_args.kwargs['data']
            self.assertEqual(sent['original_video'],'s3://archive/'+PARENT_FILENAME)
            self.assertIn('rejected',sent['question']);self.assertIn('confirmed',sent['question'])
            self.assertIn('imported estimates',sent['system_prompt'])
            client.post('/api/ride/analysis');self.assertEqual(request.call_count,1)
            self.assertEqual(client.get('/api/ride').json['findings'][0]['title'],'Trim the hedge at crossing 1')

if __name__=='__main__':unittest.main()
