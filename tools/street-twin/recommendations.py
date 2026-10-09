"""Targeted interventions and measured context for admitted passage bottlenecks."""
import hashlib
import json
from collections import Counter, defaultdict
from bottlenecks import VERSION, validate_findings

LABELS = {'passage_policy':'Policy', 'passage_infrastructure':'Infrastructure'}
CATALOGUE = {
    'parked_vehicle': {
        'policy': {'title':'Keep the riding path clear',
                   'action':'Inspect the parked-vehicle obstruction and coordinate curb use so the riding path remains clear.',
                   'owner':'Street operations and curb management',
                   'prerequisites':['Confirm the path designation and applicable curb rules on site.'],
                   'purpose':'Reduce the need to steer around parked vehicles.'},
        'infrastructure': {'title':'Evaluate a protected passage',
                           'action':'Evaluate a continuous protected passage and designated loading space outside it.',
                           'owner':'Street design and transportation planning',
                           'prerequisites':['Measure available width and confirm the street layout.', 'Check loading demand, access requirements and junction connections.'],
                           'purpose':'Separate through movement from curb access.'}},
    'temporary_barrier': {
        'policy': {'title':'Coordinate loading and barriers',
                   'action':'Inspect the truck-and-barrier constriction and coordinate loading and temporary works to maintain a clear passage.',
                   'owner':'Street operations, curb management and temporary works',
                   'prerequisites':['Confirm the barrier purpose and temporary works requirements before changing placement.'],
                   'purpose':'Reduce avoidance maneuvers around loading and temporary works.'},
        'infrastructure': {'title':'Evaluate a continuous bypass',
                           'action':'Evaluate a continuous protected passage around loading and temporary works, with loading space outside it.',
                           'owner':'Street design and transportation planning',
                           'prerequisites':['Survey street width and the temporary works boundary.', 'Check drainage, pedestrian access and junction connections.'],
                           'purpose':'Maintain passage through a constrained section.'}},
}
FOLLOW_UP = 'Compare passage-obstruction and avoidance episodes in matched footage after the intervention.'


def interval_seconds(clips):
    parents=defaultdict(list)
    for clip in clips:
        parents[clip['original_video']].append((clip['start_sec'],clip['end_sec']))
    total=0
    for intervals in parents.values():
        end=None
        for start,stop in sorted(intervals):
            total+=max(0,stop-max(start,end if end is not None else start))
            end=max(stop,end if end is not None else stop)
    return round(total,2)


def detection_statistics(clips, detections):
    presence=Counter();peaks=Counter();available=0
    labels={'car','person','bicycle','truck','bus','motorcycle'}
    for c in clips:
        sidecar=detections.get(c['id'],{})
        if not sidecar.get('available'):continue
        available+=1;seen=set()
        for frame in sidecar.get('frames',[]):
            counts=Counter(d['label'] for d in frame.get('detections',[])
                           if d.get('label') in labels and isinstance(d.get('confidence'),(int,float)) and d['confidence']>=.5)
            seen.update(counts)
            for label,n in counts.items():peaks[label]=max(peaks[label],n)
        presence.update(seen)
    return {'detection_clips':available,
            'detected_classes':[{'label':label,'clip_count':presence[label],'peak_per_frame':peaks[label]}
                                for label in sorted(presence)],
            'detection_basis':'YOLO boxes with confidence >= 0.5; frame peaks, not unique road users'}


def references(event, clips):
    claims=defaultdict(list)
    for claim in event['claims']:claims[claim['segment_id']].append(claim)
    return [{**{k:c[k] for k in ['source','original_video','segment_number','start_sec','end_sec','camera_id','location','indexed_at']},
             'segment_id':c['id'], 'roles':sorted({q['role'] for q in claims[c['id']]}),
             'caption_evidence':' '.join(dict.fromkeys(q['quote'] for q in claims[c['id']])),
             'claims':claims[c['id']]}
            for c in sorted(clips,key=lambda c:(c['original_video'],c['start_sec'])) if c['id'] in claims]


def build_recommendations(clips, events=(), detections=None, generated_at=None):
    results=[]
    for event in events:
        refs=references(event,clips)
        support=[c for c in clips if c['id'] in {r['segment_id'] for r in refs}]
        if not support:continue
        metrics={'evidence_clips':len(refs),'evidence_seconds':interval_seconds(support),
                 'episode_count':1,'cameras':1,
                 'metric_basis':'one local episode; union of cited parent-relative intervals, not measured delay',
                 **detection_statistics(support,detections or {})}
        for category,intervention in CATALOGUE[event['subtype']].items():
            kind='passage_'+category
            results.append({**intervention, 'id':hashlib.sha256(f'{event["id"]}:{category}'.encode()).hexdigest()[:16],
                            'type':kind,'label':LABELS[kind],'category':category,
                            'severity':'review','bottleneck_id':event['id'],'bottleneck':event,
                            'camera_id':support[0]['camera_id'],'location':support[0]['location'],
                            'observation':'A physical obstruction narrows passage; indexed captions describe a maneuver around it.',
                            'follow_up':FOLLOW_UP,'metrics':metrics,'segment_refs':refs,
                            'uncertainties':event['uncertainties'],'basis':event['basis'],
                            'analysis_version':VERSION,'generated_at':generated_at})
    return results


def validate_recommendation(item, clips, detections=None):
    """Recheck source claims and catalogue; reject altered identity, action or metrics."""
    try:
        event=item['bottleneck'];refs=item['segment_refs']
        parent=refs[0]['original_video']
        cohort=[c for c in clips if c['original_video']==parent]
        selected={role:[{'segment_number':q['segment_number'],'quote':q['quote']}
                        for q in event['claims'] if q['role']==role] for role in ['obstruction','movement_effect']}
        regenerated=validate_findings(json.dumps({'findings':[selected]}),cohort)
        if event not in regenerated:return False
        expected=next(r for r in build_recommendations(cohort,[event],detections,generated_at=item.get('generated_at')) if r['type']==item['type'])
        return item==expected
    except (KeyError,IndexError,StopIteration,ValueError,TypeError):
        return False
