from types import SimpleNamespace as NS
from vvs_engine.source_rules.geometry_evidence import has_pipe_run


def test_short_system_with_own_matching_leader_is_not_discarded_by_sheet_total():
    assert has_pipe_run(NS(kind='sparse',longest_chain=37,total_length=54.5,width=2.04),1,.48)


def test_short_symbol_strokes_and_unsupported_sparse_families_stay_out():
    assert not has_pipe_run(NS(kind='fragmented-dashed',longest_chain=11.5,total_length=87.6),2)
    assert not has_pipe_run(NS(kind='sparse',longest_chain=37,total_length=54.5),0)
    assert has_pipe_run(NS(kind='fragmented-dashed',longest_chain=100,total_length=200),0)


def test_matching_annotation_layer_is_not_promoted_as_a_short_pipe():
    assert not has_pipe_run(NS(kind='sparse',longest_chain=37,total_length=54.5,width=.48),1,.48)
    assert not has_pipe_run(NS(kind='sparse',longest_chain=37,total_length=54.5,width=2.04),1,None)
