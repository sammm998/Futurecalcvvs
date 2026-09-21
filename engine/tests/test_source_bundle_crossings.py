"""An explicit Nx leader crossing must survive the graph adapter without extra ink."""
from types import SimpleNamespace as NS

from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Prim, build_graph
from vvs_engine.semantics.attachment import Contact
from vvs_engine.source_rules.landings import complete_drawn_bundle_contacts, split_at_landings


def fixture(xs=(0,4), count=2, leader_end=4):
    prims=[Prim(i,f'path-{i}',0,Seg(x,0,x,100),'family','pipe-layer',1) for i,x in enumerate(xs)]
    graph=build_graph(prims,'family')
    anchor=NS(anchor_id='anchor',leader_id='leader',multiplier=count,state='VERIFIED_PIPE_ATTACHMENT',
              leader_paths=['leader-path'],evidence={},contacts=[Contact((4,50),'end','family','path-1',0,0)])
    leader=NS(lid='leader',segs=[NS(seg=Seg(-20,50,leader_end,50))])
    return {'family':graph},anchor,leader


def test_explicit_two_pipe_leader_exposes_two_landings_and_preserves_ink():
    graphs,anchor,leader=fixture()
    before=sum(p.seg.length for p in graphs['family'].prims.values())
    report=complete_drawn_bundle_contacts(graphs,[anchor],[leader])
    assert len(report)==1
    assert len(anchor.contacts)==2
    assert anchor.contacts[-1].point==(0,50)
    assert anchor.contacts[-1].kind=='bundle_crossing'
    assert split_at_landings(graphs,[anchor])==2
    assert sum(p.seg.length for p in graphs['family'].prims.values())==before
    # Reprocessing cannot add contacts, nodes or count the pipe again.
    assert complete_drawn_bundle_contacts(graphs,[anchor],[leader])==[]
    assert split_at_landings(graphs,[anchor])==0
    assert len(graphs['family'].prims)==4


def test_ordinary_leader_never_claims_a_pipe_it_only_crosses():
    graphs,anchor,leader=fixture(count=1)
    assert complete_drawn_bundle_contacts(graphs,[anchor],[leader])==[]
    assert len(anchor.contacts)==1


def test_excess_candidates_do_not_choose_nearest_pipes():
    graphs,anchor,leader=fixture(xs=(0,4,-4))
    assert complete_drawn_bundle_contacts(graphs,[anchor],[leader])==[]


def test_proximity_without_drawn_crossing_does_not_add_a_contact():
    graphs,anchor,leader=fixture()
    leader.segs=[NS(seg=Seg(2,50,4,50))]
    assert complete_drawn_bundle_contacts(graphs,[anchor],[leader])==[]


def test_other_family_is_not_part_of_the_bundle():
    graphs,anchor,leader=fixture()
    graphs['family']=build_graph([graphs['family'].prims[1]],'family')
    other=Prim(0,'other-pipe',0,Seg(0,0,0,100),'other','other-system',1)
    graphs['other']=build_graph([other],'other')
    assert complete_drawn_bundle_contacts(graphs,[anchor],[leader])==[]
