"""A short frame-to-pipe leader survives the text reader's marker inventory."""
from types import SimpleNamespace as NS

import pytest

from vvs_engine.geometry.core import Seg
from vvs_engine.semantics.annotation import AnnotationBlock, BlockRow, FreeSeg
from vvs_engine.semantics.leaders import discover_leaders
from vvs_engine.text.model import TextRow
from vvs_engine.text.vector_text import Mark


def fixture_parts(tick=True, frame=True, offset=0):
    # The drawing uses a separate 9.3 pt leader and a tick centred on its far end.
    sg = Seg(88.44, 92.52, 96.36, 97.32)
    rule = FreeSeg(0, 'rule', 0, Seg(96.36+offset, 97.32, 140.76, 97.32), 'notes', .48, 1, (0.,0.,0.))
    row = TextRow("row", 0, "S3-R8-75", [], (99.18,88.32,138.12,94.8), 0., 6.48, "stroke", layer="notes")
    b = AnnotationBlock('label', 0, [BlockRow(row, 'designation', [rule] if frame else [], 'S3-R8-75')],
                        (99.18,88.32,138.12,94.8), 0., 6.48, 'notes', 'stroke', units=[[0]])
    path = NS(pid='short-leader', segs=[sg], n_curves=0, layer='notes', width=.48, color=(0.,0.,0.))
    mark = Mark('candidate', 'notes', 'pen', sg.bbox(), [sg], ['short-leader'])
    marks = [mark]
    if tick:
        ts = Seg(88.44,89.64,88.44,95.28)
        marks.append(Mark('tick','notes','pen',ts.bbox(),[ts],['tick-path']))
    return NS(paths=[path],info=NS(index=0)), [b], [rule] if frame else [], marks


def test_a_short_leader_names_the_pipe_at_its_separate_tick():
    page, blocks, free, marks = fixture_parts()
    leaders = discover_leaders(page, blocks, free, marks)
    recovered = [l for l in leaders if 'short-leader' in l.path_ids]
    assert len(recovered) == 1
    l = recovered[0]
    assert l.end == (88.44,92.52)
    assert [m.mid for m in l.end_marks] == ['tick']
    assert not l.crossing_marks  # the leader must never become its own boundary marker


@pytest.mark.parametrize('kwargs', [{'tick': False}, {'frame': False}, {'offset': 1.0}])
def test_small_strokes_near_text_do_not_invent_leaders(kwargs):
    page, blocks, free, marks = fixture_parts(**kwargs)
    assert not any('short-leader' in l.path_ids for l in discover_leaders(page, blocks, free, marks))
