"""A dashed pipe that passes a label is the pipe, not the side of the label's frame.

On W-50-1-A-0013 a short drain run is drawn on its own layer right beside a label: three of its five dashes
fell inside the label's span, were taken for the label's box and set aside as annotation, and the run - its
own leader ending on its end with a tick - measured nothing. A frame side ends at the frame's corners; a dash
of a pipe carries on along the same line past the label, the same pen a gap apart.
"""
from vvs_engine.geometry.core import GridIndex, Seg
from vvs_engine.semantics.annotation import FreeSeg, _dash_of_a_run
from vvs_engine.text.model import row_axes


def _index(segs):
    idx = GridIndex(cell=30.0)
    fmap = {}
    for f in segs:
        idx.insert(f.fid, f.seg.bbox())
        fmap[f.fid] = f
    return fmap, idx


def _seg(fid, x0, y0, x1, y1, width=2.04, layer="V-D1"):
    return FreeSeg(fid=fid, pid=f"p{fid}", seg_index=0, seg=Seg(x0, y0, x1, y1), layer=layer, width=width,
                   n_path_segs=1, color=(0, 0, 0))


def test_a_dash_whose_line_runs_on_past_the_label_is_a_dash():
    # five dashes down x=793, a gap of about four points between them; the label spans y 292..329
    ys = [(219, 237), (241.2, 258.3), (262.5, 279.5), (283.7, 300.8), (305, 323)]
    segs = [_seg(i, 793, a, 793, b) for i, (a, b) in enumerate(ys)]
    fmap, idx = _index(segs)
    d, n = row_axes(0.0)
    for f in segs[3:]:
        assert _dash_of_a_run(f, fmap, idx, d, n, 287.0, 334.0, 8.0)


def test_the_sides_of_stacked_boxes_are_still_a_frame():
    # two boxes stacked: their left sides touch end to end on one axis, and neither is a dashed line
    segs = [_seg(0, 100, 290, 100, 310, width=0.48, layer="T"), _seg(1, 100, 310, 100, 330, width=0.48, layer="T")]
    fmap, idx = _index(segs)
    d, n = row_axes(0.0)
    assert not _dash_of_a_run(segs[0], fmap, idx, d, n, 285.0, 315.0, 8.0)


def test_a_frame_side_alone_is_a_frame():
    segs = [_seg(0, 100, 290, 100, 310, width=0.48, layer="T")]
    fmap, idx = _index(segs)
    d, n = row_axes(0.0)
    assert not _dash_of_a_run(segs[0], fmap, idx, d, n, 285.0, 315.0, 8.0)
