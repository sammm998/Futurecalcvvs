"""Changes to a reading, proposed rather than made.

The reading measures what it can defend. A person looking at the same sheet sees things the engine has no rule
for yet: a run it declined, a stretch it gave to the wrong designation, a size it read from the wrong label.
These tools turn such an observation into a correction - the same correction the drawing tools write, layered
over the reading by `corrections.apply` and undoable one at a time.

Two rules hold everything here up.

The first: every metre in a proposal comes out of the reading. A tool takes runs the reading already measured,
or geometry the reading already declined, and reads the length off that. No caller - person or model - states a
number that becomes a metre. That is what makes a proposal checkable: it says which runs it touched and what
they measure, and those two numbers are the reading's own.

The second: a proposal is not a change. Nothing in this module writes anything. It returns what it would record
and why, and a person accepts it. When the drawing does not support the change, it says so and proposes nothing
at all - `AVBOJD` is a real answer here for the same reason AMBIGUOUS is a real answer in the reading.
"""
from __future__ import annotations

import math
from typing import Any

from .model import DrawingModel
from .tools import _num, _set, tool

from .. import rules as _rules


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


# a proposal that would touch this much of the sheet is almost certainly a misunderstanding rather than a
# correction, and a person confirming a one-line summary cannot see that it was
LARGE_CHANGE_M = 50.0


def _refuse(why: str, **extra) -> dict:
    """No proposal, and the reason. What the drawing does not support, the agent does not offer."""
    return {"tillstand": "AVBOJD", "skal": why, "forslag": [], **extra}


def _offer(forslag: list[dict], sammanfattning: str, pipe_ids: list[str] | None = None, **extra) -> dict:
    total = round(sum(abs(_num(f.get("meter"))) for f in forslag), 3)
    return {"tillstand": "FORESLAGEN", "forslag": forslag, "sammanfattning": sammanfattning,
            "berord_meter": total, "stor_andring": total > _R("agent.edits.LARGE_CHANGE_M", LARGE_CHANGE_M),
            "pipe_ids": pipe_ids or [], **extra}


def _pipes(m: DrawingModel, pipe_ids: Any) -> tuple[list[dict], str | None]:
    """The runs named, or the reason they cannot be used. Ids are the reading's own; nothing else is accepted."""
    if isinstance(pipe_ids, str):
        pipe_ids = [pipe_ids]
    ids = [str(i) for i in (pipe_ids or []) if str(i).strip()]
    if not ids:
        return [], "inga rör angivna; en ändring måste peka på sträckor läsningen redan har"
    missing = [i for i in ids if i not in m.pipe_by_id]
    if missing:
        return [], f"läsningen känner inte till {', '.join(missing[:6])}"
    seen: set[str] = set()
    return [m.pipe_by_id[i] for i in ids if not (i in seen or seen.add(i))], None


def _by_designation(pipes: list[dict]) -> dict[str, dict]:
    """The named runs grouped by the designation they currently carry, with the metres each group holds."""
    out: dict[str, dict] = {}
    for p in pipes:
        d = p.get("designation") or "(namnlös)"
        g = out.setdefault(d, {"meter": 0.0, "pipe_ids": [], "dn": p.get("dn")})
        g["meter"] = round(g["meter"] + _num(p.get("horizontal_m")), 3)
        g["pipe_ids"].append(p["physical_pipe_id"])
    return out


def _written_designations(m: DrawingModel) -> dict[str, dict]:
    """The names a quantity can actually hang on, as the reading composes them.

    Not every row of recognised text is one. A sheet writes `S3-R8` on one line and its size on the next, and the
    reading composes the two into `S3-R8-75` - that composed name is what a takeoff row is keyed on, and writing
    metres to the half-name would put them in a row that stands beside the real one and belongs to nothing. So
    the candidates are exactly the names the reading itself uses: the ones it measured, and the ones it attached
    to a pipe but could not measure. The second set matters most - it is where a stretch the reading missed has
    to go.
    """
    out: dict[str, dict] = {}
    for r in (m.quantities.get("rows") or []):
        n = str(r.get("designation") or "").strip()
        if n:
            out.setdefault(n, {"base": r.get("base"), "dn": r.get("dn"), "matt": True})
    for a in m.anchors:
        if not a.get("names_a_pipe"):
            continue
        n = str(a.get("designation_display") or "").strip()
        if n:
            out.setdefault(n, {"base": a.get("designation"), "dn": a.get("dn"), "matt": False})
    return out


def _same_base(a: dict, b: dict) -> bool:
    """Two names that differ only in size: the same system and material, a different DN."""
    return bool(a.get("base")) and a.get("base") == b.get("base")


def _polyline_m(points: list[list[float]], mpp: float) -> float:
    return round(sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)) * mpp, 3)


def _correction(kind: str, designation: str, meter: float, text: str, **payload) -> dict:
    """One row for the correction log, in the shape `corrections.apply` reads."""
    return {"kind": kind, "designation": designation, "meter": round(meter, 3),
            "text": text, "payload": {k: v for k, v in payload.items() if v is not None}}


# ---------------------------------------------------------------- take metres off


@tool("foresla_radera_ror",
      "Föreslå att sträckor tas bort ur mängden - de är inte rör, eller de hör inte till det här bladet. "
      "Metrarna hämtas ur läsningen, inte ur frågan.",
      {"ror_id": {"type": "array", "items": {"type": "string"},
                  "description": "Rören som ska tas bort, med läsningens egna id.", "required": True},
       "skal": {"type": "string", "description": "Varför de inte ska räknas."}},
      writes=True)
def foresla_radera_ror(m: DrawingModel, ror_id=None, skal: str = "") -> dict:
    pipes, why = _pipes(m, ror_id)
    if why:
        return _refuse(why)
    groups = _by_designation(pipes)
    forslag = [_correction("erase", name, -g["meter"],
                           f"{name}: {g['meter']:.2f} m tas bort ({len(g['pipe_ids'])} sträckor)",
                           meters=g["meter"], pipe_ids=g["pipe_ids"], reason=skal or None)
               for name, g in sorted(groups.items())]
    total = sum(g["meter"] for g in groups.values())
    return _offer(forslag, f"Tar bort {total:.2f} m fördelat på {len(pipes)} sträckor i "
                           f"{len(groups)} beteckning{'ar' if len(groups) != 1 else ''}.",
                  [p["physical_pipe_id"] for p in pipes])


# ---------------------------------------------------------------- move metres between designations


@tool("foresla_byt_beteckning",
      "Föreslå att sträckor får en annan beteckning - läsningen knöt dem till fel beteckning. Metrarna flyttas "
      "mellan beteckningarna; inga nya meter uppstår.",
      {"ror_id": {"type": "array", "items": {"type": "string"},
                  "description": "Rören som ska byta beteckning.", "required": True},
       "till_beteckning": {"type": "string", "description": "Beteckningen de ska tillhöra. Måste stå på bladet.",
                           "required": True},
       "skal": {"type": "string", "description": "Vad på ritningen som säger det."}},
      writes=True)
def foresla_byt_beteckning(m: DrawingModel, ror_id=None, till_beteckning: str = "", skal: str = "") -> dict:
    pipes, why = _pipes(m, ror_id)
    if why:
        return _refuse(why)
    target = str(till_beteckning or "").strip()
    written = _written_designations(m)
    if not target:
        return _refuse("ingen målbeteckning angiven")
    if target not in written:
        # The one thing this system must never do is invent an identity. A designation the sheet does not write
        # is not a candidate, however plausible it looks beside the ones it does write.
        return _refuse(f"{target} är ingen beteckning läsningen mängdar på, så inga meter kan flyttas dit",
                       beteckningar=sorted(written)[:40])
    groups = _by_designation(pipes)
    if list(groups) == [target]:
        return _refuse(f"sträckorna har redan beteckningen {target}")
    forslag = []
    for name, g in sorted(groups.items()):
        if name == target:
            continue
        forslag.append(_correction("retag", target, g["meter"],
                                   f"{g['meter']:.2f} m flyttas från {name} till {target}",
                                   meters=g["meter"], **{"from": name}, pipe_ids=g["pipe_ids"],
                                   reason=skal or None))
    total = sum(f["meter"] for f in forslag)
    return _offer(forslag, f"Flyttar {total:.2f} m till {target} från "
                           f"{', '.join(n for n in sorted(groups) if n != target)}.",
                  [p["physical_pipe_id"] for p in pipes])


# ---------------------------------------------------------------- change the size


@tool("foresla_andra_dimension",
      "Föreslå att sträckor har en annan dimension än läsningen gav dem. Målbeteckningen är samma system och "
      "material med en annan storlek, och den måste stå på bladet.",
      {"ror_id": {"type": "array", "items": {"type": "string"},
                  "description": "Rören vars dimension är fel.", "required": True},
       "ny_dimension": {"type": "integer", "description": "Dimensionen ritningen anger, till exempel 110.",
                        "required": True},
       "skal": {"type": "string", "description": "Vilken beteckning eller vilket mått som säger det."}},
      writes=True)
def foresla_andra_dimension(m: DrawingModel, ror_id=None, ny_dimension=None, skal: str = "") -> dict:
    pipes, why = _pipes(m, ror_id)
    if why:
        return _refuse(why)
    if not _set(ny_dimension):
        return _refuse("ingen ny dimension angiven")
    dn = int(_num(ny_dimension))
    written = _written_designations(m)
    forslag, notes = [], []
    for name, g in sorted(_by_designation(pipes).items()):
        src = written.get(name)
        if src is None:
            notes.append(f"{name} är ingen beteckning läsningen mängdar på, så den har ingen storlek att byta")
            continue
        if int(_num(src.get("dn"))) == dn:
            notes.append(f"{name} är redan DN{dn}")
            continue
        # the sibling the sheet itself writes: same system and material, the size asked for
        target = next((t for t, d in sorted(written.items())
                       if int(_num(d.get("dn"))) == dn and _same_base(src, d)), None)
        if target is None:
            siblings = sorted({int(_num(d.get("dn"))) for d in written.values()
                               if _same_base(src, d) and _num(d.get("dn"))})
            notes.append(f"läsningen har ingen DN{dn} för {name}; den har "
                         f"{', '.join('DN' + str(s) for s in siblings) or 'ingen annan storlek'}")
            continue
        forslag.append(_correction("retag", target, g["meter"],
                                   f"{g['meter']:.2f} m flyttas från {name} till {target} (DN{dn})",
                                   meters=g["meter"], **{"from": name}, pipe_ids=g["pipe_ids"],
                                   reason=skal or None))
    if not forslag:
        return _refuse("; ".join(notes) or f"ingen av sträckorna kan byta till DN{dn}")
    total = sum(f["meter"] for f in forslag)
    return _offer(forslag, f"Byter dimension till DN{dn} på {total:.2f} m.",
                  [p["physical_pipe_id"] for p in pipes], anmarkningar=notes)


# ---------------------------------------------------------------- break a run in two


def _cut_parts(p: dict, at: tuple[float, float], side: tuple[float, float]) -> tuple[Any, Any]:
    """Split one run's drawn geometry at a vertex and return (the part to move, the part that stays).

    A run is not one polyline. It is every stroke the drawing gave that identity, and their order in the file
    says nothing about the order they lie in on the sheet - so a cut along the list would hand back two halves
    that are not two halves of anything. The cut is made in the run's own connectivity instead: the vertex
    nearest the point is removed, what falls apart falls apart, and each piece is one connected part of the run.
    Every stroke ends up in exactly one part, so the two always add back up to the whole.
    """
    def key(v) -> tuple[float, float]:
        return (round(float(v[0]), 2), round(float(v[1]), 2))

    edges: list[tuple[tuple[float, float], tuple[float, float], float]] = []
    for line in (p.get("geometry") or []):
        for i in range(len(line) - 1):
            a, b = key(line[i]), key(line[i + 1])
            if a != b:
                edges.append((a, b, math.dist(a, b)))
    if not edges:
        return None, "sträckan har ingen ritad geometri att dela"
    verts = {v for a, b, _ in edges for v in (a, b)}
    cut = min(verts, key=lambda v: math.dist(v, at))

    adj: dict[tuple[float, float], set] = {v: set() for v in verts}
    for a, b, _ in edges:
        if a == cut or b == cut:
            continue
        adj[a].add(b); adj[b].add(a)
    comp: dict[tuple[float, float], int] = {}
    n = 0
    for v in sorted(verts):
        if v == cut or v in comp:
            continue
        stack, n = [v], n + 1
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp[cur] = n
            stack.extend(w for w in adj[cur] if w not in comp)
    if n < 2:
        return None, "punkten delar inte sträckan: allt hänger ihop förbi den ändå"

    # a stroke that ends at the cut belongs to whichever side its other end is on, so nothing is lost in the cut
    length: dict[int, float] = {}
    for a, b, d in edges:
        c = comp.get(a) or comp.get(b)
        if c:
            length[c] = length.get(c, 0.0) + d
    want = min((v for v in verts if v != cut), key=lambda v: math.dist(v, side))
    ci = comp.get(want)
    if not ci:
        return None, "punkten som pekar ut delen ligger på själva delningspunkten"
    drawn = sum(length.values())
    if drawn <= 0:
        return None, "sträckan har ingen längd att dela"
    return {"cut": cut, "part": ci, "parts": length, "drawn_pt": drawn,
            "share": length.get(ci, 0.0) / drawn, "n_parts": n}, None


@tool("foresla_dela_ror",
      "Föreslå att en sträcka delas och att den ena delen får en annan beteckning - ritningen byter dimension "
      "eller material mitt i sträckan. Delarnas längder är rörets egna meter, och de summerar till hela röret.",
      {"ror_id": {"type": "string", "description": "Sträckan som ska delas.", "required": True},
       "vid_punkt": {"type": "array", "items": {"type": "number"},
                     "description": "Punkten [x, y] där ritningen byter.", "required": True},
       "pa_delen": {"type": "array", "items": {"type": "number"},
                    "description": "En punkt [x, y] på den del som ska få den nya beteckningen.",
                    "required": True},
       "ny_beteckning": {"type": "string", "description": "Beteckningen den delen ska ha. Måste vara en "
                                                          "beteckning läsningen mängdar på.", "required": True},
       "skal": {"type": "string", "description": "Vad som säger att bytet sker där."}},
      writes=True)
def foresla_dela_ror(m: DrawingModel, ror_id: str = "", vid_punkt=None, pa_delen=None,
                     ny_beteckning: str = "", skal: str = "") -> dict:
    pipes, why = _pipes(m, ror_id)
    if why:
        return _refuse(why)
    p = pipes[0]
    if not m.meters_per_pt:
        return _refuse("ritningens skala är inte fastställd, så delarna har ingen längd")
    target = str(ny_beteckning or "").strip()
    written = _written_designations(m)
    if target not in written:
        return _refuse(f"{target} är ingen beteckning läsningen mängdar på, så ingen del kan få den",
                       beteckningar=sorted(written)[:40])
    name = p.get("designation") or "(namnlös)"
    if target == name:
        return _refuse(f"sträckan har redan beteckningen {target}; en delning som inte byter något ändrar inget")
    try:
        at = (float(vid_punkt[0]), float(vid_punkt[1]))                 # type: ignore[index]
        side = (float(pa_delen[0]), float(pa_delen[1]))                 # type: ignore[index]
    except Exception:
        return _refuse("både vid_punkt och pa_delen måste vara [x, y] i ritningens koordinater")

    cut, err = _cut_parts(p, at, side)
    if err:
        return _refuse(err)
    # The run measures more than its strokes where the reading bridged a gap in a dashed line. The parts carry
    # that in proportion to what each of them draws, so the two still add up to the metre the takeoff shows.
    total = _num(p.get("horizontal_m"))
    moved = round(total * cut["share"], 3)
    stays = round(total - moved, 3)
    if moved <= 0:
        return _refuse("delen som skulle byta beteckning är noll meter lång")
    forslag = [_correction("retag", target, moved,
                           f"{moved:.2f} m av {name} blir {target}",
                           meters=moved, **{"from": name}, pipe_ids=[p["physical_pipe_id"]],
                           split_at=[cut["cut"][0], cut["cut"][1]], reason=skal or None)]
    return _offer(forslag, f"Delar {name} vid [{cut['cut'][0]:.0f}, {cut['cut'][1]:.0f}]: {stays:.2f} m stannar "
                           f"som {name}, {moved:.2f} m blir {target}.",
                  [p["physical_pipe_id"]],
                  delning={"kvar_m": stays, "flyttas_m": moved, "vid": [cut["cut"][0], cut["cut"][1]],
                           "antal_delar": cut["n_parts"], "rorets_meter": round(total, 3)})


# ---------------------------------------------------------------- draw what the reading declined


@tool("hitta_omatt_geometri_att_rita",
      "Ritad geometri läsningen inte tog som rör men som något på bladet pekar på - kandidater att rita in.", {})
def hitta_omatt_geometri_att_rita(m: DrawingModel) -> dict:
    out = []
    for f in (m.declined.get("families") or []) + (m.declined.get("unconsidered") or []):
        # A leader end resting on the geometry is the sheet pointing at it. Label votes alone are proximity, and
        # proximity is what this system refuses: the biggest thing near a pipe label on most sheets is the wall.
        if not _num(f.get("leader_ends_touching")):
            continue
        out.append({"geometri_id": f.get("family"), "meter": round(_num(f.get("length_m")), 2),
                    "skal": f.get("why_sv") or f.get("why"), "lager": f.get("layer"),
                    "hanvisningar_som_ror_den": int(_num(f.get("leader_ends_touching"))),
                    "etikettroster": round(_num(f.get("label_votes")), 1),
                    "antal_segment": int(_num(f.get("n_segments")))})
    out.sort(key=lambda r: -r["meter"])
    return {"antal": len(out), "kandidater": out[:40]}


@tool("foresla_rita_ror",
      "Föreslå att geometri läsningen valde bort räknas som rör under en beteckning. Bara geometri något på "
      "bladet pekar på kan ritas in, och metrarna är den ritade längden.",
      {"geometri_id": {"type": "string", "description": "Id från hitta_omatt_geometri_att_rita.",
                       "required": True},
       "beteckning": {"type": "string", "description": "Beteckningen den ska tillhöra. Måste stå på bladet.",
                      "required": True},
       "skal": {"type": "string", "description": "Vad på ritningen som knyter geometrin till beteckningen."}},
      writes=True)
def foresla_rita_ror(m: DrawingModel, geometri_id: str = "", beteckning: str = "", skal: str = "") -> dict:
    if not m.meters_per_pt:
        return _refuse("ritningens skala är inte fastställd, så den ritade linjen har ingen längd att lägga till")
    target = str(beteckning or "").strip()
    written = _written_designations(m)
    if target not in written:
        return _refuse(f"{target} är ingen beteckning läsningen mängdar på, så ingen geometri kan skrivas "
                       f"på den", beteckningar=sorted(written)[:40])
    fam = next((f for f in (m.declined.get("families") or []) + (m.declined.get("unconsidered") or [])
                if f.get("family") == geometri_id), None)
    if fam is None:
        return _refuse(f"läsningen har ingen bortvald geometri med id {geometri_id}")
    touching, votes = _num(fam.get("leader_ends_touching")), _num(fam.get("label_votes"))
    if not touching:
        # No leader end rests on it, so nothing on the sheet points at this geometry. A label lying near it is
        # not the sheet saying so - the nearest thing to a pipe label is very often the wall - and handing it a
        # designation on that basis is exactly the guess this system exists to refuse.
        return _refuse("ingen hänvisningslinje från någon beteckning rör den geometrin, så den kan inte knytas "
                       "till en beteckning; att den ligger nära en etikett räcker inte",
                       etikettroster=round(votes, 1), lager=fam.get("layer"))
    meters = round(_num(fam.get("length_m")), 3)
    if meters <= 0:
        return _refuse("geometrin har ingen längd")
    points = [[s[0], s[1]] for s in (fam.get("segments") or [])] + \
             ([[(fam.get("segments") or [])[-1][2], (fam.get("segments") or [])[-1][3]]]
              if fam.get("segments") else [])
    forslag = [_correction("draw", target, meters,
                           f"{meters:.2f} m ritad geometri räknas som {target}",
                           meters=meters, points=points, geometry_family=geometri_id, reason=skal or None)]
    return _offer(forslag, f"Lägger {meters:.2f} m till {target} från geometri läsningen valde bort "
                           f"({fam.get('why_sv') or fam.get('why')}).",
                  bevis={"hanvisningar_som_ror_den": int(touching), "etikettroster": round(votes, 1),
                         "lager": fam.get("layer")})


# ---------------------------------------------------------------- carry a run on past where it stopped

# Where the reading itself says it probably lost metres. A run that stops for one of these reasons stops
# because the reading ran out, not because the drawing did - and those are the only ends worth carrying on.
LOSSY_FRONTIERS = ("UNOWNED_CONTINUATION", "BROKEN_CONTINUITY", "REPRESENTATION_CHANGE")

FRONTIER_SV = {
    "UNOWNED_CONTINUATION": "samma penna fortsätter och ingen etikett når fram dit",
    "BROKEN_CONTINUITY": "samma penna fortsätter i samma riktning efter ett gap som inte kunde slutas",
    "REPRESENTATION_CHANGE": "ledningen fortsätter på en annan penna",
}


def _lossy_ends(m: DrawingModel, pipe_id: str) -> list[dict]:
    """The ends of one run where the reading says the pipe carries on and it stopped anyway."""
    return [f for f in m.frontiers_by_pipe.get(pipe_id, []) if f.get("reason") in LOSSY_FRONTIERS]


def _beyond_pt(fronts: list[dict]) -> float:
    """How much unowned ink lies past those ends, counted once per end."""
    return sum(_num((f.get("detail") or {}).get("unowned_pt")) for f in fronts)


@tool("hitta_ror_att_forlanga",
      "Rör som slutar där läsningen tog slut, inte där ritningen tar slut - kandidater att förlänga, med hur "
      "mycket oägt bläck som ligger bortom varje ände.", {})
def hitta_ror_att_forlanga(m: DrawingModel) -> dict:
    mpp = m.meters_per_pt
    out = []
    for p in m.pipes:
        fronts = _lossy_ends(m, p["physical_pipe_id"])
        if not fronts:
            continue
        pt = _beyond_pt(fronts)
        if pt <= 0:
            continue
        out.append({"ror_id": p["physical_pipe_id"], "beteckning": p.get("designation"), "dn": p.get("dn"),
                    "blad": p.get("page", 0),
                    "mangd_nu_m": round(_num(p.get("horizontal_m")), 2),
                    "bortom_anden_m": round(pt * mpp, 2) if mpp else None,
                    "bortom_anden_pt": round(pt, 2),
                    "skal": sorted({FRONTIER_SV.get(f["reason"], f["reason"]) for f in fronts}),
                    "punkter": [[round(_num(f.get("x")), 1), round(_num(f.get("y")), 1)] for f in fronts]})
    out.sort(key=lambda r: -(r["bortom_anden_m"] or r["bortom_anden_pt"]))
    return {"antal": len(out), "kandidater": out[:40],
            "skala_fastställd": bool(mpp)}


@tool("foresla_forlang_ror",
      "Föreslå att ett rör förlängs ut i det ritade bläck som fortsätter förbi den ände där läsningen stannade. "
      "Metrarna är den ritade längden bortom änden, mätt av läsningen - aldrig ett tal ur frågan.",
      {"ror_id": {"type": "string", "description": "Röret som ska förlängas, med läsningens eget id.",
                  "required": True},
       "skal": {"type": "string", "description": "Vad på ritningen som säger att ledningen fortsätter."}},
      writes=True)
def foresla_forlang_ror(m: DrawingModel, ror_id: str = "", skal: str = "") -> dict:
    """Carry a run on into the ink that continues past it.

    A run ends for a reason, and the reading writes that reason down. Four of them are the drawing's own - the
    size changes, the system changes, it goes into a riser, it leaves the sheet - and a run that ends for one of
    those ends where it is drawn to end. Three are the reading running out: the pen carries on and no label
    reaches that far, a gap could not be closed, the line continues in another pen. Only those are offered here,
    and only with the metres the reading measured beyond the end.

    What it refuses is the whole point. Asked to extend a run that ends at a real boundary it says which
    boundary and proposes nothing: extending there would take metres from the pipe on the other side and hand
    them to this one, and the sheet already said whose they are.
    """
    p = m.pipe_by_id.get(str(ror_id))
    if p is None:
        return _refuse(f"inget rör med id {ror_id}")
    if not m.meters_per_pt:
        return _refuse("ritningens skala är inte fastställd, så det som ligger bortom änden har ingen längd "
                       "att lägga till")
    alla = m.frontiers_by_pipe.get(str(ror_id), [])
    if not alla:
        return _refuse("läsningen har ingen kant för det röret, så det går inte att säga var det slutar")
    fronts = _lossy_ends(m, str(ror_id))
    if not fronts:
        return _refuse("röret slutar där ritningen säger att det slutar, inte där läsningen tog slut",
                       kanter=sorted({f.get("reason") for f in alla}),
                       skal_per_kant=sorted({f.get("reason") for f in alla}))
    pt = _beyond_pt(fronts)
    if pt <= 0:
        return _refuse("ingenting ritat fortsätter förbi den änden, så det finns inga meter att lägga till",
                       kanter=sorted({f.get("reason") for f in fronts}))
    meters = round(pt * m.meters_per_pt, 3)
    if meters > LARGE_CHANGE_M:
        return _refuse(f"förlängningen är {meters:.1f} m, mer än {LARGE_CHANGE_M:.0f} m - det är inte en "
                       f"rättelse av ett rör utan en omläsning av bladet, och den ska inte gå att godta på en "
                       f"rads sammanfattning", meter=meters)
    name = p.get("designation")
    if not name:
        return _refuse("röret har ingen beteckning att skriva metrarna på")
    forslag = [_correction("extend", name, meters,
                           f"{name}: {meters:.2f} m till där ledningen fortsätter förbi änden",
                           meters=meters, pipe_ids=[p["physical_pipe_id"]],
                           points=[[round(_num(f.get("x")), 2), round(_num(f.get("y")), 2)] for f in fronts],
                           frontier_reasons=sorted({f.get("reason") for f in fronts}),
                           reason=skal or None)]
    return _offer(forslag,
                  f"Förlänger {name} med {meters:.2f} m: "
                  + ", ".join(sorted({FRONTIER_SV.get(f["reason"], f["reason"]) for f in fronts})) + ".",
                  [p["physical_pipe_id"]],
                  bevis={"mangd_nu_m": round(_num(p.get("horizontal_m")), 2),
                         "bortom_anden_pt": round(pt, 2),
                         "kanter": sorted({f.get("reason") for f in fronts})})
