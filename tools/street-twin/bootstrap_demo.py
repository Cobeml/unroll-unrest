"""Restore the already verified demo from a completed teammate export."""
import argparse
import tempfile
from ride_sync import pull, token, service_url
from spatial import SceneStore, SpatialError, import_bundle, read_json
from ride_demo import SCENE_ID, PARENT_FILENAME, demo_document
from vss import VSS


def bootstrap(store,vss):
    # This is an explicit known/previously verified pair, not filename inference
    # for arbitrary maps. New runs use authenticated byte/checksum provenance.
    parents=[c for c in vss.archive() if c.get('original_video','').rsplit('/',1)[-1]==PARENT_FILENAME]
    if len(parents)!=1:raise SpatialError('The exact verified demo parent is missing or ambiguous.')
    parent=parents[0]
    with tempfile.TemporaryDirectory(prefix='unfold-bootstrap-') as tmp:
        directory=pull(service_url(),tmp,run_id=SCENE_ID,access_token=token())
        raw=read_json(directory/'app/ride.json')
        duration=max(float(raw['stats']['duration']),float(raw['path'][-1]['t']))
        rows=[(sid,row) for sid,row in vss.segments.items() if row.get('original_video')==parent['original_video']]
        manifest={'original_video':parent['original_video'],'verification':{'archive_filename':PARENT_FILENAME,'frame_time_sec':16.2162},
            'bindings':[{'segment_id':sid,'scene_start_sec':row['segment_start_sec'],
                'scene_end_sec':min(duration,row['segment_end_sec']),'clip_start_sec':0}
                for sid,row in rows if row['segment_start_sec']<duration]}
        staging=SceneStore(root=tmp+'/staging');staging.bucket=None
        scene=import_bundle(directory,staging,bindings=manifest,vss=vss)
        doc=demo_document(staging,vss)
        if not any(f['id']=='crossing-228-right' for f in doc['findings']):
            raise SpatialError('Restored export differs from the verified demonstration.')
        bodies={key:staging.asset(scene['id'],key)[0] for key in scene['assets']}
        store.publish(scene,bodies)
        return scene


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--s3',action='store_true');args=parser.parse_args()
    try:
        store=SceneStore()
        if not args.s3:store.bucket=None
        scene=bootstrap(store,VSS())
        print('Restored verified demo:',scene['id'])
    except Exception as e:
        print(str(e) if isinstance(e,SpatialError) else 'Demo bootstrap unavailable. Check the completed export and runtime.')
        raise SystemExit(1) from None
