"""Shareable policy reports with explicitly scoped, cited sample statistics."""
from collections import Counter, defaultdict
from recommendations import validate_recommendation

POLICY_TITLES = {
    'cyclist_passage_review':'Review cyclist passage',
    'curb_use_review':'Review curb allocation',
    'crossing_review':'Review crossing clearance',
    'queue_review':'Review intersection approaches',
}


def interval_seconds(clips):
    """Union parent-relative intervals so overlapping clips do not inflate time."""
    parents=defaultdict(list)
    for clip in clips:
        parents[clip['original_video']].append((clip['start_sec'],clip['end_sec']))
    total=0
    for intervals in parents.values():
        end=None
        for start,stop in sorted(intervals):
            if end is None or start>end:
                total+=max(0,stop-start)
            elif stop>end:
                total+=stop-end
            end=max(stop,end if end is not None else stop)
    return round(total,2)


def policy_report(data, review_id):
    review=next((r for r in data['recommendations'] if r['id']==review_id),None)
    if review is None or not validate_recommendation(review,data['clips']):
        return None
    cohort=[c for c in data['clips'] if c['camera_id']==review['camera_id'] and c['location']==review['location']]
    references={r['segment_id']:r for r in review['segment_refs']}
    evidence=[{**c,'citation_number':i+1,'caption_evidence':references[c['id']]['caption_evidence']}
              for i,c in enumerate(c for c in cohort if c['id'] in references)]
    presence=Counter()
    peaks=Counter()
    for c in evidence:
        presence.update(set(c['object_classes']))
        for label,n in c['object_counts'].items():
            if isinstance(n,(int,float)) and c['object_counts_mode']=='max_per_frame':
                peaks[label]=max(peaks[label],n)
    labels=['car','person','bicycle','truck','bus','motorcycle']
    return {
        'recommendation':review,'title':POLICY_TITLES[review['type']],
        'clips':evidence,
        'statistics':{
            'evidence_clips':len(evidence),'sampled_clips':len(cohort),
            'support_percent':round(100*len(evidence)/len(cohort),1),
            'evidence_seconds':interval_seconds(evidence),
            'detected_classes':[{'label':label,'clip_count':presence[label],'peak_per_frame':peaks.get(label)} for label in labels if presence[label]],
        },
        'analysis':f"The observation appears in {len(evidence)} of {len(cohort)} sampled clips from this camera. The cited captions support a planning review of this location.",
        'sampling_note':'Selected archive clips; adjacent clips may show the same event. Clip share is not an event rate or a citywide estimate.',
        'context':{'filters':data.get('filters'),'demo':data.get('demo')},
    }
