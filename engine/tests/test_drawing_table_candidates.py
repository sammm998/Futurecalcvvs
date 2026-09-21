from copy import deepcopy
from test_pipestudio_source_flow import Sheet
from vvs_engine.source_rules.declaration_candidates import propose
from vvs_engine.source_rules.dual import run


def sample():
    sh=Sheet();a=sh.node(0,0,'end');b=sh.node(100,0,'end');sh.stretch(a,b,layer='V-52B--FE-_Vxx-KV')
    A={'nodes':sh.nodes,'stretches':sh.stretches};R={'leaders':[],'bindings':[],'counts':{}}
    declaration={'statement':['KOPPLINGSLEDNINGAR','FRÅN FÖRDELARE TILL APPARAT ENLIGT TABELL'],
                 'connection_pipes':[dict(dn=16,dns=[16],apparatus=['BL'],text='KV01-X31-16',system_token='KV01')]}
    return sh,A,R,declaration


def test_table_proposal_keeps_scope_and_abstention_does_not_count_metres():
    sh,A,R,d=sample();assert len(propose(A,sh.labels,R,d))==1
    assert sh.labels[0]['designations'][0]['sheet_declaration']['apparatus']==['BL']
    seen=[]
    def ask(qs):
        seen.extend(qs)
        return [dict(stretch=q['stretch'],label=None,designation_idx=None,ambiguous=True) for q in qs]
    result=run(A,sh.labels,R,{'rules':[]},mode='combined',ask=ask)
    assert seen[0]['candidates'][0]['designation']['sheet_declaration']['verification_required']
    assert result['dimension']['result']['bindings']==[]
    assert result['combined']['result']['bindings']==[]


def test_explicit_leader_always_excludes_default_table_proposal():
    sh,A,R,d=sample();sh.label('KV01-X7-25',0,25);R['leaders']=sh.leaders
    assert not propose(A,sh.labels,R,d)


def test_unknown_layer_and_conflicting_rows_are_not_assigned_by_default():
    sh,A,R,d=sample();A['stretches'][0]['layer']='unidentified'
    assert not propose(A,sh.labels,R,d)
    A['stretches'][0]['layer']='KV'
    d['connection_pipes'][0]['dns']=[16,20]
    assert not propose(A,sh.labels,R,d)


def test_two_system_indices_without_explicit_layer_index_remain_ambiguous():
    sh,A,R,d=sample();other=deepcopy(d['connection_pipes'][0]);other.update(system_token='KV02',text='KV02-X31-16')
    d['connection_pipes'].append(other)
    assert not propose(A,sh.labels,R,d)
