# StreetTwin

Street video with object detections, a reserved 3D viewport, and policy recommendations backed by cited archive observations.

## Run and deploy

The deliverable runs on the team Kubernetes cluster at `/app`. Credentials and kubeconfig remain mounted under `/config`.

```bash
cd ~/vast-builders-challenge
bash tools/street-twin/deploy.sh
```

Open [the workshop](https://workshop.thecosmoslabs.com) → **App** after rollout. Deployment uses a public Python image, code ConfigMap, runtime credential Secret, and the existing team's Ingress. It discovers the existing `/api` backend Service for in-cluster calls. Updates rerun the command and restart StreetTwin; another app's `/app` route is never overwritten. No Docker build, registry, video upload, GPU installation, or DataEngine changes are involved.

For development verification, use a Python virtual environment with `requirements.txt`, runtime `VSS_URL`, `VSS_USERNAME`, and `VSS_PASSWORD`, and `gunicorn --chdir tools/street-twin --workers 1 --threads 8 --timeout 180 main:app`. Use one worker because caches and archive registration are in memory. Development preview is not the deliverable.

```bash
python -m unittest discover -s tools/street-twin/tests -v
```

## Three-minute demo

1. The initial **Street Explorer** opens NYC cycling footage. The video plays with YOLO frame boxes. Select **bicycle**, **truck**, or **person** to highlight that class; use the arrows to browse clips. Location/camera selections update the view. Dates and semantic search are inside **Filters**; detailed captions and sources are inside **Clip details**.
2. Open **Review cyclist passage**. It navigates to its own shareable `/app/policy/<id>` page. The initial explored sample has six supporting clips out of 30 camera clips (20%), representing 30 seconds of cited footage. Show numbered citations, play another cited clip, inspect its source and caption, and reload the URL. Statistics are regenerated from the same filters; they can change when the underlying archive changes.
3. Return with **Street view** and use the three compact example buttons. Each resolves a verified filename in the live archive, rather than depending on search ranking.

| Example / query | Policy review | Filename / parent-relative seconds |
| --- | --- | --- |
| Passage: Delivery trucks partially blocking the street while cycling | Cyclist passage / curb use | `20261008_072535_GOPR0130_chunk_0004_segment_005_of_006.mp4`, 20–25 s |
| Crossing: Pedestrians crossing the road near bicycles and moving vehicles | Crossing clearance | `20261008_074241_GX010001_chunk_0014_segment_002_of_006.mp4`, 5–10 s |
| Queue: Cars stopped or moving slowly beside a protected bike lane | Intersection approach | `20261008_074151_GX010001_chunk_0012_segment_006_of_006.mp4`, 25–30 s |

Use Filters to search these descriptions for related clips. Policy links preserve the active filter, search, or demo context. A demo contains one anchored clip, so its policy statistics deliberately describe that one-clip example. Select Nashville / I-24 to show ordinary traffic with no supported congestion policy. Select Neighborhood to inspect Pack D. Switching location clears incompatible cameras.

## Policy statistics and evidence

Cosmos video-reasoning captions establish observations. Conservative templates produce structured recommendations for cyclist passage, curb use, crossings, and slow traffic; validation requires matching segment IDs, sources, camera, location, timestamps, and supporting caption sentences. YOLO supplies video boxes and object context. Object co-occurrence alone does not establish danger or proximity. Optional parent-video Q&A supplies descriptive analysis without overriding the structured reports.

`GET /api/analytics` selects up to 96 segments across cameras and archive positions. `GET /api/search?query=…` uses up to 30 search results. Both accept `location`, `camera_id`, `start`, and `end`; dates describe indexing, not recording time.

`GET /api/policy/<id>` regenerates the report from the same filter/search/demo context. It contains the recommendation, cited clips, analysis, and statistics. The denominator is the selected sample from the recommendation's camera and location. Supporting clip share is not an event rate, causal estimate, or citywide prevalence. Adjacent clips may show the same event. Referenced seconds merge overlapping intervals within each parent video. Detection bars count clips containing each class; peak per-frame counts are never unique road-user totals.

Policy pages return 404 when the current view has no supporting report. Stable recommendation IDs identify type + camera + location; URL query parameters preserve the observation scope. Segment IDs hash the canonical VSS source, which remains included in every citation. No statistics establish legal violations, engine idling, calibrated distances/speeds, or congestion duration.

Other routes: `/api/metadata`, `/api/stats`, `/api/recommendations`, `/api/evidence/<id>`, `/api/detections/<id>`, `/api/stream/<id>`, `/api/demo/{passage,crossing,queue}`, `/api/spatial`, `/health`, and `POST /api/reason/<id>`. Server-side JWT refresh and Range streaming are unchanged. Caches are short-lived and in memory; credentials/JWTs are not sent to the browser. Derived VastDB storage is unnecessary.

## Loading and diagnostics

HTML declares its public base path on the server; assets do not depend on an inline script. The deployment sets `STREETTWIN_PUBLIC_PATH=/app/`; local development defaults to `/`. A reverse proxy can supply a full `X-Forwarded-Prefix` mount. Policy deep links use the same base. HTML is not cached, and CSS/JavaScript URLs carry a content version to prevent mixed frontend releases. Failed archive requests show a short message and Retry.

The team kubeconfig allows StreetTwin pod logs, rollout status, and pod events. It does not provide the user's browser Console/Network history, authenticated workshop session, or the workshop gateway's private logs. If the workshop view differs from the checked Ingress, capture the browser URL path and the first Console error or failed Network request (path, HTTP status, and content type); exclude credentials and tokens.

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

The missing information is a confirmed GPU allocation/deployment access path and the supplied codebase. There is no evidence yet to name an available GPU, assert free VRAM, promise real-time speed, or guarantee installation on the shared server.

## Corpus notes

Explored Pack A (`i24_cam-1`, 180 clips), Pack D (`neighborhood_cam-1`, 307), NYC cycling (`nyc_bike_gopro-1`, 465), and NYC street footage. The explored archive contains 612 parent videos and 3,537 indexed segments; 14 additional S3 segments were pending indexing at initial exploration and are excluded from indexed totals.

**No new videos uploaded. No re-ingest prompts used.** Current cycling captions provide usable planner observations; unsupported concepts remain unavailable.
