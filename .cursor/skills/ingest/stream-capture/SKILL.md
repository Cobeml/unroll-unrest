---
name: ingest-stream-capture
description: >-
  Trigger, monitor, and stop live/stream capture via the backend streaming API:
  POST /api/v1/streaming/start, GET /status, POST /stop. The stream service writes
  fixed-length chunks to vss-chunks (same ingest path as S3 upload). Not for uploading
  local files — use ingest-upload-videos for direct S3 puts.
---

# Ingest: trigger / status / stop stream (vss2)

## This skill = API only (you do not upload files)

| | **stream-capture** (this skill) | **upload-videos** (other skill) |
|---|--------------------------------|----------------------------------|
| What you do | Call `POST /streaming/start` (+ status/stop) | `aws s3 cp` fixed-length MP4s to `vss-chunks` |
| Source | YouTube URL, RTSP, HTTP stream, remote file URL | Local files on disk (pre-chunked ~30s) |
| Who writes S3 | `video-stream-capture` service (automatic) | You (manual S3 upload) |

Both paths land **fixed-length** chunks in `vss-chunks`. The DataEngine ingest pipeline only sees S3 objects — it does not call the streaming API.

**This skill:** you trigger capture via API; the stream service reads the source, splits at `capture_interval` (default 30s), and uploads each chunk to S3 for you.

**Not this skill:** if you already have MP4 files, split them locally and use `ingest-upload-videos` — no streaming API involved.

Requires a JWT (`retrieval/login`). Only **one capture runs at a time** (service returns "Capture is already running").

## Source support

Request field `youtube_url` accepts:
- **YouTube** VOD/live → yt-dlp path.
- **RTSP / HTTP / file** (OpenCV/FFmpeg) → put URL/path in `youtube_url`.

## Prefill S3 credentials

```bash
curl -s "$BACKEND/api/v1/streaming/prefill" -H "Authorization: Bearer $TOKEN"
```

## Trigger new stream

`POST /api/v1/streaming/start`:

```bash
curl -s -X POST "$BACKEND/api/v1/streaming/start" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "youtube_url": "https://www.youtube.com/watch?v=...",
    "access_key": "...", "secret_key": "...", "s3_endpoint": "http://...",
    "bucket_name": "vss-chunks",
    "name": "capture",
    "capture_interval": 30,
    "camera_id": "", "capture_type": "", "location": "", "scenario": ""
  }'
```

| Field | Req | Notes |
|-------|-----|-------|
| `youtube_url` | yes | YouTube URL, or any RTSP/HTTP/file URL |
| `access_key`/`secret_key`/`s3_endpoint` | yes | usually from `/prefill` |
| `bucket_name` | yes | set `vss-chunks` explicitly |
| `capture_interval` | no | 1–300s fixed chunk length (default 30) |
| `name` | no | filename prefix |
| metadata fields | no | written as S3 object metadata on each chunk |

(Direct service `POST /start` on the streamer pod also accepts `max_duration` and `s3_prefix`; backend proxy does not forward those.)

## Status (stream + ingest signals)

**Stream capture status:**

```bash
curl -s "$BACKEND/api/v1/streaming/status" -H "Authorization: Bearer $TOKEN"
```

Returns `is_running`, `current_config` (secrets redacted), `temp_files_count`. VOD auto-stops at end; live runs until `/stop`.

**Ingest pipeline status** (chunks indexed after stream writes to S3):

```bash
curl -s "$BACKEND/api/v1/dashboard/stats" -H "Authorization: Bearer $TOKEN"
```

See `retrieval/dashboard` — S3 vs VastDB inventory, ingest quality, recent videos.

## Stop stream

```bash
curl -s -X POST "$BACKEND/api/v1/streaming/stop" -H "Authorization: Bearer $TOKEN"
```

## Flow

```
stream source → capture_interval chunks → S3 vss-chunks
  → video-segmenter (5s) → vss-chunks-segments → detector → reasoner → embedder → writer
```

A 30s chunk → ~6 × 5s segments (modulo trim/cap).

## Config / dependencies

- Streaming pod: `deployments/vss-k8s-application/videostreamer-deployment.yaml` (port 5000, probe `/ping`). S3 creds are passed **per request**, not pod env.
- Optional env: `YTDLP_COOKIES_FILE`, `YTDLP_SEGMENT_TIMEOUT_SEC`, `YTDLP_FULL_DOWNLOAD_TIMEOUT_SEC`, `YTDLP_SEGMENT_MAX_RETRIES`.

## Agent instructions

1. Ensure JWT; get S3 values from `/prefill` when possible.
2. Always set `bucket_name: vss-chunks`.
3. Check `/streaming/status` before starting — only one capture at a time.
4. Chunks are **fixed length** (`capture_interval`); same contract as S3 upload skill.
5. Confirm objects arriving and indexing via `retrieval/dashboard`.
