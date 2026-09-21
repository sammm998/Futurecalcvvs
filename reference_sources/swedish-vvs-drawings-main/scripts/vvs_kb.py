"""Shared loader for the VVS knowledge base JSON bundled with this skill."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Fields that hold a code, per category. Sensors carry two.
CODE_FIELDS = ("code", "sensor_code", "instrument_code")


@lru_cache(maxsize=None)
def load_all() -> dict[str, dict]:
    """Every category keyed by its `category` field (falling back to filename)."""
    out: dict[str, dict] = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        out[doc.get("category", path.stem)] = doc
    return out


@lru_cache(maxsize=None)
def systems() -> dict[str, dict]:
    """Systembeteckningar keyed by code, e.g. systems()['VS']."""
    doc = json.loads((DATA_DIR / "system_designations.json").read_text(encoding="utf-8"))
    return {e["code"]: e for e in doc["entries"]}
