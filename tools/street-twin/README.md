# Unfold — Crosswalk Sightlines

The UnfoldUnrest ride demo on the existing VSS infrastructure: synchronized indexed bike video, a saved LingBot street reconstruction, crossing visibility, stopping-model comparisons, vision-review agreement/disagreement, and cited maintenance proposals. The default page uses the actual `20261008_074640_GX050001_chunk_0000.mp4` archive video. Reconstruction remains on the teammate’s machine. The VM imports saved outputs; no live reconstruction or new-video submission is required.

## Demo first

Open [the workshop](https://workshop.thecosmoslabs.com) → **App**. The home page is **Unfold**; the existing archive/search workflow is available through **Video archive** (`/archive`).

1. **Play the ride.** The same indexed 30-second video drives the 3D rider, route, object boxes, visibility grid and sightline overlays. Story mode slows playback to 0.4× around the assessed crossing and displays a slowdown label; all timestamps remain source-video times.
2. **Jump to crossing 2.** Click its timeline marker or crossing entry. The saved reconstruction estimates 97% of the right waiting area hidden near a 10 m modeled stopping distance, becoming fully visible about 5.3 m out. The imported Qwen review agrees that a hedge screens it. The left-side spatial claim is retained as disputed because the vision review rejects it.
3. **Open “Trim the hedge at crossing 2.”** Its page has the action, estimated statistics, paired evidence images, two indexed segment references, camera/location, and replay links. **Read Cosmos video analysis** synthesizes the same six archive segments with the imported spatial/review context; it cannot change the saved structured proposal.
4. Use **Behind the rider**, **Whole street**, **Look around**, **What the rider saw**, and **3D points** to inspect the reconstruction. Toggle **Sightlines → YOLO objects → No overlays** on the video. Space plays/pauses; arrow keys jump between crossings.
5. Show the other two crossings: one starts too close to assess; the rider turns at the other. The demo preserves these gaps rather than filling them with findings.

The 125 m route length, speed, stopping distances, footprints and visibility percentages are imported estimates using a 1.1 m assumed camera height, 1.5 s reaction time and 3 m/s² braking. The daylighting proposal calls for inspection/maintenance, not a legal or calibrated safety verdict. All six clip bindings were verified against the named archive parent; its frame at 16.2162 s visually matches the saved crossing evidence. No map video was downloaded or uploaded. `ride-preview.jpg` is a first-frame image derived from that indexed parent.

Demo endpoints: `GET /api/ride` returns the saved viewer data plus structured `findings[]` (`type`, `severity`, `metrics`, `segment_refs[]`); `GET /api/ride/video` proxies only the registered demo parent with Range support; `POST /api/ride/analysis` requests/caches Cosmos synthesis. `/finding/crossing-228-right` is the recommendation page. Map assets and the original archive remain in the existing infrastructure; CSS, JavaScript and Three.js are served locally.

## Run and deploy

The deliverable runs on the team Kubernetes cluster at `/app`. Credentials and kubeconfig remain under `/config`.

```bash
cd ~/vast-builders-challenge
python3 -m venv .venv  # only if the repository venv does not already exist
.venv/bin/python -m pip install -r tools/street-twin/mcp-requirements.txt
bash tools/street-twin/deploy.sh
```

Open [the workshop](https://workshop.thecosmoslabs.com) → **App** after rollout. The deployment uses a public Python image, versioned code and browser-module ConfigMaps, runtime Secret, and the existing team's Ingress. It discovers the existing `/api` Service for backend calls. Updates restart StreetTwin; another app's `/app` route is never overwritten. No Docker build, registry or DataEngine changes are required.

For development verification, install `requirements.txt` in a Python virtual environment, supply runtime `VSS_URL`, `VSS_USERNAME`, and `VSS_PASSWORD` without writing them into the repository, and run:

```bash
gunicorn --chdir tools/street-twin --workers 1 --threads 8 --timeout 180 main:app
python -m pip install -r tools/street-twin/mcp-requirements.txt
python -m unittest discover -s tools/street-twin/tests -v
```

One worker is required because analysis jobs and archive registration are in memory. Development preview is for testing; the deployed App is the deliverable. Never commit `.env` files or credentials.

## Archive comparison demos

1. **Find the bottleneck.** Click **Blocked passage**. The red sedan occupies part of the riding path; the rider steers around it. Footage loads immediately while background analysis diagnoses the obstruction. Use **car** to highlight YOLO boxes and **Play evidence** to watch the maneuver.
2. **Open the policy recommendation.** Choose **Keep the riding path clear**. Show one local episode, two cited clips, and 10 seconds of referenced footage. Citations distinguish the obstruction from the avoidance maneuver. Open **Implementation & evidence limits** for the responsible function, curb-rule checks, and follow-up. Reload the report URL to demonstrate shareable evidence.
3. **Open the infrastructure recommendation.** Return to Street view and open **Evaluate a protected passage**. The action proposes a continuous passage and loading space outside it, conditional on measuring width and checking access and junctions. Both recommendations cite the same diagnosed bottleneck. Use **Truck & barrier** as a second case: the pipeline generates different loading/temporary-works actions.

The presets resolve filenames in the live indexed archive, independent of search ranking. They include all six neighboring segments from their parent for temporal context. The primary maneuver is selected automatically.

| Search query / demo | Evidence | Supported action |
| --- | --- | --- |
| Parked red sedan obstructs the riding path; rider maneuvers around it | `20261008_074847_GX050001_chunk_0005_segment_004_of_006.mp4`, 15–20 s; preceding segment at 10–15 s | Coordinate curb use to keep passage clear |
| Evaluate a protected passage where a parked car causes an avoidance maneuver | Same red-sedan sequence; infrastructure card under **Blocked passage** | Survey a continuous protected passage and designated loading space |
| Delivery truck and barrier narrow passage; cyclists navigate past the truck | `20261008_072535_GOPR0130_chunk_0004_segment_004_of_006.mp4`, 15–20 s; neighboring obstruction context | Coordinate loading/temporary works; evaluate a continuous bypass |

Primary segment ID: `7d023dd390c2a7baac0f`. Truck maneuver ID: `3abeb5fe5ebffa78b989`. Camera: `nyc_bike_gopro-1`; location: `new_york`. Seconds are parent-relative, not recording clock times.

Select Nashville / I-24 to show a negative case: normal traffic produces no bottleneck recommendation. Neighborhood / Pack D parking alone also does not qualify. Crossing and queue archive presets remain available through `/api/demo/crossing` and `/api/demo/queue`; feature presence or red-light queues alone do not establish actionable bottlenecks.

## Three reliable archive queries

Scope these to New York / `nyc_bike_gopro-1`. Semantic ranking can vary; the corresponding preset always opens the verified archive anchor.

| Query | Preset / evidence | Demonstration |
| --- | --- | --- |
| Parked red sedan obstructs the riding path; rider maneuvers around it | **Blocked passage** · `7d023dd390c2a7baac0f`, 15–20s | Policy: keep the riding path clear; infrastructure: evaluate protected passage |
| Delivery trucks partially blocking the street while cycling | **Truck & barrier** · neighboring clips from `GOPR0130_chunk_0004` | Coordinate loading/barriers and evaluate a continuous bypass |
| Cyclist weaving between vehicles in slow city traffic | **Cycling in traffic** · `ef7c083c57cb1601f04f`, 5–10s | Clip retrieval and real YOLO context; a crash or qualifying obstruction is not established |

The third clip was inspected at 0, 2 and 4 seconds of playback. It shows close passage between vehicles; no collision was visible in those sampled frames. “Biker close call”/“crash” search results did not establish a crash, so the UI does not label this clip as one or manufacture a recommendation. `traffic-preview.jpg` is a derived first-frame image tied only to this segment.

## How recommendations are generated

The default crossing demo reads a checksum-validated saved export and requires explicit bindings to the named archive parent. It preserves the full crossing-end visibility samples, blocker references, stopping-model estimates and imported vision reviews. A covered, screened side with an agreeing review can produce a hedge-maintenance proposal; rejected reviews produce no proposal. An unreviewed spatial finding can only request inspection. References are computed from the actual overlapping archive intervals. The JSON action and statistics are deterministic; the optional Cosmos synthesis receives both the indexed video and imported spatial context, with their provenance and limitations.

The pipeline retrieves candidate clips, expands neighboring evidence, synthesizes a diagnosis from indexed video-reasoning captions, validates every quotation, computes statistics, and chooses interventions from a mechanism-specific catalogue. Ordinary street observations remain descriptive; keyword matches no longer produce recommendation cards.

V1 admits **obstructed passage with an observed avoidance maneuver**, with parked-vehicle and temporary-barrier subtypes. Each diagnosis requires both an obstruction and a movement-effect quote in nearby segments of the same parent. Unknown segment numbers, altered quotations, unrelated intervals, negated claims and speculative movement are rejected. JSON and a single JSON code fence are supported; one complete leading Cosmos `<think>…</think>` block is discarded. Decimal segment-number strings are losslessly normalized. A rejected response is retried once; another rejection fails closed and leaves footage available. Logs contain failure categories without runtime URLs or credentials. Model-written enforcement suggestions or metrics cannot override the catalogue or computed values.

For an archive view, the pipeline combines sampled clips with three targeted retrieval queries (eight hits each), plus the user's search if present. It analyzes at most three parents and six neighboring segments per parent. The deployed VSS rejects `llm_top_n=0`; the client remembers this and uses its required minimum of one. That search narrative is discarded. A separate quotation-constrained synthesis establishes the diagnosis.

Actions are paired **policy** and **infrastructure** proposals, with a shared bottleneck ID, responsible function, purpose, prerequisites and follow-up. They do not claim illegal parking, measured delay, capacity loss, calibrated width/speed, or quantified benefits. Infrastructure proposals require a site survey. Adjacent claims within a local episode are merged; the moving camera's entire archive is never treated as one street location.

Metrics are calculated in code: distinct cited segments, union of referenced parent-relative intervals, and YOLO class presence/peak per-frame counts at confidence ≥0.5. Referenced seconds are footage duration, not delay. Box counts are not unique road users. Missing sidecars are explicit and do not prevent a caption-supported finding. Optional parent-video Q&A is descriptive and cannot override the structured reports.

## API and background loading

- `GET /api/analytics` and `/api/search?query=…`: load archive clips and descriptive aggregates immediately. Filters: `location`, `camera_id`, `start`, `end`; dates mean indexing dates.
- `POST /api/analysis`: JSON containing those filters, optional `query`, or `demo`. Returns 202 with `id`, `status`, `phase` and scope while pending, or 200 with completed results.
- `GET /api/analysis/<id>`: poll status. Completion includes validated `bottlenecks`, `recommendations`, clips, warnings, analyzed-parent counts and generation/version fields. Large detection sidecars stay server-side.
- `GET /api/recommendations?<scope>`: starts/reuses the same scoped analysis; returns pending status or completed findings.
- `GET /api/policy/<id>?<scope>`: returns the cited report after analysis. On a cold reload it returns 202, allowing the frontend to wait for regeneration. Missing supported recommendations return 404 after completion.

Recommendation JSON retains `id`, `type`, `severity`, `metrics`, and `segment_refs[]`. It adds `bottleneck_id`, role-tagged quoted claims, `category`, purpose/owner/prerequisites/follow-up, uncertainties, and generation/version fields. Policy and infrastructure IDs derive from the local bottleneck identity; URL parameters preserve the analysis scope.

Jobs deduplicate by scope and pipeline version, use two background workers, allow at most eight active jobs and 32 retained jobs, and expire completed results after 30 minutes. Failed jobs can be retried. Analysis checks a five-minute budget between upstream calls; an in-flight request can run until its upstream timeout. Polling stops when the user changes views. Failed analysis preserves playable footage and offers a separate retry. Pod restarts discard caches and jobs; report links regenerate from their scope.

Other routes: `/api/metadata`, `/api/stats`, `/api/evidence/<id>`, `/api/detections/<id>`, `/api/stream/<id>`, `/api/demo/{bottleneck,passage,traffic,crossing,queue}`, `/api/spatial`, `/health`, and `POST /api/reason/<id>`. Server-side JWT refresh and Range streaming keep credentials out of the browser. No derived VastDB storage is needed.

## Loading and diagnostics

HTML declares the public base path server-side. Deployment sets `STREETTWIN_PUBLIC_PATH=/app/`; local verification defaults to `/`. A proxy can supply a validated `X-Forwarded-Prefix`. HTML is not cached; CSS/JavaScript URLs carry a content version. Local serif fallbacks avoid external font requests.

Video plays on explicit user action. SVG overlays use real YOLO frame boxes. The JPEG previews are first frames extracted from existing indexed segments, displayed only for their exact segment IDs: `bottleneck-preview.jpg` → `7d023dd390c2a7baac0f`; `street-preview.jpg` → `6c04f82de23dc760739a`. They are derived images, not new video uploads.

Pod logs, rollout status and pod events are accessible. The user's browser Console/Network history, authenticated workshop session and private gateway logs are not. For a browser-only failure, capture the URL path and first failed request's path/status/content type or Console error, excluding tokens and credentials.

## Spatial cockpit and saved runs

The visualizer adapts [UnfoldUnrest](https://github.com/exploring-curiosity/UnfoldUnrest) at revision `7a3163c74785d3942603587da6456adf297a90cc`. It renders the imported street surface, colored points, estimated object boxes, rider route and sightline rays. The updated `98703a5` export is also supported: `view.bin` animates estimated visible/hidden areas, crossing-end watch boxes, and imported vision-review provenance. These stay descriptive and are exposed through spatial context, without automatically admitting crossing-risk recommendations. Use **Story**, **Follow rider**, **Whole street**, **Explore**, and **Points**; click an object to inspect it. All text uses local serif fonts. Three.js 0.160.0 is vendored; no frontend CDN, Node build or Mac reconstruction dependency is required. Attribution is in `UPSTREAM.txt`.

The scene’s timeline is independent when its video is unlinked. A linked scene synchronizes registered archive clips, their YOLO overlays and the rider position using explicit offsets. No automatic 2D-to-3D object identity match is claimed. Missing maps preserve the archive player; missing WebGL uses the imported overhead image.

The deployed demo includes saved run `20261009-125354-biker`: a 29.8-second route, 400,000 source points, 230 objects and an animated visibility grid. The teammate's `biker.mp4` is a renamed copy of `20261008_074640_GX050001_chunk_0000.mp4`, verified by the matching 16.2162-second frame. Six explicit archive bindings now synchronize the saved reconstruction and video. Future imported runs still require their own verified bindings; filenames are never automatically guessed.

A completed upstream bundle needs `run.json` (if available), `app/ride.json`, its overhead image, point-coordinate/color binaries, and referenced evidence images. MP4 files are ignored. Partial runs, invalid paths, excessive sizes, nonfinite coordinates and malformed timelines are rejected. The import accepts a directory, not an arbitrary archive or remote asset URL.

Local development import:

```bash
.venv/bin/python tools/street-twin/spatial_import.py /path/to/run --local /tmp/streettwin-maps
STREETTWIN_SPATIAL_DIR=/tmp/streettwin-maps .venv/bin/gunicorn --chdir tools/street-twin --workers 1 --threads 8 main:app
```

Import into the deployed asset store:

```bash
bash tools/street-twin/with-runtime.sh .venv/bin/python tools/street-twin/spatial_import.py /path/to/run --s3
```

Pull the latest completed export from the teammate’s service:

```bash
export RIDE_URL=https://your-teammate-tunnel
bash tools/street-twin/with-runtime.sh .venv/bin/python tools/street-twin/ride_sync.py --s3
```

For authenticated service access, set `RIDE_TOKEN` or `SERVICE_TOKEN` in the environment, put only the bearer token in `/config/ride.token`, or save `SERVICE_TOKEN` in the ignored repository-root `.env`. The sync command parses token entries without executing shell commands; the token stays on this machine. It accepts both service-root and run-relative manifest paths, uses GET `/api/manifest` and GET `/runs/{id}/{path}` only, verifies size/SHA-256, and excludes video, logs and model files. It does not submit or rerun reconstruction. Use `--run RUN_ID` to select a completed run. Existing imported maps survive tunnel outages and pod restarts. Repeat the command when new exports are ready; there is no unattended polling.

Team credentials cannot create S3 buckets in this environment. Deployment therefore stores assets under the app-only `street-twin/spatial/` prefix in the existing team database bucket, using S3 object operations only. No database tables or pipeline functions change, and no assets enter ingestion buckets. A separately provisioned `team-N-street-twin-spatial` bucket can instead be selected with `STREETTWIN_SPATIAL_BUCKET`. Runtime S3 credentials remain in the Kubernetes Secret. The supplied workshop VIP has a private certificate; the wrapper sets `STREETTWIN_S3_VERIFY=false` for that connection. Browser and ride-tunnel TLS verification remain enabled.

### Link a reconstruction to indexed footage

Provide a binding manifest only when the map was built from that exact archive source. Do not bind a teammate ride to an unrelated demo clip just because both show a city street.

```json
{
  "original_video": "s3://existing-archive/existing-parent.mp4",
  "bindings": [
    {
      "segment_id": "existing_20_hex_id",
      "scene_start_sec": 15,
      "scene_end_sec": 20,
      "clip_start_sec": 0
    }
  ]
}
```

Replace the placeholders with canonical values from `/api/evidence/{segment_id}`. Pass `--bindings /path/to/bindings.json` to either import command. The importer checks the registered parent, interval lengths and nonoverlapping bindings, and obtains camera/location from VSS. Scene times refer to the reconstructed ride; clip times refer to the playable segment. Unlinked scenes remain explorable but cannot corroborate an archive recommendation.

### Spatial reasoning

`scene_id` is an optional analysis scope parameter. The scene hash participates in caching and is checked again before a job completes. After video establishes an obstruction and avoidance maneuver, Cosmos can select up to eight registered spatial fact IDs relevant to its cited clips. Recommendations add `spatial_refs[]`; reports link those estimates back to the map. Unknown facts, altered facts, unrelated clips or changed policy actions fail validation. A failed spatial selection leaves the video-grounded action available.

Standing/moving/unknown comes from the imported object spread and sufficient observations while the rider passed. Standing cannot distinguish a parked car from a signal queue. Point placement and footprints use assumed camera-height scale. Crossing rays remain unverified visual estimates, excluded from recommendation admission because upstream documentation records false positives. The upstream legal-distance verdicts and cinematic video slowdown are not reused. No traffic speed, queue duration, delay, capacity or expected benefit is measured from this export.

`SpatialScene` includes version/hash, assets, timed route, estimated objects, quality notes and explicit bindings. Public interfaces:

| Route | Data |
| --- | --- |
| `/api/spatial/scenes` | Scene index and linkage status |
| `/api/spatial/scenes/{id}` | Scene geometry metadata, quality and bindings |
| `/api/spatial/scenes/{id}/assets/{asset_id}` | Registered binary/image asset |
| `/api/spatial/context?scene_id=…&segment_id=…` | Bounded clip-linked facts |
| `/api/spatial/context?scene_id=…&start=…&end=…&object_id=…` | Scene-only observations |

Live LingBot inference remains external. Its future adapter must emit this saved-scene contract, explicit archive bindings, and calibrated poses/depth/intrinsics if 2D-to-3D identity matching is desired. This release does not install or invoke LingBot.

## Connect another Codex window through MCP

Install `mcp-requirements.txt`, then run this from the repository root on this VM:

```bash
STREETTWIN_ROOT="$(pwd)"
codex mcp add street-twin -- bash "$STREETTWIN_ROOT/tools/street-twin/with-runtime.sh" "$STREETTWIN_ROOT/.venv/bin/python" "$STREETTWIN_ROOT/tools/street-twin/mcp_bridge.py"
```

The bridge runs locally beside Codex and calls the deployed app. The wrapper derives its API base from team configuration without putting secrets in the Codex command. Reopen the Codex window and check `/mcp`. [Official Codex MCP setup](https://developers.openai.com/codex/mcp).

Tools: `search_clips`, `get_clip_evidence`, `get_detections`, `list_spatial_scenes`, `get_spatial_scene`, `get_spatial_context`, `get_ride_demo`, `get_crossing_detail`, `get_analytics`, `get_recommendations`, `get_analysis_status`, and `get_policy_report`. `get_crossing_detail(228)` exposes both sides, samples, blockers and the confirmed/rejected reviews for this demo. YOLO frames are paginated; spatial context is capped at 80 objects. Full point clouds stay behind asset links. Recommendation reads can start/reuse inference jobs, but no tool writes to the archive, uploads media, deploys or starts reconstruction. A different machine must have this bridge installed and a reachable `STREETTWIN_API_BASE`; this release does not host a remote MCP transport.

Suggested agent task: “Find an observed passage obstruction, inspect its clips and YOLO context, inspect spatial facts only if explicitly linked, and propose a policy/infrastructure action with segment and spatial references. Distinguish observed maneuvers from estimated geometry.”

## Verification

```bash
.venv/bin/python -m unittest discover -s tools/street-twin/tests -v
# Optional browser wiring check; uses temporary synthetic map data, never deployed.
# Install Playwright and Chromium separately if they are absent.
xvfb-run -a .venv/bin/python tools/street-twin/tests/browser_smoke.py
# Opt-in demo check against an already running app with the imported saved scene.
UNFOLD_TEST_BASE=http://127.0.0.1:8128/ xvfb-run -a .venv/bin/python tools/street-twin/tests/ride_browser_smoke.py
```

The browser check covers `/app/` assets, desktop/mobile WebGL, camera/timeline controls, report navigation and citations. Deployment uses server-side apply for large ConfigMaps, avoiding Kubernetes’ client annotation-size limit. Code/module ConfigMaps are versioned so an update does not partially overwrite the running app. For rollback, use the previous StreetTwin Deployment revision; imported S3 map assets persist.

No re-ingest prompt was used for this update. No new video was uploaded.
