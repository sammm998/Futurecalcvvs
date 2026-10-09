"""Läget "Alla", Fas 2: andra discipliners ledningar mäts i meter, i en andra, vidgad läsning av bladet.

VVS-läsningen namnger en ledning bara med en kod som bladets lista kallar ett system, och räknar en etikettfamilj som
rör bara om etiketterna bär en DN. En kanal skrivs TL01-Ø250 eller FL01-400x200, en kabelstege med sin bredd, ett
sprinklerrör med en kod som VVS-listan aldrig nämner: för VVS-läsningen namnger ingen av dem något. "Alla" läser
därför samma blad en gång till och behåller det den läsningen mäter på linjer som den första inte tog. Proven håller
fast:

- en kanal ritad som sina två kanter mäts en gång, i meter, under sitt namn och med sitt mått
- ett sprinklerrör som bladets VVS-lista aldrig nämner mäts, och VVS-rören är exakt desamma som i VVS-läget
- en kabelstege mäts, och uttagens taggar räknas i styck, också där de är långt fler än ledningarnas etiketter
- en tagg skriven som en ventil - kod, löpnummer och storlek - får aldrig meter
- ett don som bladets lista förklarar får aldrig meter, inte ens taggat med sin anslutnings storlek och ritat med
  kanalernas penna
- den vidgade läsningen behåller bara det den mätt på linjer mängden lämnat: ett namn mängden har är mängdens, också
  med en not bredvid, och en lednings andra kant har inga egna meter
- allt den vidgade läsningen mäter står i registret som att granska, aldrig i mängden
- den vidgade läsningens värden gäller bara i den andra läsningen
"""
import math

import pymupdf

from vvs_engine import disciplines
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page, run_size

M = 56.69          # pt per metre at 1:50
LEGEND = [("KV01", "TAPPKALLVATTEN"), ("VV01", "TAPPVARMVATTEN"), ("VVC01", "VARMVATTENCIRKULATION"),
          ("S01", "SPILLVATTEN"), ("X7", "PEX ROR"), ("S13", "MA ROR"), ("TS1", "TVATTSTALL"),
          ("BL2", "BLANDARE"), ("AV", "AVSTANGNINGSVENTIL")]


def _line(shape, p0, p1, w=0.7):
    shape.draw_line(p0, p1)
    shape.finish(width=w, color=(0, 0, 0), closePath=False)


def _dashed(shape, p0, p1, dash=12.0, gap=3.0, w=1.44):
    (x0, y0), (x1, y1) = p0, p1
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    t = 0.0
    while t < length:
        e = min(t + dash, length)
        _line(shape, (x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e), w)
        t = e + gap


def _label(page, shape, text, at, to, tick=True):
    """A label written at `at`, underlined, with a leader to `to` and a tick across where it lands."""
    x, y = at
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    w = 6.2 * len(text)
    _line(shape, (x, y + 2), (x + w, y + 2))
    _line(shape, (x + w, y + 2), to)
    if tick:
        _line(shape, (to[0] - 2.5, to[1] + 2.5), (to[0] + 2.5, to[1] - 2.5))


def _sheet(path, draw):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    shape = page.new_shape()
    draw(page, shape)
    page.insert_text((60, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * M, 560), str(i), fontsize=8, fontname="helv")
    _line(shape, (302, 566), (302 + 5 * M, 566), 1.0)
    shape.commit()
    doc.save(path)
    doc.close()
    return str(path)


def _ducts(page, shape):
    """Two ducts drawn as their two edges - TL01 round, 250 mm, 6 m; FL01 400 wide, 4 m - and a terminal's tag."""
    for y, width, length in ((300, 0.250, 6), (420, 0.400, 4)):
        _line(shape, (100, y), (100 + length * M, y), 1.0)
        _line(shape, (100, y + width * M), (100 + length * M, y + width * M), 1.0)
    _label(page, shape, "TL01-Ø250", (150, 240), (220, 300))
    _label(page, shape, "FL01-400x200", (150, 380), (230, 420))
    shape.draw_rect(pymupdf.Rect(500, 290, 515, 305))
    shape.finish(width=0.7, color=(0, 0, 0))
    _label(page, shape, "TD01", (560, 250), (510, 290), tick=False)


def _sprinkler_beside_a_vvs_list(page, shape):
    """A VVS plan with its own list, three pipes the list knows, a fire-fighting pipe (BRL, a system of the Swedish
    table) the list never mentions, and a tag written as a valve's - code, serial number, size - on a line of its
    own."""
    page.insert_text((640, 60), "BETECKNINGAR", fontsize=9, fontname="helv")
    for i, (code, desc) in enumerate(LEGEND):
        page.insert_text((640, 80 + 14 * i), code, fontsize=8, fontname="helv")
        page.insert_text((690, 80 + 14 * i), desc, fontsize=8, fontname="helv")
    for text, y in (("KV01-X7-40", 200), ("VV01-X7-25", 260), ("VVC01-X7-16", 320)):
        _dashed(shape, (100, y), (100 + 5 * M, y))
        _label(page, shape, text, (140, y - 40), (200, y))
    _line(shape, (100, 420), (100 + 5 * M, 420), 1.44)
    _label(page, shape, "BRL1-32", (140, 380), (210, 420))
    _line(shape, (450, 480), (450 + 2 * M, 480), 1.44)
    _label(page, shape, "SAV101-32", (460, 450), (520, 480))


VENT_LEGEND = [("TL", "TILLUFT"), ("FL", "FRANLUFT"), ("UL", "UTELUFT"), ("AL", "AVLUFT"), ("TD", "TILLUFTSDON"),
               ("FD", "FRANLUFTSDON")]


def _terminals_beside_a_ventilation_list(page, shape):
    """The two ducts beside a list that explains TD as a supply-air terminal, and three terminals drawn with the
    ducts' own pen as outlines 1 m across, each tagged with its code and a size written the way a duct's is."""
    page.insert_text((640, 60), "BETECKNINGAR", fontsize=9, fontname="helv")
    for i, (code, desc) in enumerate(VENT_LEGEND):
        page.insert_text((640, 80 + 14 * i), code, fontsize=8, fontname="helv")
        page.insert_text((690, 80 + 14 * i), desc, fontsize=8, fontname="helv")
    for y, width, length in ((300, 0.250, 6), (420, 0.400, 4)):
        _line(shape, (100, y), (100 + length * M, y), 1.0)
        _line(shape, (100, y + width * M), (100 + length * M, y + width * M), 1.0)
    _label(page, shape, "TL01-Ø250", (150, 240), (220, 300))
    _label(page, shape, "FL01-400x200", (150, 380), (230, 420))
    for i, x in enumerate((440, 520, 600)):
        corners = ((x, 200), (x + M, 200), (x + M, 200 + M), (x, 200 + M))
        for k in range(4):
            _line(shape, corners[k], corners[(k + 1) % 4], 1.0)
        _label(page, shape, f"TD10{i + 1}-Ø100", (x + 10, 160), (x + M / 2, 200))


def _cable_trays(page, shape):
    """Two cable trays drawn as their two edges - 300 wide and 7 m, 200 wide and 5 m - and the tags of 24 outlets:
    an electrical plan writes far more tags than runs. The tags' leaders end on the outlets' rings."""
    for y, width, length, text, to in ((300, 0.300, 7, "KS1-300x60", (230, 300)),
                                       (420, 0.200, 5, "KS2-200x60", (240, 420))):
        _line(shape, (100, y), (100 + length * M, y), 1.0)
        _line(shape, (100, y + width * M), (100 + length * M, y + width * M), 1.0)
        _label(page, shape, text, (150, y - 60), to)
    for i in range(24):
        x, y = 530 + 40 * (i % 7), 100 + 70 * (i // 7)
        shape.draw_circle((x, y), 4)
        shape.finish(width=0.5, color=(0, 0, 0))
        _label(page, shape, "UT1", (x + 6, y - 30), (x + 3, y - 3), tick=False)


def _read(path):
    vvs = analyze_page(extract_document(path).pages[0])
    with disciplines.using("alla"):
        alla = analyze_page(extract_document(path).pages[0])
    return vvs, alla


def _rows(pa):
    return [(q["designation"], q.get("dn"), q.get("confirmed_total_m")) for q in pa.quantities]


def test_a_duct_drawn_as_its_two_edges_is_measured_once_under_its_name(tmp_path):
    vvs, alla = _read(_sheet(tmp_path / "ventilation.pdf", _ducts))
    assert _rows(vvs) == _rows(alla) == [], "no duct is a pipe to the VVS reading"
    wide = {r["designation"]: r for r in alla.wide_runs}
    assert (wide["TL01-Ø250"]["size"], wide["TL01-Ø250"]["metres"]) == (250, 6.0)
    assert (wide["FL01-400x200"]["size"], wide["FL01-400x200"]["metres"]) == (400, 4.0)
    E = {e["name"]: e for e in alla.register["entries"]}
    assert (E["TL01-Ø250"]["kind"], E["TL01-Ø250"]["quantity"], E["TL01-Ø250"]["state"]) == ("ledning", 6.0, "granskas")
    assert E["TL01-Ø250"]["reasons"] == ["mätt i den vidgade läsningen, utan referensmängd"] and E["TL01-Ø250"]["runs"]
    assert (E["TD01"]["kind"], E["TD01"]["quantity"]) == ("okänd", 1), "a terminal's tag is counted, not measured"
    assert alla.register["totals"]["wide_metres"] == 10.0 and vvs.wide_runs == [] and vvs.register is None


def test_a_pipe_the_vvs_list_never_mentions_is_measured_and_the_vvs_pipes_stay_as_they_were(tmp_path):
    vvs, alla = _read(_sheet(tmp_path / "sprinkler.pdf", _sprinkler_beside_a_vvs_list))
    assert _rows(vvs) == _rows(alla) and {r[0] for r in _rows(vvs)} == {"KV01-X7-40", "VV01-X7-25", "VVC01-X7-16"}
    wide = {r["designation"]: r for r in alla.wide_runs}
    assert set(wide) == {"BRL1-32"} and wide["BRL1-32"]["metres"] == 5.0
    E = {e["name"]: e for e in alla.register["entries"]}
    assert E["BRL1-32"]["state"] == "granskas" and E["KV01-X7-40"]["state"] == "säker"
    # a tag written as a valve's names the valve, not the line it sits on: counted, never measured
    assert E["SAV101-32"]["kind"] != "ledning" and E["SAV101-32"]["unit"] == "st"


def test_a_cable_tray_is_measured_and_the_outlets_are_counted(tmp_path):
    """A tag names a thing, not a run. Taken for names of runs, the outlets' tags were 24 of the sheet's 26 labels
    and reached no run, and a sheet whose labels miss their runs is refused: the trays were not measured at all."""
    vvs, alla = _read(_sheet(tmp_path / "el.pdf", _cable_trays))
    assert _rows(vvs) == _rows(alla) == []
    wide = {r["designation"]: (r["size"], r["metres"]) for r in alla.wide_runs}
    assert wide == {"KS1-300x60": (300, 7.0), "KS2-200x60": (200, 5.0)}
    E = {e["name"]: e for e in alla.register["entries"]}
    assert (E["UT1"]["quantity"], E["UT1"]["unit"]) == (24, "st")


def test_a_terminal_the_list_explains_is_counted_even_tagged_with_a_size_and_drawn_with_the_ducts_pen(tmp_path):
    """The list says TD is a terminal. Its tags carry a size the way a duct's do, and the outlines they point at are
    drawn with the ducts' pen: had a tag named a run, each outline would have been 4 m of duct under it."""
    vvs, alla = _read(_sheet(tmp_path / "ventilation_list.pdf", _terminals_beside_a_ventilation_list))
    assert _rows(vvs) == _rows(alla)
    assert not [r for r in alla.wide_runs if r["designation"].startswith("TD")], alla.wide_runs
    E = {e["name"]: e for e in alla.register["entries"]}
    for name in ("TD101-Ø100", "TD102-Ø100", "TD103-Ø100"):
        assert (E[name]["kind"], E[name]["quantity"], E[name]["unit"]) == ("komponent", 1, "st"), E[name]
    assert (E["TL01-Ø250"]["quantity"], E["FL01-400x200"]["quantity"]) == (6.0, 4.0), "the ducts are read"


def test_the_widened_reading_keeps_only_runs_on_lines_the_takeoff_left_alone(monkeypatch):
    """A run under a name the takeoff has is the takeoff's, also with a note beside it; a run touching a line the
    takeoff owns is not taken; a run's second edge is drawn but carries no metres, as in the takeoff."""
    from types import SimpleNamespace as NS

    import vvs_engine.pipeline as P

    def run(name, size, paths, metres, twin_of=None):
        identity = NS(key=f"{name}|{size}", display=name, dn=size) if name else None
        return NS(pipe=NS(identity=identity, source_paths=paths, points=[[(0.0, 0.0), (10.0, 0.0)]]),
                  horizontal_m=metres, twin_of=twin_of)
    wide = NS(measures=[run("S3-P5-160 (L)", 160, ["a"], 0.19), run("KS1-300x60", 300, ["owned", "b"], 7.0),
                        run("TL01-Ø250", 250, ["c"], 6.0), run("TL01-Ø250", 250, ["d"], 0.4, twin_of="c"),
                        run(None, None, ["e"], 2.0)])
    monkeypatch.setattr(P, "analyze_page", lambda page, **kw: wide)
    pa = NS(quantities=[{"designation": "S3-P5-160"}], ownership=NS(pipes=[NS(source_paths=["owned"])]))
    assert [(r["designation"], r["size"], r["metres"], r["pieces"], len(r["runs"]))
            for r in P.widened_runs(pa, None, None)] == [("TL01-Ø250", 250, 6.0, 1, 2)]


def test_the_widened_values_hold_in_the_second_reading_only():
    with disciplines.using("alla"):
        assert disciplines.value("pipeline.OTHER_RUNS_NAME_RUNS", False) is False
        with disciplines.widened():
            assert disciplines.value("pipeline.OTHER_RUNS_NAME_RUNS", False) is True
            assert disciplines.value("measure.DOUBLE_LINE_BY_SIZE_ONLY", False) is True
        assert disciplines.value("measure.DOUBLE_LINE_BY_SIZE_ONLY", False) is False
    with disciplines.using("vvs"), disciplines.widened():
        assert disciplines.value("pipeline.OTHER_RUNS_NAME_RUNS", False) is False, "VVS has no widened values"


def test_a_ducts_size_is_read_as_it_is_written():
    class D:
        def __init__(self, text):
            self.text, self.tokens = text, text.split("-")
    assert [run_size(D(t)) for t in ("TL01-Ø250", "FL01-400x200", "KS1-300x60", "KV1-X32-16", "AV201-15")] == \
        [250, 400, 300, None, None]


def test_a_run_the_widened_reading_names_with_a_note_belongs_to_the_name_written_on_the_sheet():
    """The widened reading keeps a note beside a name (S3-P5-160 (L)); the sheet writes the name, and the register
    has one entry for it, with the run's metres, for review."""
    from types import SimpleNamespace as NS

    from vvs_engine.register import register_of_designations
    from vvs_engine.semantics.legend import read_legend
    d = NS(text="S3-P5", display_text="S3-P5-160 (L)", aside="(L)", bbox=(100, 100, 190, 109), multiplier=1,
           source="text")
    pa = NS(legend=read_legend([], []), designations=[d], lines=[], quantities=[],
            page=NS(source_path=None, info=NS(index=0)),
            wide_runs=[{"designation": "S3-P5-160 (L)", "size": 160, "metres": 0.19, "pieces": 1,
                        "runs": [[[100.0, 200.0], [110.8, 200.0]]]}])
    reg = register_of_designations(pa)
    assert [(e["name"], e["kind"], e["quantity"], e["state"]) for e in reg["entries"]] == \
        [("S3-P5-160", "ledning", 0.19, "granskas")]
    assert reg["entries"][0]["runs"] and reg["totals"]["wide_metres"] == 0.19


def _closed_ducts(page, shape):
    """The same two ducts, each drawn as a closed outline: its ends are drawn across."""
    for y, width, length in ((300, 0.250, 6), (420, 0.400, 4)):
        x1, d = 100 + length * M, width * M
        for p0, p1 in (((100, y), (x1, y)), ((100, y + d), (x1, y + d)), ((100, y), (100, y + d)), ((x1, y), (x1, y + d))):
            _line(shape, p0, p1, 1.0)
    _label(page, shape, "TL01-Ø250", (150, 240), (220, 300))
    _label(page, shape, "FL01-400x200", (150, 380), (230, 420))


def test_a_duct_drawn_closed_is_measured_along_one_edge_and_its_ends():
    """The name runs round the outline. The second long edge is the duct's other side, and carries no metres; the
    two ends drawn across are in the length - a limit of this reading, the duct's width once per end."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        _, alla = _read(_sheet(os.path.join(tmp, "closed.pdf"), _closed_ducts))
    wide = {r["designation"]: r["metres"] for r in alla.wide_runs}
    assert wide == {"TL01-Ø250": round(6 + 2 * 0.25, 2), "FL01-400x200": round(4 + 2 * 0.40, 2)}, wide
