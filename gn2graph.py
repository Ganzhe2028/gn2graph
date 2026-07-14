#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import Any

import fitz
from PIL import Image


def render_page(doc: fitz.Document, page_num: int, dpi: int) -> Image.Image:
    page = doc.load_page(page_num)
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def stitch_images(images: list[Image.Image], overlap_pct: float) -> Image.Image:
    if not images:
        raise ValueError("no images to stitch")
    if len(images) == 1:
        return images[0]

    width = max(im.width for im in images)
    norm_images: list[Image.Image] = []
    for im in images:
        if im.width != width:
            ratio = width / im.width
            new_height = int(im.height * ratio)
            im = im.resize((width, new_height), Image.LANCZOS)
        norm_images.append(im)

    overlap_px = int(norm_images[0].height * overlap_pct)
    total_height = sum(im.height for im in norm_images) - overlap_px * (len(norm_images) - 1)
    canvas = Image.new("RGB", (width, total_height), "white")

    y = 0
    for i, im in enumerate(norm_images):
        if i == 0:
            canvas.paste(im, (0, y))
            y += im.height
            continue

        prev_tail = canvas.crop((0, y - overlap_px, width, y))
        curr_head = im.crop((0, 0, width, overlap_px))
        mask = Image.linear_gradient("L").resize((width, overlap_px))
        blended = Image.composite(curr_head, prev_tail, mask)
        canvas.paste(blended, (0, y - overlap_px))
        canvas.paste(im.crop((0, overlap_px, width, im.height)), (0, y))
        y += im.height - overlap_px

    return canvas


def tile_image(image: Image.Image, tile_height: int, overlap_pct: float) -> list[Image.Image]:
    if image.height <= tile_height:
        return [image]

    overlap_px = int(tile_height * overlap_pct)
    step = tile_height - overlap_px
    tiles: list[Image.Image] = []
    y = 0
    while y < image.height:
        h = min(tile_height, image.height - y)
        tiles.append(image.crop((0, y, image.width, y + h)))
        if y + h >= image.height:
            break
        y += step
    return tiles


def save_tiles(
    tiles: list[Image.Image],
    output_dir: str,
    quality: int,
    canvas_size: tuple[int, int],
    source_path: str,
    dpi: int,
    tile_height: int,
    overlap_pct: float,
) -> list[dict[str, Any]]:
    os.makedirs(output_dir, exist_ok=True)
    metadata_tiles: list[dict[str, Any]] = []
    overlap_px = int(tile_height * overlap_pct)
    step = tile_height - overlap_px

    for idx, tile in enumerate(tiles):
        filename = f"tile_{idx:03d}.jpg"
        filepath = os.path.join(output_dir, filename)
        tile.save(filepath, format="JPEG", quality=quality, optimize=True)

        global_y = idx * step
        global_y_end = global_y + tile.height
        overlap_top = overlap_px if idx > 0 else 0
        overlap_bottom = overlap_px if idx < len(tiles) - 1 else 0

        metadata_tiles.append({
            "index": idx,
            "filename": filename,
            "filepath": filepath,
            "size": [tile.width, tile.height],
            "global_y": global_y,
            "global_y_end": global_y_end,
            "overlap_top": overlap_top,
            "overlap_bottom": overlap_bottom,
        })
        print(f"  Saved {filename} ({tile.width}x{tile.height})")

    return metadata_tiles


def copy_tiles_to_upload(output_dir: str, upload_dir: str, tiles_metadata: list[dict[str, Any]]) -> None:
    os.makedirs(upload_dir, exist_ok=True)
    for tile in tiles_metadata:
        src = os.path.join(output_dir, tile["filename"])
        dst = os.path.join(upload_dir, tile["filename"])
        shutil.copy2(src, dst)
    print(f"Copied {len(tiles_metadata)} tile(s) to {upload_dir}")


def write_prompt(
    output_dir: str,
    upload_dir: str,
    source_path: str,
    canvas_size: tuple[int, int],
    dpi: int,
    tile_height: int,
    overlap_pct: float,
    tile_count: int,
) -> None:
    source_name = os.path.basename(source_path)
    overlap_px = int(tile_height * overlap_pct)
    prompt = f"""# LLM Processing Prompt for `{source_name}`

Upload this file together with all `tile_*.jpg` images in this folder to ChatGPT, then type any additional request in the chat box.

## User's additional request
[Type your extra request here in the ChatGPT dialog. For example: "Focus on the top-right of tile_001" or "Group todos by project."]

## Context
You are processing a set of tile images sliced from a single GoodNotes whiteboard PDF.

- Source PDF: `{source_path}`
- Original canvas size: {canvas_size[0]} x {canvas_size[1]} px
- Rendered at {dpi} DPI
- Sliced into {tile_count} tiles, each up to {tile_height} px tall
- Overlap between adjacent tiles: {overlap_pct * 100:.0f}% ({overlap_px} px)
- Each tile filename and its global vertical position are described in `metadata.json` in the parent folder.

Each tile is a vertical slice of the same canvas. Content that spans a tile boundary appears in the overlapping region of at least one tile, so you can read tiles independently. Use `global_y` coordinates from `metadata.json` if you need absolute positions.

## Request
Extract and organize the content of this whiteboard into a structured meeting notes document, including:

1. A concise summary of the discussion or content
2. Key decisions made
3. Open questions or unresolved points
4. A list of action items / TODOs with owner, deadline, and priority if visible

## Output Format
Provide your response in this structure:

1. **Summary**: brief overview of the whiteboard content
2. **Decisions**: key decisions explicitly stated or clearly implied
3. **Open Questions**: unresolved points or things that need follow-up
4. **Action Items / TODOs**: list with owner, deadline, and priority where visible; mark unclear fields as `[unclear]`
5. **Uncertainties**: anything ambiguous, unreadable, or cut off

If absolute coordinates help, reference `tile.index` and approximate `global_y` from `metadata.json`.

## Constraints
- Do not invent information not visible in the tiles.
- If text is unreadable or cut off, mark it as `[unclear]` rather than guessing.
- Do not merge visually distinct items unless explicitly connected.
- Respect the vertical reading order implied by `global_y`.
- Combine the user's additional request above with this default task; do not ignore either.

## Checkpoint
Stop and ask for clarification if:
- The tiles appear out of order or corrupted.
- The user's additional request conflicts with the default task in a way you cannot reconcile.
- You encounter conflicting information across overlapping tiles that you cannot resolve.

Otherwise, proceed with the full extraction.
"""
    prompt_path = os.path.join(output_dir, "prompt.md")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"Saved prompt template to {prompt_path}")

    os.makedirs(upload_dir, exist_ok=True)
    upload_prompt_path = os.path.join(upload_dir, "prompt.md")
    with open(upload_prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"Copied prompt to {upload_prompt_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Slice a GoodNotes whiteboard PDF into tiles for local VLM processing."
    )
    parser.add_argument("pdf", help="Input PDF file exported from GoodNotes")
    parser.add_argument(
        "-o", "--output-dir", default="tiles", help="Output directory for tile images"
    )
    parser.add_argument(
        "--tile-height", type=int, default=2000, help="Max height in pixels per tile"
    )
    parser.add_argument(
        "--overlap", type=float, default=0.05, help="Overlap ratio between tiles/pages"
    )
    parser.add_argument("--dpi", type=int, default=200, help="PDF rendering DPI")
    parser.add_argument("--quality", type=int, default=90, help="JPEG quality for tile images")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"Error: file not found: {args.pdf}", file=sys.stderr)
        return 1

    doc = fitz.open(args.pdf)
    page_count = len(doc)
    print(f"Loaded {page_count} page(s) from {args.pdf}")

    images = [render_page(doc, p, args.dpi) for p in range(page_count)]
    canvas = stitch_images(images, args.overlap)
    print(f"Canvas size: {canvas.size}")

    tiles = tile_image(canvas, args.tile_height, args.overlap)
    print(f"Split into {len(tiles)} tile(s) of <= {args.tile_height}px height")

    metadata_tiles = save_tiles(
        tiles,
        args.output_dir,
        args.quality,
        canvas.size,
        args.pdf,
        args.dpi,
        args.tile_height,
        args.overlap,
    )

    metadata: dict[str, Any] = {
        "source": args.pdf,
        "canvas_size": [canvas.width, canvas.height],
        "dpi": args.dpi,
        "tile_height": args.tile_height,
        "overlap_ratio": args.overlap,
        "tile_count": len(tiles),
        "tiles": metadata_tiles,
    }

    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"Saved metadata to {meta_path}")

    upload_dir = os.path.join(args.output_dir, "upload")
    copy_tiles_to_upload(args.output_dir, upload_dir, metadata_tiles)

    write_prompt(
        args.output_dir,
        upload_dir,
        args.pdf,
        canvas.size,
        args.dpi,
        args.tile_height,
        args.overlap,
        len(tiles),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
