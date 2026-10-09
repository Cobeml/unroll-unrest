"""Saved crossing-sightline demo; archive playback and descriptive imported findings."""
import copy
import json
import math

SCENE_ID='20261009-125354-biker'
PARENT_FILENAME='20261008_074640_GX050001_chunk_0000.mp4'


def viewer_export(raw,scene):
    from spatial import SpatialError,number
    def select(obj,keys):return {k:copy.deepcopy(obj[k]) for k in keys.split() if k in obj}
    doc=select(raw,'fps frame_size daylight_m stats rules overlays')
    doc.update({k:copy.deepcopy(scene[k]) for k in ['path','extent','cam_h','hfov']})
    doc['stats']=select(raw.get('stats',{}),'duration distance crosswalks crossings_judged crossings_exposed ends_judged ends_exposed stopped vehicles furniture blocking scale_note checked confirmed rejected review_model')
    doc['stats']['duration']=scene['duration']
    doc['rules']=select(raw.get('rules',{}),'react_s decel window_m target_h clear cam_h')
    doc['fps']=number(doc.get('fps',5))
    if not 0<doc['fps']<=120:raise SpatialError('Invalid viewer frame rate.')
    shape=doc.get('frame_size',[])
    if len(shape)!=2 or any(type(v) is not int or not 1<=v<=16384 for v in shape):raise SpatialError('Invalid viewer frame size.')
    by_id={int(o['id']):o for o in scene['objects']}
    overlays=doc.get('overlays',{})
    if not isinstance(overlays,dict) or len(overlays)>len(scene['path']):raise SpatialError('Invalid viewer overlays.')
    for key,boxes in overlays.items():
        if not str(key).isdigit() or not 0<=int(key)<len(scene['path']) or not isinstance(boxes,list) or len(boxes)>1000:raise SpatialError('Invalid viewer overlay frame.')
        for box in boxes:
            if not isinstance(box,list) or len(box)!=5 or box[0] not in by_id or any(not math.isfinite(number(v)) for v in box[1:]):raise SpatialError('Invalid viewer object box.')
    doc['objects']=[]
    for src in raw['objects']:
        o=select(src,'id group label kinds seen t0 t1 xy spread passed parked footprint rect height blocks edge exposed confirmed t_pass')
        o['motion']=by_id[o['id']]['motion']
        o['label']=str(o.get('label') or o['group'])[:100]
        # Preserve exported visibility and review details without copying run/config fields.
        if 'ends' in src:
            o['ends']=[]
            for e in src['ends'][:4]:
                end=select(e,'side area covered why exposed seen_at_stop needed_m speed_kmh stop_k stop_d clear_k clear_from_m unnamed stop_t')
                end['side']=e.get('side') if e.get('side') in {'left','right'} else 'unknown'
                end['blockers']=[select(b,'id n before_m in_20ft') for b in e.get('blockers',[])[:20]]
                if any(b.get('id') not in by_id for b in end['blockers']):raise SpatialError('Unknown sightline blocker.')
                end['frames']=[select(f,'k d seen counted poly') for f in e.get('frames',[])[:2000]]
                for key in ['seen_at_stop','needed_m','speed_kmh','clear_from_m','stop_d']:
                    if end.get(key) is not None:
                        value=number(end[key])
                        if value<0 or (key=='seen_at_stop' and value>1):raise SpatialError('Invalid crossing estimate.')
                for f in end['frames']:
                    if f.get('poly') is not None and (len(f['poly'])!=8 or any(not isinstance(p,list) or len(p)!=2 for p in f['poly'])):raise SpatialError('Invalid projected watch area.')
                if isinstance(e.get('review'),dict):end['review']=select(e['review'],'claim reason model crossing_ahead area_visible_in_image_1 blocker blocker_kind blocker_between blocker_named_right frames')
                i=len(o['ends']);asset=scene['assets'].get('end_'+str(o['id'])+'_'+str(i))
                if asset:end['evidence']=asset['url']
                o['ends'].append(end)
        doc['objects'].append(o)
    doc['ortho']=scene['assets']['ortho']['url']
    if 'points' in scene['assets']:
        doc['cloud']={'points':scene['assets']['points']['url'],'colours':scene['assets']['colours']['url'],'n':scene['assets']['points']['size']//12}
    if scene.get('visibility'):doc['view']={**scene['visibility'],'file':scene['assets']['visibility']['url']}
    def bounded(value,depth=0):
        if depth>12:raise SpatialError('Viewer document too deeply nested.')
        if isinstance(value,str) and len(value)>2000:raise SpatialError('Viewer text exceeds limit.')
        if isinstance(value,(int,float)) and (not math.isfinite(value) or abs(value)>1e6):raise SpatialError('Invalid viewer number.')
        if isinstance(value,dict):
            for v in value.values():bounded(v,depth+1)
        elif isinstance(value,list):
            for v in value:bounded(v,depth+1)
    bounded(doc)
    return doc


def demo_document(store,vss):
    from spatial import SpatialError
    from vss import normalize
    scene=store.scene(SCENE_ID)
    if not scene.get('bindings') or 'viewer' not in scene['assets']:raise SpatialError('The demo needs its saved export and verified archive bindings.',503)
    vss.archive()
    clips=[]
    for binding in scene['bindings']:
        row=vss.get_segment(binding['segment_id'])
        if row.get('original_video','').rsplit('/',1)[-1]!=PARENT_FILENAME:raise SpatialError('Demo source does not match the indexed ride.',503)
        clips.append(normalize(row,binding['segment_id']))
    body,_,_=store.asset(SCENE_ID,'viewer');doc=json.loads(body)
    doc.update(scene_id=SCENE_ID,scene_hash=scene['hash'],source_filename=PARENT_FILENAME,clips=clips,
        video='api/ride/video',quality=scene['quality'],source_verification=scene.get('source_verification'),
        findings=crossing_findings(doc,clips))
    return doc


def crossing_findings(doc,clips):
    objects={o['id']:o for o in doc['objects']};findings=[]
    crossings=sorted((o for o in doc['objects'] if o['group']=='crosswalk'),key=lambda o:o.get('t_pass',0))
    for index,c in enumerate(crossings,1):
        for e in c.get('ends',[]):
            review=e.get('review') or {};claim=review.get('claim','unreviewed');seen=e.get('seen_at_stop')
            if not e.get('covered') or seen is None or seen>=doc.get('rules',{}).get('clear',.9):continue
            if claim=='rejected':continue
            confirmed=claim=='confirmed'
            blockers=[objects[b['id']] for b in e.get('blockers',[]) if b['id'] in objects]
            planting=any(b['group'] in {'hedge','planter','tree'} for b in blockers)
            title='Trim the hedge at crossing '+str(index) if confirmed and planting else 'Inspect the '+e['side']+' sightline at crossing '+str(index)
            action='Inspect the crossing approach and trim or lower the hedge that screens the waiting area. Recheck the sightline from the bike lane after maintenance.' if confirmed and planting else 'Inspect the crossing approach on site and confirm the obstruction before changing the street layout.'
            start=e.get('stop_t',c.get('t_pass',0));end=min(doc['stats']['duration'],c.get('t_pass',start)+1)
            refs=[{'segment_id':clip['id'],'camera_id':clip['camera_id'],'location':clip['location'],'start_sec':max(start,clip['start_sec']),'end_sec':min(end,clip['end_sec'])} for clip in clips if clip['start_sec']<end and clip['end_sec']>start]
            findings.append({'id':f'crossing-{c["id"]}-{e["side"]}','type':'crossing_sightline','severity':'review','title':title,'action':action,
                'basis':'saved_spatial_estimate_and_imported_vision_review','review':review,'crossing':index,'object_id':c['id'],'side':e['side'],
                'metrics':{'hidden_fraction':round(1-seen,3),'estimated_stop_m':e.get('needed_m'),'estimated_clear_m':e.get('clear_from_m'),'estimated_speed_kmh':e.get('speed_kmh')},
                'segment_refs':refs,'evidence_url':e.get('evidence'),'scene_time_sec':start,
                'limitations':'Geometry and stopping distances use an assumed camera height. This is a maintenance proposal, not a calibrated safety or legal finding.'})
    return findings
