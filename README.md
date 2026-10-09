# Unfold

Turn an indexed bike ride into a street you can explore, then open the evidence behind a maintenance recommendation.

The demo reconstructs **20261008_074640_GX050001_chunk_0000.mp4**. At crossing 2, a hedge screens the right waiting area. The imported frame reviewer confirms that obstruction and rejects a separate left-side claim. The recommendation is to inspect and trim the hedge, then recheck the approach. Geometry and stopping distances are estimates.

**Open the deployed app:** [Workshop](https://workshop.thecosmoslabs.com) → **App**.

The home page is a fullscreen 3D story. Click the recommendation in the top-left corner for Action, Statistics, Frames, Video, Review, Cosmos and Source tabs. **Find risk clips** searches the existing VAST archive for collision, close-call or crash candidates. Choose a segment, preview its video and YOLO detections, then reconstruct its full parent chunk on the teammate service. The result opens in the same viewer. A search match does not establish a collision.

## Get the code

```bash
git clone --recurse-submodules https://github.com/cobeml/unroll-unrest.git
cd unroll-unrest
python3 -m venv .venv
.venv/bin/pip install -r tools/street-twin/requirements.txt
```

For an existing checkout:

```bash
git submodule update --init --recursive
```

The teammate's [UnfoldUnrest](https://github.com/exploring-curiosity/UnfoldUnrest) is pinned under `third_party/unfold-unrest`. The application keeps the original `tools/street-twin/` and Kubernetes resource names so it runs on the existing VM infrastructure.

## Setup, input and output

- [Setup and run](docs/unfold/setup.md): VM configuration, remote service, deployment, saved-demo bootstrap, logs and retry.
- [Inputs, outputs and API](docs/unfold/data-contract.md): source identity, timestamps, structured recommendations, processing jobs and MCP.
- [Production workflow](docs/unfold/production.md): archive-wide danger screening followed by selective reconstruction and stakeholder review.
- [Demo script and verified examples](docs/unfold/demo.md).
- [Original workshop guide](docs/workshop-guide.md) and [stack architecture](ARCHITECTURE_REFERENCE.md).

No video is uploaded into VSS. The CPU web app uses existing VSS search, YOLO and Cosmos APIs. A separate CPU worker transfers only the selected existing parent to the external reconstruction service, imports checksum-verified map artifacts, and records canonical segment bindings. App-owned derived files and job records use an isolated S3 prefix; DataEngine functions are unchanged.

## Verify

```bash
.venv/bin/pip install -r tools/street-twin/mcp-requirements.txt
.venv/bin/python -m unittest discover -s tools/street-twin/tests -q
# Browser check additionally needs Playwright, system Chrome and Xvfb:
.venv/bin/pip install playwright
# On the configured VM, against the deployed app:
bash tools/street-twin/with-runtime.sh bash -c \
  'UNFOLD_TEST_BASE="$STREETTWIN_API_BASE" timeout 150 xvfb-run -a .venv/bin/python tools/street-twin/tests/ride_browser_smoke.py'
```

Browser checks use system Chrome and Xvfb. All pages use serif type, an off-white shell, and a fixed viewport. Long results and analysis use pagination.
