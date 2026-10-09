# StreetTwin

A city-streets planning board built on the existing VSS archive. Start with the rider's view, inspect recorded street conditions, and open the clips supporting each planning review.

## Run and deploy

The deliverable runs on the team Kubernetes cluster at `/app`. Use the existing team configuration and kubeconfig mounted under `/config`; do not copy them into the repository.

```bash
cd ~/vast-builders-challenge
bash tools/street-twin/deploy.sh
```

The deployment uses `python:3.12-slim`, installs the pinned small dependency set, mounts source from a ConfigMap, and injects VSS credentials from a Kubernetes Secret. It discovers the existing `/api` Ingress backend service for in-cluster calls, avoiding the VM-only hostname in the mounted configuration; it uses the configured URL if no unambiguous service is discoverable. It requires no registry, Docker build, or video uploads. Updates rerun the same command and restart the app. It only changes StreetTwin resources in the configured team namespace and refuses to overwrite another app's `/app` route.

After rollout, open [the workshop](https://workshop.thecosmoslabs.com) and click **App**. The app uses internal routes at `/`; the Ingress strips `/app`. Assets and API calls work both at `/app` and `/app/`.

For development validation, install `requirements.txt` in a Python virtual environment and run `gunicorn --chdir tools/street-twin --workers 1 --threads 8 --timeout 180 main:app` with runtime `VSS_URL`, `VSS_USERNAME`, and `VSS_PASSWORD` supplied from the mounted configuration. Development preview is not the deliverable. Use one worker because archive registration and caches are in memory.

```bash
python -m unittest discover -s tools/street-twin/tests -v
```

## Three-minute demo

1. Open **Analytics & Recommendations**. The initial view is `new_york` / `nyc_bike_gopro-1`: 30 sampled clips out of 465 available cycling clips in the explored archive. Show clip-presence bars, observation counts, and the four planning review types. Counts update with archive changes.
2. Click **Lane obstruction on a cycling route**. Only its referenced clips appear in Evidence / Clips. Play the USPS-truck segment, toggle YOLO context, and show the camera, location, parent-relative time, indexed date, and source ID. Peak YOLO counts describe a clip, not unique road users. **Describe this video** reads all six indexed segments of the parent video through VSS agent Q&A.
3. Return to Analytics and use the three example buttons below. Each resolves a known filename from the live archive rather than relying on search ranking. Buttons reset filters to the anchor's NYC biking camera.

| Example / search query | Planning review | Verified filename and parent-relative time |
| --- | --- | --- |
| Delivery trucks partially blocking the street while cycling | Cyclist passage / curb use | `20261008_072535_GOPR0130_chunk_0004_segment_005_of_006.mp4`, 20–25 s |
| Pedestrians crossing the road near bicycles and moving vehicles | Crossing activity | `20261008_074241_GX010001_chunk_0014_segment_002_of_006.mp4`, 5–10 s |
| Cars stopped or moving slowly beside a protected bike lane | Approach queue | `20261008_074151_GX010001_chunk_0012_segment_006_of_006.mp4`, 25–30 s |

Search these descriptions in Evidence / Clips to retrieve related footage. A relevant search hit can describe routine activity; it does not automatically produce a planning review. **Reset** returns to the current archive sample.

To demonstrate camera filtering, choose Nashville / `i24_cam-1`: the sampled highway captions describe free-flowing traffic, so there are no supported congestion reviews. Choose Neighborhood / `neighborhood_cam-1` to inspect residential footage. Changing location clears an incompatible camera selection; only cameras for that location remain in the menu.

## Evidence and recommendation contract

`GET /api/analytics` samples up to 96 segments from selected parent videos across cameras and archive positions. Optional `location`, `camera_id`, `start`, and `end` filter the indexed archive. The date fields describe indexing, not recording time. `GET /api/search?query=…` applies the same filters to up to 30 semantic-search results and recomputes clip-presence analytics.

Other routes: `GET /api/metadata`, `/api/stats`, `/api/recommendations`, `/api/evidence/<id>`, `/api/detections/<id>`, `/api/stream/<id>`, `/api/demo/{passage,crossing,queue}`, `/api/spatial`, `/health`; `POST /api/reason/<id>` describes the parent video. Internal `id` is a deterministic hash of the canonical VSS segment source; `source` is retained as the stable archive identifier.

Recommendations contain `id`, `type`, `severity`, `observation`, `action`, `metrics`, and `segment_refs[]`. Types are `cyclist_passage_review`, `curb_use_review`, `crossing_review`, and `queue_review`. Severity is `review` for obstruction/curb review and `observation` for crossing/slow-traffic observations; these indicate review priority, not calibrated risk. Every reference includes segment ID/source, parent video, segment number, seconds, camera, location, indexed timestamp, and the supporting caption sentence.

Cosmos video-reasoning captions establish observations. Conservative templates convert explicit caption phrases to structured recommendations, and a validator checks references and observation support. YOLO provides clip-presence charts, peak detection counts, and synchronized frame boxes; object co-occurrence alone does not establish proximity or danger. Negated congestion/obstruction statements are excluded. Agent Q&A is optional descriptive context and never overrides structured recommendations. This does not establish legal violations, engine idling, measured distances, vehicle speeds, congestion duration, or unique vehicle totals.

The sample is selected, not statistically representative. Neighboring segments may depict the same event; evidence-clip counts are not event counts. No derived VastDB writes or DataEngine edits are needed. Tokens and data caches are held in server memory for up to five minutes. Streaming supports Range requests and uses only sources registered through archive discovery/search. Credentials and JWTs never go to the browser.

## Corpus and re-ingest notes

Explored Pack A (`i24_cam-1`, 180 indexed clips), Pack D (`neighborhood_cam-1`, 307), NYC first-person cycling (`nyc_bike_gopro-1`, 465), and NYC street footage. The default uses cycling footage because current captions already include usable curb, passage, crossing, and slow-traffic descriptions. The explored archive contains 612 parent videos and 3,537 indexed segments. At exploration, 14 additional S3 segments were pending indexing; those are not included in app totals.

**No re-ingest prompts were used. No videos were uploaded.** Unsupported concepts remain unavailable rather than inferred. Any future small-chunk re-ingest should use the matching ingest skill and preserve existing camera/location metadata.

## Spatial interface only

`spatial.py` defines `SpatialImport { mesh_ref, segment_ids[], camera_poses? }`. Optional poses include camera ID, an existing StreetTwin segment ID, coordinate system, and a 4×4 transform. `GET /api/spatial` returns `connected: false`. The Spatial tab describes this interface; it performs no upload, reconstruction, or LingBot call.
