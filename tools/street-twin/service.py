"""Bounded archive sampling and honest analytics; no derived database writes."""
from collections import Counter, defaultdict
from datetime import date
from observations import observations, LABELS
from recommendations import build_recommendations

# Match discovered filenames, never construct deployment-specific S3 paths.
DEMO_ANCHORS = {
    'traffic':('20261008_072948_GOPR0130_chunk_0014_segment_002_of_006.mp4',
               'Cyclist weaving between vehicles in slow city traffic'),
    'bottleneck':('20261008_074847_GX050001_chunk_0005_segment_004_of_006.mp4',
                  'Parked red sedan obstructs the riding path; rider maneuvers around it'),
    'passage':('20261008_072535_GOPR0130_chunk_0004_segment_005_of_006.mp4',
               'Delivery trucks partially blocking the street while cycling'),
    'crossing':('20261008_074241_GX010001_chunk_0014_segment_002_of_006.mp4',
                'Pedestrians crossing the road near bicycles and moving vehicles'),
    'queue':('20261008_074151_GX010001_chunk_0012_segment_006_of_006.mp4',
             'Cars stopped or moving slowly beside a protected bike lane'),
}

class BadFilter(Exception):
    pass

def filters_from(args, metadata):
    filters = {'metadata_filters':{}, 'time_filter':'all'}
    for key in ['location','camera_id']:
        value = args.get(key,'').strip()
        if value:
            if value not in metadata.get(key, []):
                raise BadFilter('Choose a location or camera from the archive.')
            filters['metadata_filters'][key] = value
    start, end = args.get('start',''), args.get('end','')
    try:
        if start: date.fromisoformat(start)
        if end: date.fromisoformat(end)
    except ValueError:
        raise BadFilter('Use valid indexed dates.') from None
    if start and end and start > end:
        raise BadFilter('Indexed from must precede indexed through.')
    if start or end:
        filters.update(time_filter='custom',
            custom_start_date=(start or '1970-01-01')+'T00:00:00Z',
            custom_end_date=(end or max(start, date.today().isoformat()))+'T23:59:59.999999Z')
    return filters

def matches(row, filters):
    if row.get('capture_type') not in {'streets','traffic'}:
        return False
    if any(row.get(k) != v for k,v in filters['metadata_filters'].items()):
        return False
    if filters['time_filter'] == 'custom':
        day = (row.get('indexed_at') or row.get('upload_timestamp') or '')[:10]
        if not day or not filters['custom_start_date'][:10] <= day <= filters['custom_end_date'][:10]:
            return False
    return True

def sample(vss, filters):
    chunks = [c for c in vss.archive() if matches(c,filters)]
    groups = defaultdict(list)
    for c in chunks:
        groups[c.get('camera_id')].append(c)
    selected = []
    anchor_names = {name.rsplit('_segment_',1)[0]+'.mp4' for name,_ in DEMO_ANCHORS.values()}
    selected.extend(c for c in chunks if c.get('filename') in anchor_names)
    # Spread the bounded sample over available cameras and each camera's archive.
    for fraction in [0, .5, 1]:
        for camera in sorted(groups):
            rows=groups[camera]
            selected.append(rows[int((len(rows)-1)*fraction)])
    seen_parents=set()
    clips={}
    for chunk in selected:
        if chunk['original_video'] in seen_parents:
            continue
        seen_parents.add(chunk['original_video'])
        for row in chunk.get('timeline',[]):
            clip=vss.register({**{k:v for k,v in chunk.items() if k!='timeline'},**row})
            if clip:
                clips[clip['id']]=clip
        if len(clips)>=96:
            break
    anchor_files={name for name,_ in DEMO_ANCHORS.values()}
    ordered=sorted(clips.values(),key=lambda c:(c['filename'] not in anchor_files, c['camera_id'], c['filename']))
    return analytics(ordered[:96], available_clips=sum(len(c.get('timeline',[])) for c in chunks),
                     available_cameras=len(groups), filters=filters)

def analytics(clips, *, available_clips=None, available_cameras=None, filters=None):
    unique={c['id']:c for c in clips}
    clips=list(unique.values())
    classes=Counter()
    conditions=Counter()
    for clip in clips:
        classes.update(set(clip['object_classes']))
        observed=observations(clip)
        clip['observation_tags']=[LABELS[k] for k in observed]
        conditions.update(observed.keys())
    relevant=['car','person','bicycle','truck','bus','motorcycle']
    return {
        'clips':clips, 'sample_count':len(clips),
        'available_clips':available_clips, 'available_cameras':available_cameras,
        'camera_count':len({c['camera_id'] for c in clips}),
        'object_chart':[{'label':k,'clip_count':classes[k]} for k in relevant if classes[k]],
        'conditions':[{'type':k,'label':LABELS[k],'clip_count':conditions[k]} for k in LABELS],
        'filters':filters, 'recommendations':build_recommendations(clips),
        'sampling_note':'Up to 96 segments from selected parent videos; this is an archive sample.',
    }


def demo(vss, name):
    if name not in DEMO_ANCHORS:
        raise BadFilter('Choose an existing demo preset.')
    filename,query=DEMO_ANCHORS[name]
    for chunk in vss.archive():
        for row in chunk.get('timeline',[]):
            if row.get('source','').rsplit('/',1)[-1]==filename:
                clip=vss.register({**{k:v for k,v in chunk.items() if k!='timeline'},**row})
                neighbors=[vss.register({**{k:v for k,v in chunk.items() if k!='timeline'},**r})
                           for r in chunk.get('timeline',[])]
                neighbors=[c for c in neighbors if c]
                result=analytics(neighbors,available_clips=len(neighbors),available_cameras=1)
                result['demo']={'name':name,'query':query,'verified_anchor':True}
                result['selected_segment_id']=clip['id']
                return result
    raise BadFilter('This preset is no longer present in the indexed archive.')
