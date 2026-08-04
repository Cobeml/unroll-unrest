---
name: ingest-upload-videos
description: >-
  Upload 1..N fixed-length video chunks directly to the vss-chunks S3 bucket (not the
  backend multipart API or batch-sync). Each object should be one time-bounded MP4
  chunk (e.g. ~30s); the DataEngine ingest pipeline picks up S3 ObjectCreated events.
  Use for file-based ingest; for live/URL sources use ingest-stream-capture.
---

# Ingest: upload videos to S3 (vss2)

**Ingest does not use the streaming service or batch-sync.** The DataEngine pipeline only watches the `vss-chunks` bucket (`video-chunk-land-trigger` → `video-segmenter` → …). To add video, put fixed-length MP4 objects into that bucket.

## Fixed length (important)

Objects in `vss-chunks` are **chunks**, not arbitrary full-length raw files. Each upload should be one bounded clip (typically **~30 seconds**, aligned with stream `capture_interval`). Long sources must be split locally before upload; the segmenter then produces ~5s segments in `vss-chunks-segments`.

| Layer | Typical length | Where |
|-------|----------------|-------|
| Your S3 upload | ~30s (fixed chunk) | `vss-chunks` |
| `video-segmenter` | ~5s | `vss-chunks-segments` |

Set S3 object metadata `capture-interval` (or `chunk_duration_sec`) to the nominal chunk length in seconds so the segmenter can cap segmentation correctly.

## When to use

- Upload 1..N pre-chunked MP4 files from disk.
- Bulk copy many chunk files with `aws s3 sync` / loop over `aws s3 cp`.
- **Not** for live URLs / RTSP / YouTube → `ingest-stream-capture` (writes the same bucket via the stream API).

## Prerequisites

- S3 credentials + endpoint from `deployments/vss-k8s-application/backend-secret.yaml` (`s3_endpoint`, `s3_access_key`, `s3_secret_key`) or your tenant’s VAST S3 keys.
- Bucket: **`vss-chunks`** (`s3_upload_bucket` in backend secret).
- DataEngine ingest pipeline + `video-chunk-land-trigger` deployed (`dataengine-components/`).

Optional metadata field catalog (scenarios, capture types): `GET /api/v1/metadata/ingest-config` (public, no JWT) — see `retrieval/list-metadata`.

## Split a long file into fixed-length chunks (local)

Use the same nominal length you will set in metadata (example: 30s):

```bash
ffmpeg -i warehouse_full.mp4 -c copy -f segment -segment_time 30 -reset_timestamps 1 \
  chunks/chunk_%03d.mp4
```

## Upload 1..N chunks to S3

Object key pattern used by the UI/backend: `{owner}/{YYYYMMDD_HHMMSS}_{uuid8}.mp4` — any key under the bucket works for the trigger; use a stable prefix per owner for ACL metadata.

**Single file:**

```bash
export S3_ENDPOINT="http://<vast-s3-host>"
export AWS_ACCESS_KEY_ID="<key>"
export AWS_SECRET_ACCESS_KEY="<secret>"

aws s3 cp chunks/chunk_000.mp4 "s3://vss-chunks/myuser/20260101_120000_ab12cd34.mp4" \
  --endpoint-url "$S3_ENDPOINT" \
  --metadata \
camera-id=cam-01,capture-type=warehouse,location=Warehouse-A,scenario=general,\
capture-interval=30,is-public=true,owner=myuser,original-filename=chunk_000.mp4
```

**Many files (1..N):** loop or sync:

```bash
for f in chunks/chunk_*.mp4; do
  id=$(uuidgen | tr '[:upper:]' '[:lower:]' | cut -c1-8)
  ts=$(date -u +%Y%m%d_%H%M%S)
  aws s3 cp "$f" "s3://vss-chunks/myuser/${ts}_${id}.mp4" \
    --endpoint-url "$S3_ENDPOINT" \
    --metadata capture-interval=30,is-public=true,owner=myuser,original-filename="$(basename "$f")"
done
```

### S3 metadata keys (kebab-case)

| Metadata key | Notes |
|--------------|-------|
| `camera-id`, `capture-type`, `location` | ingest filters / search |
| `scenario` | analysis preset (ignored if `custom-prompt` set) |
| `custom-prompt` | URL-encoded, max 800 chars |
| `tags`, `allowed-users` | comma-separated |
| `is-public` | `true` / `false` |
| `owner` | username for ACL |
| `capture-interval` or `chunk_duration_sec` | nominal chunk length (seconds) |

## After upload — ingest status

No per-file job API. Check indexing via `retrieval/dashboard`:

```bash
# JWT optional for dashboard; login first if required
curl -s "$BACKEND/api/v1/dashboard/stats" -H "Authorization: Bearer $TOKEN"
```

Compare `s3_inventory.chunks_mp4` vs VastDB counts; searchable parents appear in `GET /api/v1/videos/explore` (`retrieval/videos`).

## Flow

```
fixed-length MP4(s) → S3 vss-chunks
  → video-segmenter (~5s) → vss-chunks-segments → detector → reasoner → embedder → writer
```

## Agent instructions

1. Confirm each file is already a **fixed-length chunk** (~30s); split with ffmpeg if the user has one long file.
2. Upload **directly to S3** (`aws s3 cp` / sync); do **not** use `POST /videos/upload` or `/batch-sync/*` for ingest in these skills.
3. Set `capture-interval` metadata to match the actual chunk duration.
4. For N files, upload each object; report per-object success.
5. Do not claim searchable until dashboard/explore shows the parent indexed.
