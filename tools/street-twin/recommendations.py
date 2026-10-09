"""Evidence-constrained structured planning reviews from video reasoning captions."""
import hashlib
from collections import defaultdict
from observations import observations, LABELS

TEMPLATES = {
    'cyclist_passage_review': {
        'title':'Cyclist passage narrows.', 'severity':'review',
        'observation':'Captions describe lane obstruction along a cycling route.',
        'action':'Review loading placement and space available for cyclists.'},
    'curb_use_review': {
        'title':'Vehicles occupy curb space.', 'severity':'review',
        'observation':'Captions describe stopped or parked vehicles at the curb.',
        'action':'Review curb allocation and loading arrangements.'},
    'crossing_review': {
        'title':'Pedestrian crossing activity.', 'severity':'observation',
        'observation':'Captions describe pedestrians crossing the street.',
        'action':'Review crossing clearance and traffic interactions.'},
    'queue_review': {
        'title':'Vehicles stopped or moving slowly.', 'severity':'observation',
        'observation':'Captions describe stopped or slow-moving traffic.',
        'action':'Review the intersection approach across additional clips.'},
}

def build_recommendations(clips):
    groups=defaultdict(list)
    for clip in {c['id']:c for c in clips}.values():
        for kind,quote in observations(clip).items():
            groups[(kind,clip['camera_id'],clip['location'])].append((clip,quote))
    results=[]
    for (kind,camera,location),evidence in sorted(groups.items(),key=lambda x:(list(TEMPLATES).index(x[0][0]),-len(x[1]))):
        refs=[]
        for clip,quote in evidence:
            refs.append({
                'segment_id':clip['id'], 'source':clip['source'],
                'original_video':clip['original_video'], 'segment_number':clip['segment_number'],
                'start_sec':clip['start_sec'], 'end_sec':clip['end_sec'],
                'camera_id':camera, 'location':location, 'indexed_at':clip['indexed_at'],
                'caption_evidence':quote,
            })
        item={**TEMPLATES[kind], 'type':kind, 'label':LABELS[kind],
              'id':hashlib.sha256(f'{kind}:{camera}:{location}'.encode()).hexdigest()[:16],
              'camera_id':camera,'location':location,
              'metrics':{'evidence_clips':len(refs),'cameras':1,
                         'metric_basis':'distinct referenced segments; no event deduplication'},
              'segment_refs':refs, 'basis':'indexed_video_reasoning_caption'}
        if validate_recommendation(item,clips):
            results.append(item)
    return results

def validate_recommendation(item, clips):
    """Reject unsupported types, mismatched references, and empty evidence."""
    known={c['id']:c for c in clips}
    kind=item.get('type')
    if kind not in TEMPLATES or item.get('severity') not in {'review','observation'}:
        return False
    refs=item.get('segment_refs')
    if not refs or item.get('metrics',{}).get('evidence_clips')!=len(refs):
        return False
    if len({r.get('segment_id') for r in refs})!=len(refs):
        return False
    for ref in refs:
        clip=known.get(ref.get('segment_id'))
        if not clip or kind not in observations(clip):
            return False
        expected={'source':clip['source'],'camera_id':clip['camera_id'],'location':clip['location'],
                  'start_sec':clip['start_sec'],'end_sec':clip['end_sec'],
                  'original_video':clip['original_video'],'segment_number':clip['segment_number'],
                  'indexed_at':clip['indexed_at'], 'caption_evidence':observations(clip)[kind]}
        if any(ref.get(k)!=v for k,v in expected.items()):
            return False
    return True
