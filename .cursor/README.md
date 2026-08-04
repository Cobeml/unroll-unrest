# VSS2 Cursor Skills

Agent skills for working with the VSS2 video search stack. Each skill lives in its own folder with a `SKILL.md` that has full usage instructions — open that file when you need details.

## Layout

```
.cursor/skills/
├── ingest/       # Get video into the pipeline
└── retrieval/    # Query and explore indexed video
```

## Ingest

Land fixed-length MP4 chunks in `vss-chunks`; the DataEngine pipeline picks them up from S3.

| Skill | Summary |
|-------|---------|
| [upload-videos](skills/ingest/upload-videos/SKILL.md) | Upload local chunk files directly to S3 |
| [stream-capture](skills/ingest/stream-capture/SKILL.md) | Start, monitor, and stop live stream capture via the backend API |

→ [ingest/README.md](skills/ingest/README.md) for pipeline overview.

## Retrieval

Query the indexed archive through the backend API (`/api/v1`). Most routes need a JWT — start with **login**.

| Skill | Summary |
|-------|---------|
| [login](skills/retrieval/login/SKILL.md) | Authenticate and obtain a bearer token |
| [search](skills/retrieval/search/SKILL.md) | Semantic/hybrid search over the archive |
| [list-metadata](skills/retrieval/list-metadata/SKILL.md) | Discover filterable fields and values |
| [dashboard](skills/retrieval/dashboard/SKILL.md) | Aggregate stats and ingest health |
| [suggest-prompts](skills/retrieval/suggest-prompts/SKILL.md) | AI-generated search prompt suggestions |
| [videos](skills/retrieval/videos/SKILL.md) | Browse, play back, and summarize a video |
| [agent-qa](skills/retrieval/agent-qa/SKILL.md) | Natural-language Q&A over the archive |
| [vastdb-read](skills/retrieval/vastdb-read/SKILL.md) | Raw VastDB inspection (bypasses the API) |

→ [retrieval/README.md](skills/retrieval/README.md) for route map and auth patterns.

## Typical flows

**Ingest files** → `upload-videos` → `dashboard` (verify indexing)

**Ingest a stream** → `login` → `stream-capture` → `dashboard`

**Search** → `login` → `list-metadata` (optional filters) → `search` or `agent-qa`

**Watch a result** → `login` → `videos`
