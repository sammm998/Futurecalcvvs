"""Geometry conservation: RAW RELEVANT PIPE GEOMETRY = CONFIRMED + AMBIGUOUS + UNOWNED, no double counting."""
from __future__ import annotations

from collections import Counter
from typing import Any


def reconcile(pa) -> dict[str, Any]:
    own = pa.ownership
    per_family = []
    tot = conf = amb = unowned = 0.0
    double = 0
    all_ok = True
    for fk, g in pa.graphs.items():
        f_tot = sum(q.seg.length for q in g.prims.values())
        f_conf = f_amb = f_un = 0.0
        for pid, st in own.prim_states[fk].items():
            L = g.prims[pid].seg.length
            if st.state == "CONFIRMED":
                f_conf += L
            elif st.state == "AMBIGUOUS":
                f_amb += L
            else:
                f_un += L
        # double counting: a primitive in more than one physical pipe
        seen: Counter = Counter()
        for p in own.pipes:
            if p.family != fk:
                continue
            for pid in p.prim_ids:
                seen[pid] += 1
        dbl = sum(1 for v in seen.values() if v > 1)
        pipe_sum = sum(p.raw_length_pt for p in own.pipes if p.family == fk)
        ok = abs(f_tot - (f_conf + f_amb + f_un)) <= 1e-6 * max(1.0, f_tot) and dbl == 0 and abs(pipe_sum - f_conf) <= 1e-6 * max(1.0, f_tot)
        all_ok = all_ok and ok
        double += dbl
        per_family.append({"family": fk, "raw_pt": round(f_tot, 3), "confirmed_pt": round(f_conf, 3), "ambiguous_pt": round(f_amb, 3),
                           "unowned_pt": round(f_un, 3), "physical_pipe_raw_pt": round(pipe_sum, 3), "double_counted_prims": dbl, "valid": ok})
        tot += f_tot; conf += f_conf; amb += f_amb; unowned += f_un
    return {"state": "VALID" if all_ok else "INVALID", "raw_relevant_pipe_geometry_pt": round(tot, 3), "confirmed_pt": round(conf, 3),
            "ambiguous_pt": round(amb, 3), "unowned_pt": round(unowned, 3), "residual_pt": round(tot - conf - amb - unowned, 6),
            "double_counted_prims": double, "families": per_family,
            "note": "physical pipe lengths additionally include bridged micro-gaps of the line style (reported separately)"}
