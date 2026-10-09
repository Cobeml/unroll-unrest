import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from spatial import SceneStore,SpatialError,import_bundle

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2S8AAAAASUVORK5CYII=')
SEG='a'*20


def make_bundle(root):
    app=root/'run/app';app.mkdir(parents=True)
    (app/'ortho.png').write_bytes(PNG)
    (app/'cloud.bin').write_bytes(struct.pack('<ffffff',0,0,1,2,2,1.5))
    (app/'rgb.bin').write_bytes(bytes([255,200,100,100,200,255]))
    raw={'ortho':'ortho.png','cloud':{'points':'cloud.bin','colours':'rgb.bin','n':2},
         'extent':{'x0':-5,'x1':15,'y0':-5,'y1':5},'stats':{'duration':10},
         'path':[{'t':0,'x':0,'y':0,'h':0},{'t':10,'x':10,'y':0,'h':0}],
         'objects':[{'id':1,'group':'vehicle','label':'car','seen':5,'xy':[4,1],'spread':.5,'passed':6,'parked':True,
                     'footprint':[[2,0],[6,0],[6,2],[2,2]],'height':1.4,'t0':1,'t1':8}]}
    (app/'ride.json').write_text(json.dumps(raw));(app.parent/'run.json').write_text(json.dumps({'id':'test-run','name':'Test street','status':'done'}))
    return app.parent,raw


def binding():return {'original_video':'s3://archive/parent.mp4','bindings':[{'segment_id':SEG,'scene_start_sec':0,'scene_end_sec':5,'clip_start_sec':0}]}


def archive():return SimpleNamespace(archive=lambda:[],get_segment=lambda _: {'original_video':'s3://archive/parent.mp4','segment_start_sec':0,'segment_end_sec':5,'camera_id':'camera','location':'street'})


class SpatialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.run,self.raw=make_bundle(self.root);self.store=SceneStore(self.root/'store');self.store.bucket=None
    def tearDown(self):self.temp.cleanup()
    def write(self): (self.run/'app/ride.json').write_text(json.dumps(self.raw))
    def test_import_context_hash_and_no_video_copy(self):
        (self.run/'app/ride.mp4').write_bytes(b'not uploaded')
        s=import_bundle(self.run,self.store,bindings=binding(),vss=archive())
        self.assertEqual(s['objects'][0]['motion'],'standing')
        self.assertEqual(self.store.scene(s['id']),s)
        body,mime,checksum=self.store.asset(s['id'],'points');self.assertEqual(len(body),24);self.assertEqual(hashlib.sha256(body).hexdigest(),checksum)
        context=self.store.context(s['id'],segment_id=SEG)
        self.assertTrue(context['linked']);self.assertTrue(context['facts'][0]['eligible_for_reasoning'])
        self.assertEqual(context['facts'][0]['scene_end_sec'],5)
        self.assertFalse(any(p.suffix=='.mp4' for p in self.store.root.rglob('*')))
    def test_unknown_is_not_promoted_to_moving(self):
        self.raw['objects'][0].update(parked=False,seen=1,passed=0,spread=0);self.write()
        s=import_bundle(self.run,self.store)
        self.assertEqual(s['objects'][0]['motion'],'unknown')
        self.assertFalse(self.store.context(s['id'])['facts'][0]['eligible_for_reasoning'])
        with self.assertRaises(SpatialError):self.store.context(s['id'],segment_id=SEG)
    def test_paths_invalid_cloud_and_nonfinite_fail_before_publish(self):
        cases=[lambda: self.raw.update(ortho='../run.json'),
               lambda: self.raw['cloud'].update(n=100),
               lambda: self.raw['path'][0].update(x=float('nan')),
               lambda: self.raw['path'][1].update(t=0),
               lambda: self.raw['objects'][0].update(t1=99)]
        original=copy.deepcopy(self.raw)
        for mutate in cases:
            self.raw=copy.deepcopy(original);mutate();self.write()
            with self.assertRaises(SpatialError):import_bundle(self.run,self.store)
            self.assertEqual(self.store.index()['scenes'],[])
        self.raw=original;self.write();(self.run/'app/cloud.bin').write_bytes(struct.pack('<ffffff',0,0,float('inf'),2,2,1))
        with self.assertRaises(SpatialError):import_bundle(self.run,self.store)
    def test_wrong_archive_parent_and_interval_rejected(self):
        for manifest in [binding(),binding(),binding()]:
            if not hasattr(self,'done'):manifest['original_video']='s3://archive/wrong.mp4';self.done=True
            elif not hasattr(self,'twice'):manifest['bindings'][0]['scene_end_sec']=8;self.twice=True
            else:manifest['bindings'].append(dict(manifest['bindings'][0]))
            with self.assertRaises(SpatialError):import_bundle(self.run,self.store,bindings=manifest,vss=archive())
    def test_corrupt_asset_detected_and_import_updates_version(self):
        s=import_bundle(self.run,self.store);first=s['hash']
        path=self.store.root/s['id']/s['hash']/'points';path.write_bytes(b'corrupt')
        with self.assertRaises(SpatialError):self.store.asset(s['id'],'points')
        self.raw['objects'][0]['spread']=.8;self.write();second=import_bundle(self.run,self.store)
        self.assertNotEqual(first,second['hash']);self.assertEqual(len(self.store.index()['scenes']),1)
    def test_readonly_api_and_context_bounds(self):
        from main import app
        s=import_bundle(self.run,self.store)
        with patch('main.scenes',self.store),app.test_client() as c:
            self.assertEqual(c.get('/api/spatial/scenes').json['scenes'][0]['id'],s['id'])
            self.assertEqual(c.get('/api/spatial/scenes/test-run/assets/points').status_code,200)
            self.assertEqual(c.get('/api/spatial/scenes/test-run/assets/missing').status_code,404)
            for query in ['start=nan','end=99','start=7&end=2']:
                self.assertEqual(c.get('/api/spatial/context?scene_id=test-run&'+query).status_code,400)
            self.assertEqual(c.post('/api/spatial/scenes',json={}).status_code,405)
    def test_ingestion_bucket_is_rejected(self):
        with self.assertRaises(SpatialError):SceneStore(bucket='team-1-vss-chunks')

if __name__=='__main__':unittest.main()
