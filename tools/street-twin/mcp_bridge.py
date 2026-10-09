"""Read-only stdio MCP bridge to StreetTwin's combined evidence APIs."""
import math
import os
import re
from typing import Any
from urllib.parse import urlparse
import requests
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp=FastMCP('StreetTwin',instructions='Use indexed clips and YOLO for observed events; spatial facts are estimates. Require explicit clip linkage before combining evidence. Do not infer parking legality, delay or vehicle identity from standing objects. All tools are read-only.')
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=True)


def api(path,params=None):
    base=os.environ.get('STREETTWIN_API_BASE','http://127.0.0.1:8080/').rstrip('/')+'/'
    parsed=urlparse(base)
    if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Set a valid STREETTWIN_API_BASE without credentials.')
    headers={}
    if os.environ.get('STREETTWIN_APP_TOKEN'):headers['Authorization']='Bearer '+os.environ['STREETTWIN_APP_TOKEN']
    try:
        r=requests.get(base+'api/'+path,params=params,headers=headers,timeout=(10,150),allow_redirects=False)
        if r.status_code not in {200,202}:return {'error':'StreetTwin data unavailable. Check the app connection and identifiers.','status':r.status_code}
        return r.json()
    except (requests.RequestException,ValueError):return {'error':'StreetTwin connection unavailable.'}


def segment(value):
    if not re.fullmatch('[a-f0-9]{20}',value):raise ValueError('Use an existing 20-character segment ID.')
    return value


def scene(value):
    if not re.fullmatch('[A-Za-z0-9_-]{1,80}',value):raise ValueError('Choose a registered scene ID.')
    return value


def scope(location='',camera_id='',start='',end='',scene_id=''):
    if scene_id:scene(scene_id)
    return {k:v for k,v in locals().items() if v}


@mcp.tool(annotations=READ)
def search_clips(query:str,location:str='',camera_id:str='',start:str='',end:str='')->dict[str,Any]:
    """Search indexed video with camera/location/indexing-date filters. Returns captions, IDs and aggregates."""
    if not 3<=len(query)<=500:raise ValueError('Use a query between 3 and 500 characters.')
    result=api('search',{'query':query,**scope(location,camera_id,start,end)})
    if 'clips' in result:result['clips']=result['clips'][:30]
    return result


@mcp.tool(annotations=READ)
def get_clip_evidence(segment_id:str)->dict[str,Any]:
    """Read a canonical archive caption with camera, location, parent and segment timestamps."""
    return api('evidence/'+segment(segment_id))


@mcp.tool(annotations=READ)
def get_detections(segment_id:str,start_sec:float=0,end_sec:float=30,offset:int=0,limit:int=20)->dict[str,Any]:
    """Read a bounded page of YOLO frames. Times are relative to the playable segment; boxes are 2D."""
    if not all(math.isfinite(t) for t in [start_sec,end_sec]) or start_sec<0 or end_sec<start_sec or offset<0 or not 1<=limit<=100:raise ValueError('Choose a valid frame interval/page.')
    result=api('detections/'+segment(segment_id))
    frames=[f for f in result.get('frames',[]) if start_sec<=f.get('time_sec',-1)<=end_sec]
    if 'frames' in result:result['frames']=frames[offset:offset+limit];result['next_offset']=offset+limit if len(frames)>offset+limit else None
    return result


@mcp.tool(annotations=READ)
def list_spatial_scenes()->dict[str,Any]:
    """List saved reconstructions, versions and whether archive bindings exist."""
    return api('spatial/scenes')


@mcp.tool(annotations=READ)
def get_spatial_scene(scene_id:str)->dict[str,Any]:
    """Read map quality, asset links and archive bindings. Use context for objects; binaries stay outside MCP."""
    result=api('spatial/scenes/'+scene(scene_id))
    if 'objects' in result:result['object_count']=len(result.pop('objects'))
    if 'path' in result:result['route_samples']=len(result.pop('path'))
    return result


@mcp.tool(annotations=READ)
def get_spatial_context(scene_id:str,segment_id:str='',start_sec:float=0,end_sec:float|None=None,object_id:str='')->dict[str,Any]:
    """Read estimated objects/footprints with fact IDs. A segment ID requires verified scene linkage."""
    p={'scene_id':scene(scene_id)}
    if segment_id:p['segment_id']=segment(segment_id)
    else:
        if not math.isfinite(start_sec) or (end_sec is not None and not math.isfinite(end_sec)):raise ValueError('Choose finite scene times.')
        p['start']=start_sec
        if end_sec is not None:p['end']=end_sec
    if object_id:p['object_id']=scene(object_id)
    return api('spatial/context',p)


@mcp.tool(annotations=READ)
def get_analytics(location:str='',camera_id:str='',start:str='',end:str='')->dict[str,Any]:
    """Read descriptive archive samples and detection aggregates, not citywide rates."""
    return api('analytics',scope(location,camera_id,start,end))


@mcp.tool(annotations=READ)
def get_recommendations(location:str='',camera_id:str='',scene_id:str='',demo:str='')->dict[str,Any]:
    """Read/reuse grounded analysis. May return a background job; this never writes to the archive."""
    p=scope(location,camera_id,scene_id=scene_id)
    if demo:p['demo']=demo
    return api('recommendations',p)


@mcp.tool(annotations=READ)
def get_analysis_status(job_id:str)->dict[str,Any]:
    """Poll a recommendation job returned by get_recommendations."""
    if not re.fullmatch('[a-f0-9]{16}',job_id):raise ValueError('Choose an existing job ID.')
    return api('analysis/'+job_id)


@mcp.tool(annotations=READ)
def get_policy_report(policy_id:str,location:str='',camera_id:str='',scene_id:str='',demo:str='')->dict[str,Any]:
    """Read a recommendation's clips, statistics, limitations and selected spatial facts in its original scope."""
    if not re.fullmatch('[a-f0-9]{16}',policy_id):raise ValueError('Choose an existing policy ID.')
    p=scope(location,camera_id,scene_id=scene_id)
    if demo:p['demo']=demo
    return api('policy/'+policy_id,p)

if __name__=='__main__':mcp.run(transport='stdio')
