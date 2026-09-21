"""An outlet between directed wyes has a drawn junction at which size changes."""
import math

import pytest

from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Prim, build_graph
from vvs_engine.pipes.ownership import Identity, PrimState, _resolve_family


@pytest.mark.parametrize('angle', [0, 90, 183])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('branch_dx,branch_dy,other_base,expected', [
    (40,-40,'S3-R8','CONFIRMED'),
    (40,0,'S3-R8','AMBIGUOUS'),  # tee: no directed confluence
    (40,40,'S3-R8','AMBIGUOUS'), # opposed wyes
    (40,-40,'S4-R8','AMBIGUOUS'),# another system
])
def test_size_follows_wye_direction_not_ids_or_page_orientation(angle,reverse,branch_dx,branch_dy,other_base,expected):
    segments = [((0,-80),(0,0),75,'S3-R8'), ((0,0),(0,100),None,''),
                ((0,100),(0,180),110,'S3-R8'),
                ((0,0),(branch_dx,branch_dy),75,other_base),
                ((0,100),(-40,60),75,'S3-R8')]
    theta=math.radians(angle)
    def rotate(p):
        x,y=p
        return (x*math.cos(theta)-y*math.sin(theta), x*math.sin(theta)+y*math.cos(theta))
    if reverse: segments.reverse()
    prims=[]; labels={}
    for i,(a,b,dn,base) in enumerate(segments):
        sg=Seg(*rotate(a),*rotate(b))
        prims.append(Prim(i,str(i),0,sg,'f','L',2.04))
        if dn: labels[i]=[(Identity(base,dn,base.split('-')[0],f'{base}-{dn}'),str(i),'end',sg.mid)]
        else: middle=i
    g=build_graph(prims,'f'); states={i:PrimState() for i in g.prims}
    _resolve_family(g,states,labels,[],'f')
    assert states[middle].state == expected
    if expected=='CONFIRMED':
        assert states[middle].identity.dn == 110
        assert states[middle].reason == 'outlet_between_consistently_directed_wyes'
