"""Keep the analyses from filling the disk, and say so plainly when it is full anyway.

A reading writes some thirty megabytes: overlays, the evidence behind every metre, the native detector's
diagnostics. On a service with a modest volume that fills it after a few dozen analyses, and the next one fails
with "No space left on device" - an error that tells the person who uploaded the drawing nothing.

Nothing here removes a result anyone can open. What is reclaimed is space that holds no information of its own:
a sheet's files that are byte-for-byte copies of the document's, the native diagnostics left uncompressed,
working directories left behind by an analysis that was killed, and the partial output of analyses that failed.
"""
from __future__ import annotations

import datetime as dt
import filecmp
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)

MIN_FREE_BYTES = 400 * 1024 * 1024          # below this an analysis is not started: it would not be able to finish
TEMP_PREFIXES = ("vvs-detector-cache-", "vvs-native-")
TEMP_MAX_AGE_S = 2 * 3600
FAILED_KEEP_S = 24 * 3600


def free_bytes(path: str) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def link_sheet_copies(out_dir: str) -> int:
    """Replace each sheet file that is identical to the document-level file with a hard link to it.

    A one-sheet document writes its reading twice, once for the document and once for the sheet, and the two are
    the same bytes. Linked, they are one file on disk that both paths still open, unchanged."""
    saved = 0
    base = Path(out_dir)
    sheets = base / "sheets"
    if not sheets.is_dir():
        return 0
    for copy in sheets.glob("*/*"):
        top = base / copy.name
        try:
            if not copy.is_file() or not top.is_file() or copy.is_symlink() or top.is_symlink():
                continue
            a, b = copy.stat(), top.stat()
            if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino) or a.st_size != b.st_size:
                continue
            if not filecmp.cmp(copy, top, shallow=False):
                continue
            tmp = copy.with_name(".link-" + copy.name)
            tmp.unlink(missing_ok=True)
            os.link(top, tmp)
            os.replace(tmp, copy)
            saved += a.st_size
        except OSError:
            continue                                   # housekeeping never fails a reading
    return saved


def sweep_temp(max_age_s: float = TEMP_MAX_AGE_S) -> int:
    """Working directories an analysis leaves behind when its process is killed before it can clean up."""
    saved = 0
    now = time.time()
    root = Path(tempfile.gettempdir())
    try:
        entries = list(root.iterdir())
    except OSError:
        return 0
    for p in entries:
        if not p.name.startswith(TEMP_PREFIXES):
            continue
        try:
            if now - p.stat().st_mtime < max_age_s:
                continue                               # possibly still in use by a running analysis
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
            saved += size
        except OSError:
            continue
    return saved


def remove_failed_results(keep_s: float = FAILED_KEEP_S) -> int:
    """The partial output of analyses that failed a day or more ago: nobody can open it as a result."""
    from .db import AnalysisJob, SessionLocal
    from .storage import storage
    saved = 0
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=keep_s)
    try:
        with SessionLocal() as db:
            for job in db.query(AnalysisJob).filter(AnalysisJob.status == "FAILED",
                                                    AnalysisJob.result_key.isnot(None)).all():
                done = job.finished_at
                if done is None:
                    continue
                if done.tzinfo is None:
                    done = done.replace(tzinfo=dt.timezone.utc)
                if done > cutoff:
                    continue
                path = storage.path(job.result_key)
                if os.path.isdir(path):
                    saved += sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
                    shutil.rmtree(path, ignore_errors=True)
                job.result_key = None
            db.commit()
    except Exception:                                  # noqa: BLE001
        log.exception("Kunde inte städa misslyckade analyser")
    return saved


def reclaim(results_root: str) -> dict:
    """Everything above, over every stored result. Safe to run while analyses run."""
    from .diagnostic_storage import compress_native_diagnostics
    out = {"temp": sweep_temp(), "failed": remove_failed_results(), "linked": 0, "compressed": 0}
    root = Path(results_root)
    if root.is_dir():
        for job_dir in root.glob("*/*"):
            if not job_dir.is_dir():
                continue
            out["linked"] += link_sheet_copies(str(job_dir))
            try:
                out["compressed"] += compress_native_diagnostics(str(job_dir))
            except OSError:
                pass
    return out


def ensure_room(storage_root: str, results_root: str) -> None:
    """Before an analysis starts: make room if the disk is nearly full, and refuse in plain words if it stays so."""
    if free_bytes(storage_root) >= MIN_FREE_BYTES:
        return
    got = reclaim(results_root)
    log.warning("Lite diskutrymme: städade %s", got)
    left = free_bytes(storage_root)
    if left < MIN_FREE_BYTES:
        raise OSError(
            f"Disken där ritningar och resultat sparas är full ({left // (1024 * 1024)} MB ledigt). "
            "Utöka volymen i Railway (tjänsten -> Volumes) eller ta bort gamla projekt, och kör analysen igen.")
