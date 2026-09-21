"""Pipe Detection Microservice — FutureCalc `detect-pipes` contract.

POST /predict accepts a job, answers immediately, and delivers the result by
POSTing to the caller's `callbackUrl`.  The synchronous response is only an
acknowledgement; nothing about the detection is carried in it.
"""

import base64
import binascii
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from hmac import compare_digest
from urllib.parse import urlparse

import requests
from flask import (Flask, Response, jsonify, request,
                   send_from_directory)

from .config import Config
from . import jobs
from . import review
from .detect import DetectionError, detect, render_preview
from reviewapp.models import Document as ReviewDocument
# The tuned merge geometry, taken from the local review tool rather than
# reimplemented, so the deployed UI merges exactly the way that one does.
from reviewapp import server as rsrv

log = logging.getLogger("pipe-detect")

app = Flask(__name__, static_folder="static", static_url_path="/static")

from .studio_api import api as studio_api
app.register_blueprint(studio_api)

_pool = None
_inflight = 0
_lock = threading.Lock()

_DATA_URI = re.compile(r"^data:(?P<mime>[^;,]*)(?:;charset=[^;,]*)?"
                       r"(?P<b64>;base64)?,(?P<data>.*)$", re.S)


def _pool_get():
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=Config.WORKERS,
                                   thread_name_prefix="detect")
    return _pool


def auth_failure():
    """Reject the request, or None to let it through.

    The unconfigured case is checked FIRST and explicitly. Comparing the
    header against an empty configured key would compare "" to "" for a
    request that sends no header at all — which passes, and would hand out
    unauthenticated access exactly when the service is least ready for it.
    """
    if not Config.configured():
        return jsonify({"error": "service is not configured: API_KEY is not "
                                 "set on this deployment"}), 503
    supplied = request.headers.get("X-API-Key", "")
    if not supplied or not compare_digest(supplied, Config.API_KEY):
        # contract: 401 is recorded as "Pipe detection service auth error"
        return jsonify({"error": "invalid or missing X-API-Key"}), 401
    return None


# --------------------------------------------------------------------------- #
# request parsing
# --------------------------------------------------------------------------- #
def decode_data_uri(value):
    """Pull the bytes out of a `data:<mime>;base64,<bytes>` URI.

    Bare base64 is accepted too — some callers omit the prefix, and refusing a
    job over that would be pedantry.
    """
    if not isinstance(value, str) or not value.strip():
        raise DetectionError("imageBase64 is missing or not a string")
    raw, mime = value.strip(), ""
    m = _DATA_URI.match(raw)
    if m:
        mime = (m.group("mime") or "").strip()
        raw = m.group("data")
        if not m.group("b64"):
            raise DetectionError("imageBase64 data URI must be base64-encoded")
    raw = re.sub(r"\s+", "", raw)
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DetectionError(f"imageBase64 is not valid base64: {exc}")
    if not data:
        raise DetectionError("imageBase64 decoded to zero bytes")
    return data, mime


def validate_callback(url):
    """Only http(s) callbacks, so a job cannot be aimed at a local file."""
    if not isinstance(url, str) or not url.strip():
        raise DetectionError("callbackUrl is required")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise DetectionError("callbackUrl must be an http(s) URL")
    return url.strip()


# --------------------------------------------------------------------------- #
# callback delivery
# --------------------------------------------------------------------------- #
def post_callback(url, payload):
    delay = Config.CALLBACK_BACKOFF
    last = None
    for attempt in range(1, Config.CALLBACK_RETRIES + 1):
        try:
            r = requests.post(url, json=payload,
                              timeout=Config.CALLBACK_TIMEOUT,
                              headers={"Content-Type": "application/json"})
            if 200 <= r.status_code < 300:
                log.info("callback delivered drawingId=%s status=%s attempt=%d",
                         payload.get("drawingId"), r.status_code, attempt)
                return True
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as exc:
            last = str(exc)
        log.warning("callback attempt %d/%d failed drawingId=%s: %s",
                    attempt, Config.CALLBACK_RETRIES,
                    payload.get("drawingId"), last)
        if attempt < Config.CALLBACK_RETRIES:
            time.sleep(delay)
            delay *= 2
    log.error("callback gave up drawingId=%s: %s", payload.get("drawingId"), last)
    return False


def _warn_if_throttled(wall, cpu):
    """Say so in the logs when the platform is starving background work.

    Cloud Run's default gives a container CPU only while it is handling a
    request. This service answers /predict with 202 and detects afterwards, so
    under that default the work crawls and the callback arrives late — with
    nothing in the logs to explain why. Detection is CPU-bound, so wall time
    far exceeding CPU time is the signature, and worth naming explicitly.

    CPU is measured per-thread, not per-process: each job runs on its own
    thread, and process-wide time would count the other jobs too and hide the
    very starvation this is looking for whenever two overlap.
    """
    if wall < 5 or cpu <= 0:
        return
    if cpu / wall < 0.25:
        log.warning(
            "detection used %.1fs CPU over %.1fs wall (%.0f%%) — this looks "
            "like CPU throttling. On Cloud Run redeploy with "
            "--no-cpu-throttling, or background work after the 202 will keep "
            "being starved.", cpu, wall, cpu / wall * 100)


def run_job(drawing_id, data, mime, width, height, callback_url):
    """Detect, then report — success or failure, the callback always fires."""
    global _inflight
    started = time.time()
    cpu0 = time.thread_time()
    try:
        pipes, labels, meta = detect(data, mime, width, height)
        payload = {"drawingId": drawing_id, "pipes": pipes,
                   "labels": labels, "metadata": meta}
        wall = time.time() - started
        log.info("detected drawingId=%s pipes=%d labels=%d classified=%s "
                 "in %.1fs", drawing_id, len(pipes), len(labels),
                 meta.get("pipesClassified"), wall)
        _warn_if_throttled(wall, time.thread_time() - cpu0)
    except DetectionError as exc:
        payload = {"drawingId": drawing_id, "error": str(exc)}
        log.warning("detection rejected drawingId=%s: %s", drawing_id, exc)
    except Exception as exc:                      # never lose the callback
        log.exception("detection crashed drawingId=%s", drawing_id)
        payload = {"drawingId": drawing_id,
                   "error": f"internal detection error: {exc}"}
    finally:
        with _lock:
            _inflight -= 1
    post_callback(callback_url, payload)


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    with _lock:
        busy = _inflight
    ok = Config.configured()
    body = {"status": "ok" if ok else "unconfigured",
            "apiKey": "set" if ok else "missing",
            "inflight": busy,
            "capacity": Config.WORKERS + Config.QUEUE_LIMIT}
    if not ok:
        body["hint"] = "set API_KEY on this deployment; all requests return 503"
    return jsonify(body), 200


@app.post("/predict")
def predict():
    global _inflight

    denied = auth_failure()
    if denied:
        return denied

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "body must be a JSON object"}), 400

    drawing_id = body.get("drawingId")
    if not isinstance(drawing_id, str) or not drawing_id.strip():
        return jsonify({"error": "drawingId is required"}), 400
    drawing_id = drawing_id.strip()

    try:
        callback_url = validate_callback(body.get("callbackUrl"))
        data, mime = decode_data_uri(body.get("imageBase64"))
    except DetectionError as exc:
        return jsonify({"error": str(exc), "drawingId": drawing_id}), 400

    def _dim(name):
        v = body.get(name)
        return float(v) if isinstance(v, (int, float)) and v > 0 else None

    # Backpressure is the contract's 429: better to tell FutureCalc to come
    # back than to accept work we cannot start and time the callback out.
    with _lock:
        if _inflight >= Config.WORKERS + Config.QUEUE_LIMIT:
            return jsonify({"error": "rate limit exceeded",
                            "drawingId": drawing_id}), 429
        _inflight += 1

    _pool_get().submit(run_job, drawing_id, data, mime,
                       _dim("imageWidth"), _dim("imageHeight"), callback_url)

    log.info("accepted drawingId=%s bytes=%d mime=%s", drawing_id, len(data), mime)
    return jsonify({"status": "accepted", "drawingId": drawing_id}), 202


# --------------------------------------------------------------------------- #
# browser UI
#
# The contract is fire-and-forget with a callback, which a browser cannot
# receive.  These routes exist so a drawing can be dropped on a page and looked
# at; they run the same detection and are guarded by the same API key.
# --------------------------------------------------------------------------- #
@app.get("/")
def ui():
    return send_from_directory(app.static_folder, "index.html")


def run_ui_job(job_id, data, mime):
    global _inflight
    try:
        try:
            png, pw, ph = render_preview(data, mime)
        except DetectionError:
            png, pw, ph = None, None, None
        pipes, labels, meta = detect(data, mime, pw, ph)
        jobs.finish(job_id,
                    result={"pipes": pipes, "labels": labels,
                            "metadata": meta},
                    preview=png)
        log.info("ui job %s: %d pipes, %d labels, %s classified",
                 job_id, len(pipes), len(labels),
                 meta.get("pipesClassified"))
    except DetectionError as exc:
        jobs.finish(job_id, error=str(exc))
    except Exception as exc:
        log.exception("ui job %s crashed", job_id)
        jobs.finish(job_id, error=f"internal detection error: {exc}")
    finally:
        with _lock:
            _inflight -= 1


@app.post("/api/detect")
def ui_detect():
    global _inflight

    denied = auth_failure()
    if denied:
        return denied

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "no file uploaded"}), 400
    data = upload.read()
    if not data:
        return jsonify({"error": "uploaded file is empty"}), 400
    if len(data) > Config.MAX_UPLOAD_BYTES:
        return jsonify({"error": "file is larger than the upload limit"}), 413

    with _lock:
        if _inflight >= Config.WORKERS + Config.QUEUE_LIMIT:
            return jsonify({"error": "server is busy, try again shortly"}), 429
        _inflight += 1

    job_id = jobs.create(upload.filename)
    _pool_get().submit(run_ui_job, job_id, data, upload.mimetype or "")
    return jsonify({"jobId": job_id, "status": "pending"}), 202


@app.get("/api/jobs/<job_id>")
def ui_job(job_id):
    denied = auth_failure()
    if denied:
        return denied
    rec = jobs.get(job_id)
    if rec is None:
        return jsonify({"error": "unknown or expired job"}), 404
    out = {"jobId": rec["id"], "status": rec["status"],
           "filename": rec["filename"]}
    if rec["status"] == "done":
        out.update(rec["result"])
        out["hasPreview"] = rec["preview"] is not None
    elif rec["status"] == "error":
        out["error"] = rec["error"]
    return jsonify(out), 200


@app.get("/api/jobs/<job_id>/preview.png")
def ui_preview(job_id):
    # the <img> tag cannot send a header, so this one is unauthenticated by
    # necessity; the id is an unguessable uuid4 and expires with the job
    png = jobs.preview_bytes(job_id)
    if not png:
        return jsonify({"error": "no preview"}), 404
    return Response(png, mimetype="image/png",
                    headers={"Cache-Control": "private, max-age=600"})


# --------------------------------------------------------------------------- #
# review workflow
#
# The four detection stages, exposed for correction before classification runs.
# Same pipeline as the local review tool — `service/review.py` calls straight
# into `reviewapp`, so the two cannot drift apart in what they detect.
# --------------------------------------------------------------------------- #
def run_review_job(job_id, data, mime):
    global _inflight
    try:
        doc, preview = review.build(data, mime)
        jobs.finish(job_id, result={"document": doc.to_json()},
                    preview=preview)
        jobs.attach(job_id, doc=doc, source=data, mime=mime, cache={})
        log.info("review %s: %d pipes, %d labels, %d joins, %d lines", job_id,
                 len(doc.active_pipes()), len(doc.active_labels()),
                 len(doc.active_joins()), len(doc.active_leaders()))
    except DetectionError as exc:
        jobs.finish(job_id, error=str(exc))
    except Exception as exc:
        log.exception("review job %s crashed", job_id)
        jobs.finish(job_id, error=f"internal error: {exc}")
    finally:
        with _lock:
            _inflight -= 1


@app.post("/api/review")
def review_start():
    global _inflight
    denied = auth_failure()
    if denied:
        return denied

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "no file uploaded"}), 400
    data = upload.read()
    if not data:
        return jsonify({"error": "uploaded file is empty"}), 400
    if len(data) > Config.MAX_UPLOAD_BYTES:
        return jsonify({"error": "file is larger than the upload limit"}), 413

    with _lock:
        if _inflight >= Config.WORKERS + Config.QUEUE_LIMIT:
            return jsonify({"error": "server is busy, try again shortly"}), 429
        _inflight += 1

    job_id = jobs.create(upload.filename)
    _pool_get().submit(run_review_job, job_id, data, upload.mimetype or "")
    return jsonify({"jobId": job_id, "status": "pending"}), 202


@app.get("/api/review/<job_id>")
def review_poll(job_id):
    denied = auth_failure()
    if denied:
        return denied
    rec = jobs.get(job_id)
    if rec is None:
        return jsonify({"error": "unknown or expired job"}), 404
    out = {"jobId": rec["id"], "status": rec["status"],
           "filename": rec["filename"]}
    if rec["status"] == "done":
        out.update(rec["result"])
        out["hasPreview"] = rec["preview"] is not None
    elif rec["status"] == "error":
        out["error"] = rec["error"]
    return jsonify(out), 200


@app.get("/api/review/<job_id>/preview.png")
def review_preview(job_id):
    # Same image as the /api/jobs route; both job kinds share one store, and
    # the review page should not have to know that.
    return ui_preview(job_id)


@app.post("/api/review/<job_id>/ocr")
def review_ocr(job_id):
    """Read the text inside a box the user just drew.

    So adding a label by hand starts from what the drawing actually says
    rather than from an empty field.
    """
    denied = auth_failure()
    if denied:
        return denied
    rec = jobs.get(job_id)
    if rec is None or rec.get("source") is None:
        return jsonify({"error": "unknown or expired job"}), 404
    rect = (request.get_json(silent=True) or {}).get("rect")
    if not isinstance(rect, list) or len(rect) != 4:
        return jsonify({"error": "rect [x0,y0,x1,y1] is required"}), 400
    try:
        code, text = review.ocr_rect(rec["source"], rec.get("mime", ""), rect)
    except DetectionError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        log.exception("ocr failed on %s", job_id)
        return jsonify({"error": f"internal error: {exc}"}), 500
    return jsonify({"code": code, "text": text}), 200


@app.post("/api/review/<job_id>/segment")
def review_segment(job_id):
    """Trace the pipe under a click the detector missed."""
    denied = auth_failure()
    if denied:
        return denied
    rec = jobs.get(job_id)
    if rec is None or rec.get("source") is None:
        return jsonify({"error": "unknown or expired job"}), 404
    body = request.get_json(silent=True) or {}
    try:
        x, y = float(body["x"]), float(body["y"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "x and y are required numbers"}), 400
    walls = body.get("walls")
    try:
        out = review.segment_at(rec["source"], rec.get("mime", ""), x, y,
                                cache=rec.get("cache"), walls=walls)
    except DetectionError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        log.exception("segment_at failed on %s", job_id)
        return jsonify({"error": f"internal error: {exc}"}), 500
    return jsonify(out), 200


@app.post("/api/review/<job_id>/classify")
def review_classify(job_id):
    """Classify the REVIEWED document the browser sends back."""
    denied = auth_failure()
    if denied:
        return denied
    if jobs.get(job_id) is None:
        return jsonify({"error": "unknown or expired job"}), 404
    body = request.get_json(silent=True) or {}
    doc_json = body.get("document")
    if not isinstance(doc_json, dict):
        return jsonify({"error": "document is required"}), 400
    try:
        doc = ReviewDocument.from_json(doc_json)
        summary = review.classify(doc)
    except Exception as exc:
        log.exception("classify failed on %s", job_id)
        return jsonify({"error": f"classification failed: {exc}"}), 500
    return jsonify({"document": doc.to_json(), "summary": summary}), 200


# --------------------------------------------------------------------------- #
# geometry — the merges, shared verbatim with the local review tool
# --------------------------------------------------------------------------- #
def _rings_from_body():
    rings = (request.get_json(silent=True) or {}).get("rings")
    if not isinstance(rings, list) or not rings:
        return None, (jsonify({"error": "rings is required"}), 400)
    return rings, None


@app.post("/api/geometry/merge")
def geometry_merge():
    """Union the selected rings into ONE pipe polygon.

    `single=True` bridges parts that stay apart, because "select several
    polygons and merge" has to yield one pipe — not N pipes back.
    """
    denied = auth_failure()
    if denied:
        return denied
    rings, bad = _rings_from_body()
    if bad:
        return bad
    try:
        out = rsrv.merge_rings(rings)
    except Exception as exc:
        log.exception("merge failed")
        return jsonify({"error": f"merge failed: {exc}"}), 500
    return jsonify({"rings": out}), 200


@app.post("/api/geometry/automerge")
def geometry_automerge():
    """Find polygons that are one pipe broken into pieces, and merge each set.

    A group is only merged when the union stays a single polygon, does not
    close a loop it would then paint solid, and does not cover much more than
    the pieces already did — the same three guards the local tool uses.
    """
    denied = auth_failure()
    if denied:
        return denied
    rings, bad = _rings_from_body()
    if bad:
        return bad
    try:
        out, skipped = [], 0
        for group in rsrv.same_pipe_groups(rings):
            members = [rings[i] for i in group]
            if rsrv.enclosed_area(rsrv.merged_geometry(members)) > \
                    rsrv.MAX_ENCLOSED_AREA:
                skipped += 1
                continue
            merged = rsrv.merge_rings(members)
            if len(merged) != 1:
                continue
            if rsrv._grows_too_much(members, merged[0]):
                skipped += 1
                continue
            out.append({"indices": group, "ring": merged[0]})
    except Exception as exc:
        log.exception("automerge failed")
        return jsonify({"error": f"merge failed: {exc}"}), 500
    return jsonify({"groups": out, "skipped": skipped}), 200


@app.post("/api/geometry/buffer")
def geometry_buffer():
    """A pipe polygon from a hand-drawn centreline (Draw pipe tool)."""
    denied = auth_failure()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    try:
        ring = review.buffer_centreline(body.get("path"), body.get("width"))
    except DetectionError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        log.exception("buffer failed")
        return jsonify({"error": f"buffer failed: {exc}"}), 500
    return jsonify({"ring": ring}), 200


@app.post("/api/geometry/splitline")
def geometry_splitline():
    """Split one pipe polygon along a user-drawn line (Split pipe tool)."""
    denied = auth_failure()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    try:
        rings = review.split_ring_by_line(body.get("ring"), body.get("line"))
    except DetectionError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        log.exception("splitline failed")
        return jsonify({"error": f"split failed: {exc}"}), 500
    return jsonify({"rings": rings}), 200


@app.post("/api/geometry/clipwall")
def geometry_clipwall():
    """Clip pipe polygons against wall rings (Draw wall tool)."""
    denied = auth_failure()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    rings = body.get("rings")
    if not isinstance(rings, list):
        return jsonify({"error": "rings is required"}), 400
    try:
        groups = review.clip_rings_by_wall(rings, body.get("wall"))
    except Exception as exc:
        log.exception("clipwall failed")
        return jsonify({"error": f"wall clipping failed: {exc}"}), 500
    return jsonify({"groups": groups}), 200


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "payload too large"}), 413


def create_app():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    Config.validate()
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_UPLOAD_BYTES + (2 << 20)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=Config.PORT)
