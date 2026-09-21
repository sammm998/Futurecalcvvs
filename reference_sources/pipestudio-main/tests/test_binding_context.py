from vectorascore.final_bind import questions


def graph():
    nodes = [{'id': i, 'x': i * 10, 'y': 0, 'kind': 'tick' if i in (0, 3) else 'gap',
              'stretches': [j for j in (i - 1, i) if 0 <= j < 4]} for i in range(5)]
    stretches = [{'id': i, 'node_a': i, 'node_b': i + 1, 'points': [[i * 10, 0], [(i + 1) * 10, 0]],
                  'length': 10, 'width': 1, 'line_type': 'solid', 'layer': ''} for i in range(4)]
    labels = [{'id': i, 'text': 'KV1-X7-20', 'designations': [{'system': 'KV', 'number': '1', 'dimension': 20,
               'middle': ['X7'], 'line_count': 1}]} for i in (10, 20)]
    leaders = [{'label': 10, 'landings': [{'node': 0}]}, {'label': 20, 'landings': [{'node': 3}]}]
    return {'nodes': nodes, 'stretches': stretches}, {'leaders': leaders, 'bindings': []}, labels


def candidates(q):
    return {c['label'] for c in q['candidates']}


def test_candidates_reach_connected_run_without_a_winning_rule():
    a, r, l = graph()
    qs = questions(a, r, l)
    assert 10 in candidates(qs[2])
    assert 10 not in candidates(qs[3])  # another designation is a boundary
    source = next(c for c in qs[2]['candidates'] if c['label'] == 10)['evidence'][0]
    assert source['via_stretches'] == [0, 1, 2]
    assert qs[2]['end_context'][1]['landings'][0]['label'] == 20


def test_unreadable_landing_still_stops_candidates():
    a, r, l = graph()
    l[1]['usable'] = False
    assert 10 not in candidates(questions(a, r, l)[3])


def test_crossing_leader_is_not_a_designation_boundary():
    a, r, l = graph()
    r['leaders'][1]['landings'][0]['binds'] = False
    assert 10 in candidates(questions(a, r, l)[3])


def test_no_candidate_inherits_across_entry_or_line_type_change():
    for key, value in [('entry', True), ('in_wall', True), ('line_type', 'dash-dot')]:
        a, r, l = graph()
        a['stretches'][1][key] = value
        assert 10 not in candidates(questions(a, r, l)[2])


def test_branch_does_not_donate_its_label_to_main():
    a, r, l = graph()
    a['nodes'].append({'id': 5, 'x': 10, 'y': 10, 'kind': 'tick', 'stretches': [4]})
    a['nodes'][1]['stretches'].append(4)
    a['stretches'].append({'id': 4, 'node_a': 5, 'node_b': 1, 'points': [[10, 10], [10, 0]],
                          'length': 10, 'width': 1, 'line_type': 'solid', 'layer': ''})
    r['leaders'][0]['landings'][0]['node'] = 5
    qs = questions(a, r, l)
    assert 10 in candidates(qs[4])
    assert all(10 not in candidates(q) for q in qs[:4])


def test_main_continues_past_a_label_that_only_names_a_branch():
    a, r, l = graph()
    a['nodes'].append({'id': 5, 'x': 10, 'y': 10, 'kind': 'end', 'stretches': [4]})
    a['nodes'][1]['stretches'].append(4)
    a['stretches'].append({'id': 4, 'node_a': 1, 'node_b': 5, 'points': [[10, 0], [10, 10]],
                          'length': 10, 'width': 1, 'line_type': 'solid', 'layer': ''})
    r['leaders'][1]['landings'][0]['node'] = 1
    qs = questions(a, r, l)
    assert 10 in candidates(qs[2])
    assert 20 not in candidates(qs[0]) and 20 not in candidates(qs[1])


def test_parallel_context_requires_two_pipe_shared_candidate_and_compatible_geometry():
    from vectorascore.binding_context import parallel_context
    def q(sid,y,system='VS1',count=2,label=10):
        return {'stretch':sid,'points':[[0,y],[100,y]],'line_type':'solid','layer':'V-FE--'+system+'-',
                'candidates':[{'label':label,'designation_idx':0,'designation':{'line_count':count}}]}
    rows=[q(0,0),q(1,4),q(2,8,system='VP1'),q(3,12,label=20)]
    peers=parallel_context(rows)
    assert [p['stretch'] for p in peers[0]]==[1]
    assert peers[0][0]['shared_two_pipe_candidates']==[[10,0]]
    assert parallel_context([q(0,0,count=1),q(1,4,count=1)])=={}
    assert parallel_context([q(0,0),q(1,0)])=={}
