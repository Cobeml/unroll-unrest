---
name: retrieval-vastdb-read
description: >-
  Read the VSS VastDB store directly with the vastdb Python SDK over an SSH tunnel —
  list catalog (databases/schemas/tables) and inspect rows in vss-db/vss-schema/vss-collection
  and vss-prompts-events. Use for raw DB inspection/debugging that bypasses the backend API
  (no JWT), e.g. verifying what actually got written.
---

# Retrieval: VastDB read (vss2)

Direct, backend-independent access to the store the pipeline writes and the backend queries. Uses the `vastdb` Python SDK — **not** the JWT backend. Best for debugging "did this segment actually land in VastDB?".

## VSS defaults

| Thing | Value |
|-------|-------|
| Database (bucket) | `vss-db` |
| Schema | `vss-schema` |
| Main table | `vss-collection` (segment rows: `source`, `original_video`, `reasoning_content`, `vectors` (256d text), `vectors_visual`, metadata, timing) |
| Prompts table | `vss-prompts-events` (prompt-suggester output) |

## Prereqs

1. **SSH tunnel** to the VastDB data endpoint (VIP usually not routable directly):

```bash
ssh -N -f -L 18080:<vastdb-vip>:80 <user>@<jump-host>
# e.g. ssh -N -f -L 18080:172.27.121.1:80 vastdata@v151lg1
```

2. **`.env`** at the repo root (copy `.env.example`):

```
VDB_ENDPOINT=http://127.0.0.1:18080     # or S3_ENDPOINT
VAST_ACCESS_KEY=...
VAST_SECRET_KEY=...
```

3. `pip install vastdb pyarrow pandas`.

## List the catalog

[list_catalog.py](list_catalog.py) prints database → schema → tables via the SDK (`tx.catalog()`), with a tunnel reachability probe.

```bash
python .cursor/skills/retrieval/vastdb-read/list_catalog.py                 # whole catalog
python .cursor/skills/retrieval/vastdb-read/list_catalog.py --bucket vss-db # + live bucket.schemas()
```

## Read rows

```python
import vastdb
session = vastdb.connect(endpoint="http://127.0.0.1:18080", access=ACCESS, secret=SECRET, ssl_verify=False)
with session.transaction() as tx:
    table = tx.bucket("vss-db").schema("vss-schema").table("vss-collection")
    # Exclude vector columns from projections (large / not needed for inspection):
    cols = [c for c in table.columns() if c.name not in ("vectors", "vectors_visual")]
    batch = table.select(columns=[c.name for c in cols]).read_all()
    rows = batch.to_pylist()
    print(len(rows), rows[0] if rows else "empty")
```

⚠️ Selecting `vectors`/`vectors_visual` (fixed-size lists) can fail without the vector-select patch used by the pipeline functions (`common/vastdb_patch.py`). For inspection, just exclude them.

## Common checks

- **Row count / recent writes**: count rows, sort by `timestamp`/`upload_timestamp`.
- **Missing segment**: filter by `original_video` or `source` to confirm a specific clip was written (writer skips duplicate `source`).
- **Dims**: `vectors` length must be **256** (Cosmos-Embed1) — mismatch means the collection needs recreating.

## Agent instructions

1. Start the SSH tunnel and verify `.env` before connecting; run `list_catalog.py` first.
2. Never commit `.env`.
3. Exclude vector columns unless you specifically need them.
4. This bypasses backend ACLs — for user-scoped views use `retrieval/dashboard` / `retrieval/videos` instead.
