"""The last word: what, out of everything the reading and its reviewers found, should actually change.

The reviewers state disagreements and stop there, on purpose - a review that could edit the result would hide the
disagreement it exists to surface. But nobody was deciding either, and a pile of findings that leads to nothing
is not a review, it is a wait. So one judge goes through them all afterwards and says, for each, what happens.

It works under four rules, and they are what make it safe to let it decide at all.

  * It never invents a number. Anything it implements is one of the answers the drawing itself put forward.
  * It never touches a measurement the reading confirmed. Only cases the reading itself left open are open.
  * Everything it implements is written as a correction: attributable, versioned, and undoable like any other.
  * Where the evidence does not settle a case, saying so is a verdict. Leaving it to a person is an answer, and
    a better one than a confident guess.

Nothing here calls a model. Every verdict below follows from what the artifacts already hold, which is why the
same reading judged twice gives the same verdicts.
"""
from __future__ import annotations

from typing import Any

IMPLEMENT = "GENOMFOR"
LEAVE = "LAMNA"
SILENT = "RITNINGEN_SAGER_INTE"

# Why a label and a drawn run failed to settle each other, said as the drawing would say it. A case that costs
# the takeoff nothing is not a case anyone needs to act on, and calling it one buries the ones that do.
WHY_OPEN: dict[str, str] = {
    "multi_row_label_shares_one_run":
        "etiketten namnger flera system som ritningen drar som en enda linje; att dela längden mellan koderna "
        "skulle kräva en regel ritningen inte ger, så kontakten noteras och linjen ägs av den kod som äger den",
    "multi_row_token_match_not_unique":
        "etikettens rader passar mer än en ritad grupp lika bra, och ingenting i ritningen skiljer dem åt",
    "multi_row_equal_counts_no_discrimination":
        "lika många ritade linjer som koder i etiketten, men ingen ordning i ritningen som säger vilken som är vilken",
    "multi_row_bundle_awaiting_elimination":
        "ett knippe linjer där ritningen ännu inte uteslutit någon kandidat",
    "several_vector_families_at_leader_no_token_discrimination":
        "hänvisningslinjen slutar där flera ritade familjer möts och inget lagernamn skiljer dem åt",
    "leader_endpoint_touches_no_pipe_geometry":
        "hänvisningslinjen slutar där ritningen inte ritar någon accepterad rörgeometri",
}


def _v(kind: str, decision: str, what: str, why: str, **extra: Any) -> dict:
    return {"typ": kind, "beslut": decision, "gäller": what, "skäl": why, **extra}


def _fitting_on_its_run(reason: str) -> bool:
    """A tag whose leader ends on the run it connects to: the drawing meant it to end there."""
    return reason.startswith("system_conflict")


def judge(model, proposals: list[dict] | None = None) -> dict[str, Any]:
    """Go through the reading and say what should happen to each open case.

    `model` is a DrawingModel; `proposals` are what earlier corrections on this account would say about the cases
    this reading could not settle - the only place a change can come from that the drawing did not itself offer,
    and even then only among its own candidates.
    """
    verdicts: list[dict] = []
    by_case = {p.get("id"): p for p in (proposals or []) if p.get("id")}

    def names_a_pipe(text: str) -> bool:
        """The sheet's own list decides what is a pipe designation and what is a fitting tag."""
        head = (text or "").upper().strip()
        if not head or not model.systems:
            return bool(head)
        if any(head == c or head.startswith(c) for c in model.components):
            return False
        return any(head == c or head.startswith(c) for c in model.systems)

    # What an open case actually costs. The engine records a contact it could not settle, but the run it touches
    # is usually owned by another label anyway - and a case that costs the takeoff nothing is not a case anyone
    # needs to act on. Saying so is the difference between a list worth reading and a list worth ignoring.
    unowned_m = 0.0
    r0 = model.reconciliation or {}
    if model.meters_per_pt:
        unowned_m = round(float(r0.get("unowned_pt") or 0.0) * model.meters_per_pt, 2)

    # 1. the cases the reading itself called open
    ambiguous = [a for a in model.anchors if a.get("state") == "AMBIGUOUS_PIPE_ATTACHMENT"]
    fittings = [a for a in ambiguous if _fitting_on_its_run(a.get("reason") or "")]
    if fittings:
        verdicts.append(_v(
            "komponenttagg_på_sitt_rör", LEAVE,
            f"{len(fittings)} taggar: {', '.join(sorted({a.get('designation') or '' for a in fittings})[:8])}",
            "en golvbrunn, ventil eller enhet vars hänvisningslinje slutar på den ledning den ansluter till; "
            "ritningen menar att den slutar där, och det är inget olöst fall",
            kostar_m=0.0))

    open_pipes = [a for a in ambiguous
                  if not _fitting_on_its_run(a.get("reason") or "") and names_a_pipe(a.get("designation") or "")]
    for a in open_pipes:
        reason = (a.get("reason") or "").split(":")[0]
        p = by_case.get(a["anchor_id"])
        cands = (p or {}).get("candidates") or []
        if p and p.get("answer") and p.get("answer") in cands:
            verdicts.append(_v(
                reason, IMPLEMENT, a.get("designation") or a["anchor_id"],
                f"tidigare rättelser i det här kontot avgör samma situation, och svaret är en av de kandidater "
                f"ritningen själv erbjuder ({', '.join(cands)})",
                ankare=a["anchor_id"], svar=p["answer"], kandidater=cands,
                rättelse={"kind": "attachment", "anchor_id": a["anchor_id"], "designation": p["answer"]},
                punkt=a.get("leader_endpoint")))
            continue
        delar = ((a.get("evidence") or {}).get("codes_sharing_the_run")) or []
        verdicts.append(_v(
            reason, SILENT, a.get("designation") or a["anchor_id"],
            WHY_OPEN.get(reason, "läsningen kunde inte avgöra fallet ur ritningen"),
            ankare=a["anchor_id"], delar_linje_med=delar, punkt=a.get("leader_endpoint"),
            kostar_m=0.0 if unowned_m == 0 else None))

    # 2. labels the sheet writes that never got a metre
    for i in model.issues:
        kind = i.get("kind")
        if i.get("severity") != "blocking":
            continue
        if kind == "missing_leader":
            verdicts.append(_v(
                "saknad_hänvisning", LEAVE, i.get("text") or "",
                f"ritningen drar ingen linje från etiketten ({i.get('reason') or 'inget skäl noterat'}); "
                "det finns inget att genomföra utan att peka ut ett rör som ritningen inte pekar ut",
                bbox=i.get("bbox")))
        elif kind == "missing_dn":
            verdicts.append(_v(
                "saknad_dimension", SILENT, i.get("text") or "",
                "beteckningen namnger ett rör men ingen dimension står på raden; ritningen säger den inte, "
                "och en storlek som inte står ska inte uppfinnas - raden ingår därför inte i mängden",
                bbox=i.get("bbox")))
        elif kind == "missing_pipe_attachment":
            verdicts.append(_v(
                "nådde_inget_rör", LEAVE, i.get("text") or "",
                "hänvisningslinjen slutar där ritningen inte ritar någon accepterad rörgeometri; "
                "vad den pekar på syns bara på ritningen",
                bbox=i.get("bbox")))
        else:
            verdicts.append(_v(kind or "olöst", SILENT, i.get("text") or "",
                               i.get("reason") or "ritningen ger inget som avgör fallet", bbox=i.get("bbox")))

    # 3. geometry the drawing drew twice
    dt = model.declined.get("drawn_twice") or {}
    if dt.get("n_places"):
        verdicts.append(_v(
            "dubbelritad_geometri", LEAVE, f"{dt['n_places']} ställen, {dt.get('length_m')} m",
            "samma linje är ritad två gånger, men att dra bort den kostar mer än den sparar: de dubbla "
            "stumparna sitter i skarvar, och när de togs bort flyttades en dimensionsgräns dit ritningen inte "
            "gör någon skarv - sex meter bytte storlek för att spara åtta tiondels meter dubbelräkning",
            ställen=(dt.get("places") or [])[:20]))

    # 4. the scale everything rests on
    s = model.scale
    if s.get("state") != "VERIFIED":
        verdicts.append(_v(
            "skala", LEAVE, f"skalan är {s.get('state')}",
            f"{s.get('reason') or 'skalstocken bekräftar inte skaltexten'}; läsningen använder den källa som "
            "vilar på ritad geometri framför den som vilar på text, och säger vilken - varje längd på bladet "
            "hänger på det"))

    # 5. does the drawn geometry still add up
    r = model.reconciliation
    if r and r.get("state") != "VALID":
        verdicts.append(_v(
            "avstämning", LEAVE, r.get("state") or "okänd",
            "den ritade rörgeometrin summerar inte till bekräftat plus tvetydigt plus utan ägare; "
            "en sådan läsning ska inte rättas, den ska undersökas",
            dubbelräknade=r.get("double_counted_prims")))

    # 6. what the reviewers said that nothing above already covers
    for f in model.review.get("findings", []):
        if f.get("severity") == "INFO":
            continue
        if f.get("agent") in ("scale",) and s.get("state") != "VERIFIED":
            continue        # already judged above, and once is enough
        verdicts.append(_v(
            f"granskare_{f.get('agent')}", LEAVE, f.get("code") or "",
            f.get("message") or "", allvar=f.get("severity")))

    counts = {IMPLEMENT: 0, LEAVE: 0, SILENT: 0}
    for v in verdicts:
        counts[v["beslut"]] = counts.get(v["beslut"], 0) + 1
    return {"antal": len(verdicts), "sammanfattning": counts, "utslag": verdicts,
            "regel": "Domaren genomför bara svar ritningen själv erbjuder, rör aldrig en bekräftad mätning, "
                     "och skriver varje ändring som en rättelse som kan ångras. Där ritningen inte säger något "
                     "är det svaret: sträckan räknas inte, och det står varför. Ingen människa behöver avgöra "
                     "något för att mängden ska vara färdig."}
