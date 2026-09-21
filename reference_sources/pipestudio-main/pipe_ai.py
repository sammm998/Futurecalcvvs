"""ML detector for label boxes (YOLOX ONNX).

A YOLOX-s model trained on CVAT-annotated VVS ritningar and exported to ONNX
with dynamic batch/height/width axes.  The bundled `models/model_dynamic.onnx`
is the v3 export.  Two classes, both LABELS:

    Label_Box       the system-code label as drawn in the normal style
                    (median 124 x 60 px at 200 dpi)
    type2_label     the same kind of label in a different visual style
                    (other drawing offices); handled exactly like Label_Box,
                    the class name is kept on the box so the application can
                    tell which style of label was detected

The v1/v2 exports also had a `Joining_Point` class.  The model is no longer
used for joining points: they come from the vector content (the drawn
joining circles, `pipe_types.find_join_circles` / `pipe_seg.detect_circle_marks`),
so that class is gone from the model and from this module.  An old export
that still carries it runs fine — its joining-point boxes are simply ignored.

This module only runs the network and hands back boxes in PAGE POINTS.
Reading the code inside a label box is `pipe_types.labels_from_boxes`; the
vector stages (pipe recognition, connection lines, walls, classification) are
untouched and consume the boxes where they used to consume the glyph-OCR
labels (`pipe_types.detect_marks`).

Processing mirrors the standalone `onnx_inference.ONNXDetector` so that the
app shows the same boxes the script draws on the same raster: raw BGR float32
with no normalisation, score threshold and per-class NMS outside the graph.
The one deliberate difference: the raster is PADDED with white to a multiple
of 32 instead of cropped, so nothing at the sheet border is lost.  Padding at
the right/bottom edge leaves every box coordinate unchanged.

Resolution: the export has dynamic H/W axes and the whole sheet goes through
in one pass (no tiling).  Default 144 dpi = 2 px/pt, the review UI's own
background scale, so the boxes in the app line up with the standalone script
on the exported background; training ran at ~200 dpi and the model is
scale-robust in that range.  `AI_RENDER_DPI` overrides.

Confidence: `AI_CONF` (default 0.05) is the FLOOR for the review flow — every
detection above it is returned with its score, the review document keeps the
score on each label, and the user filters with sliders before or after the
results are shown (`Document.thresholds`),
without re-running the model.  Filtering a score-sorted NMS result after the
fact gives exactly the boxes a run at that threshold would: a lower-scored
box never suppresses a higher one.  The unattended `/predict` path uses
`AI_PREDICT_CONF` (default 0.30, the standalone scripts' default).

GPU: `CUDAExecutionProvider` is used when the installed onnxruntime build and
the host expose it, otherwise CPU (a full sheet at 144 dpi takes ~10 s on
four cores).  The pip-installed NVIDIA libraries are preloaded so that
`onnxruntime-gpu` does not silently fall back to CPU.
"""

import ctypes
import glob
import logging
import os
import threading
import time

import cv2
import fitz
import numpy as np

log = logging.getLogger("pipe-ai")

CONFIG = {
    "model_path": os.environ.get(
        "AI_MODEL_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "models", "model_dynamic.onnx")),
    "render_dpi": float(os.environ.get("AI_RENDER_DPI", "144")),
    # the FLOOR for the review flow: every detection above it is kept with
    # its score and the user filters per class in the UI, before or after the
    # results are shown, without re-running the model
    "conf": float(os.environ.get("AI_CONF", "0.05")),
    # the unattended /predict path has nobody to slide anything: it keeps the
    # standalone scripts' default
    "predict_conf": float(os.environ.get("AI_PREDICT_CONF", "0.30")),
    "nms_iou": float(os.environ.get("AI_NMS_IOU", "0.45")),
    # a render larger than this (pixels) is scaled down before inference;
    # the input tensor alone is 12 bytes per pixel
    "max_pixels": int(os.environ.get("AI_MAX_PIXELS", "40000000")),
}

LABEL_CLASS = "Label_Box"
TYPE2_LABEL_CLASS = "type2_label"
# every class the model reports that is a label; both are used the same way
LABEL_CLASSES = (LABEL_CLASS, TYPE2_LABEL_CLASS)


class LabelBox(tuple):
    """A label box (x0, y0, x1, y1, score) that also remembers the model
    class it came from: `kind` is "Label_Box" or "type2_label".

    It IS the 5-tuple every consumer unpacks, so nothing downstream changes;
    the class name rides along for whoever wants to know the label style.
    """

    def __new__(cls, x0, y0, x1, y1, score, kind=LABEL_CLASS):
        obj = super().__new__(cls, (x0, y0, x1, y1, score))
        obj.kind = kind
        return obj


class AIModelError(RuntimeError):
    """The model cannot run at all (missing file, runtime or metadata)."""


class AIDetections:
    """One page's detections, in page points.

    label_boxes  [LabelBox]  (x0, y0, x1, y1, score) tuples with `.kind`,
                 both label classes together, sorted by score
    raw          [(x0, y0, x1, y1, score, class_name)] everything, unclipped
    provider     "cuda" | "cpu"
    scale        px per pt of the raster the model saw
    size         (width, height) of that raster in px, before padding
    """

    def __init__(self, label_boxes, raw, provider, scale, size, floor):
        self.label_boxes = label_boxes
        self.raw = raw
        self.provider = provider
        self.scale = scale
        self.size = size
        self.floor = floor

    def label_boxes_at(self, conf):
        return [b for b in self.label_boxes if b[4] >= conf]


# --------------------------------------------------------------------------- #
# session (lazy, shared — loading 35 MB and picking a provider once is enough)
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
_session = None          # (InferenceSession, [class names], provider str)


def _preload_cuda_libs():
    """Make pip-installed CUDA/cuDNN libraries visible to onnxruntime-gpu.

    The runtime dlopens them at session creation and silently falls back to
    CPU when they are not on the loader path, which is where the `nvidia-*`
    wheels put them.  Loading with RTLD_GLOBAL first (the PyTorch trick)
    fixes that.  Best effort.
    """
    try:
        import nvidia
        roots = list(nvidia.__path__)
    except ImportError:
        return
    order = ["libcudart.so*", "libcublasLt.so*", "libcublas.so*",
             "libcufft.so*", "libcurand.so*", "libnvrtc.so*",
             "libcudnn.so*"]
    for pattern in order:
        for root in roots:
            for path in sorted(glob.glob(
                    os.path.join(root, "*", "lib", pattern))):
                if ".so" not in os.path.basename(path):
                    continue
                try:
                    ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


def _get_session():
    global _session
    with _lock:
        if _session is not None:
            return _session
        try:
            import onnxruntime
        except ImportError:
            raise AIModelError(
                "the ML detector needs onnxruntime — install `onnxruntime` "
                "(or `onnxruntime-gpu` on a CUDA machine)")
        path = CONFIG["model_path"]
        if not os.path.isfile(path):
            raise AIModelError(
                f"ML model not found at {path} — set AI_MODEL_PATH to the "
                f"exported model_dynamic.onnx")
        onnxruntime.set_default_logger_severity(3)   # the export warns a lot
        available = onnxruntime.get_available_providers()
        providers = ["CPUExecutionProvider"]
        if "CUDAExecutionProvider" in available:
            _preload_cuda_libs()
            # HEURISTIC: the default EXHAUSTIVE cuDNN algorithm search
            # benchmarks every convolution algorithm for the actual input
            # size on the first run — on a 4768x3392 sheet that alone took
            # longer than CPU inference (14 s), and the sheets differ in size
            # so it would happen again and again.
            providers.insert(0, ("CUDAExecutionProvider",
                                 {"cudnn_conv_algo_search": "HEURISTIC"}))
        try:
            sess = onnxruntime.InferenceSession(path, providers=providers)
        except Exception as exc:
            raise AIModelError(f"could not load the ML model: {exc}")
        active = sess.get_providers()[0]
        provider = "cuda" if active == "CUDAExecutionProvider" else "cpu"
        meta = sess.get_modelmeta().custom_metadata_map
        try:
            classes = [meta[k] for k in sorted(meta, key=int)]
        except (KeyError, ValueError):
            raise AIModelError(
                "the model carries no class-name metadata — re-export with "
                "the notebook's export_onnx.py")
        log.info("ML model loaded: %s | classes=%s | provider=%s",
                 path, classes, provider)
        if provider == "cpu" and "CUDAExecutionProvider" in available:
            log.warning("onnxruntime-gpu is installed but the CUDA provider "
                        "failed to load — running on CPU (missing CUDA / "
                        "cuDNN wheels?)")
        _session = (sess, classes, provider)
        return _session


def available():
    """Can the detector run here?  (model file + runtime importable)"""
    if not os.path.isfile(CONFIG["model_path"]):
        return False
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------- #
# inference
# --------------------------------------------------------------------------- #
def pad_to_stride(img_bgr, stride=32, value=255):
    """Pad right/bottom with white so H and W are multiples of `stride`."""
    h, w = img_bgr.shape[:2]
    ph, pw = (-h) % stride, (-w) % stride
    if ph == 0 and pw == 0:
        return img_bgr
    return cv2.copyMakeBorder(img_bgr, 0, ph, 0, pw, cv2.BORDER_CONSTANT,
                              value=(value, value, value))


def detect_boxes(img_bgr, conf=None, nms=None):
    """One full-image forward pass.

    Returns (boxes Nx4 xyxy float32, scores N float32, class_ids N int64) in
    pixels of `img_bgr`.  Score floor and per-class NMS run here, exactly as
    in the standalone scripts.
    """
    conf = CONFIG["conf"] if conf is None else float(conf)
    nms = CONFIG["nms_iou"] if nms is None else float(nms)
    sess, classes, provider = _get_session()

    padded = pad_to_stride(img_bgr)
    inp = np.expand_dims(np.moveaxis(padded, -1, 0), 0).astype(np.float32)
    t0 = time.time()
    bboxes, ids = sess.run(None, {"input": inp})
    log.info("ML inference: %dx%d in %.1fs on %s", padded.shape[1],
             padded.shape[0], time.time() - t0, provider)
    bboxes, ids = np.squeeze(bboxes, 0), np.squeeze(ids, 0)

    empty = (np.empty((0, 4), np.float32), np.empty(0, np.float32),
             np.empty(0, np.int64))
    if bboxes.ndim != 2 or bboxes.shape[0] == 0:
        return empty
    keep = bboxes[:, 4] >= conf
    bboxes, ids = bboxes[keep], ids[keep]
    if bboxes.shape[0] == 0:
        return empty

    boxes = bboxes[:, :4].astype(np.float32)
    scores = bboxes[:, 4].astype(np.float32)
    xywh = boxes.copy()
    xywh[:, 2] -= boxes[:, 0]
    xywh[:, 3] -= boxes[:, 1]
    keep_b, keep_s, keep_i = [], [], []
    for cid in np.unique(ids):
        m = ids == cid
        idx = cv2.dnn.NMSBoxes(xywh[m], scores[m],
                               score_threshold=conf, nms_threshold=nms)
        if len(idx):
            idx = np.asarray(idx).reshape(-1)
            keep_b.append(boxes[m][idx])
            keep_s.append(scores[m][idx])
            keep_i.append(np.asarray(ids[m][idx], np.int64))
    if not keep_b:
        return empty
    return (np.concatenate(keep_b), np.concatenate(keep_s),
            np.concatenate(keep_i))


def render_page(page, dpi=None):
    """The page as a BGR raster at `dpi`, capped at CONFIG["max_pixels"].

    Returns (img, scale) with scale in px per pt, so callers can map boxes
    back to page points whatever the cap did.
    """
    dpi = CONFIG["render_dpi"] if dpi is None else float(dpi)
    s = dpi / 72.0
    w, h = page.rect.width, page.rect.height
    if w * h * s * s > CONFIG["max_pixels"]:
        s = (CONFIG["max_pixels"] / (w * h)) ** 0.5
        log.warning("ML render capped: %.0f dpi -> %.0f dpi to stay under "
                    "%d pixels", dpi, s * 72.0, CONFIG["max_pixels"])
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s))
    img = np.frombuffer(pix.samples, np.uint8).reshape(
        pix.height, pix.width, pix.n)
    img = cv2.cvtColor(np.ascontiguousarray(img[:, :, :3]), cv2.COLOR_RGB2BGR)
    return img, s


def detect_on_page(page, conf=None, dpi=None):
    """Detect label boxes on one fitz page, in page points.

    Both label classes (`LABEL_CLASSES`) land in `label_boxes`; each box
    keeps its class name as `.kind`.  Any other class the export may carry
    (the old `Joining_Point`) is kept in `raw` only.

    `conf` is the score threshold (default CONFIG["conf"]); every detection
    above it is returned with its score.  Coordinates come back as Python floats,
    never numpy scalars, because they end up in JSON documents.
    """
    _sess, classes, provider = _get_session()
    img, s = render_page(page, dpi)
    floor = CONFIG["conf"] if conf is None else float(conf)
    boxes, scores, ids = detect_boxes(img, conf=floor)

    label_boxes, raw = [], []
    for (x1, y1, x2, y2), score, cid in zip(boxes, scores, ids):
        px1, py1, px2, py2 = (float(x1) / s, float(y1) / s,
                              float(x2) / s, float(y2) / s)
        sc = float(score)
        name = classes[cid] if 0 <= cid < len(classes) else str(cid)
        raw.append((px1, py1, px2, py2, sc, name))
        if name in LABEL_CLASSES:
            label_boxes.append(LabelBox(px1, py1, px2, py2, sc, kind=name))
    label_boxes.sort(key=lambda b: -b[4])
    n_type2 = sum(1 for b in label_boxes if b.kind == TYPE2_LABEL_CLASS)
    log.info("ML detector (%s, conf %.2f): %d label boxes (%d Label_Box, "
             "%d type2_label) on a %dx%d raster (%.1f px/pt)", provider,
             floor, len(label_boxes), len(label_boxes) - n_type2, n_type2,
             img.shape[1], img.shape[0], s)
    return AIDetections(label_boxes, raw, provider, s,
                        (img.shape[1], img.shape[0]), floor)
