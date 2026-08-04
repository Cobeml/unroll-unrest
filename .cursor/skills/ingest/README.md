# Ingest (vss2)

Get video into the pipeline by landing **fixed-length MP4 chunks** in the `vss-chunks` bucket. The DataEngine ingest pipeline (see `dataengine-components/`) reacts to S3 events only — it does **not** call the streaming or batch-sync services.

## Skills

| Skill | Mechanism | Purpose |
|-------|-----------|---------|
| [upload-videos](upload-videos/SKILL.md) | Direct **S3 upload** (`aws s3 cp` / sync) | Upload 1..N fixed-length chunk files to `vss-chunks` |
| [stream-capture](stream-capture/SKILL.md) | `POST /streaming/start`, `GET /status`, `POST /stop` | Trigger stream capture, check stream status, stop capture |

## Fixed length (important)

Chunks in `vss-chunks` are **not** arbitrary full-length raw videos. Each object should be one time-bounded clip (typically ~30s, `capture_interval` / `capture-interval` metadata). The `video-segmenter` then splits into ~5s segments in `vss-chunks-segments`.

| Path | How chunks arrive | Nominal chunk size |
|------|-------------------|--------------------|
| S3 upload | You put fixed-length MP4s in `vss-chunks` | ~30s (your choice; set metadata) |
| Stream API | `video-stream-capture` writes to `vss-chunks` | `capture_interval` (default 30s) |
| Segmenter output | `vss-chunks-segments` | ~5s |

**Ingest status:** after either path, use `retrieval/dashboard` (`GET /api/v1/dashboard/stats`) for S3 vs VastDB alignment and ingest health.

Auth for streaming APIs: JWT via `retrieval/login`. S3 upload uses tenant S3 keys from backend secret (not the JWT).
