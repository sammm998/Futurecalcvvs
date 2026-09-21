"""Var varje rör slutar, och varför. Inget rör slutar tyst.

Ett fysiskt rör är den sammanhängande geometri som en identitet äger. Där ägandet tar slut finns en kant -
en *front* - och läsningen är inte färdig förrän varje sådan kant har ett skäl som pekar på pappret. Skälet
är det som skiljer en mätning från en gissning: "röret slutar här därför att nästa bit bär DN 22 och den här
bär DN 15" går att granska; "röret slutar här" går inte.

Skälen, i den ordning en granskare frågar efter dem:

  REAL_DN_BOUNDARY          samma ledning fortsätter med en annan dimension (etikett på båda sidor)
  REAL_SYSTEM_BOUNDARY      geometrin fortsätter men tillhör ett annat system
  REAL_DESIGNATION_BOUNDARY samma system, annat namn eller annan isolering/ytbeklädnad
  DECLARED_BOUNDARY         fortsättningen ägs av bladets skrivna regel för anslutningsrör, inte av en etikett
  AMBIGUOUS_JUNCTION        fortsättningen är tvetydig: fler än en identitet gör anspråk på den
  FLOW_BUDGET               fortsättningen togs tillbaka av flödesbudgeten: identiteten hade runnit för långt
  UNOWNED_CONTINUATION      geometrin fortsätter på samma penna och ingen etikett når den - meter ingen äger
  REPRESENTATION_CHANGE     ledningen fortsätter på en annan penna (annat lager, annan bredd, annan färg)
  REPRESENTATION_TRANSITION samma penna fortsätter som en lång heldragen linje i en streckad familj: ett annat ritsätt
  BROKEN_CONTINUITY         samma penna fortsätter i samma riktning efter ett gap bryggningen inte slöt
  VERTICAL                  röret slutar i en stigarsymbol: det går upp eller ner
  SYMBOL                    röret slutar i en ritad komponent (ventil, pump, apparat)
  SHEET_EDGE                röret går ut ur bladet
  FREE_END                  linjen slutar och ingenting finns intill: så är det ritat
  CLOSED_LOOP               röret har ingen kant alls: en sluten slinga
  UNSUPPORTED_STRUCTURE     något läsningen inte kan sätta ord på - och det står så, i stället för inget

De fyra första är riktiga gränser: rätt ställe för ett rör att sluta. UNOWNED_CONTINUATION och BROKEN_CONTINUITY
är där läsningen sannolikt tappar meter, AMBIGUOUS_JUNCTION och FLOW_BUDGET där den lämnat något öppet med
flit. Summan av det oägda bortom fronterna är ett mått på underpropagering som går att följa körning för
körning, utan något referensmått alls.

Ingenting här flyttar en meter. Fronten beskriver ägandet som det blev; den ändrar det inte.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..geometry.core import GridIndex, dist
from .representation import family_key, page_symbols
from .ink import is_stroked
from ..geometry.core import point_seg_distance

REAL_DN_BOUNDARY = "REAL_DN_BOUNDARY"
REAL_SYSTEM_BOUNDARY = "REAL_SYSTEM_BOUNDARY"
REAL_DESIGNATION_BOUNDARY = "REAL_DESIGNATION_BOUNDARY"
DECLARED_BOUNDARY = "DECLARED_BOUNDARY"
AMBIGUOUS_JUNCTION = "AMBIGUOUS_JUNCTION"
FLOW_BUDGET = "FLOW_BUDGET"
UNOWNED_CONTINUATION = "UNOWNED_CONTINUATION"
REPRESENTATION_CHANGE = "REPRESENTATION_CHANGE"
REPRESENTATION_TRANSITION = "REPRESENTATION_TRANSITION"
BROKEN_CONTINUITY = "BROKEN_CONTINUITY"
VERTICAL = "VERTICAL"
SYMBOL = "SYMBOL"
SHEET_EDGE = "SHEET_EDGE"
FREE_END = "FREE_END"
CLOSED_LOOP = "CLOSED_LOOP"
UNSUPPORTED_STRUCTURE = "UNSUPPORTED_STRUCTURE"

REASONS: dict[str, str] = {
    REAL_DN_BOUNDARY: "samma ledning fortsätter med en annan dimension",
    REAL_SYSTEM_BOUNDARY: "geometrin fortsätter men tillhör ett annat system",
    REAL_DESIGNATION_BOUNDARY: "samma system, annat namn eller annan isolering",
    DECLARED_BOUNDARY: "fortsättningen ägs av bladets skrivna regel, inte av en etikett",
    AMBIGUOUS_JUNCTION: "fler än en identitet gör anspråk på fortsättningen",
    FLOW_BUDGET: "identiteten hade runnit för långt förbi etiketterna och togs tillbaka",
    UNOWNED_CONTINUATION: "samma penna fortsätter och ingen etikett når den",
    REPRESENTATION_CHANGE: "ledningen fortsätter på en annan penna",
    REPRESENTATION_TRANSITION: "samma penna fortsätter som en lång heldragen linje: ett annat ritsätt, och ingen etikett säger att det är röret",
    BROKEN_CONTINUITY: "samma penna fortsätter i samma riktning efter ett gap bryggningen inte slöt",
    VERTICAL: "röret slutar i en stigarsymbol",
    SYMBOL: "röret slutar i en ritad komponent",
    SHEET_EDGE: "röret går ut ur bladet",
    FREE_END: "linjen slutar och ingenting finns intill",
    CLOSED_LOOP: "en sluten slinga utan kant",
    UNSUPPORTED_STRUCTURE: "något läsningen inte kan sätta ord på",
}
# riktiga gränser: rätt ställe för ett rör att sluta
REAL = (REAL_DN_BOUNDARY, REAL_SYSTEM_BOUNDARY, REAL_DESIGNATION_BOUNDARY, DECLARED_BOUNDARY, VERTICAL, SYMBOL,
        SHEET_EDGE, FREE_END, CLOSED_LOOP)
# där läsningen sannolikt tappar meter
LOSSY = (UNOWNED_CONTINUATION, BROKEN_CONTINUITY, REPRESENTATION_CHANGE)
# lämnat öppet med flit
OPEN = (AMBIGUOUS_JUNCTION, FLOW_BUDGET, UNSUPPORTED_STRUCTURE, REPRESENTATION_TRANSITION)

ENDS_AT_OTHER_INK = "ENDS_AT_OTHER_INK"   # änden ligger an mot en annan pennas bläck: en fixtur, en apparat, en vägg
# vad en onämnd gren får ta korsningens namn på: dess fria ände slutar i något ritat, inte i tomma luften
BRANCH_END_EVIDENCE = (SYMBOL, SHEET_EDGE, REPRESENTATION_CHANGE, ENDS_AT_OTHER_INK)
OTHER_INK_REACH = 3.0   # pt: så nära en annan pennas streck ligger en ände an mot det

SHEET_MARGIN = 12.0     # pt: så nära bladets kant räknas en ände som utgående
RISER_REACH = 6.0       # pt: en stigarsymbol vars centrum ligger så nära änden är den stigare röret slutar i
JOIN_TOL = 2.0          # pt: en annan pennas nod så nära änden är samma punkt på pappret
BROKEN_MIN = 12.0       # pt: minsta räckvidd när ett gap söks; annars tre gap-moder
BROKEN_ANGLE = 15.0     # grader: fortsättningen ska ligga i ändens egen riktning
UNOWNED_WALK = 5000     # primitiver: så långt följs oägd geometri bortom en front innan räkningen får räcka


@dataclass
class Frontier:
    pipe_id: str
    family: str
    node: int | None
    x: float
    y: float
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"pipe": self.pipe_id, "family": self.family, "node": self.node, "x": round(self.x, 2),
                "y": round(self.y, 2), "reason": self.reason, "detail": self.detail}


def _unowned_reach(g, st, start: int) -> tuple[float, int]:
    """Hur mycket oägd geometri som hänger ihop med den här primitiven: meter ingen äger, i pt."""
    seen = {start}
    dq = deque([start])
    total = 0.0
    while dq and len(seen) <= UNOWNED_WALK:
        p = dq.popleft()
        total += g.prims[p].seg.length
        for nid in g.prim_nodes[p]:
            for q in g.nodes[nid].prims:
                if q not in seen and st[q].state == "UNOWNED":
                    seen.add(q)
                    dq.append(q)
    return total, len(seen)


def _beyond(pipe, g, st, q: int, declared_reason: str) -> tuple[str, dict[str, Any]]:
    """Vad den primitiv som fortsätter bortom noden är, sett från det här röret."""
    s = st[q]
    ident = pipe.identity
    if s.state == "CONFIRMED":
        if s.reason == declared_reason:
            return DECLARED_BOUNDARY, {"beyond": s.identity.key if s.identity else None, "rule": s.reason}
        other = s.identity
        if other is None or other.key == ident.key:
            return UNSUPPORTED_STRUCTURE, {"why": "samma identitet på andra sidan noden men inte samma rör",
                                           "beyond": other.key if other else None, "beyond_reason": s.reason}
        if other.system != ident.system:
            return REAL_SYSTEM_BOUNDARY, {"beyond": other.key, "beyond_reason": s.reason}
        if other.stem == ident.stem and other.dn != ident.dn and other.dn is not None and ident.dn is not None:
            return REAL_DN_BOUNDARY, {"beyond": other.key, "from_dn": ident.dn, "to_dn": other.dn, "beyond_reason": s.reason}
        return REAL_DESIGNATION_BOUNDARY, {"beyond": other.key, "beyond_reason": s.reason}
    if s.state == "AMBIGUOUS":
        cands = sorted(c.key for c in s.candidates)
        if s.reason == "AMBIGUOUS_FLOW_BEYOND_THE_LABELLED_RUNS":
            return FLOW_BUDGET, {"candidates": cands, "beyond_reason": s.reason}
        return AMBIGUOUS_JUNCTION, {"candidates": cands, "beyond_reason": s.reason}
    if getattr(g.prims[q], "solid_long", False):
        return REPRESENTATION_TRANSITION, {"solid_pt": round(g.prims[q].src_len or g.prims[q].seg.length, 1),
                                           "threshold_pt": round(g.solid_long_pt or 0.0, 1)}
    reach, n = _unowned_reach(g, st, q)
    return UNOWNED_CONTINUATION, {"unowned_pt": round(reach, 2), "unowned_prims": n}


def _outward(g, node, comp: set[int]) -> tuple[float, float] | None:
    """Riktningen ut ur röret vid noden: bort från rörets egen primitiv där."""
    for p in node.prims:
        if p in comp:
            a, b = g.prim_nodes[p]
            far = g.nodes[b] if a == node.nid else g.nodes[a]
            dx, dy = node.x - far.x, node.y - far.y
            L = math.hypot(dx, dy)
            return (dx / L, dy / L) if L > 1e-9 else None
    return None


def _terminal(pipe, g, st, node, comp: set[int], page, node_idx: dict[str, GridIndex], graphs, states,
              risers: list[tuple[tuple[float, float], str, dict]], symbols) -> tuple[str, dict[str, Any]]:
    """En ände där ingenting fortsätter i den egna grafen. Vad finns där, på pappret?"""
    x, y = node.x, node.y
    W = float(page.info.width or 0.0)
    H = float(page.info.height or 0.0)
    margin = min(x, y, W - x, H - y) if W > 0 and H > 0 else float("inf")
    if margin <= SHEET_MARGIN:
        return SHEET_EDGE, {"margin_pt": round(margin, 2)}
    near = [(dist((x, y), pt), key, rec) for pt, key, rec in risers]
    near = [t for t in near if t[0] <= RISER_REACH]
    if near:
        d, key, rec = min(near, key=lambda t: (t[0], t[1]))
        return VERTICAL, {"riser": key, "designation": rec.get("designation"), "distance_pt": round(d, 2),
                          "same_identity": key == pipe.identity.key}
    covering = symbols.covering(x, y, pipe.family)
    if covering:
        return SYMBOL, {"symbol_paths": covering[:6], "n_symbol_paths": len(covering)}
    # en annan penna som fortsätter från samma punkt
    best = None
    for fk2, idx2 in node_idx.items():
        if fk2 == pipe.family:
            continue
        for nid2 in idx2.query_point(x, y, JOIN_TOL):
            n2 = graphs[fk2].nodes[nid2]
            d = dist((x, y), (n2.x, n2.y))
            if d <= JOIN_TOL and (best is None or d < best[0]):
                sts = [states[fk2][p].state for p in n2.prims]
                best = (d, fk2, nid2, max(set(sts), key=sts.count))
    if best is not None:
        d, fk2, nid2, state2 = best
        return REPRESENTATION_CHANGE, {"family": fk2, "node": nid2, "beyond_state": state2, "distance_pt": round(d, 2)}
    # samma penna, samma riktning, efter ett gap bryggningen inte slöt
    out = _outward(g, node, comp)
    reach = max(BROKEN_MIN, 3.0 * float(g.gap_mode or 0.0))
    pipe_nodes = set(pipe.nodes)
    cand = None
    if out is not None:
        for nid2 in node_idx[pipe.family].query_point(x, y, reach):
            if nid2 == node.nid or nid2 in pipe_nodes:
                continue
            n2 = g.nodes[nid2]
            vx, vy = n2.x - x, n2.y - y
            d = math.hypot(vx, vy)
            if d < 1e-6 or d > reach:
                continue
            cosang = (vx * out[0] + vy * out[1]) / d
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
            if ang <= BROKEN_ANGLE and (cand is None or d < cand[0]):
                sts = [st[p].state for p in n2.prims]
                cand = (d, nid2, ang, max(set(sts), key=sts.count))
    if cand is not None:
        d, nid2, ang, state2 = cand
        return BROKEN_CONTINUITY, {"gap_pt": round(d, 2), "angle_deg": round(ang, 1), "to_node": nid2,
                                   "beyond_state": state2, "gap_mode_pt": g.gap_mode}
    return FREE_END, {"looked_pt": round(reach, 1)}


def frontiers_of(page, graphs: dict, ownership, risers: dict | None = None,
                 declared_reason: str = "DECLARED_CONNECTION_PIPE_BY_SHEET_TABLE") -> list[Frontier]:
    """Varje kant på varje fysiskt rör, med skäl. Ett rör utan kant får CLOSED_LOOP; inget rör saknar post."""
    node_idx: dict[str, GridIndex] = {}
    for fk, g in graphs.items():
        idx = GridIndex(cell=24.0)
        for n in g.nodes.values():
            idx.insert(n.nid, (n.x, n.y, n.x, n.y))
        node_idx[fk] = idx
    riser_pts: list[tuple[tuple[float, float], str, dict]] = []
    for key, lst in sorted((risers or {}).items()):
        for rec in lst:
            pt = rec.get("point") or rec.get("center")
            if pt and len(pt) >= 2:
                riser_pts.append(((float(pt[0]), float(pt[1])), key, rec))
    symbols = page_symbols(page)
    out: list[Frontier] = []
    for pipe in sorted(ownership.pipes, key=lambda p: p.physical_pipe_id):
        g = graphs[pipe.family]
        st = ownership.prim_states[pipe.family]
        comp = set(pipe.prim_ids)
        found = 0
        for nid in pipe.nodes:
            node = g.nodes[nid]
            outside = [q for q in node.prims if q not in comp]
            if outside:
                by_reason: dict[str, list[tuple[int, dict]]] = {}
                for q in outside:
                    r, det = _beyond(pipe, g, st, q, declared_reason)
                    by_reason.setdefault(r, []).append((q, det))
                for r, lst in sorted(by_reason.items()):
                    detail = dict(lst[0][1])
                    detail["prims"] = [q for q, _ in lst]
                    if r == UNOWNED_CONTINUATION and len(lst) > 1:
                        detail["unowned_pt"] = round(max(d.get("unowned_pt", 0.0) for _, d in lst), 2)
                    detail["degree"] = node.degree
                    out.append(Frontier(pipe.physical_pipe_id, pipe.family, nid, node.x, node.y, r, detail))
                    found += 1
            elif node.degree == 1:
                r, det = _terminal(pipe, g, st, node, comp, page, node_idx, graphs, ownership.prim_states, riser_pts, symbols)
                out.append(Frontier(pipe.physical_pipe_id, pipe.family, nid, node.x, node.y, r, det))
                found += 1
        if not found:
            n0 = g.nodes[pipe.nodes[0]] if pipe.nodes else None
            out.append(Frontier(pipe.physical_pipe_id, pipe.family, n0.nid if n0 else None,
                                n0.x if n0 else 0.0, n0.y if n0 else 0.0, CLOSED_LOOP,
                                {"why": "varje nod på röret har bara rörets egna primitiver"}))
    return out


def summary(frontiers: list[Frontier], pipes, meters_per_pt: float | None) -> dict[str, Any]:
    """Läsningens fronter i siffror: hur många av varje skäl, och hur mycket ingen äger bortom dem."""
    counts: dict[str, int] = {}
    unowned_pt = 0.0
    seen_unowned: set[tuple[str, int]] = set()
    for f in frontiers:
        counts[f.reason] = counts.get(f.reason, 0) + 1
        if f.reason == UNOWNED_CONTINUATION:
            key = (f.family, tuple(f.detail.get("prims") or [])[0] if f.detail.get("prims") else -1)
            if key not in seen_unowned:
                seen_unowned.add(key)
                unowned_pt += float(f.detail.get("unowned_pt") or 0.0)
    with_front = {f.pipe_id for f in frontiers}
    silent = sorted(p.physical_pipe_id for p in pipes if p.physical_pipe_id not in with_front)
    real = sum(n for r, n in counts.items() if r in REAL)
    lossy = sum(n for r, n in counts.items() if r in LOSSY)
    open_ = sum(n for r, n in counts.items() if r in OPEN)
    return {"frontiers": len(frontiers), "pipes": len(pipes), "silent_pipes": silent,
            "by_reason": dict(sorted(counts.items())),
            "real_boundaries": real, "lossy_boundaries": lossy, "open_boundaries": open_,
            "unowned_beyond_pt": round(unowned_pt, 2),
            "unowned_beyond_m": (round(unowned_pt * meters_per_pt, 2) if meters_per_pt else None)}


def end_evidence(page, graphs: dict) -> dict[str, dict[int, dict[str, Any]]]:
    """Vad som finns vid varje fri ände i varje familj, läst innan någon äger något.

    Det är det bevis en onämnd gren behöver för att få ta korsningens namn: att den slutar i en komponent, vid
    bladets kant, i en annan pennas fortsättning eller an mot en annan pennas bläck - en fixtur, en apparat.
    En gren som slutar i tomma luften har inget sådant bevis, och en råkontakt vid korsningen är inte ett.
    Samma slag som fronterna använder efteråt, så att bevis och skäl talar samma språk.
    """
    node_idx: dict[str, GridIndex] = {}
    for fk, g in graphs.items():
        idx = GridIndex(cell=24.0)
        for n in g.nodes.values():
            idx.insert(n.nid, (n.x, n.y, n.x, n.y))
        node_idx[fk] = idx
    symbols = page_symbols(page)
    ink = GridIndex(cell=24.0)
    paths = []
    for p in page.paths:
        if not is_stroked(p):
            continue
        ink.insert(len(paths), p.bbox)
        paths.append(p)
    W = float(page.info.width or 0.0)
    H = float(page.info.height or 0.0)
    out: dict[str, dict[int, dict[str, Any]]] = {}
    for fk, g in graphs.items():
        ev: dict[int, dict[str, Any]] = {}
        for n in g.nodes.values():
            if n.degree != 1:
                continue
            x, y = n.x, n.y
            margin = min(x, y, W - x, H - y) if W > 0 and H > 0 else float("inf")
            if margin <= SHEET_MARGIN:
                ev[n.nid] = {"kind": SHEET_EDGE, "margin_pt": round(margin, 2)}
                continue
            cov = symbols.covering(x, y, fk)
            if cov:
                ev[n.nid] = {"kind": SYMBOL, "symbol_paths": cov[:6]}
                continue
            best = None
            for fk2, idx2 in node_idx.items():
                if fk2 == fk:
                    continue
                for nid2 in idx2.query_point(x, y, JOIN_TOL):
                    n2 = graphs[fk2].nodes[nid2]
                    d = dist((x, y), (n2.x, n2.y))
                    if d <= JOIN_TOL and (best is None or d < best[0]):
                        best = (d, fk2, nid2)
            if best is not None:
                ev[n.nid] = {"kind": REPRESENTATION_CHANGE, "family": best[1], "node": best[2], "distance_pt": round(best[0], 2)}
                continue
            near = None
            for i in ink.query((x - OTHER_INK_REACH, y - OTHER_INK_REACH, x + OTHER_INK_REACH, y + OTHER_INK_REACH)):
                p = paths[i]
                if family_key(p) == fk:
                    continue
                for sg in p.segs[:64]:
                    d, _ = point_seg_distance(x, y, sg)
                    if d <= OTHER_INK_REACH and (near is None or d < near[0]):
                        near = (d, p.pid, family_key(p))
            if near is not None:
                ev[n.nid] = {"kind": ENDS_AT_OTHER_INK, "path": near[1], "family": near[2], "distance_pt": round(near[0], 2)}
                continue
            ev[n.nid] = {"kind": FREE_END}
        out[fk] = ev
    return out
