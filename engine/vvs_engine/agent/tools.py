"""What the agent can actually do, as functions rather than as text.

The division is the whole point: the model decides *what* to ask, these functions decide *what the answer is*.
Every number here comes from the artifacts the measuring pipeline wrote, so an answer given through the agent and
an answer read off the takeoff table are the same answer. Nothing in this module measures, guesses or rounds
anything the reading did not already settle, and nothing here changes the drawing - a change is a correction,
which goes through the correction log and can be undone.

Each tool returns plain JSON. Where an answer is about geometry it also returns the ids and boxes to light up, so
a claim on screen can always be pointed at on the sheet.
"""
from __future__ import annotations

from typing import Any, Callable

from .model import DrawingModel

TOOLS: dict[str, dict[str, Any]] = {}


def tool(name: str, description: str, params: dict[str, Any], writes: bool = False) -> Callable:
    """Register one tool. `writes` marks the ones that propose a change rather than report a fact.

    A writing tool still only proposes: it returns the correction it would record, with every metre taken from
    the reading, and nothing happens until a person accepts it. The flag exists so the two can never be confused
    - the question path runs read tools and the change path runs writing ones, and neither can reach the other.
    """
    def wrap(fn: Callable) -> Callable:
        TOOLS[name] = {"name": name, "description": description, "writes": writes,
                       "parameters": {"type": "object", "properties": params,
                                      "required": [k for k, v in params.items() if v.get("required")],
                                      "additionalProperties": False},
                       "fn": fn}
        for v in params.values():
            v.pop("required", None)
        return fn
    return wrap


def _set(v) -> bool:
    """Whether an optional filter was actually given.

    A model filling a schema tends to write the empty value rather than leave a field out - system "", dimension
    0 - and reading a zero as "size zero" filtered every row away and answered an honest question with nothing.
    No pipe is DN 0 and no system is named "", so a blank is an absent filter.
    """
    return v is not None and v != "" and v != 0


def _num(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _pipe_out(m: DrawingModel, p: dict) -> dict:
    return {"pipe_id": p["physical_pipe_id"], "designation": p.get("designation"), "system": p.get("system"),
            "dn": p.get("dn"), "identity": p.get("identity"), "page": p.get("page", 0),
            "horizontal_m": round(_num(p.get("horizontal_m")), 3),
            "state": p.get("evidence_state"), "bbox": [round(v, 1) for v in m.bbox_of_pipe(p)]}


# ---------------------------------------------------------------- what the sheet is

@tool("hamta_ritning", "Vad ritningen är: skala, sidor, system ur förklaringslistan och totalsumman.", {})
def hamta_ritning(m: DrawingModel) -> dict:
    t = m.quantities.get("totals") or {}
    return {"skala": {"tillstand": m.scale.get("state"), "meter_per_punkt": m.meters_per_pt,
                      "skal": m.scale.get("reason")},
            "system": m.systems, "komponentkoder": m.components,
            "antal_ror": len(m.pipes), "antal_beteckningar": len(m.designations),
            "bekraftad_total_m": t.get("confirmed_total_m"), "tvetydig_m": t.get("ambiguous_m"),
            "avstamning": m.reconciliation.get("state")}


@tool("hamta_forklaringslista", "Ritningens egen förklaringslista: kod, betydelse, roll och varifrån rollen kom.", {})
def hamta_forklaringslista(m: DrawingModel) -> dict:
    return {"rader": [{"kod": e["code"], "betydelse": e.get("description"), "rubrik": e.get("heading"),
                       "roll": e.get("role"), "varifran": e.get("role_from")}
                      for e in m.legend.get("entries", [])]}


# ---------------------------------------------------------------- finding things

@tool("hitta_ror", "Rör som matchar system, material, dimension eller beteckning. Utan filter: alla rör.",
      {"system": {"type": "string", "description": "t.ex. S1"},
       "dimension": {"type": "integer", "description": "DN, t.ex. 110"},
       "beteckning": {"type": "string", "description": "hel beteckning, t.ex. S1-P2-110"},
       "sida": {"type": "integer"},
       "omrade": {"type": "array", "items": {"type": "number"}, "description": "[x0,y0,x1,y1] i ritningens punkter"}})
def hitta_ror(m: DrawingModel, system: str | None = None, dimension: int | None = None,
              beteckning: str | None = None, sida: int | None = None, omrade: list | None = None) -> dict:
    out = []
    for p in m.pipes:
        if _set(system) and (p.get("system") or "").upper() != system.upper():
            continue
        if _set(dimension) and p.get("dn") != dimension:
            continue
        if _set(beteckning) and (p.get("designation") or "").upper() != beteckning.upper():
            continue
        if sida is not None and p.get("page") != sida:
            continue
        if omrade and len(omrade) == 4:
            b = m.bbox_of_pipe(p)
            if b[2] < omrade[0] or b[0] > omrade[2] or b[3] < omrade[1] or b[1] > omrade[3]:
                continue
        out.append(_pipe_out(m, p))
    out.sort(key=lambda d: (-d["horizontal_m"], d["pipe_id"]))
    return {"antal": len(out), "summa_m": round(sum(d["horizontal_m"] for d in out), 3), "ror": out[:200]}


@tool("hitta_beteckningar", "Beteckningar bladet skriver, med eller utan textfilter.",
      {"text": {"type": "string"}, "sida": {"type": "integer"},
       "omrade": {"type": "array", "items": {"type": "number"}}})
def hitta_beteckningar(m: DrawingModel, text: str | None = None, sida: int | None = None,
                       omrade: list | None = None) -> dict:
    out = []
    for d in m.designations:
        t = (d.get("text") or "")
        if _set(text) and text.upper() not in t.upper():
            continue
        if sida is not None and d.get("page") != sida:
            continue
        b = d.get("bbox") or [0, 0, 0, 0]
        if omrade and len(omrade) == 4:
            if b[2] < omrade[0] or b[0] > omrade[2] or b[3] < omrade[1] or b[1] > omrade[3]:
                continue
        out.append({"id": d["did"], "text": t, "dn": d.get("dn"), "sida": d.get("page", 0),
                    "bbox": [round(v, 1) for v in b], "namnger_ror": d.get("names_a_pipe", True)})
    return {"antal": len(out), "beteckningar": out[:300]}


@tool("vad_finns_i_omradet", "Allt läsningen har i en ruta: rör, beteckningar och anslutningar.",
      {"omrade": {"type": "array", "items": {"type": "number"}, "required": True},
       "sida": {"type": "integer"}})
def vad_finns_i_omradet(m: DrawingModel, omrade: list, sida: int | None = None) -> dict:
    ror = hitta_ror(m, sida=sida, omrade=omrade)
    bet = hitta_beteckningar(m, sida=sida, omrade=omrade)
    ank = [a for a in m.anchors
           if (sida is None or a.get("page") == sida)
           and omrade[0] <= (a.get("leader_endpoint") or [1e9, 1e9])[0] <= omrade[2]
           and omrade[1] <= (a.get("leader_endpoint") or [1e9, 1e9])[1] <= omrade[3]]
    return {"ror": ror["ror"], "summa_m": ror["summa_m"], "beteckningar": bet["beteckningar"],
            "anslutningar": [{"id": a["anchor_id"], "beteckning": a.get("designation"),
                              "tillstand": a.get("state"), "punkt": a.get("leader_endpoint")} for a in ank[:80]]}


@tool("hamta_ror", "Allt om ett rör: identitet, längd, källa och vad det bygger på.",
      {"ror_id": {"type": "string", "required": True}})
def hamta_ror(m: DrawingModel, ror_id: str) -> dict:
    p = m.pipe_by_id.get(ror_id)
    if p is None:
        return {"fel": f"inget rör med id {ror_id}"}
    return {**_pipe_out(m, p),
            "ritade_punkter": p.get("horizontal_pdf_units"), "ratt_langd_pt": p.get("raw_pt"),
            "overbryggade_gap_pt": p.get("bridged_gap_pt"), "i_skrafferad_yta_m": p.get("in_hatched_area_m"),
            "vertikalt": p.get("vertical_m"), "stodjande_ankare": p.get("supporting_anchors"),
            "kallobjekt": p.get("source_path_ids"), "familj": p.get("representation_family")}


# ---------------------------------------------------------------- measuring

@tool("mat_ror", "Summerar en uppsättning rör och visar varje sträcka för sig.",
      {"ror_id": {"type": "array", "items": {"type": "string"}, "required": True}})
def mat_ror(m: DrawingModel, ror_id: list[str]) -> dict:
    rows = [_pipe_out(m, m.pipe_by_id[i]) for i in ror_id if i in m.pipe_by_id]
    return {"antal": len(rows), "summa_m": round(sum(r["horizontal_m"] for r in rows), 3), "stracker": rows}


@tool("mangda", "Mängden, grupperad som du vill ha den.",
      {"gruppera_pa": {"type": "string", "enum": ["beteckning", "system", "dimension"],
                       "description": "standard: beteckning"},
       "system": {"type": "string"}, "dimension": {"type": "integer"}})
def mangda(m: DrawingModel, gruppera_pa: str = "beteckning", system: str | None = None,
           dimension: int | None = None) -> dict:
    rows = [r for r in m.quantities.get("rows", [])
            if (not _set(system) or (r.get("system") or "").upper() == system.upper())
            and (not _set(dimension) or r.get("dn") == dimension)]
    if gruppera_pa == "beteckning":
        out = [{"nyckel": r["designation"], "meter": round(_num(r.get("confirmed_total_m")), 3),
                "antal_stracker": r.get("physical_pipe_count"), "ror_id": r.get("pipe_ids") or []} for r in rows]
    else:
        key = "system" if gruppera_pa == "system" else "dn"
        agg: dict[Any, dict] = {}
        for r in rows:
            k = r.get(key)
            a = agg.setdefault(k, {"nyckel": k, "meter": 0.0, "antal_stracker": 0, "ror_id": []})
            a["meter"] += _num(r.get("confirmed_total_m"))
            a["antal_stracker"] += int(r.get("physical_pipe_count") or 0)
            a["ror_id"] += r.get("pipe_ids") or []
        out = [{**v, "meter": round(v["meter"], 3)} for v in agg.values()]
    out.sort(key=lambda d: -d["meter"])
    return {"rader": out, "summa_m": round(sum(d["meter"] for d in out), 3)}


@tool("visa_hur_mangden_raknades", "Vilka sträckor som gav en beteckning dess meter.",
      {"beteckning": {"type": "string", "required": True}})
def visa_hur_mangden_raknades(m: DrawingModel, beteckning: str) -> dict:
    row = next((r for r in m.quantities.get("rows", [])
                if (r.get("designation") or "").upper() == beteckning.upper()), None)
    if row is None:
        return {"fel": f"{beteckning} finns inte i mängden"}
    rows = [_pipe_out(m, m.pipe_by_id[i]) for i in (row.get("pipe_ids") or []) if i in m.pipe_by_id]
    rows.sort(key=lambda d: -d["horizontal_m"])
    return {"beteckning": row["designation"], "summa_m": round(_num(row.get("confirmed_total_m")), 3),
            "stracker": rows, "etiketter": row.get("label_count"),
            "i_skrafferad_yta_m": row.get("in_hatched_area_m")}


@tool("varfor_ror", "Beviskedjan bakom ett rör: vilken beteckning, vilken hänvisningslinje, vilken anslutning.",
      {"ror_id": {"type": "string", "required": True}})
def varfor_ror(m: DrawingModel, ror_id: str) -> dict:
    p = m.pipe_by_id.get(ror_id)
    if p is None:
        return {"fel": f"inget rör med id {ror_id}"}
    chain = []
    for aid in p.get("supporting_anchors") or []:
        a = m.anchor_by_id.get(aid)
        if not a:
            continue
        chain.append({"beteckning": a.get("designation"), "dn": a.get("dn"), "tillstand": a.get("state"),
                      "skal": a.get("reason"), "hanvisning_id": a.get("leader_id"),
                      "punkt": a.get("leader_endpoint")})
    return {"ror_id": ror_id, "identitet": p.get("identity"), "langd_m": round(_num(p.get("horizontal_m")), 3),
            "kedja": chain, "skala": {"tillstand": m.scale.get("state"), "skal": m.scale.get("reason")}}


# ---------------------------------------------------------------- following the graph

@tool("folj_natet", "Alla rör som hänger ihop med det här, genom delade noder.",
      {"ror_id": {"type": "string", "required": True}})
def folj_natet(m: DrawingModel, ror_id: str) -> dict:
    ids = m.connected(ror_id)
    rows = [_pipe_out(m, m.pipe_by_id[i]) for i in ids if i in m.pipe_by_id]
    return {"antal": len(rows), "summa_m": round(sum(r["horizontal_m"] for r in rows), 3), "ror": rows}


@tool("grannar", "Rören som möter det här i en nod - där ritningen byter något.",
      {"ror_id": {"type": "string", "required": True}})
def grannar(m: DrawingModel, ror_id: str) -> dict:
    ids = sorted(m.adjacency.get(ror_id, ()))
    return {"antal": len(ids), "ror": [_pipe_out(m, m.pipe_by_id[i]) for i in ids if i in m.pipe_by_id]}


@tool("vag_mellan", "Färrast sträckor från ett rör till ett annat längs ritningens egen graf.",
      {"fran_ror_id": {"type": "string", "required": True}, "till_ror_id": {"type": "string", "required": True}})
def vag_mellan(m: DrawingModel, fran_ror_id: str, till_ror_id: str) -> dict:
    ids = m.path_between(fran_ror_id, till_ror_id)
    if not ids:
        return {"hittad": False, "anmarkning": "de hänger inte ihop i den läsning ritningen ger"}
    rows = [_pipe_out(m, m.pipe_by_id[i]) for i in ids if i in m.pipe_by_id]
    return {"hittad": True, "antal_stracker": len(rows),
            "summa_m": round(sum(r["horizontal_m"] for r in rows), 3), "vag": rows}


# ---------------------------------------------------------------- what to check

@tool("hitta_dubbelritad_geometri", "Var ritningen ritat samma linje två gånger.", {})
def hitta_dubbelritad_geometri(m: DrawingModel) -> dict:
    dt = m.declined.get("drawn_twice") or {}
    return {"antal_stallen": dt.get("n_places", 0), "langd_m": dt.get("length_m"),
            "stallen": (dt.get("places") or [])[:60],
            "anmarkning": "rapporteras men dras inte av: se LIMITATIONS för mätningen som avgjorde det"}


@tool("hitta_fria_rorandar", "Rörändar som inte möter något annat: anslutning, brunn, stigare eller avbrott.", {})
def hitta_fria_rorandar(m: DrawingModel) -> dict:
    e = m.free_ends()
    return {"antal": len(e), "andar": e[:120]}


@tool("hitta_dimensionsbyten", "Noder där ritningen byter dimension, system eller material.", {})
def hitta_dimensionsbyten(m: DrawingModel) -> dict:
    f = m.size_frontiers()
    return {"antal": len(f), "granser": f[:120]}


@tool("hitta_omatt_geometri", "Ritade linjer läsningen inte tog som rör, med skälet.", {})
def hitta_omatt_geometri(m: DrawingModel) -> dict:
    d = m.declined
    return {"avvisade_familjer": [{"skal": f.get("why"), "meter": f.get("length_m"), "penna": f.get("width"),
                                   "lager": f.get("layer")} for f in (d.get("families") or [])[:40]],
            "obeaktade": [{"skal": f.get("why"), "meter": f.get("length_m")} for f in (d.get("unconsidered") or [])[:40]],
            "totalt": d.get("totals")}


@tool("hitta_olosta", "Beteckningar ritningen skriver som inte fått en meter, med skälet.", {})
def hitta_olosta(m: DrawingModel) -> dict:
    blockerande = [i for i in m.issues if i.get("severity") == "blocking"]
    return {"antal_blockerande": len(blockerande), "antal_noterade": len(m.issues) - len(blockerande),
            "fall": [{"typ": i.get("kind"), "text": i.get("text"), "skal": i.get("reason"),
                      "bbox": i.get("bbox")} for i in (blockerande + [i for i in m.issues if i.get("severity") != "blocking"])[:80]]}


@tool("kontrollera_lasningen", "Granskarnas utlåtande och avstämningen mellan ritad och mätt geometri.", {})
def kontrollera_lasningen(m: DrawingModel) -> dict:
    r = m.reconciliation
    return {"granskare": m.review.get("agents"), "tillstand": m.review.get("state"),
            "utlatanden": [{"granskare": f.get("agent"), "allvar": f.get("severity"), "text": f.get("message")}
                           for f in m.review.get("findings", [])],
            "avstamning": {"tillstand": r.get("state"), "ritat_pt": r.get("raw_relevant_pipe_geometry_pt"),
                           "bekraftat_pt": r.get("confirmed_pt"), "tvetydigt_pt": r.get("ambiguous_pt"),
                           "utan_agare_pt": r.get("unowned_pt"), "dubbelraknade": r.get("double_counted_prims")}}


@tool("kontrollera_skala", "Hur skalan lästes och om skalstocken bekräftar skaltexten.", {})
def kontrollera_skala(m: DrawingModel) -> dict:
    s = m.scale
    return {"tillstand": s.get("state"), "skal": s.get("reason"), "meter_per_punkt": s.get("meters_per_pdf_point"),
            "bevis": s.get("evidence")}


def run(name: str, model: DrawingModel, args: dict[str, Any]) -> dict[str, Any]:
    """Call one tool by name. Unknown names and bad arguments are answers, not exceptions."""
    t = TOOLS.get(name)
    if t is None:
        return {"fel": f"okänt verktyg {name}", "tillgangliga": sorted(TOOLS)}
    try:
        return t["fn"](model, **{k: v for k, v in (args or {}).items() if k != "self"})
    except TypeError as e:
        return {"fel": f"fel argument till {name}: {e}"}
    except Exception as e:                                      # noqa: BLE001
        return {"fel": f"{name} kunde inte köras: {type(e).__name__}: {e}"}


def schemas() -> list[dict[str, Any]]:
    """The contract, in the shape a tool-calling model expects."""
    return [{"type": "function", "name": t["name"], "description": t["description"],
             "parameters": t["parameters"]} for t in TOOLS.values()]


def writes(name: str) -> bool:
    """Whether this tool proposes a change. It still only proposes; nothing in the agent writes."""
    return bool((TOOLS.get(name) or {}).get("writes"))


# The tools that propose a change register themselves the same way the reading tools do, and are imported here
# so one import of this module is the whole contract. It sits at the bottom because `edits` builds on `tool`,
# `_num` and `_set` above it - by this line they exist, so the loop closes.
from . import edits as _edits  # noqa: E402,F401  (registers the writing tools)
