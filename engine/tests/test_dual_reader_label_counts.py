from types import SimpleNamespace as NS
from vvs_engine.measure.label_counts import verified_label_counts


def anchor(aid, row, paths, native=False, page=0):
    return NS(anchor_id=aid, designation_id=row, leader_paths=paths, page=page,
              state='VERIFIED_PIPE_ATTACHMENT', evidence={'source':'pipestudio'} if native else {})


def test_one_written_label_has_multiple_landings_and_two_readers():
    anchors = [anchor('a','written1',['leader']), anchor('b','written1',['leader']),
               anchor('c','native1',['leader'],True), anchor('d','native1',['leader'],True),
               anchor('e','written2',['other'])]
    assert verified_label_counts(anchors,{a.anchor_id:NS(key='KV1|DN16') for a in anchors}) == {'KV1|DN16':2}


def test_same_name_on_separate_pages_and_distinct_parallel_leaders_is_retained():
    anchors=[anchor('a','row',['leader']),anchor('b','row',['leader'],page=1),
             anchor('c','native',['parallel'],True)]
    assert verified_label_counts(anchors,{a.anchor_id:NS(key='KV1|DN16') for a in anchors}) == {'KV1|DN16':3}


def test_different_designations_on_same_leader_are_not_collapsed():
    anchors=[anchor('a','row',['leader']),anchor('b','native',['leader'],True)]
    assert verified_label_counts(anchors,{'a':NS(key='KV1|DN16'),'b':NS(key='VV1|DN16')}) == {'KV1|DN16':1,'VV1|DN16':1}
