from types import SimpleNamespace as NS
from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Prim, build_graph
from vvs_engine.semantics.attachment import Contact
from vvs_engine.source_rules.landings import complete_circuit_symbol_contacts


def scene(xs=(0, 20.4), system='FJV1', leader_y=0):
    prims = [Prim(i, f'pipe-{i}', 0, Seg(x, 2, x, 100), 'family', 'layer', 1) for i,x in enumerate(xs)]
    graph = build_graph(prims, 'family')
    symbols = []
    for i,x in enumerate(xs):
        segs = [Seg(x-2,-2,x+2,-2), Seg(x+2,-2,x+2,2), Seg(x+2,2,x-2,2), Seg(x-2,2,x-2,-2)]
        symbols.append(NS(pid=f'ring-{i}', kind='s', bbox=(x-2,-2,x+2,2), segs=segs))
    a = NS(anchor_id='a', state='VERIFIED_PIPE_ATTACHMENT', multiplier=1, system_token=system,
           leader_id='l', leader_paths=['leader'], evidence={},
           contacts=[Contact((xs[-1],2),'via_symbol','family',f'pipe-{len(xs)-1}',0,0)])
    ld = NS(lid='l', segs=[NS(seg=Seg(-20,leader_y,xs[-1],leader_y))])
    return {'family':graph}, a, ld, NS(paths=symbols)


def test_circuit_leader_passes_through_first_ring_not_just_its_endpoint():
    g,a,l,p = scene()
    length = sum(x.seg.length for x in g['family'].prims.values())
    r = complete_circuit_symbol_contacts(g,[a],[l],p)
    assert len(r) == 1 and len(a.contacts) == 2
    assert a.contacts[-1].point == (0,2) and a.contacts[-1].via == 'ring-0'
    assert sum(x.seg.length for x in g['family'].prims.values()) == length
    assert complete_circuit_symbol_contacts(g,[a],[l],p) == []


def test_nearby_pair_without_a_drawn_symbol_contact_is_not_inferred():
    g,a,l,p = scene(leader_y=8)
    assert complete_circuit_symbol_contacts(g,[a],[l],p) == []


def test_single_pipe_system_does_not_take_a_second_contact():
    g,a,l,p = scene(system='KV1')
    assert complete_circuit_symbol_contacts(g,[a],[l],p) == []


def test_three_contacted_runs_do_not_guess_which_two_form_a_pair():
    g,a,l,p = scene(xs=(0,10,20.4))
    assert complete_circuit_symbol_contacts(g,[a],[l],p) == []
