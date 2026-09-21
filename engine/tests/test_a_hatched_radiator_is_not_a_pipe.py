"""En skrafferad radiator är ingen rörsträcka.

På värmebladen ritas radiatorerna som en tunn rektangel fylld med ett par dussin skrafferstreck, på en egen
penna. Läsningen vägde den pennan som rör: varje hänvisningslinje som gick förbi en radiator fick en andra
kandidatfamilj, ankaret blev tvetydigt, och metrarna på det riktiga röret gick till ingen - hundra meter på ett
blad. Bläck som står still och fyller sin egen ruta är en figur, inte en sträcka.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.pipes.representation import Prim, figure_pieces

PIPE, WRITE, RAD = 1.44, 0.72, 0.96
M = 56.69


def _scale(page):
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * M, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * M, 566), width=1.0, color=(0, 0, 0))


def _radiator(page, x, y, long_pt=110.0, deep_pt=26.0, n=24):
    """En radiator: tunn rektangel med skrafferstreck som inte rör den."""
    page.draw_rect(pymupdf.Rect(x, y, x + long_pt, y + deep_pt), width=RAD, color=(0, 0, 0))
    for k in range(n):
        fx = x + 3 + k * (long_pt - 6) / n
        page.draw_line((fx, y + 2), (fx + 6, y + deep_pt - 2), width=RAD, color=(0, 0, 0))


def _sheet(path, radiators=True):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    y = 300.0
    page.draw_line((100, y), (100 + 8 * M, y), width=PIPE, color=(0, 0, 0))
    if radiators:
        for k in range(3):
            _radiator(page, 140 + k * 150, y + 40)
    for x, to in ((150, 220), (330, 400)):
        page.insert_text((x, 200), "VS21-S13-22-F60", fontsize=10, fontname="helv")
        page.draw_line((x, 203), (x + 60, 203), width=WRITE, color=(0, 0, 0))
        page.draw_line((x + 60, 203), (to, y), width=WRITE, color=(0, 0, 0))
    if radiators:
        # en etikett vars hänvisningslinje landar på en radiator: det är så pennan blir vägd som rör alls, och
        # det är precis fallet som förr gjorde ankaret tvetydigt och tog metrarna från det riktiga röret
        page.insert_text((520, 430), "VS21-S13-22-F60", fontsize=10, fontname="helv")
        page.draw_line((520, 433), (580, 433), width=WRITE, color=(0, 0, 0))
        page.draw_line((580, 433), (446, y + 42), width=WRITE, color=(0, 0, 0))
    _scale(page)
    doc.save(path); doc.close()
    return path


def _read(path):
    pa = analyze_page(extract_document(path).pages[0])
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities), pa


def test_the_pipe_keeps_its_metres_with_radiators_on_the_sheet(tmp_path):
    m, pa = _read(_sheet(str(tmp_path / "radiatorer.pdf")))
    assert 7.4 <= m <= 8.6, f"åtta meter rör bredvid tre radiatorer; fick {m:.2f} m"
    fams = {f.split("|s|")[0] for f in pa.pipe_families}
    assert all(pa.ownership.prim_states[f] for f in pa.graphs), fams


def test_the_radiator_is_read_as_a_figure_and_the_pipe_as_a_run(tmp_path):
    """Streck för streck: radiatorns bläck står still i sin ruta, rörets går någonstans."""
    path = _sheet(str(tmp_path / "figur.pdf"))
    pg = extract_document(path).pages[0]
    rad, pipe = [], []
    for p in pg.paths:
        if p.kind != "s":
            continue
        for k, s2 in enumerate(p.segs):
            if s2.length < 1e-6:
                continue
            q = Prim(prim_id=0, pid=p.pid, seg_index=k, seg=s2, family="f", layer=p.layer, width=p.width)
            (rad if abs(p.width - RAD) < 0.01 else pipe if abs(p.width - PIPE) < 0.01 else []).append(q)
    assert rad and pipe
    runs, figures = figure_pieces(rad)
    assert not runs and len(figures) == len(rad), (len(runs), len(figures))
    runs, figures = figure_pieces(pipe)
    assert not figures and len(runs) == len(pipe), (len(runs), len(figures))


def test_a_run_is_not_a_figure_however_long(tmp_path):
    """Regeln får inte ta ett rör: en lång sträcka har bläck i proportion till vad den spänner över."""
    doc = pymupdf.open(); page = doc.new_page(width=842, height=595)
    prims = []
    for k in range(40):
        page.draw_line((100 + k * 12, 300), (112 + k * 12, 300), width=PIPE, color=(0, 0, 0))
    _scale(page)
    path = str(tmp_path / "lang.pdf"); doc.save(path); doc.close()
    pg = extract_document(path).pages[0]
    segs = [Prim(prim_id=i, pid=p.pid, seg_index=k, seg=s, family="f", layer=p.layer, width=p.width)
            for i, p in enumerate(pg.paths) for k, s in enumerate(p.segs) if abs(s.y0 - 300) < 0.5 and s.length > 1]
    runs, figures = figure_pieces(segs)
    assert figures == [] and len(runs) == len(segs), (len(runs), len(figures))
