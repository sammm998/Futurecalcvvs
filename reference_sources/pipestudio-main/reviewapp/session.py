"""Session: owns the Document, persistence, autosave and exports."""

import json
import os
import threading
import time

import cv2
import fitz
import numpy as np
from shapely.geometry import Polygon

import pipe_seg as ps
import pipe_types as pt

from .assignment import (looks_classified, reassign, repair_base,
                         resolve_join_labels)
from .models import Document, UNKNOWN
from .pipeline import Extraction, link_joins_to_pipes

SESSION_DIR = "review"
OUTPUT_DIR = "output"


class Session:
    def __init__(self, pdf_path):
        self.extraction = Extraction(pdf_path)
        self.stem = self.extraction.stem
        self.path = os.path.join(SESSION_DIR, f"{self.stem}.session.json")
        self.doc: Document = None
        self.lock = threading.RLock()
        self.progress = {"stage": "starting", "value": 0.0, "ready": False}
        self._autosave_at = 0.0

    # -- lifecycle --------------------------------------------------------- #
    def load(self, force_reprocess=False):
        with self.lock:
            if not force_reprocess and os.path.exists(self.path):
                try:
                    with open(self.path) as f:
                        data = json.load(f)
                    self.doc = Document.from_json(data)
                    self.doc.pdf_path = self.extraction.pdf_path
                    # a session written before classification became
                    # replace-only can hold an already-split `base_pipes`
                    # (needs rebuilding) and/or a missing/stale `classified`
                    # flag while `pipes` already holds a classified result
                    # (base_pipes itself is fine, just the flag is wrong) —
                    # both are checked, independently, every load
                    repaired = repair_base(self.doc, ps.log)
                    needs_save = repaired
                    # sessions saved before the line pool existed can still be
                    # resolved against the drawing by re-tracing it
                    if not self.doc.line_pool:
                        self.doc.line_pool = self.extraction.trace_line_pool()
                        if self.doc.line_pool:
                            ps.log(f"review: traced {len(self.doc.line_pool)} "
                                   f"connection lines from the drawing")
                            needs_save = True
                    if resolve_join_labels(self.doc, ps.log):
                        needs_save = True
                    if repaired or looks_classified(self.doc):
                        if not self.doc.classified:
                            ps.log("review: recovered missing 'classified' flag")
                            needs_save = True
                        self.doc.classified = True
                    if needs_save:
                        self.save()   # persist the repair so it only runs once
                    self.extraction.render_background(SESSION_DIR)
                    self._set_progress("Restored saved review", 1.0, True)
                    ps.log(f"review: restored session {self.path}")
                    return self.doc
                except Exception as exc:
                    # Re-processing REPLACES the session, so a review that took
                    # real work to build must never be thrown away just because
                    # the restore path hit a bug.  Keep it aside first.
                    keep = f"{self.path}.broken-{int(time.time())}.json"
                    try:
                        os.replace(self.path, keep)
                        ps.log(f"review: could not restore session ({exc}); "
                               f"YOUR REVIEW WAS KEPT AT {keep} — re-processing")
                    except OSError:
                        ps.log(f"review: could not restore session ({exc}); "
                               f"re-processing")
            self.doc = self.extraction.run(
                progress=lambda s, v: self._set_progress(s, v, False))
            self._set_progress("Ready", 1.0, True)
            self.save()
            return self.doc

    def _set_progress(self, stage, value, ready):
        self.progress = {"stage": stage, "value": value, "ready": ready}

    # -- persistence ------------------------------------------------------- #
    def save(self):
        with self.lock:
            os.makedirs(SESSION_DIR, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.doc.to_json(), f)
            os.replace(tmp, self.path)
            self.doc.saved = True
            return self.path

    def autosave(self, min_interval=4.0):
        now = time.time()
        if now - self._autosave_at < min_interval:
            return None
        self._autosave_at = now
        return self.save()

    def reset(self):
        with self.lock:
            if os.path.exists(self.path):
                os.remove(self.path)
            return self.load(force_reprocess=True)

    # -- document mutation from the client --------------------------------- #
    def replace_document(self, payload):
        """Client sends the full editable state; server keeps immutable fields."""
        with self.lock:
            doc = Document.from_json({
                **payload,
                "leaders": payload.get("leaders", self.doc.to_json()["leaders"]),
                "stem": self.stem,
                "pdf_path": self.extraction.pdf_path,
                "page": self.doc.page,
                "scale": self.doc.scale,
                "wall": self.doc.wall,
            })
            doc.saved = False
            self.doc = doc
            return doc

    # -- stages ------------------------------------------------------------ #
    def run_assignment(self):
        with self.lock:
            summary = reassign(self.doc, log=ps.log)
            self.save()
            return summary

    # -- exports ----------------------------------------------------------- #
    def export_json(self):
        with self.lock:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            s = ps.CONFIG["render_dpi"] / 72.0
            records = []
            for i, p in enumerate(self.doc.active_pipes(), start=1):
                ring = [[round(x * s, 1), round(y * s, 1)] for x, y in p.polygon]
                records.append({"id": i, "polygon": ring, "type": p.type})
            path = os.path.join(OUTPUT_DIR, f"{self.stem}.json")
            with open(path, "w") as f:
                json.dump(records, f)
            return {"path": path, "pipes": len(records)}

    def export_png(self):
        """Painted PNG + per-class overview, using the current edited state."""
        with self.lock:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            page = self.extraction.ensure_page()
            typed = []
            for p in self.doc.active_pipes():
                if len(p.polygon) < 4:
                    continue
                poly = Polygon(p.polygon)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_empty:
                    continue
                if poly.geom_type == "MultiPolygon":
                    poly = max(poly.geoms, key=lambda g: g.area)
                typed.append((poly, p.type))

            ps.CONFIG["out_painted"] = os.path.join(OUTPUT_DIR, f"{self.stem}.png")
            ps.CONFIG["out_json"] = os.path.join(OUTPUT_DIR, f"{self.stem}.json")
            pt.save_typed_outputs(page, typed)

            labels = [pt.Label(l.code, fitz.Rect(*l.rect), fitz.Rect(*l.rect),
                               l.conf)
                      for l in self.doc.active_labels()]
            leader_by_join = {e.joinId: e for e in self.doc.active_leaders()
                              if e.joinId}
            att = []
            for j in self.doc.active_joins():
                if not j.code:
                    continue
                e = leader_by_join.get(j.id)
                path = [(tuple(a), tuple(b)) for a, b in (e.path if e else [])]
                att.append((j.code, tuple(j.anchor or j.point),
                            tuple(j.point), path))
            overview = os.path.join(OUTPUT_DIR, f"{self.stem}_typed.png")
            pt.save_typed_overview(page, typed, labels, att, overview)
            return {"paths": [ps.CONFIG["out_painted"], ps.CONFIG["out_json"],
                              overview], "pipes": len(typed)}

    # -- payload ----------------------------------------------------------- #
    def payload(self):
        with self.lock:
            d = self.doc.to_json()
            d["background"] = f"/api/background.png?v={self.stem}"
            d["progress"] = self.progress
            return d
