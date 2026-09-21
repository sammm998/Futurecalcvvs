"""No angular blind spot between straight dash joins and curved dash joins."""
import math
import pytest
from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Prim, build_graph


@pytest.mark.parametrize('turn', [5,10,14,30])
@pytest.mark.parametrize('gap,joined', [(4.25,True),(10.,False)])
def test_a_shallow_bend_joins_only_across_the_drawings_own_gap(turn,gap,joined):
    theta=math.radians(turn)
    c,s=math.cos(theta),math.sin(theta)
    half=gap/2
    # A straight sample establishes this pen's 4.25 pt dash rhythm.
    segments=[Seg(i*21.25,100,i*21.25+17,100) for i in range(8)]
    segments += [Seg(-17,0,0,0),Seg(half+half*c,half*s,half+(half+17)*c,(half+17)*s)]
    ps=[Prim(i,str(i),0,seg,'f','L',.96) for i,seg in enumerate(segments)]
    g=build_graph(ps,'f')
    a,b=g.prim_nodes[8][1],g.prim_nodes[9][0]
    assert (a==b) is joined
    if joined:
        assert any(row['kind']=='corner' for row in g.bridges)
