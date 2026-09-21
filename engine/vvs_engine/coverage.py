"""Läsningens giltighet: åtta mått på hur mycket av bladet läsningen nådde, och ett omdöme.

Konserveringen (reconcile.py) säger att ingen meter dubbelräknas och att RAW = CONFIRMED + AMBIGUOUS + UNOWNED.
Det är nödvändigt och räcker inte: en läsning som accepterade ingen rörgeometri alls konserverar perfekt.
Giltigheten är den andra frågan - nådde läsningen bladet? - och den ställs i åtta mått som var och en har en
tydlig riktning, och ett omdöme som är strängare ju mer läsningen missat:

  VALID      läsningen nådde bladet: namnen fick meter, bläcket fick ägare, rören slutar med skäl
  DEGRADED   läsningen är giltig men glest: en väsentlig del av det bladet skriver fick inga meter
  INVALID    något som aldrig får hända hände: konserveringen bröts, ett rör slutar tyst, ingen skala,
             eller bladet namnger rör och läsningen mätte inget

Måtten hämtas ur det läsningen redan vet; inget här läser referensen, och inget här flyttar en meter.
"""
from __future__ import annotations

from typing import Any

MEASURES = (
    "DESIGNATIONS_READ",             # antal beteckningar bladet skriver och läsningen läste
    "DESIGNATIONS_WITH_DN_SHARE",    # andel av dem med en dimension
    "ATTACHMENT_VERIFIED_SHARE",     # andel etiketter vars hänvisning nådde ett rör
    "NAMES_WITH_METRES_SHARE",       # andel rörnamn på bladet som fick meter
    "INK_CONFIRMED_SHARE",           # andel av rörpennornas bläck som ägs
    "INK_AMBIGUOUS_SHARE",           # andel som lämnats öppet
    "INK_UNOWNED_SHARE",             # andel ingen etikett nådde
    "FRONTIER_LOSSY_SHARE",          # andel av rörens kanter där meter sannolikt tappas
)

# under de här börjar en läsning vara gles snarare än giltig
DEGRADED_NAMES_WITH_METRES = 0.5
DEGRADED_INK_CONFIRMED = 0.3
DEGRADED_LOSSY_FRONTIERS = 0.35


def coverage_validity(cov: dict[str, Any], anchors: list, reconciliation: dict | None, scale_state: str | None,
                      n_pipes: int) -> dict[str, Any]:
    """Åtta mått och ett omdöme, ur läsningens täckning (pipeline.reading_coverage), ankarna, konserveringen,
    skalans tillstånd och antalet fysiska rör."""
    labels = len(anchors)
    verified = sum(1 for a in anchors if getattr(a, "state", "") == "VERIFIED_PIPE_ATTACHMENT")
    names = cov.get("pipe_names") or 0
    got = cov.get("pipe_names_with_metres") or 0
    # Andelarna räknas på bläcket, inte på metrarna: ett blad utan fastställd skala har inga meter alls, och
    # då blev varje andel None fast den var fullt räknelig. Punkterna finns oavsett vad skalan säger.
    drawn = float(cov.get("drawn_pt") if cov.get("drawn_pt") is not None else (cov.get("drawn_m") or 0.0))
    conf = float(cov.get("confirmed_pt") if cov.get("confirmed_pt") is not None else (cov.get("confirmed_m") or 0.0))
    amb = float(cov.get("ambiguous_pt") if cov.get("ambiguous_pt") is not None else (cov.get("ambiguous_m") or 0.0))
    un = float(cov.get("unowned_pt") if cov.get("unowned_pt") is not None else (cov.get("unowned_m") or 0.0))
    fr = cov.get("frontiers") or {}
    n_fr = fr.get("frontiers") or 0
    lossy = fr.get("lossy_boundaries") or 0
    with_dn = cov.get("designations_with_dn")
    n_des = cov.get("designations_read")
    measures = {
        "DESIGNATIONS_READ": n_des if n_des is not None else names,
        "DESIGNATIONS_WITH_DN_SHARE": (round(with_dn / n_des, 3) if n_des else None) if with_dn is not None else None,
        "ATTACHMENT_VERIFIED_SHARE": round(verified / labels, 3) if labels else None,
        "NAMES_WITH_METRES_SHARE": round(got / names, 3) if names else None,
        "INK_CONFIRMED_SHARE": round(conf / drawn, 3) if drawn else None,
        "INK_AMBIGUOUS_SHARE": round(amb / drawn, 3) if drawn else None,
        "INK_UNOWNED_SHARE": round(un / drawn, 3) if drawn else None,
        "FRONTIER_LOSSY_SHARE": round(lossy / n_fr, 3) if n_fr else None,
    }
    reasons: list[str] = []
    verdict = "VALID"
    if reconciliation is not None and reconciliation.get("state") != "VALID":
        verdict = "INVALID"; reasons.append("GEOMETRY_CONSERVATION_BROKEN")
    if fr and fr.get("silent_pipes"):
        verdict = "INVALID"; reasons.append(f"SILENT_PIPES:{len(fr['silent_pipes'])}")
    if scale_state in (None, "NONE"):
        verdict = "INVALID"; reasons.append("NO_SCALE")
    if names and got == 0 and n_pipes == 0:
        verdict = "INVALID"; reasons.append("SHEET_NAMES_PIPES_BUT_NOTHING_WAS_MEASURED")
    elif not names and not n_pipes:
        verdict = "INVALID"; reasons.append("NO_READABLE_PIPE_LABELS")
    if verdict == "VALID":
        if measures["NAMES_WITH_METRES_SHARE"] is not None and measures["NAMES_WITH_METRES_SHARE"] < DEGRADED_NAMES_WITH_METRES:
            verdict = "DEGRADED"; reasons.append("MOST_NAMES_WITHOUT_METRES")
        if measures["INK_CONFIRMED_SHARE"] is not None and measures["INK_CONFIRMED_SHARE"] < DEGRADED_INK_CONFIRMED and drawn > 0:
            verdict = "DEGRADED"; reasons.append("MOST_PIPE_INK_UNOWNED")
        if measures["FRONTIER_LOSSY_SHARE"] is not None and measures["FRONTIER_LOSSY_SHARE"] > DEGRADED_LOSSY_FRONTIERS:
            verdict = "DEGRADED"; reasons.append("MANY_LOSSY_FRONTIERS")
        if scale_state in ("CONFLICT", "SCALE_UNSETTLED"):
            verdict = "DEGRADED"; reasons.append("SCALE_UNSETTLED")
    return {"verdict": verdict, "reasons": reasons, "measures": measures,
            "thresholds": {"names_with_metres": DEGRADED_NAMES_WITH_METRES, "ink_confirmed": DEGRADED_INK_CONFIRMED,
                           "lossy_frontiers": DEGRADED_LOSSY_FRONTIERS},
            "geometry_conservation": (reconciliation or {}).get("state"),
            "accuracy_verified": False,
            "note": "konservering säger att inget dubbelräknas; giltighet säger om läsningen nådde bladet - två frågor"}
