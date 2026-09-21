"""Panelen: de andraläsare den här installationen kan nå, och regeln att de måste vara överens.

Motorn svarar ur bladets egen geometri. Där den kan försvara ett svar frågar den ingen, och där den inte kan
säger den TVETYDIGT. En andraläsare får bara röra den sista sortens fall, och bara välja bland de kandidater
ritningen själv lagt fram (`vvs_engine/semantics/astra.py`).

Med en enda läsare är den ordningen ändå sårbar på ett sätt: ett öppet fall har flera rimliga kandidater, och
en modell som gissar fel gör ett ärligt tvetydigt fall till ett självsäkert fel. Två oberoende läsare som
måste peka på *samma* kandidat kan inte göra det. De kan bara enas om ett av ritningens egna alternativ, eller
lämna fallet öppet - och öppet är ett giltigt svar.

Reglerna, med avsikt hårda:

  * Är två läsare **konfigurerade** måste båda svara och båda välja samma kandidat. Svarar bara den ena - den
    andra är onåbar, tog slut på tid, eller sa OKLART - står fallet kvar tvetydigt. En nedtappad läsare ska
    tysta panelen, inte tyst göra den till en ensam röst.
  * Är bara **en** läsare konfigurerad beter sig panelen som förut: den läsarens svar går vidare till samma
    prövning som alltid.
  * Ingen läsare kan namnge något som inte redan står i frågan. Det avgörs av `verify` i motorn, före och efter
    panelen, och panelen gör den prövningen ännu en gång för sin egen räkning.

Ingen nyckel står här. Varje transport läser sin egen ur miljön i anropsögonblicket.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

NAMES = ("astra", "claude")


def _mods():
    from . import astra_transport, claude_transport          # noqa: PLC0415
    return {"astra": astra_transport, "claude": claude_transport}


def _load():
    """Modulerna, importerade som fristående skript också fungerar (verktygen körs båda vägarna)."""
    try:
        return _mods()
    except ImportError:
        import astra_transport, claude_transport             # noqa: E401, PLC0415
        return {"astra": astra_transport, "claude": claude_transport}


def wanted() -> tuple[str, ...]:
    """Vilka läsare den här installationen ber om: VVS_SECOND_READERS, annars de som går att nå."""
    raw = (os.environ.get("VVS_SECOND_READERS") or "").strip().lower()
    if raw in ("", "auto"):
        return tuple(n for n in NAMES if _load()[n].available()[0])
    if raw in ("none", "off", "false"):
        return ()
    picked = tuple(n.strip() for n in raw.replace(";", ",").split(",") if n.strip())
    return tuple(n for n in picked if n in NAMES)


def state() -> list[dict]:
    """Varje läsares namn, modell, om den går att nå och varför - för statussidan och för admin."""
    mods = _load()
    asked = wanted()
    out = []
    for n in NAMES:
        ok, why = mods[n].available()
        out.append({"name": n, "model": mods[n].MODEL, "reachable": ok, "why": why, "in_use": n in asked})
    return out


def readers(effort: str = "low") -> dict[str, Callable]:
    mods = _load()
    return {n: mods[n].transport(effort) for n in wanted()}


def vision(effort: str = "low") -> Callable | None:
    """Synläsaren: den första konfigurerade läsare som går att nå, eller None.

    Här krävs ingen enighet, för ingenting en synläsare säger kan bli en meter - `review.vision.look` har ingen
    väg att skriva in i en läsning. Den beskriver vad den ser, och en människa läser beskrivningen.
    """
    mods = _load()
    for n in wanted():
        try:
            return mods[n].vision_transport(effort)
        except Exception:                                     # noqa: BLE001
            continue
    return None


def _verify(q, raw: str):
    from vvs_engine.semantics.astra import verify             # noqa: PLC0415
    return verify(q, raw)


def panel_transport(effort: str = "low", asks: dict[str, Callable] | None = None) -> Callable | None:
    """En anropbar för analyze_page(second_reader=...) som talar för hela panelen, eller None om den är tom.

    Den lämnar tillbaka *text*, precis som en ensam läsare gör, och motorns egen `verify` prövar den en gång
    till. Enigheten avgörs här därför att det är här svaren finns bredvid varandra; regeln om vad som får
    svaras ligger kvar i motorn.
    """
    asks = readers(effort) if asks is None else asks
    if not asks:
        return None
    if len(asks) == 1:
        return next(iter(asks.values()))

    def ask(q) -> str:
        said: dict[str, str] = {}
        for name, fn in sorted(asks.items()):
            try:
                a = _verify(q, fn(q))
            except Exception as e:                            # noqa: BLE001
                said[name] = f"nådde inte fram ({type(e).__name__})"
                continue
            said[name] = a.choice or (a.refused or "OKLART")
        trail = "; ".join(f"{k}: {v}" for k, v in sorted(said.items()))
        picks = {v for k, v in said.items()}
        if len(said) == len(asks) and len(picks) == 1:
            only = next(iter(picks))
            if only in q.candidates:
                return f"{only}\ntvå läsare överens - {trail}"
        return f"OKLART\nläsarna är inte överens - {trail}"
    return ask
