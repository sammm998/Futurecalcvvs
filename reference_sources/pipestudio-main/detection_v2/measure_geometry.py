"""Read-only audit: python -m detection_v2.measure_geometry saved-review.json [...]."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

from .contract import graph_length, validate_result
from .detector import to_contract
from .geometry import simplify, point_segment_distance


def adjacency(graph):
    result = {n['id']:set() for n in graph['nodes']}
    for a,b in graph['edges']:
        result[a].add(b); result[b].add(a)
    return result


def measure(path):
    data = json.loads(Path(path).read_text())
    rv = data.get('stages', {}).get('09_review', data)
    method = rv['metadata']['assignmentMethod']
    body = {'protocolVersion':2, 'drawingId':'00000000-0000-4000-8000-000000000001',
            'runId':'00000000-0000-4000-8000-000000000002', 'assignmentMethod':method,
            'coordinateSpace':dict(zip(('width','height'), [x*rv['scale'] for x in rv['page']])),
            'output':{'includeScaleAndLengths':True}}
    measurements = []
    def checked(graph, protected, *, report=None):
        stats = {} if report is None else report
        result = simplify(graph, protected, report=stats)
        old = {n['id']:n for n in graph['nodes']}; new = {n['id']:n for n in result['nodes']}
        adj, nadj = adjacency(graph), adjacency(result)
        assert all(old[i] == n for i,n in new.items())
        assert all(i in new for i in set(protected)&set(old))
        assert all(i in new for i,ns in adj.items() if len(ns)!=2)
        assert all(len(adj[i])==len(nadj[i]) for i in new)
        # Every output edge must replace an actual original path, and every
        # original edge must be represented once: no split, dropped branch or merge.
        covered = set()
        largest_deviation = 0.0
        for a in new:
            for first in adj[a]:
                previous, current = a, first
                chain = [tuple(sorted((previous,current)))]
                trace = [a,first]
                while current not in new:
                    following = next(i for i in adj[current] if i != previous)
                    previous, current = current, following
                    chain.append(tuple(sorted((previous,current))))
                    trace.append(current)
                assert current in nadj[a]
                deviation = max(point_segment_distance(old[i],old[a],old[current]) for i in trace)
                assert deviation <= 1.0
                largest_deviation = max(largest_deviation,deviation)
                if a < current:
                    assert not covered.intersection(chain)
                    covered.update(chain)
        assert covered == {tuple(sorted(e)) for e in graph['edges']}
        before,after = graph_length(graph),graph_length(result)
        assert abs(after-before)/before < 0.001
        assert abs(largest_deviation-stats['max_discarded_deviation_px']) < 1e-9
        measurements.append(stats)
        return result
    with patch('detection_v2.detector.simplify', side_effect=checked):
        result = to_contract(rv,body)
    validate_result(result,body)
    assert all(p['length']['px']==graph_length(p['geometry']) for p in result['pipes'])
    # The app receives the same simplified geometry when it owns length calculation.
    body['output']['includeScaleAndLengths']=False
    without_length = to_contract(rv,body); validate_result(without_length,body)
    assert [p['geometry'] for p in result['pipes']]==[p['geometry'] for p in without_length['pipes']]
    # Pipe order and ownership must match unsimplified serialization as well.
    with patch('detection_v2.detector.simplify', side_effect=lambda graph, protected, **kwargs:graph):
        full = to_contract(rv,body)
    assert [(p['id'],p['labelId']) for p in full['pipes']] == [(p['id'],p['labelId']) for p in result['pipes']]
    for pipe,stats in zip(result['pipes'],measurements):
        stats.update(pipe_id=pipe['id'],method=method,run_id=rv['metadata'].get('run_id'))
    return {'source':str(path), 'sheet':rv['sheet'], 'method':method, 'run_id':rv['metadata'].get('run_id'),
            'pipes':len(measurements), 'points_before':sum(x['points_before'] for x in measurements),
            'points_after':sum(x['points_after'] for x in measurements),
            'length_px_before':sum(x['length_px_before'] for x in measurements),
            'length_px_after':sum(x['length_px_after'] for x in measurements),
            'max_pipe_length_change_percent':max((abs(x['length_change_percent']) for x in measurements),default=0),
            'max_discarded_deviation_px':max((x['max_discarded_deviation_px'] for x in measurements),default=0),
            'retained_subpixel_counts':{key:sum(len(x['retained_subpixel_vertices'][key]) for x in measurements)
                                       for key in ('topology','length_budget','deviation','reversal')},
            'topology_original_coordinates_and_final_deviation_verified':True,
            'both_output_flags_schema_valid':True, 'per_pipe':measurements}



if __name__ == '__main__':
    print(json.dumps([measure(path) for path in sys.argv[1:]],indent=2))
