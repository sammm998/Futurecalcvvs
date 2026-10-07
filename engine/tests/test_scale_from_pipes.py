"""A sheet without a stated scale is measured on its pipes - but only where they are drawn with both edges."""
from types import SimpleNamespace as NS

from vvs_engine.geometry.core import Seg
from vvs_engine.measure.scale import MM_PER_PT, pipe_scale, snap_ratio


def _page(pipes):
    """Each pipe drawn as two parallel edges `gap` points apart, all in one pen."""
    paths = []
    for i, (y, gap) in enumerate(pipes):
        for k, yy in enumerate((y, y + gap)):
            paths.append(NS(pid=f"p{i}{k}", kind="s", layer="VS", width=0.5, color=(0, 0, 0),
                            segs=[Seg(0, yy, 200, yy)]))
    return NS(paths=paths)


def _anchors(pipes, dns):
    from vvs_engine.pipes.representation import stroke_family
    fam = stroke_family("VS", 0.5, (0, 0, 0))
    return [NS(dn=dn, designation_display=f"S2-P5-{dn}", contacts=[NS(kind="end", point=(100, y), family=fam)])
            for (y, _), dn in zip(pipes, dns)]


def test_pipes_drawn_with_both_edges_give_the_standard_scale():
    pt_per_mm = 1 / (50 * MM_PER_PT)                       # 1:50
    dns = [110, 75, 160, 110]
    pipes = [(100 * i, dn * pt_per_mm) for i, dn in enumerate(dns)]
    ev = pipe_scale(_page(pipes), _anchors(pipes, dns))
    assert ev is not None and ev.detail["standard_ratio"] == 50
    assert abs(ev.value - 50 * MM_PER_PT / 1000) < 1e-12


def test_a_pair_of_single_lines_is_not_a_pipe_width():
    # 12 and 16 drawn as pairs 8 and 10.5 pt apart agree with each other at about 1:4 - no plan is drawn so
    dns = [12, 16, 12, 16]
    pipes = [(100 * i, 8.0 if dn == 12 else 10.5) for i, dn in enumerate(dns)]
    assert pipe_scale(_page(pipes), _anchors(pipes, dns)) is None


def test_one_size_alone_settles_nothing():
    pt_per_mm = 1 / (50 * MM_PER_PT)
    pipes = [(100 * i, 110 * pt_per_mm) for i in range(4)]
    assert pipe_scale(_page(pipes), _anchors(pipes, [110] * 4)) is None


def test_snap():
    assert snap_ratio(100 * MM_PER_PT / 1000 * 1.03)[1] == 100
    assert snap_ratio(100 * MM_PER_PT / 1000 * 1.3)[1] is None
