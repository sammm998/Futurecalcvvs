"""Optional OCR second opinion over the rendered page.

Used by the review layer to look for designations the vector reading may have missed, and by the OCR-assisted
resolver to name characters the stroke recogniser could not. It never reads the drawing on its own: the vector
geometry stays the source of the measurement.

The page is rendered at a legible resolution and read in overlapping tiles, because a whole A1 sheet scaled down
to one image leaves 6 pt CAD text too small for any recogniser. Lines found twice in an overlap are deduplicated.
"""
from __future__ import annotations

import math
import time

import numpy as np

TILE_PX = 768
OVERLAP_PX = 120
_ENGINE = None


def _engine():
    """Load the optional local reader; images never leave this process."""
    global _ENGINE
    if _ENGINE is None:
        import os
        try:
            from rapidocr import RapidOCR, LangRec, OCRVersion, ModelType
            params = {"Rec.lang_type": LangRec.LATIN, "Rec.ocr_version": OCRVersion.PPOCRV5,
                      "Rec.model_type": ModelType.MOBILE, "Det.model_type": ModelType.TINY,
                      "Global.return_word_box": True,
                      "Rec.rec_batch_num": 1, "Cls.cls_batch_num": 1,
                      "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
                      "EngineConfig.onnxruntime.intra_op_num_threads": 1,
                      "EngineConfig.onnxruntime.inter_op_num_threads": 1}
            if os.environ.get("VVS_OCR_MODEL_DIR"):
                params["Global.model_root_dir"] = os.environ["VVS_OCR_MODEL_DIR"]
            _ENGINE = RapidOCR(params=params)
        except ImportError:
            try:
                from rapidocr_onnxruntime import RapidOCR
                _ENGINE = RapidOCR()
            except (ImportError, OSError) as e:
                raise RuntimeError(f"OCR-motorn kunde inte laddas: {e}") from e
    return _ENGINE


def _ocr_rows(result):
    """Keep each word's own box; a line box cannot locate several words."""
    if hasattr(result, "txts"):
        if result.boxes is None or result.txts is None or result.scores is None:
            return []
        words = getattr(result, "word_results", None)
        rows = []
        for i, (box, text, confidence) in enumerate(zip(result.boxes, result.txts, result.scores)):
            line_words = words[i] if words and i < len(words) else None
            if line_words and isinstance(line_words[0], (list, tuple)):
                rows.extend((b, w, min(float(c), float(confidence)))
                            for w, c, b in line_words if b is not None and len(str(w).split()) == 1)
            elif len(str(text).split()) == 1:
                rows.append((box, text, confidence))
        return rows
    rows, _ = result
    return [r for r in rows or [] if len(str(r[1]).split()) == 1]


def _tiles(width, height, tile, overlap, regions):
    """Centre targeted crops on complete rows, so tile edges do not cut words."""
    if regions is None:
        return [(float(x), float(y)) for y in np.arange(0, height, tile-overlap)
                for x in np.arange(0, width, tile-overlap)]
    out = []
    for x0,y0,x1,y1 in sorted(regions, key=lambda r: (r[1],r[0])):
        x0,y0,x1,y1 = max(0,x0),max(0,y0),min(width,x1),min(height,y1)
        if x1 <= x0 or y1 <= y0:
            continue
        # Very long rows still require overlapping crops; ordinary labels fit
        # entirely in one crop including the resolver's context margin.
        xs = [x0] if x1-x0 <= tile else np.arange(x0,x1-overlap,tile-overlap)
        ys = [y0] if y1-y0 <= tile else np.arange(y0,y1-overlap,tile-overlap)
        for y in ys:
            for x in xs:
                right,bottom = min(x+tile,x1),min(y+tile,y1)
                if any(tx <= x and ty <= y and tx+tile >= right and ty+tile >= bottom for tx,ty in out):
                    continue
                tx = max(0., min(width-tile, (x+right-tile)/2))
                ty = max(0., min(height-tile, (y+bottom-tile)/2))
                out.append((float(tx),float(ty)))
    return out


def _crops(width, height, tile, overlap, regions):
    """Pack complete target rows into bounded crops without reading empty margins.

    Fixed-size crops centred on successive rows repeatedly OCR the same nearby
    text. Keeping the union of assigned regions lets a crop grow as needed,
    while preserving every row's context and the original pixel resolution.
    """
    if regions is None:
        return [(x, y, min(x+tile, width), min(y+tile, height))
                for x, y in _tiles(width, height, tile, overlap, None)]
    groups = []
    for a,b,c,d in sorted(regions, key=lambda r: (r[1], r[0])):
        a,b,c,d = max(0,a),max(0,b),min(width,c),min(height,d)
        if c <= a or d <= b:
            continue
        xs = [a] if c-a <= tile else np.arange(a,c-overlap,tile-overlap)
        ys = [b] if d-b <= tile else np.arange(b,d-overlap,tile-overlap)
        for y in ys:
            for x in xs:
                region = (float(x),float(y),min(x+tile,c),min(y+tile,d))
                candidates = []
                for i, box in enumerate(groups):
                    union = (min(box[0],region[0]),min(box[1],region[1]),
                             max(box[2],region[2]),max(box[3],region[3]))
                    w,h = union[2]-union[0],union[3]-union[1]
                    if w <= tile and h <= tile:
                        added = w*h-(box[2]-box[0])*(box[3]-box[1])
                        candidates.append((added,i,union))
                if candidates:
                    _,i,union = min(candidates)
                    groups[i] = union
                else:
                    groups.append(region)
    return groups


def ocr_words(page, dpi: int = 300, progress=None, regions=None,
              budget_s: float | None = None, seen=None, stats=None) -> list[tuple[str, list[float], float]]:
    """Read the page with OCR. Returns (word, bbox in page points, confidence) in the page's display space.

    `regions` limits the work to the parts of the sheet that are worth reading - a pass that exists to name three
    unreadable characters has no business rendering a whole A1 at 300 dpi. `budget_s` bounds it in time: this is
    an assist, never the measurement, so when the budget runs out it stops and says how far it got rather than
    holding a reading that is otherwise finished.
    """
    global _ENGINE
    import pymupdf
    src = getattr(page, "source_path", None)
    if not src:
        raise RuntimeError("page carries no source path to render")
    doc = pymupdf.open(src)
    try:
        p = doc[page.info.index]
        s = dpi / 72.0
        # Page.rect and get_pixmap already respect the page rotation.
        disp_w, disp_h = p.rect.width, p.rect.height
        tile_pt, ov_pt = TILE_PX / s, OVERLAP_PX / s
        engine = _engine()
        out: list[tuple[str, list[float], float]] = []
        started = time.monotonic()
        tiles = _crops(disp_w, disp_h, tile_pt, ov_pt, regions)
        if stats is not None:
            stats.update(crops_planned=len(tiles), crops_read=0, budget_exhausted=False)
        for i, box in enumerate(tiles):
            if budget_s is not None and time.monotonic() - started > budget_s:
                if stats is not None:
                    stats['budget_exhausted'] = True
                break
            clip_disp = pymupdf.Rect(box)
            pix = p.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip_disp,
                                colorspace=pymupdf.csRGB, annots=False)
            if pix.width < 8 or pix.height < 8:
                continue
            img = np.frombuffer(pix.samples_mv, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            for box, text, conf in _ocr_rows(engine(img)):
                xs = [(pix.x + float(q[0])) / s for q in box]
                ys = [(pix.y + float(q[1])) / s for q in box]
                out.append((str(text).strip(), [min(xs), min(ys), max(xs), max(ys)], float(conf)))
            del img, pix
            if stats is not None:
                stats['crops_read'] += 1
            if seen:
                seen((clip_disp.x0, clip_disp.y0, clip_disp.x1, clip_disp.y1), out[-40:], i + 1, len(tiles))
            if progress:
                progress(f"ruta {i + 1}/{len(tiles)}")
        if stats is not None:
            stats['seconds'] = round(time.monotonic()-started, 2)
        return _dedupe(out)
    finally:
        doc.close()
        # OCR assistance and review share this module. Do not retain three
        # ONNX sessions throughout the rest of the drawing analysis.
        _ENGINE = None


def _dedupe(words: list[tuple[str, list[float], float]]) -> list[tuple[str, list[float], float]]:
    """The same word read in two overlapping tiles: keep the more confident reading."""
    kept: list[tuple[str, list[float], float]] = []
    for w, b, c in sorted(words, key=lambda t: -t[2]):
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        h = max(b[3] - b[1], 1.0)
        if any(w2 == w and math.hypot(cx - (b2[0] + b2[2]) / 2, cy - (b2[1] + b2[3]) / 2) <= 0.6 * h for w2, b2, _ in kept):
            continue
        kept.append((w, b, c))
    return kept
