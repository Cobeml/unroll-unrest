# Inputs, outputs and evidence contract

## Input

The only public processing input is:

```json
{"segment_id":"ef7c083c57cb1601f04f"}
```

`POST /api/runs` resolves that canonical 20-character ID through the existing VSS archive. The client cannot supply a URL, filesystem path, bucket, model prompt, token or arbitrary video. Street/traffic sources are admitted. The **full parent** is transferred as indexed; its start is scene time zero. Segment timestamps remain parent-relative. The selected moment is a highlight, not an edited clip.

## Processing and identity

A durable job ID hashes the parent identity, coordinator version and remote service code version. Repeated submissions reuse the same job. Job records include selected segment, camera/location, source filename, parent identity internally, SHA-256/bytes, upload count, upstream run ID, versions, progress and result link. Jobs are stored under `jobs/` inside the isolated app prefix, so browser or pod restart does not erase them.

The coordinator reconciles uncertain remote create responses using `source.vm_job_id`, resumes transfers at the service's byte count, verifies full source checksum, and records the remote run ID before continuing. Output manifests provide sizes and SHA-256 for each asset. Only approved map assets are mirrored: `run.json`, `app/ride.json`, image evidence and binary grids/clouds. Video copies, logs, `.env`, depth/model files and arbitrary paths are excluded.

Automatic bindings are valid because this coordinator sent and verified the exact full parent bytes. For each indexed segment it records `[scene_start_sec, scene_end_sec]` and `clip_start_sec`; canonical camera/location are recovered from VSS. Saved demo linkage separately preserves its established visual frame match. Matching a filename alone does not prove source identity.

## Output

| Output | API / storage | Use |
| --- | --- | --- |
| Job progress | `GET /api/runs/<24hex>` | Status, stage, source checksum, versions, result link |
| Recent jobs | `GET /api/runs` | At most 100 most recent public records |
| Registered scenes | `GET /api/spatial/scenes` | Immutable scene versions and linkage status |
| Viewer document | `GET /api/rides/<scene_id>` | Route, footprints, overlays, estimates, reviews, clips and findings |
| Source video | `GET /api/rides/<scene_id>/video` | Authenticated VSS parent proxy with byte ranges |
| Segment evidence | `GET /api/evidence/<20hex>` | Caption, tags, IDs, camera/location and timestamps |
| YOLO | `GET /api/detections/<20hex>` | Segment-relative 2D frame boxes; optional sidecar |
| Spatial facts | `GET /api/spatial/context?scene_id=...&segment_id=...` | Bound estimated objects, footprints, fact IDs, visibility/reviews |
| Cosmos synthesis | `POST /api/rides/<scene_id>/analysis` | Indexed captions combined with imported map/review context |
| Stakeholder page | `/rides/<scene_id>` | Fullscreen 3D story; selected moment in `?t=5` |
| Recommendation page | `/rides/<scene_id>/recommendations/<id>` | Action, statistics, frames, video, disagreement, analysis, source |

Assets are immutable under `<scene_id>/<scene_hash>/`; the scene index is published after every validated file. Imported binaries must match the declared dimensions and checksums. Limits: 32 MiB per map asset, 96 MiB per bundle, 1 million points, 1,000 objects, 50,000 route samples. This prototype does not import arbitrary meshes or a live map socket. `SpatialScene` remains the explicit interchange interface for future live LingBot output.

## Structured recommendations

Findings are JSON, separate from Cosmos prose:

```json
{
  "id": "crossing-228-right",
  "type": "crossing_sightline",
  "severity": "review",
  "title": "Trim the hedge at crossing 2",
  "action": "Inspect, trim or lower the hedge, then recheck the bike-lane sightline.",
  "metrics": {
    "hidden_fraction": 0.97,
    "estimated_stop_m": 10,
    "estimated_clear_m": 5.3
  },
  "segment_refs": [{
    "segment_id": "02608291925981fb2ad8",
    "camera_id": "nyc_bike_gopro-1",
    "location": "new_york",
    "start_sec": 16.2162,
    "end_sec": 20
  }]
}
```

Production responses also retain `review`, `evidence_url`, `basis`, `scene_time_sec`, `object_id`, `side`, and limitations. Actions require a covered crossing approach, obstructed estimated waiting area and canonical overlapping clip references. A confirmed vegetation obstruction can propose maintenance; an unreviewed/uncertain obstruction proposes **inspection**. A rejected frame review **never** admits an action. No supported finding yields an empty list and a limited-result status.

The map's standing/moving/uncertain labels use aggregate footprint evidence. Standing does not imply illegal parking or establish queue duration, traffic delay, measured speed or vehicle identity. The same principle applies to archive detection counts: frame detections are not unique road-user counts or citywide risk rates.

Cosmos uses indexed captions plus the imported spatial estimates and confirmed/rejected reviews. It explains supported bottlenecks; it cannot overwrite the structured finding admission rules. No crash, causal mechanism, legal verdict or measured intervention benefit is invented.

## Manual saved-map import

```bash
bash tools/street-twin/with-runtime.sh .venv/bin/python tools/street-twin/spatial_import.py \
  /path/to/completed/run --s3 --bindings /path/to/private/bindings.json
```

The bindings file must give a verified existing `original_video` and a list of canonical segment intervals. See `spatial.py` import validation; unbound scenes can be stored for exploration but cannot support combined video recommendations. Keep runtime archive URIs and local manifests outside public commits.

## Read-only MCP

```bash
.venv/bin/pip install -r tools/street-twin/mcp-requirements.txt
bash tools/street-twin/with-runtime.sh .venv/bin/python tools/street-twin/mcp_bridge.py
```

Connect another agent using the executable path to `with-runtime.sh` and arguments pointing to the virtualenv Python and `mcp_bridge.py`. The wrapper sets the deployed API base; it does not expose VSS/service tokens to the agent.

Fifteen tools expose search, clip evidence, paginated YOLO, saved spatial scenes/context, demo/crossing details, analytics, legacy grounded policies and durable processing runs. `get_ride_insights(scene_id)` and `get_crossing_detail(object_id, scene_id)` work on newly reconstructed scenes. `list_processing_runs()` and `get_processing_run(job_id)` expose progress/provenance only. MCP cannot upload, start, retry, deploy or change DataEngine. Require linked segment evidence and read rejected reviews before recommending action.

The API runs inside the existing team's app access boundary. It is not a multi-tenant production authorization layer. Public job responses omit service tokens and internal parent URIs; the VSS evidence API retains canonical source identity for authorized analysis.
