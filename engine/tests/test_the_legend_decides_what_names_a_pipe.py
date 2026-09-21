"""Bladets egen förklaringslista avgör vad som är en rörbeteckning.

En ritning skriver ut sina koder uppe i hörnet: `KV11 PLASTRÖR TYP ALU-PEX`, `VS11 PLASTRÖR LK s ALU-PEX`,
`D14 DAGVATTENLEDNING AV PE`. Det är ritningens eget besked om vad koderna på den betyder.

Rumsnummer har samma form som en rörbeteckning. `C 2004` med `FRD` under sig och `3,4 m²` därunder ser ut
precis som `KV11-16` med sin dimension på raden under - bokstäver, siffror, tre rader - och läsningen tog dem
som rör. Ett helt hus av rumsnummer hamnade i mängden med meter och stigare, och de metrarna finns inte.

Formen kan inte skilja dem åt. Listan kan: `C` står inte i den. En kod som bladets egen förklaringslista aldrig
nämner är ingen rörbeteckning på det bladet, hur mycket den än liknar en.

Regeln är smal med flit. Den gäller bara när bladet har en egen lista som säger något om system, och den
stänger bara ute koder listan inte känner alls - en kod som står i listan, vad den än fått för roll, får passera
som förut. En partiell lista ska inte kunna radera rör den bara råkat utelämna.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PEN = 1.44
LEAD = 0.72

LEGEND = [
    ("KV11", "PLASTROR TYP ALU-PEX"),
    ("VV11", "PLASTROR TYP ALU-PEX"),
    ("VVC11", "PLASTROR TYP ALU-PEX"),
    ("VS11", "PLASTROR LK s ALU-PEX"),
    ("VS12", "PLASTROR LK s ALU-PEX RIR"),
    ("D14", "DAGVATTENLEDNING AV PE"),
    ("S12", "AVLOPPSROR TYP LJUDDAMPANDE"),
    ("B1", "GOLVBRUNN SIDOUTLOPP"),
    ("TB", "TAKBRUNN"),
    ("BL1", "DISKLADSBLANDARE"),
]


def _label(page, x: float, y: float, text: str, to) -> None:
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
    page.draw_line((to[0] - 1, to[1] - 1), (to[0] + 1, to[1] + 1), width=LEAD, color=(0, 0, 0))


def _sheet(path: str, rooms: bool) -> str:
    """En ledning med tre KV11-etiketter, en förklaringslista, och - i det ena fallet - rumsnummer.

    Rumsnumren ritas som ritningen ritar dem: koden, en rad under, och en ledare ned till rummets vägg. Det är
    just den formen som lurade läsningen.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (460, 300), width=PEN, color=(0, 0, 0))
    for x in (80.0, 200.0, 330.0):
        _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))

    if rooms:
        # rumsnummer med samma form som en rörbeteckning: kod, rad under, ledare ned till rummet
        page.draw_line((60, 420), (460, 420), width=PEN, color=(0, 0, 0))
        for i, x in enumerate((80.0, 220.0, 360.0)):
            _label(page, x, 380.0, f"C0{i + 1}", (x + 60, 420.0))

    # förklaringslistan uppe till höger: kod i en kolumn, beskrivning i nästa
    page.insert_text((600, 90), "FORKLARINGAR", fontsize=11, fontname="helv")
    for i, (code, text) in enumerate(LEGEND):
        y = 110 + i * 13
        page.insert_text((600, y), code, fontsize=8, fontname="helv")
        page.insert_text((660, y), text, fontsize=8, fontname="helv")

    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _rows(path: str):
    pa = analyze_page(extract_document(path).pages[0])
    return {q["designation"]: round(q["confirmed_total_m"], 2) for q in pa.quantities}, pa


def test_the_legend_is_read(tmp_path):
    _, pa = _rows(_sheet(str(tmp_path / "lista.pdf"), rooms=False))
    codes = {e.code.upper() for e in pa.legend.entries}
    assert "KV11" in codes and "D14" in codes, f"förklaringslistan lästes inte: {sorted(codes)}"


def test_a_code_the_legend_lists_is_measured(tmp_path):
    rows, _ = _rows(_sheet(str(tmp_path / "ror.pdf"), rooms=False))
    assert any(d.startswith("KV11") for d in rows), rows
    assert max(rows.values()) > 6.0, rows


def test_legend_entries_do_not_count_as_pipe_labels_that_failed_to_reach_geometry(tmp_path):
    _, pa = _rows(_sheet(str(tmp_path / "legend-is-not-a-run.pdf"), rooms=False))
    passes = pa.contact_stats['reading_passes']
    assert passes
    # Three labels out on the plan; the list explains additional systems but
    # those entries are not additional runs lacking a leader.
    assert all(p['labels'] == 3 for p in passes), passes


def test_a_code_the_legend_never_mentions_is_not_a_pipe(tmp_path):
    """`C` står inte i listan. Rumsnumren får inte bli rader i mängden."""
    rows, _ = _rows(_sheet(str(tmp_path / "rum.pdf"), rooms=True))
    strays = [d for d in rows if d.upper().startswith("C0")]
    assert not strays, f"rumsnummer blev rörbeteckningar: {strays} (hela tabellen: {rows})"


def test_the_run_the_rooms_point_at_is_not_measured_under_their_name(tmp_path):
    """Ledningen rumsnumren råkar peka på ska inte mätas som ett C-rör."""
    clean, _ = _rows(_sheet(str(tmp_path / "ren.pdf"), rooms=False))
    with_rooms, _ = _rows(_sheet(str(tmp_path / "med.pdf"), rooms=True))
    assert sum(with_rooms.values()) <= sum(clean.values()) + 0.5, (
        f"rumsnumren tog med sig meter in i mängden: {with_rooms} mot {clean}")

# ---- själva regeln, utan omvägen över en ritning ------------------------------------------------------------
#
# Slutet av kedjan (att en kod utan meter inte får en rad) går att prova på ett blad. Regeln själv - vilka koder
# listan stänger ute, och när den inte får stänga ute något alls - provas här, för det är den som är rättningen.

class _Des:
    def __init__(self, did, text, head=None):
        self.did, self.text = did, text
        self.system_token = head if head is not None else text.split("-")[0]


class _Entry:
    def __init__(self, code):
        self.code, self.role, self.role_from, self.heading = code, "material", "usage", ""


class _Legend:
    """Så mycket av förklaringslistan som regeln läser."""

    def __init__(self, codes, own=True):
        self.entries = [_Entry(c) for c in codes]
        self.own = own
        self.by_code = {c.upper(): e for c, e in zip(codes, self.entries)}

    def role_of_head(self, head):
        head = (head or "").upper()
        best = None
        for c in self.by_code:
            if head == c or head.startswith(c):
                if best is None or len(c) > len(best):
                    best = c
        return self.by_code[best].role if best else None


TEN = ["KV11", "VV11", "VVC11", "VS11", "VS12", "D14", "S12", "B1", "TB", "BL1"]


def test_a_code_the_list_never_mentions_is_refused():
    from vvs_engine.pipeline import _unknown_to_the_legend
    des = [_Des("d1", "KV11-16"), _Des("d2", "VS11-22"), _Des("d3", "D14-160"),
           _Des("c1", "C09-07"), _Des("c2", "C 2004", head="C")]
    unknown = _unknown_to_the_legend(_Legend(TEN), des)
    assert unknown == {"c1", "c2"}, unknown


def test_a_list_that_does_not_know_this_sheet_refuses_nothing():
    """Känner listan bara enstaka av bladets koder säger den ingenting om bladet - och stänger inte ute något."""
    from vvs_engine.pipeline import _unknown_to_the_legend
    des = [_Des("d1", "KV11-16"), _Des("c1", "C09-07"), _Des("c2", "X1-2"), _Des("c3", "Y7-9")]
    assert _unknown_to_the_legend(_Legend(TEN), des) == set()


def test_a_short_list_refuses_nothing():
    from vvs_engine.pipeline import _unknown_to_the_legend
    des = [_Des("d1", "KV11-16"), _Des("d2", "VS11-22"), _Des("d3", "D14-160"), _Des("c1", "C09-07")]
    assert _unknown_to_the_legend(_Legend(["KV11", "VS11", "D14"]), des) == set()


def test_a_borrowed_list_refuses_nothing():
    """En lista läst från ett annat blad i omgången får aldrig radera ett rör det här bladet ritar."""
    from vvs_engine.pipeline import _unknown_to_the_legend
    des = [_Des("d1", "KV11-16"), _Des("d2", "VS11-22"), _Des("d3", "D14-160"), _Des("c1", "C09-07")]
    assert _unknown_to_the_legend(_Legend(TEN, own=False), des) == set()


def test_a_code_the_list_knows_passes_whatever_its_role():
    """En kod som står i listan får passera - också när listan aldrig hann bestämma vad den är."""
    from vvs_engine.pipeline import _unknown_to_the_legend
    lg = _Legend(TEN)
    for e in lg.entries:
        e.role = "unused"
    des = [_Des("d1", "KV11-16"), _Des("d2", "VS11-22"), _Des("d3", "D14-160"), _Des("c1", "C09-07")]
    assert _unknown_to_the_legend(lg, des) == {"c1"}
