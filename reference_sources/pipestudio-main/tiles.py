import argparse
import math
import os

from pdf2image import convert_from_path
from PIL import Image


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def parse_ratio(ratio_str):
    if ratio_str is None:
        return None
    parts = ratio_str.split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("Ratio must be in the form height:width, e.g. 1:1 or 3:4")
    return float(parts[0]), float(parts[1])


def find_best_grid(tile_count, ratio=None):
    if tile_count <= 0:
        raise ValueError("Tile count must be greater than zero")
    if ratio is None:
        side = int(math.sqrt(tile_count))
        if side * side == tile_count:
            return side, side
        return side, math.ceil(tile_count / side)

    ratio_h, ratio_w = ratio
    target_aspect = ratio_h / ratio_w
    best = None
    for rows in range(1, tile_count + 1):
        cols = math.ceil(tile_count / rows)
        total_tiles = rows * cols
        aspect = rows / cols
        score = abs(aspect - target_aspect) + 0.0001 * (total_tiles - tile_count)
        if best is None or score < best[0]:
            best = (score, rows, cols)
    return best[1], best[2]


def pdf_to_images(pdf_path, dpi=200):
    return convert_from_path(pdf_path, dpi=dpi)


def tile_image(image, tiles=4, ratio=None, output_dir=None, base_name="image", page_index=1):
    if output_dir is None:
        output_dir = os.getcwd()
    ensure_dir(output_dir)

    if isinstance(image, str):
        image_path = image
        image = Image.open(image_path)

    rows, cols = find_best_grid(tiles, ratio)
    tile_width = image.width // cols
    tile_height = image.height // rows
    output_files = []
    saved = 0

    for row in range(rows):
        for col in range(cols):
            if saved >= tiles:
                break
            left = col * tile_width
            upper = row * tile_height
            right = image.width if col == cols - 1 else (col + 1) * tile_width
            lower = image.height if row == rows - 1 else (row + 1) * tile_height
            tile = image.crop((left, upper, right, lower))
            tile_name = f"{base_name}_page_{page_index}_tile_{saved + 1:02d}.png"
            tile_path = os.path.join(output_dir, tile_name)
            tile.save(tile_path)
            output_files.append(tile_path)
            saved += 1

    return output_files, saved


def collect_pdf_paths(input_path):
    if os.path.isdir(input_path):
        return [
            os.path.join(input_path, f)
            for f in sorted(os.listdir(input_path))
            if f.lower().endswith(".pdf")
        ]
    return [input_path]


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF files to tiles from PDF pages and save all tiles in a single folder."
    )
    parser.add_argument("input_path", help="PDF file or directory containing PDF files")
    parser.add_argument("--output", "-o", default="tiles_output", help="Output directory for tile images")
    parser.add_argument("--tiles", "-t", type=int, default=4, help="Number of tiles to generate per page")
    parser.add_argument(
        "--ratio",
        "-r",
        type=parse_ratio,
        default=None,
        help="Tile grid ratio as height:width, e.g. 1:1 or 3:4",
    )
    parser.add_argument("--max_tiles", "-m", type=int, default=None, help="Maximum total number of tiles to save")
    parser.add_argument("--dpi", type=int, default=200, help="DPI for PDF to image conversion")
    args = parser.parse_args()

    pdf_paths = collect_pdf_paths(args.input_path)
    if not pdf_paths:
        raise SystemExit("No PDF files found in the input path")

    total_saved = 0
    for pdf_path in pdf_paths:
        if args.max_tiles is not None and total_saved >= args.max_tiles:
            break

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        pages = pdf_to_images(pdf_path, dpi=args.dpi)
        for page_index, page in enumerate(pages, start=1):
            if args.max_tiles is not None and total_saved >= args.max_tiles:
                break

            remaining_tiles = None if args.max_tiles is None else max(0, args.max_tiles - total_saved)
            tile_count = args.tiles if remaining_tiles is None else min(args.tiles, remaining_tiles)
            if tile_count <= 0:
                break

            _, saved = tile_image(
                page,
                tiles=tile_count,
                ratio=args.ratio,
                output_dir=args.output,
                base_name=base_name,
                page_index=page_index,
            )
            total_saved += saved

    print(f"Processed {len(pdf_paths)} PDF(s). Saved {total_saved} tile(s) under: {args.output}")


if __name__ == "__main__":
    main()
