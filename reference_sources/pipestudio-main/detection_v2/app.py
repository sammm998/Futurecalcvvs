"""Protocol 2 ingress and bounded asynchronous HMAC callback delivery."""
import base64
import gzip
import hashlib
import hmac
import io
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import requests
from defusedxml import ElementTree
from flask import Flask, jsonify, request
from jsonschema import ValidationError

from .contract import validate, validate_result
from .detector import detect

log = logging.getLogger(__name__)

CONTRACT_VERSION = "2.0.2"
ASSIGNMENT_METHODS = {"llm", "dimension"}      # contract 2.0.2: required, never defaulted, no fallback


def signature_headers(raw, key_id, secret, timestamp=None):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    signature = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-Key-Id": key_id,
            "X-Timestamp": timestamp, "X-Signature": "v1=" + signature}


def deliver(raw, config):
    for attempt in range(config["CALLBACK_RETRIES"]):
        try:
            response = requests.post(config["CALLBACK_URL"], data=raw,
                headers=signature_headers(raw, config["CALLBACK_KEY_ID"], config["CALLBACK_HMAC_KEY"]),
                timeout=config["CALLBACK_TIMEOUT"], allow_redirects=False)
            if 200 <= response.status_code < 300:
                return True
            if response.status_code < 500 and response.status_code not in (408, 429):
                log.error("callback rejected: HTTP %s", response.status_code)
                return False
        except requests.RequestException:
            log.warning("callback transport failed, attempt %d", attempt + 1)
        if attempt + 1 < config["CALLBACK_RETRIES"]:
            time.sleep(config["CALLBACK_BACKOFF"] * 2 ** attempt)
    return False


def decode_image(encoded, limit):
    try:
        compressed = base64.b64decode(encoded, validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            svg = stream.read(limit + 1)
        if not svg or len(svg) > limit:
            raise ValueError("SVG is empty or exceeds decompressed size limit")
        root = ElementTree.fromstring(svg)
        if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
            raise ValueError("image must contain SVG")
        return svg
    except Exception as exc:
        raise ValueError("image must be base64 of a valid, bounded gzipped SVG") from exc


def create_app(overrides=None, detector=detect, callback=deliver, executor=None, backend=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(
        EXECUTION_MODE=os.getenv("EXECUTION_MODE", "local"),
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
        API_KEY=os.getenv("API_KEY", ""), API_KEY_PREVIOUS=os.getenv("API_KEY_PREVIOUS", ""),
        CALLBACK_URL=os.getenv("CALLBACK_URL", ""),
        CALLBACK_KEY_ID=os.getenv("CALLBACK_KEY_ID", ""),
        CALLBACK_HMAC_KEY=os.getenv("CALLBACK_HMAC_KEY", ""),
        WORKERS=int(os.getenv("WORKERS", "1")), QUEUE_LIMIT=int(os.getenv("QUEUE_LIMIT", "0")),
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_UPLOAD_BYTES", "31000000")),
        MAX_SVG_BYTES=int(os.getenv("MAX_SVG_BYTES", "67108864")),
        MAX_IMAGE_PIXELS=int(os.getenv("MAX_IMAGE_PIXELS", "80000000")),
        CALLBACK_RETRIES=int(os.getenv("CALLBACK_RETRIES", "5")),
        CALLBACK_TIMEOUT=int(os.getenv("CALLBACK_TIMEOUT", "30")),
        CALLBACK_BACKOFF=float(os.getenv("CALLBACK_BACKOFF", "2")))
    if overrides:
        app.config.update(overrides)
    config = app.config
    mode = config["EXECUTION_MODE"]
    if mode not in ("local", "ingress", "worker"):
        raise ValueError("invalid EXECUTION_MODE")
    if os.getenv("K_SERVICE") and mode == "local":
        raise ValueError("Cloud Run requires ingress or worker execution mode")
    if mode != "local":
        from .queue_backend import CloudBackend
        backend = backend or CloudBackend(mode)
    if config["WORKERS"] < 1 or config["QUEUE_LIMIT"] < 0 or config["CALLBACK_RETRIES"] < 1:
        raise ValueError("invalid worker/queue/retry configuration")
    pool = (executor or ThreadPoolExecutor(max_workers=config["WORKERS"], thread_name_prefix="detection-v2")) if mode == "local" else None
    slots = threading.BoundedSemaphore(config["WORKERS"] + config["QUEUE_LIMIT"])
    app.extensions["detection_executor"] = pool

    def configured():
        if mode == "ingress":
            return bool(config["API_KEY"])
        url = urlsplit(config["CALLBACK_URL"])
        return bool((mode == "worker" or config["API_KEY"]) and config["CALLBACK_KEY_ID"] and config["CALLBACK_HMAC_KEY"]
                    and url.scheme == "https" and url.hostname and not url.username and not url.fragment)

    def method_available(method):
        """Contract 2.0.2: "llm" needs the model credentials, "dimension" must not
        touch a model at all, so it needs none.  A method that cannot be performed
        is reported through a failed callback; it is never swapped for the other one."""
        return method == "dimension" or detector is not detect or bool(config["OPENAI_API_KEY"])

    def run(body):
        started = time.monotonic()
        log.info("detection started runId=%s drawingId=%s", body["runId"], body["drawingId"])
        try:
            try:
                if not method_available(body["assignmentMethod"]):
                    result = {"protocolVersion": 2, "drawingId": body["drawingId"], "runId": body["runId"],
                              "status": "failed", "error": {"code": "assignment_method_unavailable",
                              "message": "The requested assignment method is unavailable", "retryable": False}}
                else:
                    svg = decode_image(body["image"], config["MAX_SVG_BYTES"])
                    result = detector(svg, body)
                validate_result(result, body)
                log.info("detection completed runId=%s elapsed=%.1fs", body["runId"], time.monotonic() - started)
            except Exception:
                log.exception("detection failed runId=%s", body["runId"])
                result = {"protocolVersion": 2, "drawingId": body["drawingId"], "runId": body["runId"],
                          "status": "failed", "error": {"code": "detection_failed",
                          "message": "Input could not be processed into a valid detection result", "retryable": False}}
            raw = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
            if not callback(raw, config):
                log.error("callback delivery exhausted runId=%s drawingId=%s", body["runId"], body["drawingId"])
            else:
                log.info("callback delivered runId=%s status=%s elapsed=%.1fs", body["runId"], result["status"], time.monotonic() - started)
        except Exception:
            log.exception("job delivery crashed runId=%s", body["runId"])
        finally:
            # Keep capacity occupied until delivery ends, including retries.
            slots.release()

    @app.get("/health")
    def health():
        return jsonify(status="ok" if configured() else "unconfigured", protocolVersion=2,
                       contractVersion=CONTRACT_VERSION, assignmentMethods=sorted(ASSIGNMENT_METHODS), endpoint="/"), 200

    @app.post("/")
    def submit():
        if mode == "worker":
            return jsonify(error="not found"), 404
        if not configured():
            return jsonify(error="service is not configured"), 503
        key = request.headers.get("X-API-Key", "").encode()
        matches = [hmac.compare_digest(key, candidate.encode()) for candidate in
                   (config["API_KEY"], config["API_KEY_PREVIOUS"]) if candidate]
        if not key or not any(matches):
            return jsonify(error="invalid or missing X-API-Key"), 401
        body = request.get_json(silent=True)
        try:
            validate("request", body)
            # assignmentMethod is required and never defaulted: refused before any work
            if body.get("assignmentMethod") not in ASSIGNMENT_METHODS:
                raise ValueError("assignmentMethod must be one of " + ", ".join(sorted(ASSIGNMENT_METHODS)))
            space = body["coordinateSpace"]
            if space["width"] * space["height"] > config["MAX_IMAGE_PIXELS"]:
                raise ValueError("canvas exceeds processing limit")
        except (ValidationError, ValueError, TypeError, AttributeError):
            return jsonify(error=f"request does not conform to contract {CONTRACT_VERSION}"), 400
        if mode == "ingress":
            from .queue_backend import JobConflict
            try:
                backend.enqueue(body)
            except JobConflict:
                return jsonify(error="runId already belongs to a different request"), 409
            except Exception:
                log.exception("durable job submission failed runId=%s", body["runId"])
                return jsonify(error="job could not be queued; retry with the same runId"), 503
            return jsonify(protocolVersion=2, status="accepted", drawingId=body["drawingId"], runId=body["runId"]), 202
        if not slots.acquire(blocking=False):
            return jsonify(error="rate limit exceeded"), 429, {"Retry-After": "5"}
        try:
            pool.submit(run, body)
        except Exception:
            slots.release()
            log.exception("job submission failed")
            return jsonify(error="job could not be scheduled"), 503
        return jsonify(protocolVersion=2, status="accepted", drawingId=body["drawingId"], runId=body["runId"]), 202

    @app.post("/tasks/process")
    def process_task():
        # This route exists only on the private worker service. Cloud Run IAM
        # verifies the queue's OIDC token before a request reaches Flask.
        if mode != "worker":
            return jsonify(error="not found"), 404
        if not configured():
            return jsonify(error="worker is not configured"), 503
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"job"} or not isinstance(body["job"], str) or not re.fullmatch(r"[0-9a-f]{64}", body["job"]):
            return jsonify(error="invalid task"), 400
        from .queue_worker import process
        return process(backend, body["job"], config, callback)

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="payload too large"), 413

    return app
