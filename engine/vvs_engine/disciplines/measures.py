"""Mättyper och källtyper, och de rader som finns idag sedda som en gemensam rad.

En mängdrad i en ny disciplin bär en eller flera mätningar: meter rör, meter kanal och m² plåt ur samma sträcka,
ett antal don. Varje mätning har sin typ, sin enhet, hur den kom till och hur säker den är. Raden säger också var
den kommer ifrån:

  UPPMÄTT   läsningen mätte den på bladet
  RÄKNAD    läsningen räknade den på bladet (symboler, rum)
  SCHABLON  den är härledd ur räknade enheter och ett nyckeltal
  MANUELL   en människa mätte eller räknade den själv

VVS-raderna och de manuella markeringarna ändras inte av det här. De ses bara som gemensamma rader där en lista
som rymmer flera discipliner eller källor behöver det - deras egna fält står kvar som de är, och exporterna för
VVS är desamma som förut.
"""
from __future__ import annotations

from typing import Any

LENGTH, AREA, COUNT, VOLUME = "LENGTH", "AREA", "COUNT", "VOLUME"
UNITS = {LENGTH: "m", AREA: "m²", COUNT: "st", VOLUME: "m³"}
UPPMATT, RAKNAD, SCHABLON, MANUELL = "UPPMÄTT", "RÄKNAD", "SCHABLON", "MANUELL"
SOURCE_TYPES = (UPPMATT, RAKNAD, SCHABLON, MANUELL)


def measure(kind: str, value: float, derivation: str = "measured", state: str = "CONFIRMED",
            confidence: float | None = None) -> dict:
    if kind not in UNITS:
        raise ValueError(f"okänd mättyp: {kind}")
    return {"type": kind, "unit": UNITS[kind], "value": round(float(value), 3), "derivation": derivation,
            "state": state, "confidence": confidence}


def _num(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def vvs_row_view(row: dict, discipline: str = "vvs") -> dict:
    """A VVS quantity row as the common row. Its horizontal metres, and its vertical ones where the reading knows
    them, are what it measured; metres the reading could not settle are carried as AMBIGUOUS, never added in."""
    measures = [measure(LENGTH, _num(row.get("confirmed_horizontal_m")), "horizontal")]
    vertical = row.get("vertical_m")
    if vertical not in (None, "UNKNOWN") and _num(vertical) > 0:
        measures.append(measure(LENGTH, _num(vertical), "vertical"))
    if _num(row.get("ambiguous_m")) > 0:
        measures.append(measure(LENGTH, _num(row.get("ambiguous_m")), "ambiguous", state="AMBIGUOUS"))
    return {"discipline": discipline, "source_type": UPPMATT, "system": _system(row.get("designation")),
            "designation": row.get("designation"),
            "dimension": {"format": "DN", "value": row.get("dn")} if row.get("dn") is not None else None,
            "measures": measures, "state": row.get("state"),
            "evidence": {"pipe_ids": list(row.get("pipe_ids") or [])}}


MARKUP_MEASURES = (("m", LENGTH), ("kvm", AREA), ("m3", VOLUME), ("antal", COUNT))


def markup_row_view(markup: dict, discipline: str = "vvs") -> dict:
    """A markup a person drew as the common row: MANUELL, with what the tool measured."""
    me = markup.get("measure") or {}
    measures = [measure(kind, _num(me.get(key)), "manual") for key, kind in MARKUP_MEASURES if me.get(key) is not None]
    return {"discipline": discipline, "source_type": MANUELL, "system": _system(markup.get("designation")),
            "designation": markup.get("designation"), "dimension": None, "measures": measures,
            "state": markup.get("status"), "evidence": {"markup_id": markup.get("id"), "page": markup.get("page")}}


def _system(designation: str | None) -> str | None:
    """The system the designation opens with (KV1 in KV1-X7-40), as written; None for a row without a name."""
    head = (designation or "").strip().split("-")[0].split("/")[0]
    return head or None
