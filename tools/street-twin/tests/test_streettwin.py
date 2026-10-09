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
        self.assertIn('cyclist_passage_review',observations(c))
        self.assertEqual(build_recommendations([c,c]),[])

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
        from test_bottlenecks import fixture,proposal
        from bottlenecks import validate_findings
        import json
        clips=fixture();elsewhere={**clips[0],'id':'other','original_video':'s3://test/other.mp4'}
        events=validate_findings(json.dumps(proposal(clips)),clips)
        data={'clips':clips+[elsewhere],'recommendations':build_recommendations(clips,events),'bottlenecks':events}
        review=data['recommendations'][0]
        report=policy_report(data,review['id'])
        self.assertEqual(report['statistics']['sampled_clips'],6)
        self.assertEqual(report['statistics']['evidence_clips'],2)
        self.assertEqual(report['statistics']['episode_count'],1)
        self.assertEqual(report['clips'][0]['source'],clips[2]['source'])
        self.assertEqual(report['clips'][0]['citation_number'],1)
        self.assertIsNone(policy_report(data,'unknown'))

    def test_overlapping_evidence_time_is_not_double_counted(self):
        from policy import interval_seconds
        a=clip('Routine.');b={**a,'start_sec':3,'end_sec':8}
        self.assertEqual(interval_seconds([a,b]),8)


class PolicyRouteTests(unittest.TestCase):
    def test_shell_assets_keep_the_public_mount_without_inline_script(self):
        from main import app
        from html.parser import HTMLParser
        from urllib.parse import urljoin
        class Links(HTMLParser):
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag=='base':self.base=attrs['href']
                if tag=='link' and attrs.get('rel')=='stylesheet':self.css=attrs['href']
                if tag=='script':self.script=attrs.get('src')
        with patch.dict(app.config,{'PUBLIC_PATH':'/app/'}),app.test_client() as client:
            self.assertEqual(client.get('/archive').status_code,302)
            self.assertEqual(client.get('/policy/'+'a'*16).status_code,302)
            for route in ['/', '/ride']:
                with client.get(route) as response:
                    page=Links();page.feed(response.text)
                    self.assertEqual(page.base,'/app/')
                    self.assertTrue(urljoin(page.base,page.css).startswith('/app/assets/ride.css?v='))
                    self.assertTrue(urljoin(page.base,page.script).startswith('/app/assets/ride.js?v='))
                    self.assertEqual(response.headers['Cache-Control'],'no-store')
            with client.get('/',headers={'X-Forwarded-Prefix':'/gateway/team/app'}) as response:
                self.assertIn('<base href="/gateway/team/app/">',response.text)
            for invalid in ['//evil.example','/../evil','https://evil.example/','/bad"prefix']:
                with client.get('/',headers={'X-Forwarded-Prefix':invalid}) as response:
                    self.assertIn('<base href="/app/">',response.text)

    def test_shareable_route_and_scoped_missing_report(self):
        from main import app
        from test_bottlenecks import fixture,proposal
        from bottlenecks import validate_findings
        import json
        clips=fixture();events=validate_findings(json.dumps(proposal(clips)),clips)
        data={'clips':clips,'recommendations':build_recommendations(clips,events),'bottlenecks':events}
        review_id=data['recommendations'][0]['id']
        with patch('main.vss.metadata',return_value={}),patch('main.analyses.start',return_value={'id':'a'*16,'status':'complete'}),patch('main.analyses.result',return_value=data):
            with app.test_client() as client:
                with client.get('/policy/'+review_id) as page:
                    self.assertEqual(page.status_code,302)
                report=client.get('/api/policy/'+review_id)
                self.assertEqual(report.status_code,200)
                self.assertEqual(report.json['statistics']['evidence_clips'],2)
                self.assertEqual(client.get('/api/policy/'+'0'*16).status_code,404)
                self.assertEqual(client.get('/policy/invalid').status_code,404)

if __name__=='__main__':unittest.main()
