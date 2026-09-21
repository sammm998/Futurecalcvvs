"""Vad projektagenten kan göra: frågor till hela handlingen, besvarade ur det som redan lästs.

Samma delning som för ritningsagenten: modellen bestämmer VAD som ska frågas, de här funktionerna bestämmer
vad svaret ÄR. Varje siffra kommer ur projektanalysens rapport och ur de läsningar som redan körts på bladen -
ingenting här mängdar, gissar eller rundar något läsningen inte redan avgjort, och ingenting här ändrar
projektet.

Två regler som är projektets egna och inte ritningens:

  * Ett svar om ett hus byggs bara på det husets blad. Hus A och hus B har var sin beteckningslista, och en
    summa över projektet är en summa över två olika saker.
  * Varje svar säger vilka blad det vilar på. Ett påstående om en handling som inte pekar på ett blad går inte
    att kontrollera, och då är det inte ett svar.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

TOOLS: dict[str, dict[str, Any]] = {}


def tool(name: str, description: str, params: dict[str, Any]) -> Callable:
    def wrap(fn: Callable) -> Callable:
        TOOLS[name] = {"name": name, "description": description, "writes": False,
                       "parameters": {"type": "object", "properties": params,
                                      "required": [k for k, v in params.items() if v.get("required")],
                                      "additionalProperties": False},
                       "fn": fn}
        for v in params.values():
            v.pop("required", None)
        return fn
    return wrap


def _set(v) -> bool:
    return v is not None and v != "" and v != 0


class ProjectModel:
    """Projektet som agenten ser det: rapporten, mängderna per blad, rättelserna, ändringslistorna."""

    def __init__(self, report: dict, rows_by_drawing: dict[str, list[dict]],
                 changes_for: Callable[[str], dict] | None = None, overrides: list[dict] | None = None):
        self.report = report or {}
        self.rows_by_drawing = rows_by_drawing
        self.changes_for = changes_for
        self.overrides = overrides or []

    @property
    def documents(self) -> list[dict]:
        return self.report.get("documents") or []

    def doc(self, drawing_id: str) -> dict | None:
        return next((d for d in self.documents if d.get("drawing_id") == drawing_id), None)

    @staticmethod
    def val(d: dict, field: str):
        f = d.get(field) or {}
        return f.get("value") if isinstance(f, dict) else f

    def cite(self, d: dict) -> dict:
        return {"drawing_id": d.get("drawing_id"), "blad": d.get("filename"),
                "nummer": self.val(d, "number"), "hus": self.val(d, "building")}


def _match(m: ProjectModel, d: dict, hus=None, plan=None, disciplin=None, nummer=None) -> bool:
    if _set(hus) and str(m.val(d, "building") or "").upper() != str(hus).upper():
        return False
    if _set(plan) and str(m.val(d, "floor") or "").upper() != str(plan).upper():
        return False
    if _set(disciplin) and str(m.val(d, "discipline") or "").upper() != str(disciplin).upper():
        return False
    if _set(nummer) and str(nummer).upper() not in str(m.val(d, "number") or "").upper():
        return False
    return True


@tool("hamta_handling", "Vad handlingen består av: hus, discipliner, antal blad, versionspar och det som inte gick att ordna.", {})
def hamta_handling(m: ProjectModel) -> dict:
    r = m.report
    return {"hus": r.get("buildings", []), "discipliner": r.get("disciplines", []),
            "totalt": r.get("totals", {}), "olasbara": r.get("unreadable", []),
            "dubbletter": r.get("duplicates", {}),
            "blad_med_lasning": sum(1 for d in m.documents if m.rows_by_drawing.get(d.get("drawing_id"))),
            "blad_utan_lasning": [m.cite(d) for d in m.documents if not m.rows_by_drawing.get(d.get("drawing_id"))]}


@tool("hitta_blad", "Vilka blad som finns, valfritt avgränsat till ett hus, ett plan, en disciplin eller en del av ritningsnumret.",
      {"hus": {"type": "string"}, "plan": {"type": "string"}, "disciplin": {"type": "string"}, "nummer": {"type": "string"}})
def hitta_blad(m: ProjectModel, hus: str | None = None, plan: str | None = None, disciplin: str | None = None,
               nummer: str | None = None) -> dict:
    out = []
    for d in m.documents:
        if not _match(m, d, hus, plan, disciplin, nummer):
            continue
        out.append({**m.cite(d), "plan": m.val(d, "floor"), "disciplin": m.val(d, "discipline"),
                    "status": m.val(d, "status"), "revision": m.val(d, "revision"),
                    "datum": m.val(d, "document_date"), "titel": m.val(d, "title"),
                    "last": bool(m.rows_by_drawing.get(d.get("drawing_id")))})
    return {"antal": len(out), "blad": out}


@tool("mangder_per_hus", "Mängderna summerade per hus och beteckning, ur de läsningar som redan gjorts. Aldrig över husen.",
      {"hus": {"type": "string"}, "system": {"type": "string"}})
def mangder_per_hus(m: ProjectModel, hus: str | None = None, system: str | None = None) -> dict:
    q = m.report.get("quantities") or {}
    out = {}
    for b, rows in q.items():
        if _set(hus) and str(b).upper() != str(hus).upper():
            continue
        keep = [r for r in rows if not _set(system) or str(r.get("designation", "")).upper().startswith(str(system).upper())]
        if keep:
            out[b] = {"rader": keep, "summa_m": round(sum(r.get("horizontal_m") or 0 for r in keep), 2),
                      "stigare": sum(r.get("risers") or 0 for r in keep)}
    return {"per_hus": out, "forbehall": "Summerat per hus och aldrig över projektet; ett hus utan läsningar har inga mängder."}


@tool("mangder_for_beteckning", "En beteckning genom hela handlingen: vilka blad den finns på, hur många meter på vart och ett, och per hus.",
      {"beteckning": {"type": "string", "required": True}})
def mangder_for_beteckning(m: ProjectModel, beteckning: str) -> dict:
    want = (beteckning or "").upper().strip()
    hits = []
    per_hus: dict[str, float] = defaultdict(float)
    for d in m.documents:
        did = d.get("drawing_id")
        for r in m.rows_by_drawing.get(did) or []:
            name = str(r.get("designation", "")).upper()
            if name == want or name.startswith(want):
                mtr = r.get("confirmed_horizontal_m") or 0.0
                hits.append({**m.cite(d), "beteckning": r.get("designation"), "m": round(mtr, 2),
                             "stigare": max(r.get("riser_count") or 0, r.get("riser_count_from_labels") or 0),
                             "tillstand": r.get("state")})
                per_hus[str(m.val(d, "building") or "Okänt hus")] += mtr
    return {"beteckning": beteckning, "traffar": hits, "per_hus": {k: round(v, 2) for k, v in per_hus.items()},
            "blad_utan_lasning": [m.cite(d) for d in m.documents if not m.rows_by_drawing.get(d.get("drawing_id"))]}


@tool("versioner", "Versionsparen handlingen själv bär ordningen för, och de blad som inte gick att ordna - med skälen.", {})
def versioner(m: ProjectModel) -> dict:
    r = m.report
    return {"par": [{"nyckel": p.get("key"), "fore": m.cite(p.get("before") or {}), "efter": m.cite(p.get("after") or {}),
                     "skal": p.get("why"), "sakerhet": p.get("confidence")} for p in r.get("pairs") or []],
            "oklara": [{"nyckel": u.get("key"), "lasning": u.get("reading"), "skal": u.get("why"),
                        "blad": [m.cite(d) for d in u.get("docs") or []]} for u in r.get("unclear") or []],
            "regel": "Ett par påstås bara när handlingarna själva bär ordningen: revision, datum eller skede. Ett tal i filnamnet är ingen revision."}


@tool("vad_andrades", "Ändringslistan för ett versionspar: tillkomna, borttagna och ändrade beteckningar mellan före och efter. Finns bara när båda bladen är mängdade.",
      {"nyckel": {"type": "string", "required": True}})
def vad_andrades(m: ProjectModel, nyckel: str) -> dict:
    pair = next((p for p in m.report.get("pairs") or [] if p.get("key") == nyckel), None)
    if pair is None:
        return {"fel": "Det finns inget säkert versionspar med den nyckeln. Ett par som inte gick att ordna har inget före och inget efter, och därmed ingen ändringslista.",
                "tillgangliga": [p.get("key") for p in m.report.get("pairs") or []]}
    if m.changes_for is None:
        return {"fel": "Ändringslistan är inte tillgänglig i det här läget."}
    return {"nyckel": nyckel, "fore": m.cite(pair.get("before") or {}), "efter": m.cite(pair.get("after") or {}),
            "andringar": m.changes_for(nyckel)}


@tool("rattelser", "Vad människor rättat om bladen - hus, disciplin, nummer - och som går före läsningen.", {})
def rattelser(m: ProjectModel) -> dict:
    return {"antal": len(m.overrides), "rader": m.overrides}


@tool("kontrollera_handlingen", "Det som bör tittas på: blad utan läsning, blad utan nummer eller hus, oklara par, dubbletter.", {})
def kontrollera_handlingen(m: ProjectModel) -> dict:
    r = m.report
    saknar_nummer = [m.cite(d) for d in m.documents if not m.val(d, "number")]
    saknar_hus = [m.cite(d) for d in m.documents if not m.val(d, "building")]
    return {"blad_utan_lasning": [m.cite(d) for d in m.documents if not m.rows_by_drawing.get(d.get("drawing_id"))],
            "blad_utan_nummer": saknar_nummer, "blad_utan_hus": saknar_hus,
            "oklara_par": len(r.get("unclear") or []), "dubbletter": r.get("duplicates", {}),
            "olasbara": r.get("unreadable", [])}


def run(name: str, model: ProjectModel, args: dict[str, Any]) -> dict[str, Any]:
    t = TOOLS.get(name)
    if t is None:
        return {"fel": f"okänt verktyg: {name}", "verktyg": sorted(TOOLS)}
    try:
        return t["fn"](model, **{k: v for k, v in (args or {}).items() if k in t["parameters"]["properties"]})
    except TypeError as e:
        return {"fel": f"fel argument till {name}: {e}"}


def schemas() -> list[dict[str, Any]]:
    return [{"type": "function", "name": t["name"], "description": t["description"],
             "parameters": t["parameters"], "strict": False} for t in TOOLS.values()]


def writes(name: str) -> bool:
    return False
