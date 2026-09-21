"""Artefakternas version, och hur en äldre artefakt läses som dagens.

Varje JSON-artefakt bär `artifact_schema`. Numret byts när formen byts - ett fält som tillkommer, ett som
byter mening - och för varje gammalt nummer finns här vad som saknas jämfört med dagens, så att ett resultat
som räknades förra veckan öppnas i dagens vy utan att ett fält som inte fanns då läses som ett fel nu.

  1  före 2026-09-11: inga fronter på rören, ingen inventering av påskriften i råinventeringen
  2  2026-09-11: påskriften inventeras före klassificering (markup_set_aside, input_class per sida)
  3  2026-09-11: fronter på varje rör (frontiers, frontier_reasons), pipe-extent-frontiers.json

Adaptern hittar på ingenting: ett fält som saknas fylls med det tomma värdet som betyder "inte räknat då",
aldrig med ett värde som ser räknat ut. En front som inte fanns är en tom lista, och `upgraded_from` säger
att den är tom därför att läsningen var äldre, inte därför att röret saknar kanter.
"""
from __future__ import annotations

from typing import Any

ARTIFACT_SCHEMA = 3


def stamp(obj: Any) -> Any:
    """Dagens nummer på en artefakt som är ett objekt. Listor och skalärer lämnas som de är."""
    if isinstance(obj, dict) and "artifact_schema" not in obj:
        obj["artifact_schema"] = ARTIFACT_SCHEMA
    return obj


def upgrade(name: str, obj: Any) -> Any:
    """En artefakt som den ser ut idag, vilken version den än skrevs i."""
    if not isinstance(obj, dict):
        return obj
    have = int(obj.get("artifact_schema") or 1)
    if have >= ARTIFACT_SCHEMA:
        return obj
    if name == "physical-pipes.json":
        for p in obj.get("physical_pipes") or []:
            p.setdefault("frontiers", [])
            p.setdefault("frontier_reasons", [])
    elif name == "raw-vector-inventory.json":
        for pg in obj.get("pages") or []:
            pg.setdefault("markup_set_aside", None)
            pg.setdefault("input_class", None)
        obj.setdefault("skipped_pages", [])
    elif name == "reading-coverage.json":
        for sh in obj.get("sheets") or []:
            sh.setdefault("frontiers", None)
    elif name == "pipe-extent-frontiers.json":
        obj.setdefault("frontiers", [])
        obj.setdefault("summary", {})
    obj["artifact_schema"] = ARTIFACT_SCHEMA
    obj["upgraded_from"] = have
    return obj
