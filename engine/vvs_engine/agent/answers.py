"""A tool result, said in Swedish, without a model.

Every question worth putting on a button is a single call into the reading, and the answer is already a number -
so composing the sentence is arithmetic and grammar, not judgement. That matters twice over: it costs nothing,
and it works on an installation that has no model at all. A drawing does not stop being readable because nobody
paid for a second opinion.

Free text still needs a model to choose the tool. These are the questions the interface asks for you.
"""
from __future__ import annotations

from typing import Any


def _m(v: Any) -> str:
    try:
        return f"{float(v):.2f}".replace(".", ",") + " m"
    except Exception:
        return "–"


def say(name: str, result: dict[str, Any]) -> str:
    """One tool's result as a sentence. Unknown tools get their own numbers back rather than a shrug."""
    if not isinstance(result, dict):
        return str(result)
    if result.get("fel"):
        return str(result["fel"])

    # A proposed change says the same thing whichever tool made it: what it would do, to how much, and - when
    # the drawing does not support it - why nothing is offered instead.
    if result.get("tillstand") == "AVBOJD":
        return "Ingen ändring föreslås: " + str(result.get("skal") or "ritningen stöder den inte") + "."
    if result.get("tillstand") == "FORESLAGEN":
        rows = "\n".join("  " + str(f.get("text")) for f in (result.get("forslag") or [])[:20])
        head = str(result.get("sammanfattning") or "")
        warn = ("\n  Obs: ändringen rör mer än 50 m. Kontrollera att den är menad så."
                if result.get("stor_andring") else "")
        return (f"{head}\n{rows}{warn}\n"
                f"Ingenting är ändrat än - rättelsen skrivs när du godkänner den, och kan ångras.")

    if name == "hitta_omatt_geometri_att_rita":
        k = result.get("kandidater") or []
        if not k:
            return ("Ingen bortvald geometri har en hänvisningslinje på sig, så det finns inget att rita in "
                    "som ritningen faktiskt pekar ut.")
        rows = "\n".join(f"  {c['meter']:.2f} m på {c['lager']}: {c['skal']} "
                          f"({c['hanvisningar_som_ror_den']} hänvisning(ar) rör den)" for c in k[:12])
        n = int(result.get("antal") or 0)
        return f"{n} ställe{'n' if n != 1 else ''} läsningen valde bort men något pekar på.\n{rows}"

    if name == "mangda":
        rows = result.get("rader") or []
        if not rows:
            return "Ingen bekräftad längd på det här bladet."
        head = "\n".join(f"  {r['nyckel']}: {_m(r['meter'])}  ({r.get('antal_stracker', 0)} sträckor)"
                         for r in rows[:24])
        return (f"{len(rows)} poster, {_m(result.get('summa_m'))} totalt.\n{head}"
                + ("\n  …" if len(rows) > 24 else ""))

    if name == "visa_hur_mangden_raknades":
        st = result.get("stracker") or []
        rows = "\n".join(f"  {s['pipe_id'][-8:]}  {_m(s['horizontal_m'])}" for s in st[:24])
        return (f"{result.get('beteckning')} är {_m(result.get('summa_m'))} fördelat på {len(st)} sträckor.\n{rows}"
                + ("\n  …" if len(st) > 24 else ""))

    if name == "hitta_dimensionsbyten":
        g = result.get("granser") or []
        if not g:
            return "Ritningen byter aldrig dimension inne i en sträcka på det här bladet."
        rows = "\n".join(f"  {' ↔ '.join(x.get('between') or [])} vid {x['point'][0]:.0f}, {x['point'][1]:.0f}"
                         for x in g[:20])
        return f"{result.get('antal')} noder där ritningen byter dimension, system eller material.\n{rows}" + \
               ("\n  …" if len(g) > 20 else "")

    if name == "hitta_fria_rorandar":
        e = result.get("andar") or []
        if not e:
            return "Varje rörände möter något annat: ingen fri ände på bladet."
        by: dict[str, int] = {}
        for x in e:
            by[x.get("designation") or "?"] = by.get(x.get("designation") or "?", 0) + 1
        rows = "\n".join(f"  {k}: {v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:16])
        return (f"{result.get('antal')} fria rörändar — anslutning, brunn, stigare, fortsättning på annat blad, "
                f"eller ett avbrott i läsningen.\n{rows}")

    if name == "hitta_dubbelritad_geometri":
        n = result.get("antal_stallen") or 0
        if not n:
            return "Ingen linje är ritad två gånger på det här bladet."
        return (f"{n} ställen där samma linje är ritad två gånger, {_m(result.get('langd_m'))} totalt. "
                f"{result.get('anmarkning')}")

    if name == "hitta_olosta":
        b = result.get("antal_blockerande") or 0
        n = result.get("antal_noterade") or 0
        if not b and not n:
            return "Ingenting är olöst: varje beteckning ritningen skriver har fått sin meter."
        rows = "\n".join(f"  {c.get('typ')}: {c.get('text') or ''}" for c in (result.get("fall") or [])[:16])
        return f"{b} att åtgärda, {n} noterade.\n{rows}"

    if name == "hitta_omatt_geometri":
        fam = result.get("avvisade_familjer") or []
        rows = "\n".join(f"  {f.get('skal')}: {_m(f.get('meter'))} (penna {f.get('penna')})" for f in fam[:14])
        return f"{len(fam)} ritade familjer läsningen inte tog som rör, med skälet.\n{rows}" if fam \
            else "Ingen ritad familj avvisades: allt bladet ritar med rörens pennor är med."

    if name == "hamta_forklaringslista":
        rows = result.get("rader") or []
        sys_ = [r for r in rows if r.get("roll") == "system"]
        comp = [r for r in rows if r.get("roll") == "component"]
        mat = [r for r in rows if r.get("roll") == "material"]
        out = [f"{len(rows)} rader: {len(sys_)} rörsystem, {len(comp)} komponenter, {len(mat)} material."]
        for r in sys_[:20]:
            out.append(f"  {r['kod']} — {r.get('betydelse') or ''}")
        return "\n".join(out)

    if name == "kontrollera_skala":
        mpp = result.get("meter_per_punkt")
        return (f"Skalan är {result.get('tillstand') or 'oläst'} ({result.get('skal') or 'inget skäl noterat'}), "
                + (f"{mpp} meter per ritningspunkt." if mpp else "ingen längd kan anges utan den."))

    if name == "kontrollera_lasningen":
        av = result.get("avstamning") or {}
        st = result.get("tillstand")
        head = (f"Granskningen slutade i {st}" if st else "Ingen granskning kördes för det här jobbet")
        lines = [f"{head}; avstämningen är {av.get('tillstand') or 'inte gjord'}, "
                 f"{av.get('dubbelraknade', 0)} dubbelräknade sträckor."]
        for u in (result.get("utlatanden") or [])[:12]:
            lines.append(f"  {u.get('granskare')} ({u.get('allvar')}): {u.get('text')}")
        return "\n".join(lines)

    if name == "hamta_ritning":
        return (f"Skalan är {(result.get('skala') or {}).get('tillstand')}. "
                f"{result.get('antal_ror')} rör och {result.get('antal_beteckningar')} beteckningar. "
                f"Bekräftat {_m(result.get('bekraftad_total_m'))}, tvetydigt {_m(result.get('tvetydig_m'))}. "
                f"System: {', '.join(result.get('system') or []) or '–'}.")

    if name in ("hitta_ror", "mat_ror", "folj_natet", "grannar"):
        rows = result.get("ror") or result.get("stracker") or []
        head = "\n".join(f"  {r.get('designation')}  {_m(r.get('horizontal_m'))}" for r in rows[:20])
        return f"{result.get('antal', len(rows))} sträckor, {_m(result.get('summa_m'))} totalt.\n{head}"

    return "\n".join(f"{k}: {v}" for k, v in result.items()
                     if not isinstance(v, (list, dict)) and v is not None) or "Inget att visa."
