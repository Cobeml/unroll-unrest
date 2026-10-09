"""Reports cite a local episode; sample context never becomes a citywide rate."""
from recommendations import validate_recommendation, interval_seconds


def policy_report(data, review_id):
    review=next((r for r in data['recommendations'] if r['id']==review_id),None)
    if review is None or not validate_recommendation(review,data['clips'],data.get('detections')):return None
    parent=review['segment_refs'][0]['original_video']
    cohort=[c for c in data['clips'] if c['original_video']==parent]
    refs={r['segment_id']:r for r in review['segment_refs']}
    evidence=[{**c,'citation_number':i+1,'caption_evidence':refs[c['id']]['caption_evidence'],
               'roles':refs[c['id']]['roles'],'claims':refs[c['id']]['claims']}
              for i,c in enumerate(sorted((c for c in cohort if c['id'] in refs),key=lambda c:c['start_sec']))]
    return {'recommendation':review,'title':review['title'],'clips':evidence,
            'statistics':{**review['metrics'],'sampled_clips':len(cohort),
                          'analyzed_episodes':len(data.get('bottlenecks',[])),
                          'support_percent':round(100*len(evidence)/len(cohort),1)},
            'analysis':'The cited captions connect an obstruction with an avoidance maneuver in this local sequence. The action addresses that mechanism; infrastructure remains conditional on a site survey.',
            'sampling_note':'Selected neighboring archive segments. Adjacent citations describe one episode; referenced seconds are footage duration, not delay. This is not an event rate or a citywide estimate.',
            'context':{'filters':data.get('filters'),'demo':data.get('demo')}}
