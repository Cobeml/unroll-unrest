import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ride_sync import pull,token
from spatial import SpatialError

class Response:
    def __init__(self,body=b'',status=200):self.body=body;self.status_code=status
    def close(self):pass
    def json(self):return json.loads(self.body)
    def iter_content(self,_):yield self.body

class SyncTests(unittest.TestCase):
    def test_service_token_file_is_parsed_without_shell_execution(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{},clear=True),patch('ride_sync.Path.is_file',autospec=True,side_effect=lambda p:str(p)!='/config/ride.token' and p.exists()):
            env=Path(tmp)/'.env'
            env.write_text('export SERVICE_TOKEN="literal-$(touch /tmp/never)-token" # private\nUNRELATED=ignored\n')
            self.assertEqual(token(env),'literal-$(touch /tmp/never)-token')
            with patch.dict('os.environ',{'SERVICE_TOKEN':'from-environment'}):self.assertEqual(token(env),'from-environment')
    def test_service_root_manifest_paths_and_wrong_run_rejected(self):
        body=b'{}';checksum=hashlib.sha256(body).hexdigest()
        manifest={'runs':{'run':{'run':{'id':'run','status':'done'},'files':{'runs/run/app/ride.json':{'size':2,'sha256':checksum},'runs/run/app/ride.mp4':{'size':2,'sha256':checksum}}}}}
        calls=[]
        class Session:
            def get(self,url,**kw):calls.append(url);return Response(json.dumps(manifest).encode() if url.endswith('/api/manifest') else body)
        with tempfile.TemporaryDirectory() as tmp:
            dest=pull('https://maps.example',tmp,session=Session())
            self.assertTrue((dest/'app/ride.json').is_file());self.assertEqual(calls[-1],'https://maps.example/runs/run/app/ride.json')
            self.assertFalse((dest/'app/ride.mp4').exists())
            manifest['runs']['run']['files']={'runs/other/app/ride.json':{'size':2,'sha256':checksum}}
            with self.assertRaisesRegex(SpatialError,'another run'):pull('https://maps.example',tmp,session=Session())
    def test_only_get_derived_maps_and_verified_mirror(self):
        body=b'{}';files={p:{'size':len(body),'sha256':hashlib.sha256(body).hexdigest()} for p in ['app/ride.json','app/cloud.bin','app/ride.mp4','.env','log.txt']}
        manifest={'runs':{'run':{'run':{'id':'run','status':'done'},'files':files}}}
        calls=[]
        class Session:
            def get(self,url,**kw):calls.append((url,kw));return Response(json.dumps(manifest).encode() if url.endswith('/api/manifest') else body)
        with tempfile.TemporaryDirectory() as tmp:
            dest=pull('https://maps.example',tmp,session=Session(),access_token='private')
            self.assertTrue((dest/'app/cloud.bin').is_file());self.assertFalse((dest/'app/ride.mp4').exists())
            self.assertEqual(len(calls),3);self.assertTrue(all(c[1]['headers']=={'Authorization':'Bearer private'} for c in calls))
            pull('https://maps.example',tmp,session=Session(),access_token='private');self.assertEqual(len(calls),4)
    def test_access_and_corrupt_download_errors_are_sanitized(self):
        class Session:
            def get(self,*a,**k):return Response(b'private upstream',401)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(SpatialError,'token in /config/ride.token'):pull('https://maps.example',tmp,session=Session())
        for url in ['https://user:secret@maps.example','https://maps.example?token=secret']:
            with self.assertRaises(SpatialError):pull(url,'/tmp',session=Session())
    def test_bad_manifest_hash_leaves_no_published_file(self):
        manifest={'runs':{'run':{'run':{'status':'done'},'files':{'app/ride.json':{'size':2,'sha256':'0'*64}}}}}
        class Session:
            def get(self,url,**k):return Response(json.dumps(manifest).encode() if url.endswith('/api/manifest') else b'{}')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SpatialError):pull('https://maps.example',tmp,session=Session())
            self.assertFalse((Path(tmp)/'run/app/ride.json').exists());self.assertFalse(list(Path(tmp).rglob('*.part')))

if __name__=='__main__':unittest.main()
