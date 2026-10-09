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

    def test_negative_crossing_parking_and_slow_flow_do_not_alert(self):
        self.assertEqual(observations(clip('No pedestrians are crossing the street. Vehicles are not parked at the curb. Traffic is not moving slowly.')), {})

    def test_delivery_vehicle_alone_does_not_establish_curb_placement(self):
        self.assertNotIn('curb_use_review', observations(clip('A USPS truck is parked in the middle of the road.')))

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


class PolicyTests(unittest.TestCase):
    def test_policy_denominator_uses_its_camera_and_citations(self):
        from policy import policy_report
        a=clip('A cyclist passes a USPS truck parked at the curb, partially blocking the lane.')
        b=clip('Routine street activity.','s3://archive/segments/b.mp4')
        elsewhere=clip('A cyclist passes a truck partially blocking the lane.','s3://archive/segments/c.mp4')
        elsewhere['camera_id']='other'
        data=analytics([a,a,b,elsewhere])
        review=next(r for r in data['recommendations'] if r['type']=='cyclist_passage_review' and r['camera_id']=='bike')
        report=policy_report(data,review['id'])
        self.assertEqual(report['statistics']['sampled_clips'],2)
        self.assertEqual(report['statistics']['evidence_clips'],1)
        self.assertEqual(report['statistics']['support_percent'],50)
        self.assertEqual(report['clips'][0]['source'],a['source'])
        self.assertEqual(report['clips'][0]['citation_number'],1)
        self.assertIsNone(policy_report(data,'unknown'))

    def test_overlapping_evidence_time_is_not_double_counted(self):
        from policy import interval_seconds
        a=clip('Routine.');b={**a,'start_sec':3,'end_sec':8}
        self.assertEqual(interval_seconds([a,b]),8)


class PolicyRouteTests(unittest.TestCase):
    def test_shareable_route_and_scoped_missing_report(self):
        from main import app
        a=clip('A cyclist passes a truck parked at the curb, partially blocking the lane.')
        data=analytics([a])
        review_id=data['recommendations'][0]['id']
        with patch('main.vss.metadata',return_value={}),patch('main.sample',return_value=data):
            with app.test_client() as client:
                self.assertEqual(client.get('/policy/'+review_id).status_code,200)
                report=client.get('/api/policy/'+review_id)
                self.assertEqual(report.status_code,200)
                self.assertEqual(report.json['statistics']['evidence_clips'],1)
                self.assertEqual(client.get('/api/policy/'+'0'*16).status_code,404)
                self.assertEqual(client.get('/policy/invalid').status_code,404)

if __name__=='__main__':unittest.main()
