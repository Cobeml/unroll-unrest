import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bottlenecks import allowed_claims, validate_findings


def fixture(name='20261008_074847_GX050001_chunk_0005.mp4'):
    return json.loads((Path(__file__).parent/'fixtures/bottlenecks.json').read_text())[name]


def proposal(clips):
    allowed = allowed_claims(clips)
    return {'findings':[{role:claims[-2:] for role,claims in allowed.items()}]}


class DiagnosisTests(unittest.TestCase):
    def test_inspected_red_sedan_and_truck_sequences(self):
        for name,subtype in [('20261008_074847_GX050001_chunk_0005.mp4','parked_vehicle'),
                             ('20261008_072535_GOPR0130_chunk_0004.mp4','temporary_barrier')]:
            clips=fixture(name)
            events=validate_findings(json.dumps(proposal(clips)),clips)
            self.assertEqual(len(events),1)
            self.assertEqual(events[0]['subtype'],subtype)
            self.assertEqual({c['role'] for c in events[0]['claims']},{'obstruction','movement_effect'})
            for claim in events[0]['claims']:
                self.assertIn(claim['quote'], next(c['caption'] for c in clips if c['id']==claim['segment_id']))

    def test_fences_duplicate_findings_and_order_do_not_change_episode(self):
        clips=fixture();p=proposal(clips)
        p['findings'][0]['obstruction']=[allowed_claims(clips)['obstruction'][0]]
        first=validate_findings(json.dumps(p),clips)
        p['findings']*=2
        result=validate_findings('```json\n'+json.dumps(p)+'\n```',list(reversed(clips)))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['id'],first[0]['id'])

    def test_normal_highway_and_parked_vehicles_have_no_movement_claim(self):
        self.assertEqual(allowed_claims(fixture('20261001_055405_scene1_p1c1_chunk_0003.mp4'))['movement_effect'],[])
        c=fixture()[0]
        c['caption']='A car is parked at the curb. Traffic stops at a red light. No vehicle blocks the lane.'
        self.assertEqual(allowed_claims([c]),{'obstruction':[],'movement_effect':[]})

    def test_missing_effect_unknown_or_unrelated_citation_rejected(self):
        clips=fixture();p=proposal(clips)
        for mutate in [lambda p:p['findings'][0].update(movement_effect=[]),
                       lambda p:p['findings'][0]['movement_effect'][0].update(segment_number=999),
                       lambda p:p['findings'][0]['movement_effect'][0].update(quote='The traffic delay is 25 seconds.'),
                       lambda p:p['findings'][0].update(action='Fine the driver.')]:
            changed=copy.deepcopy(p);mutate(changed)
            with self.assertRaises(ValueError):validate_findings(json.dumps(changed),clips)

    def test_unrelated_interval_and_cross_parent_rejected(self):
        clips=fixture();p=proposal(clips)
        p['findings'][0]['obstruction']=[allowed_claims(clips)['obstruction'][0]]
        effect=p['findings'][0]['movement_effect'][0]['segment_number']
        for c in clips:
            if c['segment_number']==effect:c['start_sec']=100;c['end_sec']=105
        with self.assertRaises(ValueError):validate_findings(json.dumps(p),clips)
        clips=fixture();clips[-1]['original_video']='s3://test-archive/other.mp4'
        with self.assertRaises(ValueError):validate_findings(json.dumps(proposal(clips)),clips)

    def test_malformed_and_extra_model_output_rejected(self):
        for answer in ['not JSON','[]','{"findings":{},"delay":10}','prefix ```json\n{}\n```']:
            with self.assertRaises(ValueError):validate_findings(answer,fixture())

    def test_decimal_segment_strings_are_lossless_but_bool_is_not(self):
        p=proposal(fixture())
        for role in p['findings'][0]:
            for claim in p['findings'][0][role]:claim['segment_number']=str(claim['segment_number'])
        self.assertEqual(len(validate_findings(json.dumps(p),fixture())),1)
        p['findings'][0]['movement_effect'][0]['segment_number']=True
        with self.assertRaises(ValueError):validate_findings(json.dumps(p),fixture())


if __name__=='__main__':unittest.main()
