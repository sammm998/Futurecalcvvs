import pymupdf
import pytest
from shapely.geometry import Point
from vvs_engine.pdf.visibility import clip_geometry
from vvs_engine.pdf.extract import extract_document


def document(tmp_path, stream, rotation=0):
    d=pymupdf.open();p=d.new_page(width=200,height=200)
    x=d.get_new_xref();d.update_object(x,'<<>>');d.update_stream(x,stream.encode());p.set_contents(x)
    p.set_rotation(rotation);path=tmp_path/'clip.pdf';d.save(path);d.close()
    return extract_document(str(path)).pages[0]


def test_diagonal_clip_uses_polygon_not_bounds(tmp_path):
    pg=document(tmp_path,'q 0 0 m 200 0 l 0 200 l h W n 2 w 20 180 m 190 180 l S Q')
    assert sum(p.length for p in pg.paths)==pytest.approx(0,abs=1e-6)
    assert pg.visibility_report['hidden_paths']==1


def test_partial_clip_preserves_source_interval(tmp_path):
    pg=document(tmp_path,'q 0 0 100 200 re W n 2 w 20 100 m 180 100 l S Q')
    assert sum(p.length for p in pg.paths)==pytest.approx(80)
    assert pg.paths[0].source_length_pt==pytest.approx(160)
    assert pg.paths[0].visible_intervals[0]==pytest.approx((0,0,.5))


def test_nested_clips_restore_parent_and_page(tmp_path):
    pg=document(tmp_path,'q 0 0 100 200 re W n q 0 0 50 200 re W n 0 50 m 180 50 l S Q 0 100 m 180 100 l S Q 0 150 m 180 150 l S')
    assert sorted(p.length for p in pg.paths)==pytest.approx([50,100,180])


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_rotating_clipped_page_keeps_length(tmp_path,angle):
    pg=document(tmp_path,'q 0 0 100 200 re W n 20 100 m 180 100 l S Q',angle)
    assert sum(p.length for p in pg.paths)==pytest.approx(80)


def test_clip_fill_rule_holes_and_winding():
    items=[('re',pymupdf.Rect(0,0,100,100),1),('re',pymupdf.Rect(20,20,80,80),1)]
    assert clip_geometry(items,False).covers(Point(50,50))
    assert not clip_geometry(items,True).covers(Point(50,50))
    items[1]=('re',pymupdf.Rect(20,20,80,80),-1)
    assert not clip_geometry(items,False).covers(Point(50,50))


def test_same_geometry_different_color_has_distinct_source(tmp_path):
    pg=document(tmp_path,'0 0 0 RG 20 100 m 180 100 l S 1 0 0 RG 20 100 m 180 100 l S')
    assert len({p.pid for p in pg.paths})==2
    assert not any(p.pid.endswith('_1') for p in pg.paths)


def test_dash_pattern_preserved(tmp_path):
    pg=document(tmp_path,'[8 3 1 3] 2 d 20 100 m 180 100 l S')
    assert '8 3 1 3' in pg.paths[0].dashes


def test_transparent_stroke_does_not_enter_geometry(tmp_path):
    d=pymupdf.open();p=d.new_page(width=200,height=200)
    p.draw_line((10,10),(180,10),stroke_opacity=0)
    p.draw_line((10,30),(180,30),stroke_opacity=1)
    path=tmp_path/'opacity.pdf';d.save(path);d.close()
    pg=extract_document(str(path)).pages[0]
    assert len(pg.paths)==1
    assert pg.visibility_report['hidden_paths']==1


def test_open_fill_stroke_hairline_remains_measurable(tmp_path):
    from vvs_engine.pipes.ink import is_stroked
    pg=document(tmp_path,'0 w 20 100 m 180 100 l B')
    assert len(pg.paths)==1 and pg.paths[0].width==0
    assert is_stroked(pg.paths[0])


def test_clip_curve_must_not_shortcut_collinear_reversal():
    from vvs_engine.pdf.visibility import _curve
    pts=_curve((0,0),(100,0),(-100,0),(10,0))
    assert len(pts)>2 and min(x for x,y in pts)<0 and max(x for x,y in pts)>10


def test_rectangle_acceleration_matches_exact_intersections():
    import random
    from shapely.geometry import box
    from vvs_engine.geometry.core import Seg
    from vvs_engine.pdf.visibility import Visibility, clip_segments
    rng = random.Random(1701)
    v = Visibility((0, 0, 200, 200))
    state = v.consume({'type': 's'})
    lines = [Seg(0, 0, 200, 0), Seg(0, 0, 0, 200), Seg(-10, 50, 210, 50)]
    lines += [Seg(*(rng.uniform(-100, 300) for _ in range(4))) for _ in range(300)]
    for i, line in enumerate(lines):
        visible, intervals = v.apply([line], {'type': 's'}, state, str(i))
        expected, expected_intervals = clip_segments([line], box(0, 0, 200, 200))
        assert sum(s.length for s in visible) == pytest.approx(sum(s.length for s in expected), abs=1e-8)
        assert len(intervals) == len(expected_intervals)
        for actual, expected_interval in zip(intervals, expected_intervals):
            assert actual == pytest.approx(expected_interval)
