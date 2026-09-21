"""Bound raster inference memory without lowering the drawing's resolution.

The preserved PipeStudio model and box detector run on overlapping PDF clips.
Only small box records are retained between tiles, never a full-page raster.
"""
import math
import os
from contextlib import contextmanager


def tile_starts(length, size, overlap):
    if length <= size:
        return [0]
    starts = list(range(0, length - size + 1, size - overlap))
    if starts[-1] != length - size:
        starts.append(length - size)
    return starts


@contextmanager
def bounded_model():
    """Release the model and its allocations before OCR and graph assembly."""
    import pipe_ai
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.log_severity_level = 3
    session = ort.InferenceSession(pipe_ai.CONFIG['model_path'], sess_options=options,
                                   providers=['CPUExecutionProvider'])
    meta = session.get_modelmeta().custom_metadata_map
    classes = [meta[k] for k in sorted(meta, key=int)]
    previous = pipe_ai._session
    pipe_ai._session = (session, classes, 'cpu')
    try:
        yield classes, 'cpu'
    finally:
        pipe_ai._session = previous
        del session


def detect(pdf_path, page_no=0, *, progress=None):
    with bounded_model() as (classes, provider):
        return _detect_tiles(pdf_path, page_no, classes, provider, progress=progress)


def _detect_tiles(pdf_path, page_no, classes, provider, *, progress=None):
    import cv2
    import numpy as np
    import pymupdf
    import pipe_ai

    size = int(os.environ.get('VVS_DETECTION_TILE_PX', '768'))
    if not 512 <= size <= 2048:
        raise ValueError('VVS_DETECTION_TILE_PX must be between 512 and 2048')
    overlap = size // 4
    scale = float(pipe_ai.CONFIG['render_dpi']) / 72
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError('AI_RENDER_DPI must be positive and finite')
    floor = 0.05  # Same threshold as vectorascore.detect.LABEL_CONF.
    found = []
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_no]
        width, height = math.ceil(page.rect.width * scale), math.ceil(page.rect.height * scale)
        xs, ys = tile_starts(width, size, overlap), tile_starts(height, size, overlap)
        for row, y in enumerate(ys):
            for col, x in enumerate(xs):
                if progress:
                    progress(f'PIPESTUDIO_DETECT_TILE_{row * len(xs) + col + 1}_OF_{len(xs) * len(ys)}')
                clip = pymupdf.Rect(x / scale, y / scale, min(x + size, width) / scale,
                                    min(y + size, height) / scale) & page.rect
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip,
                                      colorspace=pymupdf.csRGB, alpha=False)
                image = np.frombuffer(pix.samples_mv, np.uint8).reshape(pix.height, pix.width, 3)
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                boxes, scores, ids = pipe_ai.detect_boxes(image, conf=floor)
                for box, score, cid in zip(boxes, scores, ids):
                    kind = classes[int(cid)] if 0 <= int(cid) < len(classes) else str(cid)
                    if kind not in pipe_ai.LABEL_CLASSES:
                        continue
                    x0, y0, x1, y1 = map(float, box)
                    rect = [(max(0, x0) + pix.x) / scale, (max(0, y0) + pix.y) / scale,
                            (min(pix.width, x1) + pix.x) / scale, (min(pix.height, y1) + pix.y) / scale]
                    if rect[2] > rect[0] and rect[3] > rect[1]:
                        found.append((rect, float(score), kind))
                del image, pix, boxes, scores, ids
    # Original per-class NMS also removes detections repeated in tile overlaps.
    kept = []
    for kind in sorted({f[2] for f in found}):
        group = [f for f in found if f[2] == kind]
        xywh = [[r[0], r[1], r[2] - r[0], r[3] - r[1]] for r, _, _ in group]
        indices = cv2.dnn.NMSBoxes(xywh, [f[1] for f in group], floor, pipe_ai.CONFIG['nms_iou'])
        kept.extend(group[int(i)] for i in np.asarray(indices).reshape(-1))
    kept.sort(key=lambda f: (-f[1], f[0]))
    return {'label_boxes': [{'id': i, 'rect': [round(v, 2) for v in rect],
                             'score': round(score, 3), 'cls': kind}
                            for i, (rect, score, kind) in enumerate(kept)],
            'ml_joins': [], 'provider': provider,
            'raster_strategy': {'mode': 'overlapping_tiles', 'tile_px': size,
                                'overlap_px': overlap, 'dpi': scale * 72,
                                'tiles': len(xs) * len(ys)}}
