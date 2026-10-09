# Demo script

## 1. A screened crossing → maintenance

Open the home story and click **Play the story**. At roughly 16–20 seconds, the hedge and the right-side waiting area are highlighted. Open **Trim the hedge at crossing 2**.

- Statistics: 97% waiting area hidden at modeled stopping distance; approximately 10 m stopping distance; fully visible from approximately 5.3 m. These are imported estimates.
- Frames: paired approach frames support the hedge obstruction.
- Review: the right-side claim is confirmed; the left-side claim is rejected and produces no action.
- Source: exact indexed filename, camera, location and segment IDs.
- Cosmos: generate video analysis using the same indexed parent and imported estimates/reviews.

Source: `20261008_074640_GX050001_chunk_0000.mp4`, camera `nyc_bike_gopro-1`, location `new_york`. This is the preserved UnfoldUnrest demo, not a generated replacement street.

## 2. Close-call screening → selected parent reconstruction

Click **Find risk clips**, choose **Close call**, location **new_york** and camera **nyc_bike_gopro-1**. Review an avoidance/obstruction candidate, show YOLO objects, then **Rebuild this street**. The matched segment is a highlight; the full parent is reconstructed.

Reliable existing archive example: segment `ef7c083c57cb1601f04f`, parent `20261008_072948_GOPR0130_chunk_0014.mp4`, interval 5–10 s. Captions describe weaving through slow traffic; this is not a verified collision. Search ranking can change. Use the canonical segment ID through `POST /api/runs` when replaying the exact acceptance run.

## 3. A constrained riding path → evidence review

The archive query **“parked red sedan obstructs the riding path, rider maneuvers around it”** returns street footage with a visible path constraint and avoidance. Known example: segment `7d023dd390c2a7baac0f`, parent `20261008_074847_GX050001_chunk_0005.mp4`, interval 15–20 s, same bike camera/location. Use MCP `search_clips` to locate the caption and detection context, then select the parent for reconstruction. The reconstruction may find no assessed crossing; its output must say so rather than invent a maintenance recommendation.

## Re-ingestion and reconstruction notes

No new video uploads or planner-caption re-ingestion were used for this update. Existing indexed captions and detections remain intact. LingBot/OWL/Qwen processing is invoked only on selected existing parent bytes in the external service. The demo map was imported from completed run `20261009-125354-biker`; source alignment was previously visually checked at 16.2162 s.
