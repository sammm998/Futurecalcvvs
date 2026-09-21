import pytest
from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Prim,build_graph
from vvs_engine.pipes.ownership import Identity,PrimState,_resolve_family


@pytest.mark.parametrize('reverse',[False,True])
def test_unlabelled_straight_link_between_incompatible_tees_is_not_confirmed(reverse):
    segments=[Seg(0,0,100,0),Seg(100,0,200,0),Seg(200,0,300,0),
              Seg(100,0,100,100),Seg(200,0,200,100)]
    if reverse: segments.reverse()
    prims=[Prim(i,str(i),0,s,'f','L',1.44) for i,s in enumerate(segments)]
    g=build_graph(prims,'f')
    states={i:PrimState() for i in g.prims}
    seeds={}
    for i,p in g.prims.items():
        if p.seg.mid==(50,0): seeds[i]=[(Identity('KV',20,'KV','KV-20'),'a','line',(50,0))]
        if p.seg.mid==(250,0): seeds[i]=[(Identity('KV',40,'KV','KV-40'),'b','line',(250,0))]
    _resolve_family(g,states,seeds,[],'f')
    centre=next(i for i,p in g.prims.items() if p.seg.mid==(150,0))
    assert states[centre].state=='AMBIGUOUS'
    assert {x.dn for x in states[centre].candidates}=={20,40}
