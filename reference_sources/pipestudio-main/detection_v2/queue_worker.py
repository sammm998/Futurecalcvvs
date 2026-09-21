"""Process within the queue's active HTTP request, never after returning 2xx."""
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .queue_backend import Busy, encode

log = logging.getLogger(__name__)


def calculate(body):
    # A hard wall-clock deadline also works with gunicorn's threaded worker.
    # Killing this subprocess bounds CPU execution before a lease can expire.
    # Each attempt loads its own model; later optimisation can reuse a worker
    # process, provided it retains this cancellation guarantee.
    with tempfile.TemporaryDirectory(prefix="pipe-task-") as directory:
        source, result = Path(directory)/"request.json", Path(directory)/"result.json"
        source.write_bytes(encode(body))
        child = subprocess.Popen([sys.executable, "-m", "detection_v2.task_detect", str(source), str(result)],
                                 start_new_session=True)
        try:
            code = child.wait(timeout=900)
            if code:
                raise subprocess.CalledProcessError(code, child.args)
        finally:
            # Tesseract descendants must not survive a timeout either.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        return json.loads(result.read_bytes())


def process(backend, job, config, callback, calculate_fn=calculate):
    started = time.monotonic()
    try:
        state, generation = backend.claim(job)
    except Busy:
        return {"error": "job already running"}, 503
    except Exception:
        log.exception("task claim failed job=%s", job)
        return {"error": "storage unavailable"}, 503
    if state.get("delivered"):
        return {"status": "already delivered"}, 200
    try:
        if "result" not in state:
            body = backend.request(job)
            log.info("queued detection started runId=%s job=%s", body["runId"], job)
            # Runtime crashes/OOM/timeout are retried, not cached as a terminal
            # input error. Deterministic detection failures are result objects.
            state["result"] = calculate_fn(body)
            from .contract import validate_result
            validate_result(state["result"], body)
            generation = backend.save(job, state, generation)
            log.info("queued detection completed runId=%s elapsed=%.1fs", body["runId"], time.monotonic()-started)
        # Cloud Tasks supplies backoff. One callback attempt per dispatch avoids
        # paying for sleeps and persists the exact result across retries.
        if not callback(encode(state["result"]), {**config, "CALLBACK_RETRIES": 1}):
            log.error("queued callback failed job=%s; Cloud Tasks will retry", job)
            return {"error": "callback failed"}, 503
        state["delivered"] = True
        generation = backend.save(job, state, generation)
        log.info("queued callback delivered job=%s elapsed=%.1fs", job, time.monotonic()-started)
        return {"status": "delivered"}, 200
    except Exception:
        log.exception("queued processing failed job=%s; Cloud Tasks will retry", job)
        return {"error": "processing failed"}, 503
    finally:
        try:
            # On an uncertain/fenced write, never overwrite another attempt's
            # state. The old generation fails closed; its lease will expire.
            # Never persist an uncommitted result or delivered flag here.
            # Those writes must succeed before a retry can skip either phase.
            current, current_generation = backend.read(f"jobs/{job}/state.json")
            if current_generation == generation:
                current["lease_until"] = 0
                backend.save(job, current, generation)
        except Exception:
            log.exception("lease release failed job=%s; expires automatically", job)
