import pytest
from vectorascore import bucket, assemble, labels
from vectorascore.extract import Extraction, Path


def path(i, points, width=1.44):
    return Path(i, 's', width, [0, 0, 0], None, '[] 0', '', False,
                [min(x for x, y in points), min(y for x, y in points),
                 max(x for x, y in points), max(y for x, y in points)],
                [['l', *a, *b] for a, b in zip(points, points[1:])])


@pytest.mark.parametrize('ys,expected', [([22], {'over': True, 'under': False}),
                                       ([36], {'over': False, 'under': True}),
                                       ([22, 36], {'over': True, 'under': True})])
@pytest.mark.parametrize('bar_length,dimension', [(10, '75'), (28.32, '50/W'), (28.32, '50/WB')])
def test_direction_bars_are_metadata_not_pipes(monkeypatch, ys, expected, bar_length, dimension):
    calibration = {'pipe_widths': [1.44], 'leader_width': .48, 'dash_gaps': {},
                   'circle': None, 'has_layers': False, 'layers': {}, 'pipe_layers': []}
    monkeypatch.setattr(bucket, 'calibrate', lambda *args, **kwargs: calibration)   # bucket passes the extraction, label boxes and style mode too
    paths = [path(i, [(20, y), (20 + bar_length, y)]) for i, y in enumerate(ys)]
    paths += [path(10, [(5, 40), (70, 40)]),  # crossing pipe
              path(11, [(10, 42), (21, 42)]),  # centre inside, endpoint outside
              path(12, [(20, 37), (20, 43)]),  # vertical stroke inside
              path(13, [(20, 21), (50, 21), (70, 40)], .48)]  # shelf + leader
    ex = Extraction('synthetic', [100, 100], 0, paths)
    label = {'id': 7, 'rect': [15, 10, 55, 45], 'stroke_notation': None,
             'rows': [{'text': 'S1-P2', 'rect': [18, 13, 40, 21]},
                      {'text': dimension, 'rect': [20, 27, 30, 34]}]}
    b = bucket.bucket(ex, {}, {'label_boxes': [label]})
    labels.refresh_stroke_notation([label], ex, b['buckets'])
    assert label['stroke_notation'] == expected
    assert len(label['stroke_bars']) == len(ys)
    assert all(b['buckets'][str(i)] == 'stroke_bar' for i in range(len(ys)))
    assert b['buckets']['10'] == 'pipe'
    assert b['buckets']['11'] == 'pipe'
    assert b['buckets']['12'] == 'pipe'
    assert b['buckets']['13'] != 'stroke_bar'
    # Removing notation before assembly yields the same pipe graph.
    a = assemble.assemble(ex, b)
    clean = Extraction('synthetic', [100, 100], 0, paths[len(ys):])
    assert a == assemble.assemble(clean, b)


@pytest.mark.parametrize('dimension', ['50/W', '50/WB'])
@pytest.mark.parametrize('y,side', [(22, 'over'), (36, 'under')])
def test_long_bar_is_read_from_pdf(monkeypatch, dimension, y, side):
    import fitz
    import pipe_types
    monkeypatch.setattr(pipe_types, '_LETTERING_INDEX', {})
    doc = fitz.open()
    page = doc.new_page(width=100, height=100)
    page.draw_line((20, y), (48.32, y), color=(0, 0, 0), width=1.44)
    # Centre inside is insufficient: this second line crosses the label box.
    page.draw_line((5, 40), (70, 40), color=(0, 0, 0), width=1.44)
    rows = [('FJV1-S6', fitz.Rect(18, 13, 50, 21), 92),
            (dimension, fitz.Rect(20, 27, 48, 34), 92)]
    bars = pipe_types.stroke_bars(page, [15, 10, 55, 45], rows)
    assert len(bars) == 1
    assert bars[0]['side'] == side
    assert bars[0]['x1'] - bars[0]['x0'] == pytest.approx(28.32)
    doc.close()
