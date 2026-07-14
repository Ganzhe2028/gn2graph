# GoodNotes Whiteboard Agent Handoff

You are a multimodal agent reading a preprocessed GoodNotes whiteboard folder.
Follow this file as the instruction source; the user does not need to write another prompt.

## Mandatory Read Order

1. Read this `prompt.md` first.
2. Read `graph.json` if it exists. Treat `nodes` and `edges` as the highest-priority structural evidence.
3. Read `manifest.json` for page sizes, tile coordinates, drawing paths, connector candidates, and warnings.
4. Inspect each `overview.png` to understand the full whiteboard layout.
5. Open high-resolution tile images only when text, handwriting, or local detail is unclear.

## Evidence Priority

- Preserve every `graph.json.edges[]` relationship explicitly in the final notes.
- If an edge has `from_text` and `to_text`, write that relationship literally, for example: `from_text -> to_text`.
- Long-distance connectors are not decorative unless the visual evidence clearly proves otherwise.
- Do not replace graph edges with broad summaries such as "the line connects the overall structure".
- Use `overview.png` to verify global placement and tile images to verify exact handwriting.
- When graph evidence and visual interpretation conflict, report the conflict instead of silently choosing a smoother story.
- Mark uncertain readings with `[unclear]`; do not invent missing text to make the notes sound complete.

## Required Output

Produce Markdown with these sections:

1. `忠实转写`: preserve the visible whiteboard structure and important arrows/lines.
2. `结构关系`: list graph edges and important visual relationships as `A -> B`.
3. `整理版`: a cleaned-up explanation that does not remove or blur the graph edges.
4. `Mermaid`: a mindmap or flowchart that includes the explicit graph edges.
5. `不确定处`: list uncertain handwriting, ambiguous arrows, and any evidence conflicts.

## Coordinate Notes

- All `bbox` values are PDF page coordinates in points: `[x0, y0, x1, y1]`.
- Tile image paths are relative to this output folder.
- Each tile overlaps neighbors, so repeated content should be deduplicated by text and bbox.

## Recognition Task Mode

- Use `recognition_tasks/page_XXX.json` to OCR/VLM each tile.
- Do not summarize tiles. Return structured text blocks only.
- Return tile-local `bbox` values in pixels. The pipeline can convert them to global PDF coordinates.
- Content may repeat across overlapping tiles; repeated text will be deduplicated later.
- Fill the response shape described in `text_blocks.schema.json`, then run `goodnotes-prep attach-text OUT --text-blocks TEXT_BLOCKS.json`.

## Graph Edges To Preserve

- Page 1: `问题：但为何奏效？` -> `学术 / 原理层面的理解` via `d_1775` (long_distance_connector, confidence=0.95).

## Pages

- Page 1: overview `pages/page_001/overview.png`, 24 tiles, 2 text blocks, 1 edge candidates.