"""Non-pipe notes still draw annotation: they must never become pipe runs."""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page


def test_notes_on_their_own_pen_are_not_pipes(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    for i in range(3):
        y = 200+i*100
        page.draw_line((150,y),(650,y),width=2.04,color=(0,0,0))
        page.draw_circle((147,y),3,width=.48,color=(0,0,0))
        page.insert_text((50,y-40),'S01-P5-110',fontsize=10)
        page.draw_line((50,y-37),(112,y-37),width=.48,color=(0,0,0))
        page.draw_line((112,y-37),(147,y),width=.48,color=(0,0,0))
        page.insert_text((700,y-50),'SE DETALJ',fontsize=10)
        page.draw_line((700,y-47),(750,y-47),width=.96,color=(0,0,0))
        page.draw_line((700,y-47),(147,y),width=.96,color=(0,0,0))
    file=tmp_path/'notes.pdf'
    doc.save(file);doc.close()
    result=analyze_page(extract_document(str(file)).pages[0],given_scale=50 * 25.4 / 72 / 1000)
    metres=sum(q['confirmed_horizontal_m'] for q in result.quantities)
    assert 25 < metres < 28, metres  # three 500pt pipe runs, never diagonal note leaders
    assert all(abs(f.width-.96)>.01 for f in result.pipe_families.values())


def test_riser_read_as_a_letter_on_a_pipe_layer_does_not_erase_its_pipe(tmp_path):
    from vvs_engine.pipeline import prepare_page
    from vvs_engine.semantics.leaders import discover_leaders

    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    layer = doc.add_ocg('V-53BB-FE--S01-')
    for i in range(3):
        y = 200+i*100
        page.draw_line((150, y), (650, y), width=2.04, color=(0, 0, 0), oc=layer)
        page.draw_circle((147, y), 3, width=2.04, color=(0, 0, 0), oc=layer)
        page.insert_text((50, y-40), 'S01-P5-110', fontsize=10)
        page.draw_line((50, y-37), (112, y-37), width=.48, color=(0, 0, 0))
        page.draw_line((112, y-37), (147, y), width=.48, color=(0, 0, 0))
    file = tmp_path/'riser-symbols.pdf'
    doc.save(file)
    doc.close()
    page = extract_document(str(file)).pages[0]
    prep = prepare_page(page)
    # These real circle shapes trigger vector O/zero readings and false leaders.
    blocks = {b.bid: b for b in prep.blocks}
    candidates = discover_leaders(page, prep.blocks, prep.free, prep.vtext.marks, None)
    false = [ld for ld in candidates if all(r.text_norm in ('O', '0')
                                           for r in blocks[ld.block_id].rows)]
    assert len(false) == 3
    result = analyze_page(page, prepared=prep, given_scale=50 * 25.4 / 72 / 1000)
    assert not ({ld.lid for ld in false} & {ld.lid for ld in result.leaders})
    metres = sum(q['confirmed_horizontal_m'] for q in result.quantities)
    assert 26.4 < metres < 26.5  # all three 500pt pipe runs still exist


def test_repeated_coupling_ticks_are_not_annotation_text_on_a_component_layer():
    from types import SimpleNamespace
    from vvs_engine.pipeline import _annotation_row_has_text
    def row(text, source='stroke', layer='component-symbols'):
        return SimpleNamespace(text_norm=text, line=SimpleNamespace(source=source, layer=layer))
    for text in ('I / / / /', '1 / / /', '| \\ \\ \\', '/ /'):
        assert not _annotation_row_has_text(row(text), {'pipe-layer'})
    # Actual text, detail identifiers and notes keep their annotation leaders.
    for text in ('SE DETALJ', 'B1', 'I', '1/2', 'KV1/16'):
        assert _annotation_row_has_text(row(text), {'pipe-layer'})
    assert _annotation_row_has_text(row('I / / / /', source='text'), set())
