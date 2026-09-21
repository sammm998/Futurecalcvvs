"""Review agents.

The measuring pipeline states what it found. These agents ask, independently and after the fact, whether that
result is believable: is the drawn pipe accounted for, do the designations the page carries all appear in the
takeoff, are the sizes and lengths physically plausible, does the network hang together, is the scale sound.

Every agent returns findings with a severity, a location to jump to and the numbers behind the verdict, so the
operator sees where to look rather than a score. Nothing here changes the measurement; a review that could edit
the result would only hide the disagreement it exists to surface.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..semantics.grammar import NOMINAL_SIZES, is_code_like

from .. import rules as _rules


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)



@dataclass
class Finding:
    agent: str
    severity: str                 # 'INFO' | 'WARN' | 'ERROR'
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)
    bbox: list[float] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"agent": self.agent, "severity": self.severity, "code": self.code, "message": self.message,
                "detail": self.detail, "bbox": self.bbox}


OCR_REVIEW_BUDGET_S = 30.0   # a sanity check may not cost more than the reading it is checking
# The cross-check asks whether OCR sees a designation-shaped word where the vector reader has nothing. That is a
# question about presence, not about shape, and half the resolution answers it: measured on the reference sheet,
# 150 dpi reads 685 words to 300 dpi's 863 at the same confidence, in 12 s instead of 32.
OCR_REVIEW_DPI = (150, 100)


def run_review(pa, ocr: bool = True, progress=None) -> dict[str, Any]:
    """Run every agent over a finished PageAnalysis. `ocr` enables the optional cross-check agent."""
    findings: list[Finding] = []
    agents = [_scale_agent, _coverage_agent, _plausibility_agent, _topology_agent, _designation_agent]
    ran = []
    for fn in agents:
        if progress:
            progress(fn.__name__.strip("_"))
        findings.extend(fn(pa))
        ran.append(fn.__name__.strip("_"))
    if ocr:
        if progress:
            progress("ocr")
        f, state = _ocr_crosscheck_agent(pa, progress=progress)
        findings.extend(f)
        ran.append(f"ocr_crosscheck({state})")
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    findings.sort(key=lambda x: (order.get(x.severity, 9), x.agent, x.code))
    worst = min((order.get(f.severity, 9) for f in findings), default=2)
    return {"state": ["ERROR", "WARN", "OK"][min(worst, 2)] if findings else "OK",
            "agents": ran, "n_findings": len(findings), "findings": [f.as_dict() for f in findings]}


# ---------------------------------------------------------------- agents

def _scale_agent(pa) -> list[Finding]:
    s = pa.scale
    if s.meters_per_pt is None:
        return [Finding("scale", "ERROR", "no_scale",
                        "Ingen skala kunde läsas ur ritningen, så inga längder kan anges.", {"reason": s.reason})]
    out = []
    ratio = s.meters_per_pt * 1000.0 / (25.4 / 72.0)
    if s.state not in ("VERIFIED",):
        out.append(Finding("scale", "WARN", f"scale_{s.state.lower()}",
                           f"Skalan 1:{ratio:.0f} vilar på en enda källa ({s.state}); ingen skalstock bekräftar den.",
                           {"state": s.state, "reason": s.reason}))
    if not (10 <= ratio <= 2000):
        out.append(Finding("scale", "WARN", "scale_unusual", f"Skalan 1:{ratio:.0f} ligger utanför det vanliga intervallet.",
                           {"implied_ratio": round(ratio, 1)}))
    return out


def _coverage_agent(pa) -> list[Finding]:
    """How much of the geometry the pipe families hold is actually accounted for."""
    mpp = pa.scale.meters_per_pt or 0.0
    total = owned = ambiguous = 0.0
    for fk, g in pa.graphs.items():
        sts = pa.ownership.prim_states.get(fk, {})
        for pid, prim in g.prims.items():
            L = prim.seg.length
            total += L
            st = sts.get(pid)
            if st is None:
                continue
            if st.state == "CONFIRMED":
                owned += L
            elif st.state == "AMBIGUOUS":
                ambiguous += L
    if total <= 0:
        return [Finding("coverage", "ERROR", "no_pipe_geometry",
                        "Ingen vektorfamilj godtogs som rör, så ingenting kunde mängdas.", {})]
    share = owned / total
    out = [Finding("coverage", "INFO", "owned_share",
                   f"{share * 100:.1f} % av den godtagna rörgeometrin är ägd av en beteckning "
                   f"({owned * mpp:.1f} m av {total * mpp:.1f} m).",
                   {"owned_m": round(owned * mpp, 2), "total_m": round(total * mpp, 2),
                    "ambiguous_m": round(ambiguous * mpp, 2), "share": round(share, 4)})]
    if share < 0.9:
        out.append(Finding("coverage", "WARN", "unowned_pipe_geometry",
                           f"{(total - owned - ambiguous) * mpp:.1f} m ritat rör i de godtagna familjerna saknar ägare "
                           f"och ingår inte i mängden.",
                           {"unowned_m": round((total - owned - ambiguous) * mpp, 2)}))
    return out


def _plausibility_agent(pa) -> list[Finding]:
    """Sizes against the nominal series, lengths against the drawing's own extent."""
    out: list[Finding] = []
    mpp = pa.scale.meters_per_pt or 0.0
    page_diag = math.hypot(pa.page.info.width, pa.page.info.height) * mpp
    for r in pa.quantities:
        dn = r.get("dn")
        if dn is not None and dn not in NOMINAL_SIZES:
            out.append(Finding("plausibility", "WARN", "dn_outside_nominal_series",
                               f"{r['designation']} har dimension {dn}, som inte finns i standardserien.",
                               {"designation": r["designation"], "dn": dn}))
        if dn is None and r.get("physical_pipe_count", 0) > 0:
            out.append(Finding("plausibility", "WARN", "missing_dn",
                               f"{r['designation']} mängdas utan dimension; ritningen anger ingen som kunde läsas.",
                               {"designation": r["designation"], "m": round(r["confirmed_horizontal_m"], 2)}))
        if page_diag and r["confirmed_horizontal_m"] > 3 * page_diag:
            out.append(Finding("plausibility", "WARN", "length_exceeds_drawing",
                               f"{r['designation']} mängdas till {r['confirmed_horizontal_m']:.1f} m, mer än tre gånger "
                               f"ritningens diagonal ({page_diag:.1f} m).",
                               {"designation": r["designation"], "m": round(r["confirmed_horizontal_m"], 2)}))
    return out


def _topology_agent(pa) -> list[Finding]:
    """A run that ends in mid air, with no fitting, symbol or junction, is usually a break in the reading."""
    out: list[Finding] = []
    per_family: dict[str, int] = {}
    for fk, g in pa.graphs.items():
        sts = pa.ownership.prim_states.get(fk, {})
        loose = sum(1 for n in g.nodes.values()
                    if n.degree == 1 and (sts.get(n.prims[0]) is not None and sts[n.prims[0]].state == "CONFIRMED"))
        if loose:
            per_family[fk] = per_family.get(fk, 0) + loose
    if per_family:
        out.append(Finding("topology", "INFO", "free_ends",
                           f"{sum(per_family.values())} fria rörändar totalt (anslutningar, brunnar, stigare eller "
                           f"avbrott i läsningen).",
                           {"per_family": {k: v for k, v in sorted(per_family.items(), key=lambda kv: -kv[1])}}))
    tot_amb = sum(r["ambiguous_m"] for r in pa.quantities)
    if tot_amb > 0.5:
        out.append(Finding("topology", "WARN", "ambiguous_runs",
                           f"{tot_amb:.1f} m ligger mellan två möjliga beteckningar och räknas inte som bekräftat.",
                           {"ambiguous_m": round(tot_amb, 2)}))
    return out


def _designation_agent(pa) -> list[Finding]:
    """Designations the page carries that never reached a pipe."""
    out: list[Finding] = []
    attached = {a.designation_id for a in pa.anchors if a.state == "VERIFIED_PIPE_ATTACHMENT"}
    orphans = [d for d in pa.designations if d.did not in attached and is_code_like(d.text) and d.dn is not None]
    if orphans:
        out.append(Finding("designations", "WARN", "labels_without_pipe",
                           f"{len(orphans)} beteckningar med dimension nådde aldrig ett rör och ingår inte i mängden.",
                           {"examples": sorted({d.text for d in orphans})[:8], "count": len(orphans)},
                           bbox=[round(v, 1) for v in orphans[0].bbox]))
    unknown = [d for d in pa.designations if d.unknown_chars]
    if unknown:
        out.append(Finding("designations", "WARN", "unreadable_characters",
                           f"{len(unknown)} beteckningar innehåller tecken som inte kunde läsas.",
                           {"examples": sorted({d.text for d in unknown})[:8]},
                           bbox=[round(v, 1) for v in unknown[0].bbox]))
    return out


def _ocr_crosscheck_agent(pa, progress=None) -> tuple[list[Finding], str]:
    """Read the rendered page with OCR and compare its designation-like words with the vector reading.

    The vector reading is authoritative - it reads the drawing's own geometry. OCR is a second pair of eyes over
    the same page: a code-like word OCR sees where the vector reader has nothing is a place to look at.
    """
    try:
        from .ocr_check import ocr_words
    except Exception as e:                                    # pragma: no cover - optional dependency
        return [Finding("ocr_crosscheck", "INFO", "ocr_unavailable",
                        "OCR-kontrollen kördes inte (rapidocr-onnxruntime saknas i installationen).",
                        {"error": str(e)[:120]})], "unavailable"
    # A whole A1 sheet rendered at 300 dpi and read in tiles is the heaviest thing this review does, and in a
    # small container it is what runs out of memory first. Rather than reporting a blank failure, drop the
    # resolution and read the page again: a coarser second pair of eyes still catches a label sitting where the
    # vector reading has nothing, and the finding says which resolution it managed.
    # This is a second pair of eyes over a reading that is already finished, so it is bounded: it may not cost
    # more than the reading it checks. Rendering a whole A1 at 300 dpi and recognising every tile took minutes on
    # a small machine, and a check nobody can wait for is a check nobody runs.
    words = None
    dpi_used = 0
    first: Exception | None = None
    for dpi in OCR_REVIEW_DPI:
        try:
            words = ocr_words(pa.page, dpi=dpi, budget_s=_R("review.agents.OCR_REVIEW_BUDGET_S", OCR_REVIEW_BUDGET_S),
                              progress=(lambda t: progress(f"ocr {t}")) if progress else None)
            dpi_used = dpi
            break
        except Exception as e:                                # pragma: no cover - runtime failure
            if first is None:
                first = e
    if words is None:
        why = str(first)[:160] or first.__class__.__name__
        return [Finding("ocr_crosscheck", "INFO", "ocr_failed",
                        f"Synagenten kunde inte läsa sidan: {why}",
                        {"error": str(first)[:200], "type": type(first).__name__})], "failed"
    from ..semantics.grammar import compress_pattern
    ours = {d.text.upper() for d in pa.designations}
    ours_norm = {_norm(t) for t in ours}
    # the patterns this drawing writes the designations that actually reached a pipe in; legend codes and grid
    # bubbles share the page but not the pattern of a pipe label
    attached_ids = {a.designation_id for a in pa.anchors if a.state == "VERIFIED_PIPE_ATTACHMENT"}
    pat_count: dict[str, int] = {}
    for d in pa.designations:
        if d.did in attached_ids:
            pat_count[d.pattern] = pat_count.get(d.pattern, 0) + 1
    patterns = {p for p, n in pat_count.items() if n >= 2}
    read_boxes = [ln.bbox for ln in pa.lines]
    missed = []
    for w, box, conf in words:
        t = w.upper()
        if conf < 0.6 or not is_code_like(t) or compress_pattern(t) not in patterns:
            continue
        if _norm(t) in ours_norm or any(_close(_norm(t), _norm(o)) for o in ours):
            continue
        if any(_overlaps(box, b) for b in read_boxes):
            continue          # the vector reader has text here: a reading difference, not a missed label
        missed.append((t, box, conf))
    coarse = " vid nedsatt upplösning, sedan den vanliga inte gick att köra" if dpi_used < OCR_REVIEW_DPI[0] else ""
    out = [Finding("ocr_crosscheck", "INFO", "ocr_ran",
                   f"Synagenten läste {len(words)} ord över samma sida som oberoende jämförelse{coarse}; "
                   f"{len(pa.designations)} beteckningar lästes ur vektorkoden.",
                   {"ocr_words": len(words), "vector_designations": len(pa.designations), "dpi": dpi_used})]
    if missed:
        out.append(Finding("ocr_crosscheck", "WARN", "ocr_sees_extra_codes",
                           f"Synagenten ser {len(missed)} beteckningar på platser där vektorläsningen inte har någon text alls.",
                           {"examples": [m[0] for m in missed[:8]], "count": len(missed)},
                           bbox=[round(v, 1) for v in missed[0][1]]))
    return out, "ok"


def _overlaps(a, b) -> bool:
    return not (a[2] < b[0] - 1 or b[2] < a[0] - 1 or a[3] < b[1] - 1 or b[3] < a[1] - 1)


def _norm(t: str) -> str:
    """Fold the glyph pairs OCR and stroke fonts confuse, so a cross-check does not report font noise."""
    table = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2", "G": "6", "|": "1", " ": ""})
    return t.upper().translate(table)


def _close(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1 or not a or not b:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    long, short = (a, b) if len(a) > len(b) else (b, a)
    return any(long[:i] + long[i + 1:] == short for i in range(len(long)))
