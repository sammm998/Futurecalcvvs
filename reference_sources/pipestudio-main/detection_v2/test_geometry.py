from copy import deepcopy
import math
import pytest
from .geometry import simplify, point_segment_distance
from .contract import graph_length, validate_result
from .detector import to_contract
from .test_studio_adapter import review
from .test_service import request_body


def graph(points, edges=None):
    return {'nodes':[{'id':i,'x':x,'y':y} for i,(x,y) in enumerate(points)],
            'edges':edges if edges is not None else [[i,i+1] for i in range(len(points)-1)]}


def test_dash_boundaries_collapse_to_two_original_ends():
    before=graph([(i,2*i) for i in range(17)])
    original=deepcopy(before)
    after=simplify(before)
    assert after['nodes']==[before['nodes'][0],before['nodes'][-1]]
    assert after['edges']==[[0,16]]
    assert graph_length(after)==pytest.approx(graph_length(before),rel=1e-14)
    assert before==original


def test_junction_branches_and_corner_survive():
    before=graph([(0,0),(1,0),(2,0),(3,0),(4,0),(2,1),(2,2),(3,2)],
                 [[0,1],[1,2],[2,3],[3,4],[2,5],[5,6],[6,7]])
    after=simplify(before)
    assert {n['id'] for n in after['nodes']}=={0,2,4,6,7}
    assert {tuple(e) for e in after['edges']}=={(0,2),(2,4),(2,6),(6,7)}
    assert graph_length(after)==graph_length(before)


def test_protected_contact_on_straight_chain_survives():
    after=simplify(graph([(i,0) for i in range(5)]),{2})
    assert [n['id'] for n in after['nodes']]==[0,2,4]


@pytest.mark.parametrize('points',[
    [(0,0),(2,0),(1,0)],  # reversal must not shorten the billed run
])
def test_direction_changes_are_not_smoothed(points):
    before=graph(points)
    assert simplify(before)==before


def test_cycle_retains_topology():
    before=graph([(0,0),(1,0),(2,0),(2,2),(0,2)],[[0,1],[1,2],[2,3],[3,4],[4,0]])
    after=simplify(before)
    assert len(after['edges'])==len(after['nodes'])==4
    assert graph_length(before)==graph_length(after)


@pytest.mark.parametrize('method',['dimension','llm'])
@pytest.mark.parametrize('include',[False,True])
def test_wire_geometry_simplified_for_both_methods_and_output_flags(method,include):
    rv=review();rv['stretches'][0]['points']=[[x,10] for x in range(10,31)]
    body=request_body();body['assignmentMethod']=method
    body['coordinateSpace']={'width':200,'height':300}
    body['output']['includeScaleAndLengths']=include
    result=to_contract(rv,body);validate_result(result,body)
    assert len(result['pipes'])==1
    pipe=result['pipes'][0]
    assert len(pipe['geometry']['nodes'])==4  # tee and all three ends
    assert graph_length(pipe['geometry'])==140
    assert ('length' in pipe)==include
    if include:assert pipe['length']['px']==graph_length(pipe['geometry'])

def test_straight_stretch_boundary_is_removed_but_cross_label_tee_is_kept():
    rv=review()
    # A third branch with a different label must not erase the main's tee.
    rv['labels'].append({**deepcopy(rv['labels'][0]),'id':8})
    rv['bindings'][2]['label']=8
    body=request_body();body['coordinateSpace']={'width':100,'height':100}
    body['output']['includeScaleAndLengths']=True
    result=to_contract(rv,body);validate_result(result,body)
    main=next(p for p in result['pipes'] if p['labelId']=='label-7-0')
    assert {(n['x'],n['y']) for n in main['geometry']['nodes']}=={(10,10),(30,10),(50,10)}
    # Without that physical branch, the same point is just straight filler.
    rv['stretches']=rv['stretches'][:2];rv['bindings']=rv['bindings'][:2]
    result=to_contract(rv,body);validate_result(result,body)
    assert len(result['pipes'])==1
    assert len(result['pipes'][0]['geometry']['nodes'])==2


def assert_chain_bounds(before,after):
    old={n['id']:n for n in before['nodes']}
    kept={n['id']:n for n in after['nodes']}
    assert all(n==old[i] for i,n in kept.items())
    for a,b in after['edges']:
        assert max(point_segment_distance(old[i],old[a],old[b]) for i in range(a,b+1))<=1.0
    assert abs(graph_length(after)-graph_length(before))/graph_length(before)<0.001


def test_supplied_fillet_uses_best_original_corner():
    before=graph([(1026.56,449.20),(1014.56,461.20),(1013.96,461.92),
                  (1013.60,462.64),(1013.36,463.48),(1013.24,464.32),(1013.24,549.16)])
    stats={};after=simplify(before,report=stats)
    assert [n['id'] for n in after['nodes']]==[0,3,6]
    assert_chain_bounds(before,after)
    assert stats['max_discarded_deviation_px']==pytest.approx(0.35300665)
    assert stats['length_change_percent']==pytest.approx(-0.07928310)
    assert simplify(before)==after


def test_subpixel_wobble_is_removed():
    before=graph([(0,0),(0.06,8),(0,17)])
    after=simplify(before)
    assert len(after['nodes'])==2
    assert_chain_bounds(before,after)


def test_short_pipe_retains_subpixel_corner_to_preserve_length():
    before=graph([(0,0),(1,0.1),(2,0)])
    stats={};after=simplify(before,report=stats)
    assert after==before
    assert stats['retained_subpixel_vertices']['length_budget']==[1]


def test_repeated_removals_cannot_accumulate_distance_error():
    before=graph([(i*10,1.5*math.sin(i/10)) for i in range(101)])
    after=simplify(before)
    assert 2<len(after['nodes'])<len(before['nodes'])
    assert_chain_bounds(before,after)


def test_curve_preserves_original_coordinates_and_length_budget():
    before=graph([(math.cos(t/10),math.sin(t/10)) for t in range(16)])
    after=simplify(before)
    assert_chain_bounds(before,after)
    assert len(after['nodes'])>2


def test_large_bend_survives_despite_generous_pipe_length_budget():
    before=graph([(0,0),(10000,0),(10000,10),(10000,10000)])
    after=simplify(before)
    assert [n['id'] for n in after['nodes']]==[0,1,3]
    assert_chain_bounds(before,after)


def test_explicit_collinear_contact_is_reported_as_protected():
    stats={};simplify(graph([(0,0),(10,0),(20,0)]),{1},report=stats)
    assert stats['retained_subpixel_vertices']['topology']==[1]


def test_closed_trace_cannot_be_collapsed_to_duplicate_edge():
    before=graph([(0,0),(100,0),(100,0.01),(0,0.01)],[[0,1],[1,2],[2,3],[3,0]])
    after=simplify(before)
    assert len(after['nodes'])>=3
    assert len(after['edges'])==len(after['nodes'])
    assert len({tuple(sorted(e)) for e in after['edges']})==len(after['edges'])
    assert abs(graph_length(after)-graph_length(before))/graph_length(before)<0.001
