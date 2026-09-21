"""Referensarbetsböcker som bara finns på Drive, lästa via Drive-API:ets textform och sparade som CSV.

Drive ger arbetsboken som en enda textrad: rubrikraden följd av rader som var och en börjar med versionen
("1,") och dokumentnamnet. Fälten är kommaseparerade, tal med decimalkomma är citerade ("0,2"). Här görs det
till en CSV med tre kolumner (Ämne;Längd;unit) per blad, sparad under data/validation_W/<blad>/facit.csv -
git-ignorerat som allt annat referensmaterial. Vertikalraderna (Antal_VS, Vertikal_höjd_VS) hoppas över på
samma sätt som arbetsboksläsaren gör: de bär ingen längd.

Verktyget läser aldrig något in i motorn. Det är en del av poängsättningen, som kommer efter en fryst blind
körning.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys

DATA = "/home/user/vvs5/data"


def parse_drive_text(text: str) -> tuple[list[str], list[list[str]]]:
    """Rubriker och rader ur Drive-textformen. Raderna hittas på sina versionsprefix ('1,' följt av .pdf-namnet)."""
    text = text.replace("\\_", "_").replace("\\[", "[").replace("\\]", "]").replace("\\#", "#")
    m = re.match(r"^(?:Blad\d+\s+)?(.*?)(?=\s1,[^,]*\.pdf,)", text, re.S)
    head = next(csv.reader([m.group(1).strip()])) if m else []
    rows = []
    for chunk in re.split(r"\s(?=1,[^,]*\.pdf,)", text[m.end():] if m else text):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            rows.append(next(csv.reader([chunk])))
        except Exception:
            continue
    return head, rows


def _col(idx: dict[str, int], *names: str) -> int | None:
    """Kolumnindex för första rubriken som finns; arbetsböckerna växlar mellan svenska och engelska rubriker."""
    for n in names:
        if n in idx:
            return idx[n]
    return None


def rows_to_facit(head: list[str], rows: list[list[str]]) -> list[dict]:
    """Ämne/Längd/unit per rad med en längd, normaliserat till punkt-decimal."""
    idx = {h.strip(): i for i, h in enumerate(head)}
    ia, il, iu = _col(idx, "Ämne", "Subject"), _col(idx, "Längd", "Length"), _col(idx, "unit", "Unit")
    out = []
    for r in rows:
        if ia is None or il is None or ia >= len(r) or il >= len(r):
            continue
        name, length = r[ia].strip(), r[il].strip()
        if not name or not length:
            continue
        mm = re.match(r"^-?\d+(?:[.,]\d+)?", length)
        if not mm:
            continue
        unit = (r[iu].strip() if iu is not None and iu < len(r) else "m") or "m"
        out.append({"Ämne": name, "Längd": mm.group(0).replace(",", "."), "unit": unit})
    return out


def drawing_id(document: str) -> str | None:
    m = re.search(r"([VW])-?(\d{2,3})-?(\d)-?([A-Z]{1,3})?-?(\d{3,4})", document.upper())
    if not m:
        return None
    s, a, b, letters, n = m.groups()
    return f"{s}-{a}-{b}-{letters or ''}{n.zfill(4)}"


def save(text: str, expect_id: str | None = None) -> str:
    head, rows = parse_drive_text(text)
    fac = rows_to_facit(head, rows)
    idx = {h.strip(): i for i, h in enumerate(head)}
    doc = next((r[idx["Document"]] for r in rows if "Document" in idx and idx["Document"] < len(r)), "")
    did = drawing_id(doc) or expect_id
    if not did:
        raise SystemExit(f"kan inte se vilket blad texten hör till: {doc!r}")
    if expect_id and did != expect_id:
        raise SystemExit(f"texten namnger {did}, väntade {expect_id}: sparas inte")
    d = os.path.join(DATA, "validation_W", did)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "facit.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Ämne", "Längd", "unit"])
        for r in fac:
            w.writerow([r["Ämne"], r["Längd"], r["unit"]])
    with open(os.path.join(d, "drive_source.json"), "w", encoding="utf-8") as fh:
        json.dump({"document": doc, "rows": len(rows), "rows_with_length": len(fac), "head": head}, fh, ensure_ascii=False, indent=1)
    # den rena PDF:en: CVAT-kopian är bytevis samma fil som Bluebeam-mappens 'clear'/'Without measurement'
    src = os.path.join(DATA, "cvat", "CVAT", f"{did[:6]}-{did[6:7]}-{did[8:]}.pdf".replace("--", "-"))
    cand = [src, os.path.join(DATA, "cvat", "CVAT", f"W-50-1-A-{did[-4:]}.pdf")]
    for c in cand:
        if os.path.isfile(c) and not os.path.exists(os.path.join(d, "clean.pdf")):
            os.symlink(c, os.path.join(d, "clean.pdf"))
            break
    return d


if __name__ == "__main__":
    # python3 drive_facit.py <fil med Drive-text> [<väntat blad>]
    text = open(sys.argv[1], encoding="utf-8").read()
    print("sparat:", save(text, sys.argv[2] if len(sys.argv) > 2 else None))
