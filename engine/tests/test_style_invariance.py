"""The same drawing in another house style reads the same: turned, printed on another paper size, all pens black."""
import pymupdf

from vvs_engine.pdf.orient import text_turn


def _sheet(path, rotate=0, upright_text=True):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    for i in range(6):
        text = f"VS2-S13-{12 + i}/S4"
        if upright_text:
            page.insert_text((80, 80 + 40 * i), text, fontsize=9)
        else:
            page.insert_text((80 + 40 * i, 500), text, fontsize=9, rotate=90)
    page.set_rotation(rotate)
    doc.save(path)
    return path


def test_a_sheet_turned_by_its_rotate_entry_is_turned_back_by_its_text(tmp_path):
    # P0113 exported with /Rotate 90 over upright content: 6 of 24 designations measured before
    assert text_turn(_sheet(tmp_path / 'upright.pdf'), 0) == 0
    assert text_turn(_sheet(tmp_path / 'viewer_turned.pdf', rotate=90), 0) == 270
    # content drawn on its side on an upright page reads up the sheet: a quarter turn shows it left to right
    assert text_turn(_sheet(tmp_path / 'content_turned.pdf', upright_text=False), 0) == 90


def test_a_sheet_without_a_text_layer_leaves_the_turn_to_its_reading(tmp_path):
    doc = pymupdf.open(); doc.new_page(width=842, height=595).draw_line((10, 10), (500, 10)); doc.save(tmp_path / 'ink.pdf')
    assert text_turn(tmp_path / 'ink.pdf', 0) is None


def test_a_ratio_stated_for_another_paper_size_is_rescaled_to_this_one():
    from types import SimpleNamespace
    from vvs_engine.measure.scale import _ratio_for_other_format, ScaleEvidence, MM_PER_PT
    a2 = SimpleNamespace(info=SimpleNamespace(width=594 / MM_PER_PT, height=420 / MM_PER_PT))
    t = ScaleEvidence(kind='scale_text', text='SKALA 1:50 (A1)', bbox=[], value=50 * MM_PER_PT / 1000, detail={})
    value, stated, actual = _ratio_for_other_format(a2, t)
    assert (stated, actual) == ('A1', 'A2') and abs(value / t.value - 2 ** 0.5) < 1e-9


def test_a_stored_style_yields_to_the_sheets_own_leaders_sooner_than_the_width_rule():
    from types import SimpleNamespace as NS
    from vvs_engine.source_rules import native_detection as nd
    nd.load_runtime()
    # V-50-1-666340-0113 with every pen black: 40 landings on 1.44 pt against 25 on the chosen 0.72 pt
    votes = {'1.44|black': {'landings': 40, 'length': 3007.0}, '0.72|black': {'landings': 25, 'length': 1359.0}}
    def calib(method):
        return {'calibration': {'pipe_widths': [0.72], 'family_method': method, 'u_paper': 1.0,
                                'landings': {'votes': votes, 'leader_families': {'0.48|black': 30}}}}
    pipe = NS(id=1, kind='s', width=1.44, color=[0.0, 0.0, 0.0], dashes='[] 0', layer='', closed=False,
              items=[['l', 0.0, 0.0, 50.0, 0.0]], duplicate_of=None, rect=[0.0, 0.0, 50.0, 0.0])
    ex = NS(paths=[pipe])
    # the sheet's own width rule keeps PipeStudio's 5x margin
    assert nd.landed_policy(ex, calib('width rule, confirmed by 25 leader landings')) is None
    # a value from another office's stored style yields at 1.5x
    landed = nd.landed_policy(ex, calib('library starting values (blackhornet-2xa0) confirmed by the sheet'))
    assert landed is not None and landed['report']['landed_pipe_pen'] == '1.44|black'
