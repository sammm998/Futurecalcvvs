"""Agenten vid ritbordet: typade verktyg mot byggmodellen, som föreslår och aldrig skriver.

Två sorters verktyg, som i ritningsagenten (vvs_engine.agent.tools):

* Läsande: vad modellen innehåller - nivåer, objekt, mängder, det som skulle avvisas. Svaren är ur dokumentet
  som det är.
* Skrivande: en vägg, en dörr, ett rum, ett rör... Varje sådant verktyg kräver sina mått som tal - det finns
  inget "en normal dörr", ingen standardhöjd som fylls i åt användaren. Saknas ett mått är svaret till modellen
  att fråga användaren. Det som verktyget gör är ett *förslag*: ett färdigt objekt med ursprung
  AGENT_CREATED_APPROVED som ritbordet visar som spöke tills en människa godkänner det; först då blir det en
  transaktion i dokumentet. Servern skriver aldrig i bladet från den här modulen.

Modellen agenten arbetar mot (`CadAgentModel`) är dokumentet plus listan med förslag turen samlar på sig.
"""
from __future__ import annotations

import math
import uuid
from typing import Any, Callable

from . import cad_geom as G
from . import cad_model

TOOLS: dict[str, dict[str, Any]] = {}

SYSTEM_NOTE = (
    "Du arbetar vid ett ritbord mot en byggmodell i millimeter: nivåer, väggar, dörrar, fönster, bjälklag, tak, "
    "rum, pelare, balkar, rör och kanaler. Du svarar på svenska. Du hittar aldrig på ett mått: ett verktyg som "
    "skapar något kräver måtten som tal, och saknar användaren ett mått frågar du efter det i stället för att "
    "anta. Det du skapar är förslag som användaren godkänner i ritbordet - säg det, och säg vad förslaget "
    "innehåller med sina mått. Använd modellens egna nivåer (hamta_modell) och befintliga objekt (lista_objekt) "
    "innan du föreslår något som ska sitta i eller på dem."
)


class CadAgentModel:
    def __init__(self, doc: dict) -> None:
        self.doc = doc
        self.proposals: list[dict] = []
        self._added: list[dict] = []     # så att en dörr kan sättas i en vägg som föreslogs i samma tur

    def entity(self, eid: str) -> dict | None:
        return G.entity(self.doc, eid) or next((e for e in self._added if e.get("id") == eid), None)

    def level(self, lid: str | None) -> dict | None:
        return next((l for l in self.doc.get("levels") or [] if l.get("id") == lid), None)

    def propose_add(self, e: dict, why: str) -> dict:
        self._added.append(e)
        self.proposals.append({"op": "add", "collection": "entities", "item": e, "why": why})
        return {"forslag": "registrerat - kräver godkännande i ritbordet", "objekt": e, "id": e["id"]}


def tool(name: str, description: str, params: dict[str, Any], writes: bool = False) -> Callable:
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


def _uid() -> str:
    return "a_" + uuid.uuid4().hex[:10]


def _num(v, name: str) -> float:
    """Ett mått måste vara ett tal större än noll. Allt annat är ett fel som modellen får tillbaka."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} måste anges som ett tal i millimeter") from None
    if not math.isfinite(f) or f <= 0:
        raise ValueError(f"{name} måste vara större än noll")
    return f


def _pt(v, name: str) -> list:
    if not (isinstance(v, (list, tuple)) and len(v) >= 2):
        raise ValueError(f"{name} ska vara [x, y] i millimeter")
    try:
        return [float(v[0]), float(v[1])]
    except (TypeError, ValueError):
        raise ValueError(f"{name} ska vara två tal") from None


def _pts(v, name: str, n: int = 3) -> list:
    if not isinstance(v, list) or len(v) < n:
        raise ValueError(f"{name} behöver minst {n} punkter")
    return [_pt(p, name) for p in v]


def _layer_for(m: CadAgentModel, discipline: str) -> str:
    for l in m.doc.get("layers") or []:
        if l.get("discipline") == discipline:
            return l["id"]
    return (m.doc.get("layers") or [{"id": "l_ark"}])[0]["id"]


def _common(m: CadAgentModel, discipline: str, level: str | None) -> dict:
    d = {"id": _uid(), "layer": _layer_for(m, discipline), "discipline": discipline, "phase": "NEW",
         "provenance": "AGENT_CREATED_APPROVED", "version": 1}
    if level:
        d["level"] = level
    return d


def _level(m: CadAgentModel, lid, name: str = "nivå") -> str:
    if not lid:
        raise ValueError(f"{name} saknas: ange en av modellens nivåer (hamta_modell)")
    if not m.level(lid):
        raise ValueError(f"{name} {lid!r} finns inte i modellen; nivåerna är {[l['id'] for l in m.doc.get('levels') or []]}")
    return str(lid)


# ---------------------------------------------------------------- läsande

@tool("hamta_modell", "Vad modellen består av: projekt, nivåer med höjder, lager, material och antal objekt per typ.", {})
def hamta_modell(m: CadAgentModel) -> dict:
    counts: dict[str, int] = {}
    for e in m.doc.get("entities") or []:
        counts[e.get("type", "?")] = counts.get(e.get("type", "?"), 0) + 1
    return {"projekt": m.doc.get("project"), "byggnad": m.doc.get("building"),
            "nivaer": [{"id": l["id"], "namn": l.get("name"), "hojd_mm": l.get("elevation_mm")} for l in m.doc.get("levels") or []],
            "lager": [{"id": l["id"], "namn": l.get("name"), "disciplin": l.get("discipline")} for l in m.doc.get("layers") or []],
            "material": [{"id": x["id"], "namn": x.get("name")} for x in m.doc.get("materials") or []],
            "antal_per_typ": counts, "revision": m.doc.get("revision")}


@tool("lista_objekt", "Objekten i modellen, med typ, nivå och de mått som ritar dem. Filtrera på typ och nivå.",
      {"typ": {"type": "string", "description": "wall, door, window, floor, roof, room, column, beam, pipe, duct ... (tomt = alla)"},
       "niva": {"type": "string", "description": "nivåns id (tomt = alla)"}})
def lista_objekt(m: CadAgentModel, typ: str = "", niva: str = "") -> dict:
    rows = []
    for e in m.doc.get("entities") or []:
        if typ and e.get("type") != typ:
            continue
        lv = e.get("base_level") or e.get("level")
        if niva and lv != niva:
            continue
        rows.append(_brief(m, e))
    return {"antal": len(rows), "objekt": rows[:200], "avklippt": max(0, len(rows) - 200)}


def _brief(m: CadAgentModel, e: dict) -> dict:
    t = e.get("type")
    d: dict[str, Any] = {"id": e.get("id"), "typ": t, "namn": e.get("name"), "niva": e.get("base_level") or e.get("level"), "disciplin": e.get("discipline"), "ursprung": e.get("provenance")}
    if t in ("wall", "curtain_wall"):
        d.update(p=e.get("p"), tjocklek=e.get("thickness"), langd_mm=round(G.wall_length(e)), hojd_mm=round(cad_model.height_of(m.doc, e)))
    elif t in ("door", "window", "opening"):
        d.update(host=e.get("host"), t=e.get("t"), bredd=e.get("width"), hojd=e.get("height"), sill=e.get("sill"))
    elif t in ("floor", "roof", "ceiling", "room"):
        d.update(hörn=len(e.get("p") or []), area_m2=round(G.polygon_area(e.get("p") or []) / 1e6, 2), tjocklek=e.get("thickness"))
    elif t == "column":
        d.update(p=e.get("p"), profil=e.get("profile"), hojd_mm=round(cad_model.height_of(m.doc, e)))
    elif t == "beam":
        d.update(p=e.get("p"), profil=e.get("profile"))
    elif t in G.MEP_PATH:
        d.update(system=e.get("system"), dn=e.get("dn"), punkter=len(e.get("path") or []), langd_m=round(G.path_length(e.get("path") or []) / 1000, 2))
    return d


@tool("hamta_objekt", "Ett objekt i sin helhet, med alla fält.", {"id": {"type": "string", "required": True}})
def hamta_objekt(m: CadAgentModel, id: str) -> dict:
    e = m.entity(id)
    return {"objekt": e} if e else {"fel": f"inget objekt med id {id}"}


@tool("mangder", "Mängderna ur modellens egna mått: antal, meter, kvadratmeter, kubikmeter och kilo per grupp.", {})
def mangder(m: CadAgentModel) -> dict:
    q = cad_model.quantities(m.doc)
    return {"grupper": q.get("groups"), "material": cad_model.material_quantities(m.doc)}


@tool("validera", "Vad som skulle avvisas om modellen sparades nu, inklusive de förslag turen samlat.", {})
def validera(m: CadAgentModel) -> dict:
    doc = dict(m.doc, entities=list(m.doc.get("entities") or []) + list(m._added))
    return {"problem": cad_model.validate(doc)}


# ---------------------------------------------------------------- skrivande: förslag

@tool("skapa_vagg", "Föreslå en vägg mellan två punkter. Tjocklek och nivå krävs; höjd krävs om nivån ovanför inte ska ge den.",
      {"a": {"type": "array", "items": {"type": "number"}, "description": "[x, y] mm", "required": True},
       "b": {"type": "array", "items": {"type": "number"}, "description": "[x, y] mm", "required": True},
       "tjocklek_mm": {"type": "number", "required": True},
       "niva": {"type": "string", "description": "undre nivåns id", "required": True},
       "hojd_mm": {"type": "number", "description": "väggens höjd; utelämnas om väggen ska gå till nivån ovanför"},
       "material": {"type": "string", "description": "material-id ur hamta_modell"},
       "namn": {"type": "string"}}, writes=True)
def skapa_vagg(m: CadAgentModel, a, b, tjocklek_mm, niva, hojd_mm=None, material: str = "", namn: str = "") -> dict:
    A, B = _pt(a, "a"), _pt(b, "b")
    if math.dist(A, B) <= 0:
        raise ValueError("väggen har ingen längd")
    lv = _level(m, niva)
    e = dict(_common(m, "ARK", lv), type="wall", p=[A, B], thickness=_num(tjocklek_mm, "tjocklek_mm"), base_level=lv, alignment="centre")
    if hojd_mm is not None and hojd_mm != 0:
        e["height"] = _num(hojd_mm, "hojd_mm")
    elif not G.level_above(m.doc, lv):
        raise ValueError("det finns ingen nivå ovanför; ange hojd_mm")
    if material:
        e["material"] = material
    if namn:
        e["name"] = namn
    return m.propose_add(e, f"vägg {round(math.dist(A, B))} mm, {e['thickness']:g} mm tjock")


def _hosted(m: CadAgentModel, kind: str, vagg_id: str, lage_mm, bredd_mm, hojd_mm, sill_mm=None, **extra) -> dict:
    w = m.entity(vagg_id)
    if not w or w.get("type") not in ("wall", "curtain_wall"):
        raise ValueError(f"{vagg_id!r} är ingen vägg (lista_objekt typ=wall)")
    L = G.wall_length(w)
    x = _num(lage_mm, "lage_mm")
    width = _num(bredd_mm, "bredd_mm")
    if x - width / 2 < -1 or x + width / 2 > L + 1:
        raise ValueError(f"{kind} får inte plats: väggen är {round(L)} mm lång, läget {x:g} med bredden {width:g}")
    lv = w.get("base_level") or w.get("level")
    e = dict(_common(m, "ARK", lv), type=kind, host=w["id"], t=x / L, width=width, height=_num(hojd_mm, "hojd_mm"))
    if kind != "door":
        e["sill"] = _num(sill_mm, "sill_mm") if sill_mm not in (None, 0) else 0.0 if sill_mm == 0 else None
        if e["sill"] is None:
            raise ValueError("sill_mm (bröstningshöjd) måste anges")
    e.update({k: v for k, v in extra.items() if v})
    return e


@tool("skapa_dorr", "Föreslå en dörr i en befintlig vägg. Läge (mm från väggens start), bredd och höjd krävs.",
      {"vagg_id": {"type": "string", "required": True}, "lage_mm": {"type": "number", "required": True},
       "bredd_mm": {"type": "number", "required": True}, "hojd_mm": {"type": "number", "required": True},
       "slag": {"type": "string", "description": "left, right, double eller sliding"}}, writes=True)
def skapa_dorr(m: CadAgentModel, vagg_id, lage_mm, bredd_mm, hojd_mm, slag: str = "") -> dict:
    e = _hosted(m, "door", vagg_id, lage_mm, bredd_mm, hojd_mm, swing=slag if slag in ("left", "right", "double", "sliding") else "")
    return m.propose_add(e, f"dörr {e['width']:g}×{e['height']:g} i {vagg_id}")


@tool("skapa_fonster", "Föreslå ett fönster i en befintlig vägg. Läge, bredd, höjd och bröstningshöjd (sill) krävs.",
      {"vagg_id": {"type": "string", "required": True}, "lage_mm": {"type": "number", "required": True},
       "bredd_mm": {"type": "number", "required": True}, "hojd_mm": {"type": "number", "required": True},
       "sill_mm": {"type": "number", "required": True}}, writes=True)
def skapa_fonster(m: CadAgentModel, vagg_id, lage_mm, bredd_mm, hojd_mm, sill_mm) -> dict:
    e = _hosted(m, "window", vagg_id, lage_mm, bredd_mm, hojd_mm, sill_mm)
    return m.propose_add(e, f"fönster {e['width']:g}×{e['height']:g} i {vagg_id}")


@tool("skapa_bjalklag", "Föreslå ett bjälklag över en kontur på en nivå. Tjocklek krävs.",
      {"kontur": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "[[x,y],...] mm, minst tre hörn", "required": True},
       "tjocklek_mm": {"type": "number", "required": True}, "niva": {"type": "string", "required": True},
       "material": {"type": "string"}}, writes=True)
def skapa_bjalklag(m: CadAgentModel, kontur, tjocklek_mm, niva, material: str = "") -> dict:
    lv = _level(m, niva)
    e = dict(_common(m, "ARK", lv), type="floor", p=_pts(kontur, "kontur"), thickness=_num(tjocklek_mm, "tjocklek_mm"), level=lv)
    if material:
        e["material"] = material
    return m.propose_add(e, f"bjälklag {round(G.polygon_area(e['p']) / 1e6, 1)} m²")


@tool("skapa_rum", "Föreslå ett rum över en kontur på en nivå, med namn och eventuellt nummer.",
      {"kontur": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "required": True},
       "niva": {"type": "string", "required": True}, "namn": {"type": "string", "required": True}, "nummer": {"type": "string"}}, writes=True)
def skapa_rum(m: CadAgentModel, kontur, niva, namn, nummer: str = "") -> dict:
    lv = _level(m, niva)
    e = dict(_common(m, "ARK", lv), type="room", p=_pts(kontur, "kontur"), level=lv, name=str(namn))
    if nummer:
        e["number"] = str(nummer)
    return m.propose_add(e, f"rum {namn} {round(G.polygon_area(e['p']) / 1e6, 1)} m²")


@tool("skapa_pelare", "Föreslå en pelare i en punkt. Profil (rektangel b×d eller cirkel d) och nivå krävs.",
      {"p": {"type": "array", "items": {"type": "number"}, "required": True}, "niva": {"type": "string", "required": True},
       "bredd_mm": {"type": "number", "description": "rektangelns bredd, eller cirkelns diameter", "required": True},
       "djup_mm": {"type": "number", "description": "rektangelns djup; utelämnas för cirkel"},
       "hojd_mm": {"type": "number", "description": "utelämnas om pelaren ska gå till nivån ovanför"}, "material": {"type": "string"}}, writes=True)
def skapa_pelare(m: CadAgentModel, p, niva, bredd_mm, djup_mm=None, hojd_mm=None, material: str = "") -> dict:
    lv = _level(m, niva)
    prof = {"kind": "rect", "w": _num(bredd_mm, "bredd_mm"), "d": _num(djup_mm, "djup_mm")} if djup_mm not in (None, 0) else {"kind": "circle", "d": _num(bredd_mm, "bredd_mm")}
    e = dict(_common(m, "KONSTR", lv), type="column", p=[_pt(p, "p")], profile=prof, base_level=lv)
    if hojd_mm not in (None, 0):
        e["height"] = _num(hojd_mm, "hojd_mm")
    elif not G.level_above(m.doc, lv):
        raise ValueError("det finns ingen nivå ovanför; ange hojd_mm")
    if material:
        e["material"] = material
    return m.propose_add(e, "pelare")


@tool("skapa_balk", "Föreslå en balk mellan två punkter, med underkant vid nivån (plus förskjutning). Bredd och höjd krävs.",
      {"a": {"type": "array", "items": {"type": "number"}, "required": True}, "b": {"type": "array", "items": {"type": "number"}, "required": True},
       "niva": {"type": "string", "required": True}, "bredd_mm": {"type": "number", "required": True}, "hojd_mm": {"type": "number", "required": True},
       "forskjutning_mm": {"type": "number", "description": "överkantens läge relativt nivån, 0 = i nivå"}, "material": {"type": "string"}}, writes=True)
def skapa_balk(m: CadAgentModel, a, b, niva, bredd_mm, hojd_mm, forskjutning_mm=0, material: str = "") -> dict:
    lv = _level(m, niva)
    A, B = _pt(a, "a"), _pt(b, "b")
    if math.dist(A, B) <= 0:
        raise ValueError("balken har ingen längd")
    e = dict(_common(m, "KONSTR", lv), type="beam", p=[A, B], profile={"kind": "rect", "w": _num(bredd_mm, "bredd_mm"), "d": _num(hojd_mm, "hojd_mm")}, level=lv, elevation_offset=float(forskjutning_mm or 0))
    if material:
        e["material"] = material
    return m.propose_add(e, f"balk {round(math.dist(A, B))} mm")


@tool("skapa_ror", "Föreslå ett rör längs en väg. DN, system och höjd över nivån krävs.",
      {"vag": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "[[x,y],...] mm, minst två punkter", "required": True},
       "dn": {"type": "number", "required": True}, "system": {"type": "string", "description": "t.ex. KV, VV, VVC, S", "required": True},
       "niva": {"type": "string", "required": True}, "hojd_mm": {"type": "number", "description": "rörets höjd över nivån", "required": True}, "material": {"type": "string"}}, writes=True)
def skapa_ror(m: CadAgentModel, vag, dn, system, niva, hojd_mm, material: str = "") -> dict:
    lv = _level(m, niva)
    pts = _pts(vag, "vag", 2)
    e = dict(_common(m, "VVS", lv), type="pipe", path=[[p[0], p[1], 0.0] for p in pts], dn=_num(dn, "dn"), system=str(system), level=lv, elevation=float(hojd_mm))
    if material:
        e["material"] = material
    return m.propose_add(e, f"rör {system} DN{e['dn']:g}, {round(G.path_length(e['path']) / 1000, 1)} m")


@tool("skapa_kanal", "Föreslå en ventilationskanal längs en väg. Rektangulär (bredd×höjd) eller rund (diameter); system och höjd krävs.",
      {"vag": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "required": True},
       "system": {"type": "string", "required": True}, "niva": {"type": "string", "required": True}, "hojd_over_niva_mm": {"type": "number", "required": True},
       "bredd_mm": {"type": "number", "description": "bredd, eller diameter för rund"}, "hojd_mm": {"type": "number", "description": "höjd; utelämnas för rund"}}, writes=True)
def skapa_kanal(m: CadAgentModel, vag, system, niva, hojd_over_niva_mm, bredd_mm=None, hojd_mm=None) -> dict:
    lv = _level(m, niva)
    pts = _pts(vag, "vag", 2)
    e = dict(_common(m, "VENT", lv), type="duct", path=[[p[0], p[1], 0.0] for p in pts], system=str(system), level=lv, elevation=float(hojd_over_niva_mm))
    if hojd_mm not in (None, 0):
        e.update(shape="rect", w=_num(bredd_mm, "bredd_mm"), h=_num(hojd_mm, "hojd_mm"))
    else:
        e.update(shape="round", d=_num(bredd_mm, "bredd_mm"))
    return m.propose_add(e, f"kanal {system}")


@tool("skapa_niva", "Föreslå en ny nivå med namn och höjd över noll.",
      {"namn": {"type": "string", "required": True}, "hojd_mm": {"type": "number", "description": "höjd över ±0; noll är tillåtet", "required": True}}, writes=True)
def skapa_niva(m: CadAgentModel, namn, hojd_mm) -> dict:
    try:
        z = float(hojd_mm)
    except (TypeError, ValueError):
        raise ValueError("hojd_mm måste vara ett tal") from None
    if any(abs(float(l.get("elevation_mm") or 0) - z) < 1 for l in m.doc.get("levels") or []):
        raise ValueError("det finns redan en nivå på den höjden")
    lv = {"id": "lv_" + uuid.uuid4().hex[:8], "name": str(namn), "elevation_mm": z}
    m.doc = dict(m.doc, levels=list(m.doc.get("levels") or []) + [lv])
    m.proposals.append({"op": "add", "collection": "levels", "item": lv, "why": f"nivå {namn} på {z:g} mm"})
    return {"forslag": "registrerat - kräver godkännande i ritbordet", "niva": lv}


@tool("flytta", "Föreslå att ett objekt flyttas dx, dy millimeter i planen.",
      {"id": {"type": "string", "required": True}, "dx_mm": {"type": "number", "required": True}, "dy_mm": {"type": "number", "required": True}}, writes=True)
def flytta(m: CadAgentModel, id, dx_mm, dy_mm) -> dict:
    e = m.entity(id)
    if not e:
        raise ValueError(f"inget objekt med id {id}")
    if e.get("type") in ("door", "window", "opening"):
        raise ValueError("det som sitter i en vägg flyttas längs väggen: ändra fältet t med andra")
    dx, dy = float(dx_mm), float(dy_mm)
    after = dict(e, version=int(e.get("version") or 1) + 1)
    if "path" in e:
        after["path"] = [[p[0] + dx, p[1] + dy] + list(p[2:]) for p in e["path"]]
    elif "points" in e:
        after["points"] = [[p[0] + dx, p[1] + dy] + list(p[2:]) for p in e["points"]]
    elif "p" in e:
        after["p"] = [[p[0] + dx, p[1] + dy] + list(p[2:]) for p in e["p"]]
        if e.get("ridge"):
            after["ridge"] = [[p[0] + dx, p[1] + dy] for p in e["ridge"]]
    m.proposals.append({"op": "update", "collection": "entities", "before": e, "after": after, "why": f"flytta {id} ({dx:g}, {dy:g})"})
    return {"forslag": "registrerat - kräver godkännande i ritbordet", "objekt": after}


@tool("andra", "Föreslå att ett fält på ett objekt får ett nytt värde (t.ex. thickness, height, name, material, dn, system, t, width).",
      {"id": {"type": "string", "required": True}, "falt": {"type": "string", "required": True},
       "varde": {"description": "det nya värdet: tal eller text", "required": True}}, writes=True)
def andra(m: CadAgentModel, id, falt, varde) -> dict:
    e = m.entity(id)
    if not e:
        raise ValueError(f"inget objekt med id {id}")
    if falt in ("id", "type", "version", "provenance"):
        raise ValueError(f"{falt} kan inte ändras")
    if falt in ("thickness", "height", "width", "dn", "sill", "risers", "tread_d", "w", "h", "d", "elevation", "off") and varde is not None:
        varde = float(varde) if falt != "risers" else int(varde)
        if falt != "sill" and falt != "elevation" and falt != "off" and varde <= 0:
            raise ValueError(f"{falt} måste vara större än noll")
    if falt == "t":
        varde = float(varde)
        if not 0 <= varde <= 1:
            raise ValueError("t är en andel längs väggen, 0-1")
    after = dict(e, version=int(e.get("version") or 1) + 1)
    after[falt] = varde
    probs = [p for p in cad_model.validate(dict(m.doc, entities=[after if x.get("id") == id else x for x in m.doc.get("entities") or []])) if p.get("id") == id]
    if probs:
        raise ValueError("ändringen skulle avvisas: " + "; ".join(p["message"] for p in probs))
    m.proposals.append({"op": "update", "collection": "entities", "before": e, "after": after, "why": f"{id}: {falt} → {varde!r}"})
    return {"forslag": "registrerat - kräver godkännande i ritbordet", "objekt": after}


@tool("ta_bort", "Föreslå att ett objekt tas bort (det som sitter i det följer med).", {"id": {"type": "string", "required": True}}, writes=True)
def ta_bort(m: CadAgentModel, id) -> dict:
    e = m.entity(id)
    if not e:
        raise ValueError(f"inget objekt med id {id}")
    m.proposals.append({"op": "remove", "collection": "entities", "item": e, "why": f"ta bort {id}"})
    hosted = [h for h in m.doc.get("entities") or [] if h.get("host") == id]
    for h in hosted:
        m.proposals.append({"op": "remove", "collection": "entities", "item": h, "why": f"ta bort {h['id']} (satt i {id})"})
    return {"forslag": "registrerat - kräver godkännande i ritbordet", "tas_bort": [id] + [h["id"] for h in hosted]}


# ---------------------------------------------------------------- registret, i samma form som ritningsagentens

def run(name: str, model: CadAgentModel, args: dict[str, Any]) -> dict[str, Any]:
    t = TOOLS.get(name)
    if t is None:
        return {"fel": f"okänt verktyg {name}", "tillgangliga": sorted(TOOLS)}
    try:
        return t["fn"](model, **{k: v for k, v in (args or {}).items() if k != "self"})
    except TypeError as e:
        # ett mått som saknas är en fråga till användaren, inte ett antagande
        return {"fel": f"fel argument till {name}: {e}", "fraga_anvandaren": True}
    except ValueError as e:
        return {"fel": str(e), "fraga_anvandaren": True}
    except Exception as e:                                      # noqa: BLE001
        return {"fel": f"{name} kunde inte köras: {type(e).__name__}: {e}"}


def schemas() -> list[dict[str, Any]]:
    return [{"type": "function", "name": t["name"], "description": t["description"], "parameters": t["parameters"]} for t in TOOLS.values()]


def writes(name: str) -> bool:
    return bool((TOOLS.get(name) or {}).get("writes"))
