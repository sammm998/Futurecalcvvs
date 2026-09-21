from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Prim, Node, PipeGraph
from vvs_engine.pipes.ownership import Identity, PrimState, _build_pipes
from vvs_engine.measure.measure import _vertical


def network():
    edges=[((0,0),(10,0)),((10,0),(20,0)),((20,0),(30,0)),((20,0),(20,10))]
    points=[(0,0),(10,0),(20,0),(30,0),(20,10)]
    ends={0:(0,1),1:(1,2),2:(2,3),3:(2,4)}
    prims={i:Prim(i,f'path{i}',0,Seg(*a,*b),'f','layer',1) for i,(a,b) in enumerate(edges)}
    nodes={i:Node(i,*point,[p for p,ns in ends.items() if i in ns]) for i,point in enumerate(points)}
    g=PipeGraph('f',prims,nodes,ends,[],None)
    ident=Identity('S1-P2',160,'S1','S1-P2-160')
    return g,{p:PrimState(state='CONFIRMED',identity=ident,anchors={'remote'}) for p in prims}


def test_same_designation_is_split_at_level_landings_and_junction_without_losing_ink():
    g,states=network()
    whole=_build_pipes(g,states,'f',0)
    sections=_build_pipes(g,states,'f',0,stop_nodes={1,2})
    assert len(whole)==1 and len(sections)==4
    assert sorted(p for s in sections for p in s.prim_ids)==list(g.prims)
    assert sum(s.length_pt for s in sections)==whole[0].length_pt==40
    assert len({s.physical_pipe_id for s in sections})==4


def test_local_section_levels_do_not_inherit_distant_model_label_elevation():
    g,states=network()
    p=_build_pipes(g,states,'f',0,stop_nodes={1,2})[0]
    p.elevation_anchor_ids=['a','b']
    elevations={'a':[{'tag':'VG','value':1.63,'unit':'m'}],
                'b':[{'tag':'VG','value':1.62,'unit':'m'}],
                'remote':[{'tag':'VG','value':9.99,'unit':'m'}]}
    value,evidence=_vertical(p,elevations)
    assert value==.01 and evidence['values']==[1.62,1.63]
    p.elevation_anchor_ids=['a']
    assert _vertical(p,elevations)==(None,None)


def test_a_level_boundary_shares_an_existing_dash_gap_without_changing_total():
    g,states=network()
    g.bridges=[{'from_node':1,'gap_pt':2.0}]
    whole=_build_pipes(g,states,'f',0)
    sections=_build_pipes(g,states,'f',0,stop_nodes={1,2})
    assert sum(p.length_pt for p in sections)==whole[0].length_pt==42
    assert sorted(p.bridged_gap_pt for p in sections)==[0,0,1,1]
