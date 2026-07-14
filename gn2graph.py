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


def tile_image_vertical(image: Image.Image, tile_height: int, overlap_pct: float) -> list[Image.Image]:
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


def tile_image_horizontal(image: Image.Image, tile_width: int, overlap_pct: float) -> list[Image.Image]:
    if image.width <= tile_width:
        return [image]

    overlap_px = int(tile_width * overlap_pct)
    step = tile_width - overlap_px
    tiles: list[Image.Image] = []
    x = 0
    while x < image.width:
        w = min(tile_width, image.width - x)
        tiles.append(image.crop((x, 0, x + w, image.height)))
        if x + w >= image.width:
            break
        x += step
    return tiles


def tile_name(mode: str, idx: int) -> str:
    if mode == "horizontal":
        return f"left_to_right_{idx:02d}.jpg"
    return f"top_to_bottom_{idx:02d}.jpg"


def save_tiles(
    tiles: list[Image.Image],
    output_dir: str,
    quality: int,
    canvas_size: tuple[int, int],
    source_path: str,
    dpi: int,
    mode: str,
    tile_dimension: int,
    overlap_pct: float,
) -> list[dict[str, Any]]:
    os.makedirs(output_dir, exist_ok=True)
    metadata_tiles: list[dict[str, Any]] = []
    overlap_px = int(tile_dimension * overlap_pct)
    step = tile_dimension - overlap_px

    for idx, tile in enumerate(tiles):
        filename = tile_name(mode, idx)
        filepath = os.path.join(output_dir, filename)
        tile.save(filepath, format="JPEG", quality=quality, optimize=True)

        if mode == "horizontal":
            global_x = idx * step
            global_x_end = global_x + tile.width
            tile_meta = {
                "index": idx,
                "filename": filename,
                "filepath": filepath,
                "size": [tile.width, tile.height],
                "global_x": global_x,
                "global_x_end": global_x_end,
                "overlap_left": overlap_px if idx > 0 else 0,
                "overlap_right": overlap_px if idx < len(tiles) - 1 else 0,
            }
        else:
            global_y = idx * step
            global_y_end = global_y + tile.height
            tile_meta = {
                "index": idx,
                "filename": filename,
                "filepath": filepath,
                "size": [tile.width, tile.height],
                "global_y": global_y,
                "global_y_end": global_y_end,
                "overlap_top": overlap_px if idx > 0 else 0,
                "overlap_bottom": overlap_px if idx < len(tiles) - 1 else 0,
            }

        metadata_tiles.append(tile_meta)
        print(f"  Saved {filename} ({tile.width}x{tile.height})")

    return metadata_tiles


def copy_tiles_to_upload(output_dir: str, upload_dir: str, tiles_metadata: list[dict[str, Any]]) -> None:
    os.makedirs(upload_dir, exist_ok=True)
    for tile in tiles_metadata:
        src = os.path.join(output_dir, tile["filename"])
        dst = os.path.join(upload_dir, tile["filename"])
        shutil.copy2(src, dst)
    print(f"Copied {len(tiles_metadata)} tile(s) to {upload_dir}")


def extract_source_text(doc: fitz.Document) -> str:
    parts: list[str] = []
    for page_num in range(len(doc)):
        text = doc.load_page(page_num).get_text()
        if text.strip():
            parts.append(f"--- Page {page_num + 1} ---\n{text.strip()}")
    return "\n\n".join(parts)


def copy_source_files(
    source_path: str,
    output_dir: str,
    upload_dir: str,
    doc: fitz.Document,
    include_source: bool,
) -> tuple[bool, bool]:
    copied_pdf = False
    text_written = False
    if not include_source:
        return copied_pdf, text_written

    os.makedirs(upload_dir, exist_ok=True)

    pdf_basename = os.path.basename(source_path)
    pdf_dst = os.path.join(upload_dir, pdf_basename)
    shutil.copy2(source_path, pdf_dst)
    copied_pdf = True
    print(f"Copied original PDF to {pdf_dst}")

    text = extract_source_text(doc)
    if text:
        text_path = os.path.join(output_dir, "source_text.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)
        upload_text_path = os.path.join(upload_dir, "source_text.txt")
        shutil.copy2(text_path, upload_text_path)
        text_written = True
        print(f"Saved extracted text to {text_path}")
    else:
        print("No searchable text found in PDF; skipped source_text.txt")

    return copied_pdf, text_written


def write_prompt(
    output_dir: str,
    upload_dir: str,
    source_path: str,
    canvas_size: tuple[int, int],
    dpi: int,
    mode: str,
    tile_dimension: int,
    overlap_pct: float,
    tile_count: int,
    has_source_pdf: bool,
    has_source_text: bool,
) -> None:
    source_name = os.path.basename(source_path)
    overlap_px = int(tile_dimension * overlap_pct)

    if mode == "horizontal":
        axis = "horizontal"
        reading_order = "left-to-right"
        coord_name = "global_x"
        tile_label = f"each up to {tile_dimension} px wide"
        boundary_note = "left/right neighbor"
        tile_pattern = "left_to_right_*.jpg"
        example_request = "Focus on the right side of left_to_right_03"
    else:
        axis = "vertical"
        reading_order = "top-to-bottom"
        coord_name = "global_y"
        tile_label = f"each up to {tile_dimension} px tall"
        boundary_note = "top/bottom neighbor"
        tile_pattern = "top_to_bottom_*.jpg"
        example_request = "Focus on the lower half of top_to_bottom_01"

    source_pdf_note = ""
    if has_source_pdf:
        source_pdf_note = f"- The original PDF (`{source_name}`) is also attached for layout verification."

    source_text_note = ""
    if has_source_text:
        source_text_note = "- A `source_text.txt` file with the PDF's embedded searchable text is also included for reference."

    reference_constraint = ""
    if has_source_pdf or has_source_text:
        reference_constraint = "- Use the original PDF and any `source_text.txt` only as reference; do not let them override what is actually visible in the tiles."

    prompt = f"""# LLM Processing Prompt for `{source_name}`

Upload this file together with all `{tile_pattern}` images in this folder to ChatGPT, then type any additional request in the chat box.

## User's additional request
[Type your extra request here in the ChatGPT dialog. For example: "{example_request}" or "Group todos by project."]

## Context
You are processing a set of tile images sliced from a single GoodNotes whiteboard PDF.

- Source PDF: `{source_path}`
- Original canvas size: {canvas_size[0]} x {canvas_size[1]} px
- Rendered at {dpi} DPI
- Sliced into {tile_count} {axis} tiles, {tile_label}
- Overlap between adjacent tiles: {overlap_pct * 100:.0f}% ({overlap_px} px)
- Reading order: {reading_order}
- Each tile filename and its `{coord_name}` position are described in `metadata.json` in the parent folder.
{source_pdf_note}
{source_text_note}

Each tile is a {axis} slice of the same canvas. Content that spans a tile boundary appears in the overlapping region of at least one tile, so you can read tiles independently. Use `{coord_name}` coordinates from `metadata.json` if you need absolute positions.

If something is unclear in one tile, check its {boundary_note} for the same content at a different crop.

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

If absolute coordinates help, reference the tile index and approximate `{coord_name}` from `metadata.json`.

## Constraints
- Do not invent information not visible in the tiles.
- If text is unreadable or cut off, mark it as `[unclear]` rather than guessing.
- Do not merge visually distinct items unless explicitly connected.
- Respect the {reading_order} reading order implied by `{coord_name}`.
- Combine the user's additional request above with this default task; do not ignore either.
{reference_constraint}

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
        "--mode",
        choices=["horizontal", "vertical"],
        default="horizontal",
        help="Slicing orientation (default: horizontal)",
    )
    parser.add_argument(
        "--tile-width",
        type=int,
        default=2000,
        help="Max width in pixels per tile (horizontal mode only)",
    )
    parser.add_argument(
        "--tile-height",
        type=int,
        default=2000,
        help="Max height in pixels per tile (vertical mode only)",
    )
    parser.add_argument(
        "--overlap",
        type=float,
        default=0.10,
        help="Overlap ratio between tiles/pages",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PDF rendering DPI")
    parser.add_argument("--quality", type=int, default=90, help="JPEG quality for tile images")
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Do not copy the original PDF or extract searchable text into upload/",
    )
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

    if args.mode == "horizontal":
        tiles = tile_image_horizontal(canvas, args.tile_width, args.overlap)
        tile_dimension = args.tile_width
        print(f"Split into {len(tiles)} tile(s) of <= {args.tile_width}px width")
    else:
        tiles = tile_image_vertical(canvas, args.tile_height, args.overlap)
        tile_dimension = args.tile_height
        print(f"Split into {len(tiles)} tile(s) of <= {args.tile_height}px height")

    metadata_tiles = save_tiles(
        tiles,
        args.output_dir,
        args.quality,
        canvas.size,
        args.pdf,
        args.dpi,
        args.mode,
        tile_dimension,
        args.overlap,
    )

    metadata: dict[str, Any] = {
        "source": args.pdf,
        "canvas_size": [canvas.width, canvas.height],
        "mode": args.mode,
        "dpi": args.dpi,
        "overlap_ratio": args.overlap,
        "tile_count": len(tiles),
        "tiles": metadata_tiles,
    }
    if args.mode == "horizontal":
        metadata["tile_width"] = args.tile_width
    else:
        metadata["tile_height"] = args.tile_height

    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"Saved metadata to {meta_path}")

    upload_dir = os.path.join(args.output_dir, "upload")
    copy_tiles_to_upload(args.output_dir, upload_dir, metadata_tiles)

    has_source_pdf, has_source_text = copy_source_files(
        args.pdf, args.output_dir, upload_dir, doc, include_source=not args.no_source
    )

    write_prompt(
        args.output_dir,
        upload_dir,
        args.pdf,
        canvas.size,
        args.dpi,
        args.mode,
        tile_dimension,
        args.overlap,
        len(tiles),
        has_source_pdf,
        has_source_text,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
