# StreetTwin

Street bottlenecks, object detections, and paired policy/infrastructure recommendations grounded in indexed video evidence. Off-white, serif, video-first web interface; reconstruction remains deferred.

## Run and deploy

The deliverable runs on the team Kubernetes cluster at `/app`. Credentials and kubeconfig remain under `/config`.

```bash
cd ~/vast-builders-challenge
bash tools/street-twin/deploy.sh
```

Open [the workshop](https://workshop.thecosmoslabs.com) → **App** after rollout. The deployment uses a public Python image, code ConfigMap, runtime Secret, and the existing team's Ingress. It discovers the existing `/api` Service for backend calls. Updates restart StreetTwin; another app's `/app` route is never overwritten. No Docker build, registry or DataEngine changes are required.

For development verification, install `requirements.txt` in a Python virtual environment, supply runtime `VSS_URL`, `VSS_USERNAME`, and `VSS_PASSWORD` without writing them into the repository, and run:

```bash
gunicorn --chdir tools/street-twin --workers 1 --threads 8 --timeout 180 main:app
python -m unittest discover -s tools/street-twin/tests -v
```

One worker is required because analysis jobs and archive registration are in memory. Development preview is for testing; the deployed App is the deliverable. Never commit `.env` files or credentials.

## Three-minute demo

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

## How recommendations are generated

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

Other routes: `/api/metadata`, `/api/stats`, `/api/evidence/<id>`, `/api/detections/<id>`, `/api/stream/<id>`, `/api/demo/{bottleneck,passage,crossing,queue}`, `/api/spatial`, `/health`, and `POST /api/reason/<id>`. Server-side JWT refresh and Range streaming keep credentials out of the browser. No derived VastDB storage is needed.

## Loading and diagnostics

HTML declares the public base path server-side. Deployment sets `STREETTWIN_PUBLIC_PATH=/app/`; local verification defaults to `/`. A proxy can supply a validated `X-Forwarded-Prefix`. HTML is not cached; CSS/JavaScript URLs carry a content version. Local serif fallbacks avoid external font requests.

Video plays on explicit user action. SVG overlays use real YOLO frame boxes. The JPEG previews are first frames extracted from existing indexed segments, displayed only for their exact segment IDs: `bottleneck-preview.jpg` → `7d023dd390c2a7baac0f`; `street-preview.jpg` → `6c04f82de23dc760739a`. They are derived images, not new video uploads.

Pod logs, rollout status and pod events are accessible. The user's browser Console/Network history, authenticated workshop session and private gateway logs are not. For a browser-only failure, capture the URL path and first failed request's path/status/content type or Console error, excluding tokens and credentials.

## Spatial status

The main view reserves a 3D street viewport with orbit/zoom controls and the selected segment reference. Its grid is an empty viewer scaffold: no reconstructed buildings, camera poses, or invented 3D object positions are displayed. `GET /api/spatial` remains `connected: false`. Object highlighting currently operates on real 2D YOLO frame boxes.

`spatial.py` retains `SpatialImport { mesh_ref, segment_ids[], camera_poses? }`. Future poses include camera ID, existing segment ID, coordinate system, and a 4×4 transform. LingBot installation, inference, import routes, and reconstruction remain deferred until the user's codebase and pipeline are provided.

## LingBot GPU feasibility — checked 2026-10-09

**Assessment: plausible with a separately allocated CUDA worker; deployment onto the shared GPU host is not yet verified or available through the supplied access.** This is an inference from the observed access boundaries and the official installation requirements, not a GPU benchmark.

Observed environment:

- The VM exposes no NVIDIA device files or NVIDIA PCI devices. StreetTwin's deployed container requests CPU and RAM only.
- Shared YOLO `/healthz` returns HTTP 200 with `cuda_available: true` and `model_loaded: true`. Cosmos Reason and Embed each pass their models, ready, and live endpoints. Shared GPU inference is functioning.
- Team pod inventory shows no GPU requests. Node inventory is denied by Kubernetes RBAC. Accessible health responses do not disclose GPU model, VRAM, free memory, driver version, compute capability, or spare allocation.
- Existing credentials provide calls to the pre-running models. They do not provide a documented arbitrary-model deployment API or confirmed shell access/allocation on the GPU host. No GPU process or workload was installed, launched, or modified.

For ordinary street-video reconstruction, the relevant public project appears to be **LingBot-Map**; the imported codebase may differ. Its official guide uses Python 3.10, PyTorch 2.8.0 / torchvision 0.23.0 with CUDA 12.8. FlashInfer is recommended, with native SDPA fallback. CPU offload, fewer initial scale frames, and keyframe/window controls reduce memory pressure. The offline renderer adds Kaolin and compiled CUDA extensions. These are separate from StreetTwin's small CPU web container. [Official installation and memory guidance](https://github.com/Robbyant/lingbot-map#-installation).

The published package manifest requires Python ≥3.10 and lists core and visualization dependencies. The imported pipeline's exact dependencies must be inspected rather than assuming that the web runtime or every README extra is sufficient. [Official package manifest](https://github.com/Robbyant/lingbot-map/blob/main/pyproject.toml).

Once the codebase and GPU access are available, adapt in this order:

1. Verify the allocated GPU model/VRAM, driver compatibility, writable storage, CUDA/PyTorch build, and supported precision inside a dedicated worker. Endpoint health alone cannot establish these requirements. Do not alter the shared Cosmos/YOLO serving environments.
2. Pin the supplied code revision and checkpoint. Start with a single existing NYC cycling parent chunk, decoded in chronological order with segment IDs and timestamps preserved. Use conservative frame sampling and bounded windows; measure actual peak VRAM and latency before growing the input. No new source video is needed.
3. Establish a simple inference baseline before adding optional acceleration or rendering extensions. Compare the imported pipeline's full geometry output and real video timing. The official `gct_profile.py` uses synthetic inputs and can omit the point head, so its FPS is not a substitute for complete reconstruction profiling. [Official profiling code](https://github.com/Robbyant/lingbot-map/blob/main/gct_profile.py).
4. Export geometry, confidence, intrinsics, and poses keyed to the same segment/frame times. Project YOLO detections through the matching depth/intrinsics/poses; moving objects need separate treatment from the static street. Preserve uncertainty and avoid interpreting uncalibrated coordinates as measured street dimensions. Cycling footage provides changing viewpoints; fixed-camera packs require separate evaluation.
5. Serve the resulting mesh/point cloud and object associations to StreetTwin's reserved viewer through an isolated worker/API and derived-asset storage. Keep inference out of browser requests and the CPU app container. Treat this as future integration work, not an implemented pipeline.

The user will run LingBot on a separate machine and supply its visualizer codebase and tunnel. Shared GPU deployment is no longer the planned integration path. Once supplied, inspect the visualizer's export/API contract and adapt the interface around existing segment IDs before providing a spatial analysis tool to the recommender. No tunnel client, reconstruction, or spatial agent tool is connected yet.

## Corpus and re-ingest notes

Existing indexed sources only: Pack A (`i24_cam-1`), Pack D (`neighborhood_cam-1`), NYC cycling (`nyc_bike_gopro-1`), and other street packs. Both inspected demo sequences are NYC cycling footage. Archive counts are available live through `/api/stats` and can change as existing indexing completes.

**No new videos uploaded. No re-ingest prompts used.** Current indexed captions support these diagnoses. The diagnosis prompt is in `bottlenecks.py`; it runs read-only synthesis, not re-ingestion. LingBot and spatial tool access remain deferred.
