"""Import only derived map assets; never upload video or call ingestion."""
import argparse
import os
from spatial import SceneStore, SpatialError, import_bundle, read_json
from pathlib import Path
from vss import VSS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory');parser.add_argument('--id');parser.add_argument('--bindings',type=Path)
    parser.add_argument('--local',type=Path,help='Local map store (development)')
    parser.add_argument('--s3',action='store_true',help='Use configured app-owned map bucket')
    args=parser.parse_args()
    if args.local and args.s3:parser.error('Choose local or S3 storage.')
    if args.s3 and not os.environ.get('STREETTWIN_SPATIAL_BUCKET'):parser.error('Set STREETTWIN_SPATIAL_BUCKET to the dedicated map bucket.')
    store=SceneStore(root=args.local,bucket=os.environ.get('STREETTWIN_SPATIAL_BUCKET') if args.s3 else None)
    if not args.s3:store.bucket=None
    try:
        manifest=read_json(args.bindings) if args.bindings else None
        scene=import_bundle(args.directory,store,scene_id=args.id,bindings=manifest,vss=VSS() if manifest else None)
        print(f'Imported {scene["id"]}: {len(scene["objects"])} objects, {len(scene["bindings"])} linked archive segments.')
    except Exception as error:
        print(str(error) if isinstance(error,SpatialError) else 'Map import failed. Check the bundle and runtime configuration.')
        raise SystemExit(1) from None

if __name__=='__main__':main()
