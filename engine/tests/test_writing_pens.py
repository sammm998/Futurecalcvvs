"""What a sheet writes with is never what it draws with.

An office that gives each system its own layer gives that system's *text* its own layer too, named the same way:
the pipes on `V-56B--FE-_VS2x-`, the labels and their leaders on `V-56B---T-_VS2x-`. Two rules in the reading
looked at those names and drew the wrong conclusion from each.

The first gathers layers that follow an accepted pipe layer's name template, so that a size drawn on a layer no
label happens to reach is still measured. Handed a sheet named this way it gathered the text layer with the
pipe layers - and a text layer taken as pipe turns every leader the tracer did not follow into metres, then
wins the reading, because the labels all reach their own leaders.

The second learns which pens the sheet writes with from the attachments the first reading verified, and hides
those pens from the second reading's leader search. Learned from the verified blocks alone, it knew the text
layers of the systems that happened to verify and no others - so the second reading withdrew the leaders of
every system that had not, and those systems went unlabelled and unmeasured. One sheet of five hundred lost a
hundred and seven of its hundred and seven metres that way.

Both are held here by the drawn evidence that settles them: the bar ruled under a designation is annotation and
nothing else, it is drawn for every label the sheet writes, and no pipe is ever one.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

# One office, two systems, and for each of them a flow layer, a return layer and a text layer, all named the
# same way. That is what widens the name template until it reaches the text layers: two content codes among the
# accepted pipe layers make that position a variable, and the system position already is one. The second
# system's pipes are drawn with the pen the sheet writes with, so the style matches too - which is the shape the
# real sheet had, and the shape under which the reading measured its own leaders as pipe.
PIPE_LAYER = "V-56B--FE-_VS2x-"
RETURN_LAYER = "V-56B--KE-_VS2x-"
TEXT_LAYER = "V-56B---T-_VS2x-"
PIPE_LAYER_2 = "V-56B--FE-_VS1x-"
TEXT_LAYER_2 = "V-56B---T-_VS1x-"
TEXT_LAYERS = (TEXT_LAYER, TEXT_LAYER_2)
WRITE_PEN = 0.96


def _label(page, oc, x, y, target, text):
    """A designation with a bar ruled under it and a line from the bar's end up to its pipe."""
    page.insert_text((x, y), text, fontsize=10, fontname="helv", oc=oc)
    page.draw_line((x, y + 2), (x + 76, y + 2), width=WRITE_PEN, color=(0, 0, 0), oc=oc)
    page.draw_line((x + 76, y + 2), (x + 76, target), width=WRITE_PEN, color=(0, 0, 0), oc=oc)
    page.draw_line((x + 75, target - 1), (x + 77, target + 1), width=WRITE_PEN, color=(0, 0, 0), oc=oc)


def _sheet(path: str) -> str:
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=760)
    oc = {n: doc.add_ocg(n) for n in (PIPE_LAYER, RETURN_LAYER, TEXT_LAYER, PIPE_LAYER_2, TEXT_LAYER_2)}

    runs = ((PIPE_LAYER, 1.44, (300.0, 340.0)),
            (RETURN_LAYER, WRITE_PEN, (560.0, 600.0)),
            (PIPE_LAYER_2, WRITE_PEN, (160.0, 200.0)))
    for layer, pen, ys in runs:
        for y in ys:
            page.draw_line((100, y), (700, y), width=pen, color=(0, 0, 0), oc=oc[layer])

    for x, y, target in ((200.0, 420.0, 340.0), (500.0, 420.0, 300.0)):
        _label(page, oc[TEXT_LAYER], x, y, target, "VS21-S13-15-F50")
    for x, y, target in ((200.0, 680.0, 600.0), (500.0, 680.0, 560.0)):
        _label(page, oc[TEXT_LAYER], x, y, target, "VS22-S13-15-F50")
    for x, y, target in ((200.0, 100.0, 160.0), (500.0, 100.0, 200.0)):
        _label(page, oc[TEXT_LAYER_2], x, y, target, "VS11-S13-35-F60")

    page.insert_text((100, 730), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 730), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 736), (302 + 5 * 56.69, 736), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def test_the_layer_a_sheet_writes_on_is_never_taken_as_pipe(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "per-system.pdf"))).pages[0])
    took = {f.partition("|s|")[0] for f in pa.pipe_families}
    assert not (set(TEXT_LAYERS) & took), (
        "a layer carrying the sheet's own designation bars and leaders was measured as pipe; "
        f"took {sorted(took)}")


def test_the_pipes_are_still_found(tmp_path):
    """The refusal must cost nothing: the pipes under those labels are still measured."""
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "per-system2.pdf"))).pages[0])
    took = {f.partition("|s|")[0] for f in pa.pipe_families}
    assert {PIPE_LAYER, RETURN_LAYER, PIPE_LAYER_2} <= took, f"a pipe layer went missing; took {sorted(took)}"
    assert any((q.get("confirmed_horizontal_m") or 0) > 1 for q in pa.quantities), \
        "the labelled runs must still carry metres"


def test_every_label_frame_teaches_the_writing_pens(tmp_path):
    """The pens learned for the second reading come from every label's frame, not only the verified ones."""
    from vvs_engine.pipes.representation import stroke_family
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "per-system3.pdf"))).pages[0])
    frames = {stroke_family(u.layer, u.width, u.color)
              for b in pa.blocks for r in b.rows for u in r.underline}
    assert frames, "the sheet rules a bar under each designation"
    assert not (frames & set(pa.pipe_families)), \
        "a pen that rules the bar under a designation is a writing pen and may not be measured as pipe"
