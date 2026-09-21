"""In-memory job store for the browser UI.

The FutureCalc contract is fire-and-forget with a callback, which a browser
cannot receive.  So the UI submits through its own endpoint and polls this
store instead.  It is deliberately process-local and time-limited: results are
a convenience for looking at a drawing, never a record of anything.
"""

import threading
import time
import uuid

# a job lives as long as someone is working with it: every poll or edit call
# refreshes its clock, so a long review session never loses its document
# mid-edit.  Only ABANDONED jobs expire.
TTL_SECONDS = 4 * 60 * 60
MAX_JOBS = 64

_jobs = {}
_lock = threading.Lock()


def _prune(now):
    """Drop expired jobs, then the oldest if we are still over the cap."""
    def last_used(r):
        return r.get("touched", r["created"])
    for jid in [j for j, r in _jobs.items()
                if now - last_used(r) > TTL_SECONDS]:
        _jobs.pop(jid, None)
    if len(_jobs) > MAX_JOBS:
        for jid, _r in sorted(_jobs.items(),
                              key=lambda kv: last_used(kv[1]))[
                :len(_jobs) - MAX_JOBS]:
            _jobs.pop(jid, None)


def create(filename):
    now = time.time()
    jid = uuid.uuid4().hex
    with _lock:
        _prune(now)
        _jobs[jid] = {"id": jid, "status": "pending", "filename": filename,
                      "created": now, "preview": None, "result": None,
                      "error": None}
    return jid


def finish(jid, result=None, error=None, preview=None):
    with _lock:
        rec = _jobs.get(jid)
        if rec is None:
            return
        rec["status"] = "error" if error else "done"
        rec["result"] = result
        rec["error"] = error
        if preview is not None:
            rec["preview"] = preview
        rec["finished"] = time.time()


def attach(jid, **fields):
    """Hang extra state on a job (the parsed document, the source bytes, and
    the merged-stroke cache the click-to-segment path reuses)."""
    with _lock:
        rec = _jobs.get(jid)
        if rec is not None:
            rec.update(fields)


def get(jid):
    with _lock:
        rec = _jobs.get(jid)
        if rec is not None:
            rec["touched"] = time.time()
        return dict(rec) if rec else None


def preview_bytes(jid):
    with _lock:
        rec = _jobs.get(jid)
        return rec["preview"] if rec else None
