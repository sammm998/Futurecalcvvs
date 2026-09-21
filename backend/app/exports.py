"""Exports: Excel, CSV, JSON, analysis report and marked PDF are produced from the frozen artifacts."""
from __future__ import annotations

import csv
import io
import json
import os

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

HEADERS = ["Beteckning", "DN", "Beteckningar på ritningen", "Sammanhängande rörsträckor", "Horisontellt m", "Vertikalt m", "Vertikalt ursprung", "Totalt m", "Tvetydigt m", "Varav enligt bladets tabell m", "Varav i skrafferat område m", "Andra kanten av dubbellinje m", "Stigare (symboler)", "Stigare (etiketter)", "Status"]


def _rows(result_dir: str, floor_height: float | None = None, include_hatched: bool = False,
          rows: list[dict] | None = None, riser_source: str = "labels", include_declared: bool = True) -> list[dict]:
    """The rows an export is built from.

    `rows` is the corrected reading when the caller has one. Without it the engine's own reading is read off the
    artifact, which is right only for a drawing nobody has corrected: an export that quietly drops a correction
    is a priced spreadsheet that disagrees with the screen it was taken from.
    """
    if rows is None:
        with open(os.path.join(result_dir, "quantities.json"), "r", encoding="utf-8") as fh:
            rows = json.load(fh)["rows"]
    rows = [dict(r) for r in rows]
    for r in rows:
        # Förklarade kopplingsledningar: rör ingen etikett pekar ut, men som bladet namnger i ord. De räknas med
        # som förval - ritningen säger att de är där - och räknas bort för den förteckning som prissätter dem per
        # apparat eller mäter dem på ett annat blad. Filen ska visa samma summa som skärmen den togs från.
        if not include_declared:
            declared = float(r.get("declared_m", 0.0) or 0.0)
            if declared:
                r["confirmed_horizontal_m"] = round(max(0.0, r["confirmed_horizontal_m"] - declared), 3)
                r["confirmed_total_m"] = round(max(0.0, float(r.get("confirmed_total_m", 0.0) or 0.0) - declared), 3)
        # pipe drawn inside hatched areas is measured but stays out of the total unless the takeoff includes it
        if include_hatched:
            hatched = float(r.get("in_hatched_area_m", 0.0) or 0.0)
            r["confirmed_horizontal_m"] = round(r["confirmed_horizontal_m"] + hatched, 3)
            if r["vertical_m"] != "UNKNOWN":
                r["confirmed_total_m"] = round(r["confirmed_horizontal_m"] + float(r["vertical_m"]), 3)
            else:
                r["confirmed_total_m"] = r["confirmed_horizontal_m"]
        # Where the vertical metres came from travels with them. A height the reader typed is an assumption
        # about the building, not something the drawing states, and a takeoff that cannot tell the two apart
        # invites an assumed metre to be priced as a measured one.
        r["vertical_source"] = "OKÄNT" if r["vertical_m"] == "UNKNOWN" else "MÄTT"
        if floor_height:
            # vertical metres from the user's floor height: every riser counts one floor height. Which risers
            # those are is the reader's choice on screen - drawn symbols or labels with the dimension on the row
            # below - and the export has to count the same ones or it states a different quantity than they saw.
            risers = int((r.get("riser_count_from_labels") if riser_source == "labels"
                          else r.get("riser_count")) or 0)
            if risers > 0:
                known = 0.0 if r["vertical_m"] == "UNKNOWN" else float(r["vertical_m"])
                r["vertical_m"] = round(known + risers * floor_height, 3)
                r["confirmed_total_m"] = round(r["confirmed_horizontal_m"] + r["vertical_m"], 3)
                r["vertical_source"] = (f"ANTAGET ({risers} stigare x {floor_height:g} m)" if known == 0.0
                                        else f"MÄTT + ANTAGET ({risers} stigare x {floor_height:g} m)")
    return rows


def _fmt(v):
    return v if v != "UNKNOWN" else "OKÄNT"


MARKUP_HEADERS = ["Verktyg", "Lager", "Beteckning", "Sida", "Meter", "Kvadratmeter", "Antal", "Skala", "Text"]


def _markup_row(m: dict) -> list:
    """En egen markering som en rad: vad den mäter, i det den mäter. Aldrig en ytas omkrets i meterkolumnen."""
    me = m.get("measure") or {}
    tool = m.get("tool", "")
    metres = me.get("m") if tool in ("langd", "polylinje", "frihand") else None
    sqm = me.get("kvm") if tool in ("area", "rektangel", "moln") else None
    n = me.get("antal") if tool == "antal" else None
    return [tool, m.get("layer", ""), m.get("designation") or "", m.get("page", 0),
            round(metres, 2) if isinstance(metres, (int, float)) else "",
            round(sqm, 2) if isinstance(sqm, (int, float)) else "",
            n if isinstance(n, int) else "", "verifierad" if me.get("scale") == "VERIFIERAD" else "ingen skala",
            m.get("text") or ""]


def to_xlsx(result_dir: str, floor_height: float | None = None, include_hatched: bool = False,
          rows: list[dict] | None = None, riser_source: str = "labels", markups: list[dict] | None = None,
          include_declared: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Mängder"
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in _rows(result_dir, floor_height, include_hatched, rows, riser_source, include_declared):
        ws.append([r["designation"], r["dn"] if r["dn"] is not None else "?", r.get("label_count", 0), r["physical_pipe_count"], round(r["confirmed_horizontal_m"], 2),
                   _fmt(r["vertical_m"]) if r["vertical_m"] == "UNKNOWN" else round(r["vertical_m"], 2),
                   r["vertical_source"], round(r["confirmed_total_m"], 2),
                   round(r["ambiguous_m"], 2), round(r.get("declared_m", 0.0), 2), round(r.get("in_hatched_area_m", 0.0), 2), round(r.get("double_line_m", 0.0), 2), r.get("riser_count", 0),
                   r.get("riser_count_from_labels", 0), r["state"]])
    for i, _ in enumerate(HEADERS, 1):
        ws.column_dimensions[get_column_letter(i)].width = 20
    # Det mängdaren själv ritade in, på ett eget blad. Aldrig i samma tabell som läsningen: de två svarar på
    # olika frågor, och en summa som blandar dem går inte att härleda.
    if markups:
        ws2 = wb.create_sheet("Egna markeringar")
        ws2.append(MARKUP_HEADERS)
        for c in ws2[1]:
            c.font = Font(bold=True)
        for m in markups:
            ws2.append(_markup_row(m))
        for i, _ in enumerate(MARKUP_HEADERS, 1):
            ws2.column_dimensions[get_column_letter(i)].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_csv(result_dir: str, floor_height: float | None = None, include_hatched: bool = False,
          rows: list[dict] | None = None, riser_source: str = "labels", include_declared: bool = True) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(HEADERS)
    for r in _rows(result_dir, floor_height, include_hatched, rows, riser_source, include_declared):
        w.writerow([r["designation"], r["dn"] if r["dn"] is not None else "?", r.get("label_count", 0), r["physical_pipe_count"], f"{r['confirmed_horizontal_m']:.2f}",
                    _fmt(r["vertical_m"]) if r["vertical_m"] == "UNKNOWN" else f"{r['vertical_m']:.2f}",
                    r["vertical_source"], f"{r['confirmed_total_m']:.2f}",
                    f"{r['ambiguous_m']:.2f}", f"{r.get('declared_m', 0.0):.2f}", f"{r.get('in_hatched_area_m', 0.0):.2f}", f"{r.get('double_line_m', 0.0):.2f}", r.get("riser_count", 0),
                    r.get("riser_count_from_labels", 0), r["state"]])
    return buf.getvalue()
