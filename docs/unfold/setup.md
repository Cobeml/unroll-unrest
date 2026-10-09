# Setup and run

## What runs where

| Component | Runtime | Responsibility |
| --- | --- | --- |
| Unfold web app | Team Kubernetes, CPU, `/app` | 3D viewer, clip discovery, job API, evidence and recommendations |
| Unfold coordinator | Separate singleton CPU worker | Durable queue, transfer, remote polling, import and Cosmos synthesis |
| Existing VSS | Pre-deployed stack | Indexed archive, semantic search, YOLO sidecars, Cosmos reasoning |
| Teammate reconstruction service | Teammate Mac/GPU machine through HTTPS tunnel | Frames, LingBot geometry, OWLv2 objects, export, Qwen frame review |
| App storage | Existing team database bucket, `street-twin/spatial/` | Immutable maps, indices, jobs and saved analysis; no database table writes |

The VM does **not** run LingBot or install model weights. The app keeps working with its imported scenes when the external machine or tunnel is unavailable. Source video streams from the existing VSS archive through the app, independently of Cloudflare. The story displays video and 3D together with one play/pause/seek clock; its **Video** button hides or shows the inset. Cloudflare is used only for remote reconstruction and artifact transfer.

## 1. VM dependencies

Clone recursively and install the root README's requirements. The workshop VM already has `kubectl`, its team configuration and kubeconfig in `/config`. Never commit or print those values. `with-runtime.sh` reads exactly one team `.config` and selects only that team's namespace.

Create an ignored root `.env` using a private editor:

```dotenv
RIDE_URL=https://YOUR-TUNNEL.trycloudflare.com
SERVICE_TOKEN=YOUR_PRIVATE_SERVICE_TOKEN
```

Use the same token as the teammate service. Do not paste it into chat, embed it in a URL, commit `.env`, or source an untrusted environment file. The application reads only its allowlisted settings without executing shell content. Environment `RIDE_TOKEN` or `SERVICE_TOKEN` overrides the file; `/config/ride.token` is also supported. `RIDE_URL` can be set in the process environment.

Required VSS/S3 variables are supplied by `with-runtime.sh`: `VSS_URL`, `VSS_USERNAME`, `VSS_PASSWORD`, `S3_ENDPOINT`, `ACCESS_KEY`, `SECRET_KEY`, `STREETTWIN_SPATIAL_BUCKET`, `STREETTWIN_SPATIAL_PREFIX`. `/config` values are injected only into a Kubernetes Secret. The public frontend receives none of them.

## 2. Teammate service prerequisites

The pinned submodule's README describes its Mac setup:

```bash
cd third_party/unfold-unrest
python -m ride.service --port 8791
# In another terminal:
cloudflared tunnel --no-autoupdate --url http://localhost:8791
```

Before starting, install the upstream Python/model dependencies (`fastapi`, `uvicorn`, `python-multipart`, `av`, `torch`, `transformers`, `numpy`, `opencv-python`, `pillow`, `weave`, and `openai`) in the teammate environment and create its ignored `.env` with `SERVICE_TOKEN`, `WANDB_API_KEY`, and `WANDB_PROJECT`. The service requires the file to exist even when some settings are provided through environment variables.

**Fresh hardware needs adaptation:** pinned `ride/__init__.py` hardcodes an ElideDB checkout under the original developer's Mac home. Set `ELIDE` to the actual checkout containing LingBot-Map and its weights, and follow that model's hardware-specific installation. The VM integration does not establish CUDA compatibility or supply those weights. Keep machine configuration outside commits. Existing healthy teammate service is the tested default; do not launch the GPU pipeline on this CPU VM.

The service has authenticated create/upload/start/poll/export endpoints and one GPU job at a time. A quick Cloudflare tunnel changes URL when restarted. Update the VM's ignored `.env` and redeploy to update the Kubernetes Secret.

## 3. Bootstrap the saved demo

The initial team deployment already has the saved scene. A new isolated app store requires a completed upstream demo run. Restore it with:

```bash
bash tools/street-twin/with-runtime.sh .venv/bin/python tools/street-twin/bootstrap_demo.py --s3
```

This imports existing map files from run `20261009-125354-biker`, binds the six indexed segments of the exact known parent, and preserves the previously verified frame match at 16.2162 seconds. It downloads no new footage and ingests nothing. If the teammate has removed that run, restore its saved `app/` export and `run.json`, then use the importer and explicit bindings described in the data contract. Do not replace it with a similarly named unrelated video.

## 4. Deploy

```bash
bash tools/street-twin/deploy.sh
bash tools/street-twin/with-runtime.sh bash -c \
  'kubectl -n "$USERNAME" rollout status deployment/street-twin --timeout=55s'
bash tools/street-twin/with-runtime.sh bash -c \
  'kubectl -n "$USERNAME" rollout status deployment/street-twin-worker --timeout=55s'
```

Deployment uses `python:3.12-slim`, versioned code ConfigMaps, vendored browser modules and a server-only Secret. No Docker build or registry is needed. The API runs one Gunicorn process with eight threads; the worker runs one replica with **Recreate** rollout strategy. Keep those constraints unless you add distributed job leases and conditional writes. Scratch transfer files are temporary and excluded from commits; the worker reserves up to 5 GiB of ephemeral disk. Model processing happens remotely.

Open [Workshop](https://workshop.thecosmoslabs.com) → **App**. Ingress strips `/app`, so API and assets use a server-generated base path and work on deep links.

## 5. Process a different indexed video

1. Click **Find risk clips** in the upper-right corner.
2. Select Close call, Collision or Crash; optionally filter location/camera. Results are paginated, deduplicated by parent, and labeled candidates.
3. Choose a moment. Preview the indexed segment and enable **YOLO objects** if available. Missing YOLO does not establish absence of objects.
4. Click **Rebuild this street**. It always processes the **full indexed parent chunk**, normally about 30 seconds, while recording the matched segment/time as the highlight.
5. Leave or reload the run page; job progress is persisted independently of the browser. Frames → 3D map → objects → export → review → import are tracked.
6. Click **Explore this street** when complete. The resulting page has the same viewer and evidence tabs as the demo. No assessed crossing or supported obstruction means a limited result, not a fabricated action.

The service accepts clips up to 4 GiB. The coordinator uses 64 MiB chunks, resumes from the remote byte count, and verifies the remote file's SHA-256 before starting reconstruction. An unchanged parent and service/pipeline version reuses its existing job. After a remote failure, **Retry processing** resumes from the failed stage. Tunnel/storage interruptions wait and retry automatically without losing the remote run ID.

## 6. Logs and diagnosis

These commands show application logs without requesting secrets:

```bash
bash tools/street-twin/with-runtime.sh bash -c \
  'kubectl -n "$USERNAME" logs deployment/street-twin --tail=80'
bash tools/street-twin/with-runtime.sh bash -c \
  'kubectl -n "$USERNAME" logs deployment/street-twin-worker --tail=80'
bash tools/street-twin/with-runtime.sh bash -c \
  'kubectl -n "$USERNAME" get pods -l app=street-twin-worker'
```

- CSS/deep-link failure: check `/app` ingress rewrite and both ConfigMap mounts, then browser network errors. Assets are same-origin, with no runtime CDN.
- Search unavailable: inspect API logs and VSS health; verify filter values via metadata. Search is bounded to the top 100 hits, not exhaustive.
- Run waiting: check current tunnel and service authentication; redeploy if URL/token changed. Existing scene pages remain available.
- Reconstruction failed: ask the teammate for **`runs/<remote_run_id>/log.txt`** and its service console, plus the stage shown on the run page. Those logs live on the teammate machine and are intentionally not fetched or exposed by this app; they can contain provider configuration.
- Import failed: check source checksum, archive intervals, point-cloud dimensions and exported asset sizes. Unsupported/malformed bundles are rejected.
- Cosmos unavailable: frame evidence and deterministic structured findings remain usable; use the Cosmos tab to retry synthesis.

For local debugging only, run the API and worker in separate terminals with the same runtime wrapper. Stop the deployed worker first or use a separate **local** `STREETTWIN_SPATIAL_DIR` with no S3 bucket; two coordinators must never advance the same store. The delivered application remains the on-cluster app.
