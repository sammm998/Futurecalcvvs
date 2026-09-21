"""Runtime configuration, all from the environment so nothing is baked in.

API_KEY has no default. Without it the service still starts (see `validate`)
but rejects every request, so it is never reachable unauthenticated.
"""

import logging
import os


def _int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _bool(name, default):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # -- API surface (port and path are fixed by the FutureCalc contract) ---- #
    PORT = _int("PORT", 5005)
    API_KEY = os.environ.get("API_KEY", "")

    # -- capacity ----------------------------------------------------------- #
    # Detection is CPU-heavy (OCR + geometry), so concurrency is deliberately
    # small.  Work past this queues; past the queue the service answers 429,
    # which is the contract's "rate limit exceeded".
    WORKERS = _int("WORKERS", 2)
    QUEUE_LIMIT = _int("QUEUE_LIMIT", 8)
    JOB_TIMEOUT = _int("JOB_TIMEOUT", 600)          # seconds

    # -- input limits ------------------------------------------------------- #
    MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_BYTES", 64 * 1024 * 1024)
    MAX_IMAGE_PIXELS = _int("MAX_IMAGE_PIXELS", 80_000_000)

    # -- callback ----------------------------------------------------------- #
    CALLBACK_TIMEOUT = _int("CALLBACK_TIMEOUT", 30)
    CALLBACK_RETRIES = _int("CALLBACK_RETRIES", 3)
    CALLBACK_BACKOFF = _int("CALLBACK_BACKOFF", 2)  # seconds, doubled each try

    # -- output shaping ----------------------------------------------------- #
    # The RFP's examples all show a bare system code ("VV", "KV", "S") while
    # our own codes carry the system index ("VV1", "VS1", "S2").  Section 6.3,
    # which would list the accepted codes, is missing from the document — so
    # this follows the examples by default and can be turned off in one place
    # once the real list is known.
    STRIP_SYSTEM_INDEX = _bool("STRIP_SYSTEM_INDEX", True)
    # Unclassified runs still carry real length, so they are reported with an
    # explicit installationType rather than silently dropped.
    INCLUDE_UNCLASSIFIED = _bool("INCLUDE_UNCLASSIFIED", True)
    UNCLASSIFIED_INSTALLATION_TYPE = os.environ.get(
        "UNCLASSIFIED_INSTALLATION_TYPE", "UNKNOWN")
    # Vertices closer together than this (in output pixels) collapse to one
    # node, keeping payloads reasonable without moving the geometry visibly.
    SIMPLIFY_TOLERANCE = float(os.environ.get("SIMPLIFY_TOLERANCE", "0.75"))

    @classmethod
    def configured(cls):
        """Is there a key to check requests against?"""
        return bool(cls.API_KEY)

    @classmethod
    def validate(cls):
        """Report configuration problems without refusing to boot.

        Crashing on a missing API_KEY reads well as "fail closed", but on a
        platform that deploys from a git push it fails in the wrong place:
        Cloud Run reports the container as having "failed to start and listen
        on the port", which points at the port rather than the key, and the
        rollout fails. So the service starts, answers /health saying it is
        unconfigured, and REJECTS every API request with 503 until a key is
        set — which is equally closed and far easier to diagnose.
        """
        if not cls.configured():
            logging.getLogger("pipe-detect").error(
                "API_KEY is not set. The service is running but will reject "
                "every request with 503 until it is. Set API_KEY on the "
                "service (Cloud Run: --set-secrets API_KEY=...:latest).")
        return cls
