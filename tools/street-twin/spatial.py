"""Interface only for a future LingBot/map-mesh adapter; no import executes."""
from typing import TypedDict, NotRequired

class CameraPose(TypedDict):
    camera_id: str
    segment_id: str
    coordinate_system: str
    pose_4x4: list[list[float]]

class SpatialImport(TypedDict):
    mesh_ref: str
    segment_ids: list[str]
    camera_poses: NotRequired[list[CameraPose]]

SPATIAL_INTERFACE = {
    'connected': False,
    'name': 'SpatialImport',
    'fields': {'mesh_ref':'URI of a future mesh',
               'segment_ids':'StreetTwin segment IDs returned by /api/analytics',
               'camera_poses':'Optional camera ID, segment ID, coordinate system and 4×4 pose'},
}
