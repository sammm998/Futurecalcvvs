from copy import deepcopy
from vvs_engine.source_rules.model_payload import group_equivalent_candidates


def candidate(label, count=1, dimension=16, level=None, system='KV', middle=None):
    return {'label':label,'designation_idx':0,'text':f'{system}1-X31-{dimension}',
            'designation':{'raw':f'{system}1-X31-{dimension}','system':system,'number':'1',
                           'dimension':dimension,'count':count,'line_count':1,'middle':middle or ['X31']},
            'level':level,'evidence':[{'kind':'leader_landing','node':label}]}


def test_identical_designations_with_different_local_bundle_counts_are_aliases():
    qs=[{'stretch':10,'candidates':[candidate(5,5),candidate(2,2)],'end_context':[{'landings':[2,5]}]}]
    before=deepcopy(qs)
    grouped,audit=group_equivalent_candidates(qs)
    assert qs==before
    assert len(grouped[0]['candidates'])==1
    c=grouped[0]['candidates'][0]
    assert c['label']==2
    assert c['equivalent_occurrences']==qs[0]['candidates']
    assert grouped[0]['end_context']==qs[0]['end_context']
    assert audit==[{'stretch':10,'representative':[2,0],'equivalent_pairs':[[5,0],[2,0]]}]


def test_real_differences_in_size_level_system_and_material_remain_choices():
    cs=[candidate(1),candidate(2,dimension=20),candidate(3,level={'kind':'VG','value':1.2}),
        candidate(4,system='VV'),candidate(5,middle=['R8'])]
    grouped,audit=group_equivalent_candidates([{'stretch':0,'candidates':cs}])
    assert grouped[0]['candidates']==cs
    assert not audit


def test_empty_candidates_remain_empty():
    assert group_equivalent_candidates([{'stretch':0,'candidates':[]}])==([{'stretch':0,'candidates':[]}],[])


def test_transport_keeps_model_uncertainty_and_original_candidate_validation(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'backend'))
    monkeypatch.delenv('STUDIO_ASTRA_EFFORT', raising=False)
    from app.source_model import AssignmentTransport
    from vvs_engine.source_rules.pipestudio.final_bind import validate_decisions
    import json
    captured=[]
    decision={'stretch':10,'label':2,'designation_idx':0,'ambiguous':True}
    def create(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(status='completed',output_text=json.dumps({'decisions':[decision]}),
                               usage=None,model='test',id='test')
    qs=[{'stretch':10,'candidates':[candidate(5,5),candidate(2,2)]}]
    ask=AssignmentTransport(SimpleNamespace(responses=SimpleNamespace(create=create)),'test')
    result=ask(qs)
    assert result==[decision]  # ambiguity is never promoted away by the adapter
    assert captured[0]['reasoning']=={'effort':'medium'}
    assert 'equivalent_occurrences' in captured[0]['input'][1]['content']
    assert ask.candidate_aliases[0]['representative']==[2,0]
    bindings,_,issues=validate_decisions(qs,result,'test')
    assert bindings[0]['confidence']=='low' and not issues


def test_missing_pressure_cl_is_not_a_second_identity_but_conflicting_levels_are():
    known = candidate(5, level={'kind':'CL','value':1.6})
    missing = candidate(2)
    grouped, _ = group_equivalent_candidates([{'stretch':0,'candidates':[missing, known]}])
    assert len(grouped[0]['candidates']) == 1
    assert grouped[0]['candidates'][0]['label'] == 5
    assert grouped[0]['candidates'][0]['equivalent_occurrences'][0]['level'] is None
    different = candidate(7, level={'kind':'CL','value':2.0})
    grouped, _ = group_equivalent_candidates([{'stretch':0,'candidates':[missing, known, different]}])
    assert len(grouped[0]['candidates']) == 3


def test_missing_gravity_level_never_inherits_a_neighbour_level_in_payload():
    cs = [candidate(1, system='S'), candidate(2, system='S', level={'kind':'CL','value':1.6})]
    grouped, audit = group_equivalent_candidates([{'stretch':0,'candidates':cs}])
    assert grouped[0]['candidates'] == cs and not audit
