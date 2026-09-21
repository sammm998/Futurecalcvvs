from copy import deepcopy
from vvs_engine.source_rules.endpoint_agreement import bounded_label_agreement


def example():
    d={'system':'S','number':'8','middle':['P2'],'dimension':110}
    A={'stretches':[{'id':0,'node_a':1,'node_b':2}]}
    L=[{'id':i,'designations':[deepcopy(d)]} for i in (10,20)]
    R={'leaders':[{'label':i,'landings':[{'node':n}]} for i,n in ((10,1),(20,2))]}
    p={'stretch':0,'label':10,'designation_idx':0,'confidence':'high'}
    return A,L,R,p


def test_matching_explicit_endpoints_confirm_interval_without_model_guess():
    assert bounded_label_agreement(*example())


def test_missing_conflicting_or_shared_contacts_do_not_confirm():
    A,L,R,p=example(); R['leaders'].pop()
    assert not bounded_label_agreement(A,L,R,p)
    A,L,R,p=example(); L[1]['designations'][0]['dimension']=75
    assert not bounded_label_agreement(A,L,R,p)
    A,L,R,p=example(); R['leaders'][1]['label']=10
    assert not bounded_label_agreement(A,L,R,p)
    A,L,R,p=example(); R['leaders'][1]['landings'][0]['binds']=False
    assert not bounded_label_agreement(A,L,R,p)
    A,L,R,p=example(); A['stretches'][0]['in_wall']=True
    assert not bounded_label_agreement(A,L,R,p)
    A,L,R,p=example(); L[1]['designations'][0]['count']=2
    assert not bounded_label_agreement(A,L,R,p)


def test_combined_resolves_abstention_and_uncertain_matching_candidate():
    from vvs_engine.source_rules.dual import run
    from test_pipestudio_source_flow import Sheet
    for abstain in (True, False):
        sh=Sheet(); a=sh.node(0,0); b=sh.node(100,0); sh.stretch(a,b)
        label=sh.label('VS1-S13-22',a,22); sh.label('VS1-S13-22',b,22)
        def ask(qs):
            return [dict(stretch=q['stretch'],label=None if abstain else label,
                         designation_idx=None if abstain else 0,ambiguous=True) for q in qs]
        result=run({'nodes':sh.nodes,'stretches':sh.stretches},sh.labels,
                   {'leaders':sh.leaders,'bindings':[],'counts':{}},{'rules':[]},mode='combined',ask=ask)
        assert result['combined']['status']=='COMPLETED'
        bindings=result['combined']['result']['bindings']
        assert len(bindings)==1
        assert bindings[0]['confidence']=='high'
        assert bindings[0]['rule']=='combined_matching_endpoint_labels'
        assert result['combined']['endpoint_confirmations']==[0]
        assert result['combined']['review_required']==0
