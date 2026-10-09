"""Meaningful boundaries: evidence grounding, isolation, auth and streaming."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from observations import observations
from recommendations import build_recommendations, validate_recommendation
from service import filters_from, analytics, matches, BadFilter
from vss import VSS, UpstreamError, normalize


def clip(caption, source='s3://archive/segments/a.mp4'):
    return normalize({'source':source,'original_video':'s3://archive/a.mp4','camera_id':'bike',
        'location':'city','capture_type':'streets','segment_number':1,'segment_start_sec':0,
        'segment_end_sec':5,'upload_timestamp':'2026-10-08T12:00:00',
        'reasoning_content':caption,'object_classes':'person,car,bicycle',
        'object_counts':'{"person":3,"car":2,"bicycle":1}'},source[-5])

class GroundingTests(unittest.TestCase):
    def test_negated_obstruction_and_normal_flow_do_not_alert(self):
        c=clip('A bicycle is on the street. No vehicles are blocking the lane. Traffic is free-flowing with no congestion.')
        self.assertEqual(observations(c),{})
        self.assertEqual(build_recommendations([c]),[])

    def test_detection_cooccurrence_does_not_establish_proximity(self):
        self.assertEqual(build_recommendations([clip('A routine street scene.')]),[])

    def test_supported_refs_and_counts(self):
        c=clip('A cyclist rides along the street. A USPS truck is parked at the curb, partially blocking the lane.')
        reviews=build_recommendations([c,c])
        self.assertEqual(len(reviews),2)
        for r in reviews:
            self.assertEqual(r['metrics']['evidence_clips'],1)
            self.assertTrue(validate_recommendation(r,[c]))
            changed=copy.deepcopy(r);changed['segment_refs'][0]['source']='s3://unrelated/a.mp4'
            self.assertFalse(validate_recommendation(changed,[c]))
            changed=copy.deepcopy(r);changed['segment_refs'][0]['segment_id']='unknown'
            self.assertFalse(validate_recommendation(changed,[c]))

    def test_duplicate_presence_not_inflated(self):
        c=clip('Routine traffic.')
        x=analytics([c,c]);self.assertEqual(x['sample_count'],1)
        self.assertTrue(all(v['clip_count']==1 for v in x['object_chart']))

    def test_no_parking_claim_from_parked_bicycle(self):
        self.assertNotIn('curb_use_review',observations(clip('A bicycle is parked at the curb.')))

    def test_metadata_and_date_isolation(self):
        metadata={'location':['city'],'camera_id':['bike']}
        f=filters_from({'camera_id':'bike','start':'2026-10-08','end':'2026-10-08'},metadata)
        self.assertTrue(matches(clip('Routine.'),f))
        f['metadata_filters']['camera_id']='different';self.assertFalse(matches(clip('Routine.'),f))
        for args in [{'camera_id':'bad'},{'start':'invalid'},{'start':'2026-10-09','end':'2026-10-08'}]:
            with self.assertRaises(BadFilter):filters_from(args,metadata)

class AuthTests(unittest.TestCase):
    @patch('vss.requests.request')
    @patch('vss.requests.post')
    def test_401_refresh_once(self,login,request):
        v=VSS();v.base='http://example.invalid';v.username='test';v.password='test';v.token='old'
        login.return_value=Mock(status_code=200,json=lambda:{'access_token':'new'})
        request.side_effect=[Mock(status_code=401),Mock(status_code=200,json=lambda:{'ok':True})]
        self.assertEqual(v.request('metadata/schema'),{'ok':True})
        self.assertEqual(login.call_count,1);self.assertEqual(request.call_count,2)

    def test_unregistered_sources_rejected(self):
        with self.assertRaises(UpstreamError):VSS().get_segment('unknown')

    def test_non_s3_sources_rejected(self):
        self.assertIsNone(VSS().register({'source':'https://evil.invalid/a.mp4'}))

    @patch('vss.VSS.request')
    def test_missing_detections(self,request):
        v=VSS();c=v.register({'source':'s3://archive/a.mp4'})
        request.side_effect=UpstreamError(404)
        self.assertFalse(v.detections(c['id'])['available'])

if __name__=='__main__':unittest.main()
