"""Mängdarens egna streck mot läsningens rör, sträcka för sträcka.

En markerad ritning (`marked.pdf`) bär mängdarens mätlinjer som PDF-annoteringar: ämnet är beteckningen,
innehållet längden i meter och punkterna själva geometrin. Det gör en annan sorts jämförelse möjlig än
`facit_metrics.py` gör - den jämför summor per beteckning, den här jämför *var på ritningen* metrarna ligger.

    python3 engine/tools/markup_metrics.py A C D E

Varje mätlinje provpunktas med jämna mellanrum, och för varje provpunkt frågas vad läsningen äger inom
toleransen. Svaret blir tre tal per beteckning: metrar vi äger under *samma* namn, under ett *annat* namn, och
metrar vi inte äger alls. Det skiljer två fel åt som summorna blandar ihop - att tappa ett rör och att kalla
det något annat - och det andra är det som dominerar.

Sidrotationen är inte en detalj. Annoteringarnas punkter står i sidans oroterade rum medan läsningens geometri
ligger i det visade. Tre av fyra provblad är ritade stående och visas liggande, och utan sidans rotationsmatris
hamnar mängdarens streck någon annanstans än rören - första körningen påstod att nittio procent av mätningen
låg utanför ägandet, vilket var verktygets fel och inte läsningens.

Aldrig importerat av motorn: det här läser referensmaterial och hör till granskningen, som facit_metrics.py.
"""
from __future__ import annotations

import collections
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ""))

import pymupdf  # noqa: E402

from vvs_engine.geometry.core import GridIndex  # noqa: E402
from vvs_engine.pdf.extract import extract_document  # noqa: E402
from vvs_engine.pipeline import analyze_page  # noqa: E402

DATA = "/home/user/vvs5/data"
TOL = 4.0          # pt: mängdaren drar sitt streck ovanpå röret
STEP = 3.0         # pt mellan provpunkterna längs mätlinjen
NOT_A_RUN = ("markera", "markering")     # ämnen som är överstrykning, inte en mätsträcka


def sheet_paths(tag: str) -> tuple[str, str] | None:
    """Den markerade och den rena ritningen för ett blad, i vilken av korpusens två kataloglägen den än ligger."""
    for marked, clean in ((f"{DATA}/validation_{tag}/marked.pdf", f"{DATA}/validation_{tag}/clean.pdf"),
                          (f"{DATA}/validation_W/{tag}/marked.pdf", f"{DATA}/validation_W/{tag}/clean.pdf"),
                          (f"{DATA}/validation_set3/{tag}/marked.pdf", f"{DATA}/validation_set3/{tag}/clean.pdf")):
        if os.path.isfile(marked) and os.path.isfile(clean):
            return marked, clean
    return None


def measured_runs(path: str) -> list[dict]:
    """Mängdarens mätlinjer: beteckning, uttalad längd och sträckan i visat sidrum."""
    doc = pymupdf.open(path)
    page = doc[0]
    rot = page.rotation_matrix
    out: list[dict] = []
    for a in page.annots():
        if a.type[1] != "PolyLine":
            continue
        subject = (a.info.get("subject") or "").strip()
        if not subject or subject.lower() in NOT_A_RUN:
            continue
        pts = [tuple(pymupdf.Point(x, y) * rot) for x, y in (a.vertices or [])]
        if len(pts) < 2:
            continue
        m = re.search(r"([\d,.]+)\s*m", a.info.get("content") or "")
        out.append({"designation": subject, "points": pts,
                    "stated_m": float(m.group(1).replace(",", ".")) if m else None})
    doc.close()
    return out


def owned_segments(pa) -> list[tuple]:
    """Läsningens ägda geometri som (a, b, beteckning)."""
    segs = []
    for pipe in pa.ownership.pipes:
        if pipe.identity is None:
            continue
        for poly in pipe.points:
            for i in range(len(poly) - 1):
                segs.append((poly[i], poly[i + 1], pipe.identity.display))
    return segs


def compare(tag: str) -> dict:
    marked, clean = sheet_paths(tag)
    their = measured_runs(marked)
    pa = analyze_page(extract_document(clean).pages[0])
    mpp = pa.scale.meters_per_pt or 0.0
    segs = owned_segments(pa)
    idx = GridIndex(cell=20.0)
    for i, (a, b, _) in enumerate(segs):
        idx.insert(i, (min(a[0], b[0]) - 1, min(a[1], b[1]) - 1, max(a[0], b[0]) + 1, max(a[1], b[1]) + 1))

    def owner_at(x: float, y: float) -> str | None:
        best = None
        for j in idx.query((x - TOL, y - TOL, x + TOL, y + TOL)):
            a, b, name = segs[j]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
            d = math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy))
            if d <= TOL and (best is None or d < best[0]):
                best = (d, name)
        return best[1] if best else None

    per: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    total: collections.Counter = collections.Counter()
    for run in their:
        for (x0, y0), (x1, y1) in zip(run["points"], run["points"][1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(L / STEP))
            for k in range(n):
                t = (k + 0.5) / n
                who = owner_at(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
                per[run["designation"]][who or "—"] += (L / n) * mpp
            total[run["designation"]] += L * mpp
    return {"tag": tag, "runs": len(their), "meters_per_pt": mpp, "per": per, "total": total}


def render(r: dict) -> None:
    per, total = r["per"], r["total"]
    print(f"=== {r['tag']}: {r['runs']} mätlinjer, skala {r['meters_per_pt']:.6f} m/pt")
    print(f"{'mängdarens beteckning':22s} {'deras m':>8s} {'samma':>8s} {'annan':>8s} {'inget':>8s}   vad vi kallade det")
    for name in sorted(per):
        c = per[name]
        same, none = c.get(name, 0.0), c.get("—", 0.0)
        other = sum(v for k, v in c.items() if k not in (name, "—"))
        says = ", ".join(f"{k} {v:.1f}" for k, v in sorted(c.items(), key=lambda kv: -kv[1])
                         if k not in (name, "—"))[:60]
        print(f"{name:22s} {total[name]:8.1f} {same:8.1f} {other:8.1f} {none:8.1f}   {says}")
    S = sum(total.values()) or 1.0
    SA = sum(per[n].get(n, 0.0) for n in per)
    NO = sum(per[n].get("—", 0.0) for n in per)
    print(f"{'SUMMA':22s} {S:8.1f} {SA:8.1f} {S - SA - NO:8.1f} {NO:8.1f}"
          f"   ({100 * SA / S:.0f} % samma namn, {100 * NO / S:.0f} % inget ägande)")


def all_marked() -> list[str]:
    tags = [t.split("_", 1)[1] for t in os.listdir(DATA)
            if t.startswith("validation_") and os.path.isfile(f"{DATA}/{t}/marked.pdf")]
    for sub in ("validation_W", "validation_set3"):
        if os.path.isdir(f"{DATA}/{sub}"):
            tags += [t for t in os.listdir(f"{DATA}/{sub}") if os.path.isfile(f"{DATA}/{sub}/{t}/marked.pdf")]
    return sorted(set(tags))


def main(tags: list[str]) -> None:
    if not tags:
        tags = all_marked()
        print(f"blad med markerad ritning: {', '.join(tags) or 'inga'}\n")
    for tag in tags:
        if sheet_paths(tag) is None:
            print(f"{tag}: ingen markerad ritning"); continue
        render(compare(tag))


if __name__ == "__main__":
    main(sys.argv[1:])
