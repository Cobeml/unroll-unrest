# Unfold application

The fullscreen 3D street story, VSS risk discovery, remote reconstruction coordinator, evidence pages and read-only MCP bridge live here. Existing filenames and Kubernetes names retain `street-twin` for compatibility with the VM.

Start with the [root README](../../README.md), then:

- [Setup and run](../../docs/unfold/setup.md)
- [Input/output, API and MCP](../../docs/unfold/data-contract.md)
- [Production screening workflow](../../docs/unfold/production.md)
- [Demo script](../../docs/unfold/demo.md)

Entry points: `main.py` (API), `processing.py` (singleton worker), `ride.html/ride.js/ride.css` (3D story and recommendation tabs), `discover.html/discover.js` (archive candidates and run progress), `deploy.sh` (team-only no-registry deployment), `bootstrap_demo.py` (restore known saved demo), `spatial_import.py` (explicit saved-map import), and `mcp_bridge.py` (read-only tools).

The teammate model code is pinned as `../../third_party/unfold-unrest`. The VM transfers selected existing archive bytes to that external service and imports derived artifacts; it does not run LingBot locally or upload video into VSS.
