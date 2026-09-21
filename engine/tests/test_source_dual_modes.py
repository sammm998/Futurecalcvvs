from copy import deepcopy
from vvs_engine.source_rules.dual import run
from test_pipestudio_source_flow import Sheet


def test_both_modes_keep_disagreement_and_do_not_reuse_dimension_answer():
    sh=Sheet();a=sh.node(0,0);b=sh.node(100,0);sid=sh.stretch(a,b)
    big=sh.label('VS1-S13-22',a,22);small=sh.label('VS1-S13-15',b,15)
    A={'nodes':sh.nodes,'stretches':sh.stretches};L=sh.labels;R={'leaders':sh.leaders,'bindings':[],'counts':{}}
    original=deepcopy((A,L,R));questions=[]
    def ask(qs):
        questions.extend(qs)
        return [{'stretch':q['stretch'],'label':small,'designation_idx':0,'ambiguous':False} for q in qs]
    result=run(A,L,R,{'rules':[]},ask=ask)
    assert result['dimension']['result']['bindings'][0]['label']==big
    assert result['model']['result']['bindings'][0]['label']==small
    assert result['differences']==[{'stretch':sid,'dimension':(big,0),'model':(small,0)}]
    assert (A,L,R)==original
    assert not any(e['kind']=='rule_proposal' for q in questions for c in q['candidates'] for e in c['evidence'])


def test_missing_model_is_not_reported_as_agreement_or_a_completed_model_run():
    result=run({'nodes':[],'stretches':[]},[],{'leaders':[],'bindings':[],'counts':{}},{'rules':[]})
    assert result['dimension']['status']=='COMPLETED'
    assert result['model']['status']=='NOT_CONFIGURED'
    assert result['comparison_status']=='NOT_AVAILABLE'


def test_combined_supplies_dimension_proposals_to_final_model_and_preserves_inputs():
    sh=Sheet();a=sh.node(0,0);b=sh.node(100,0);sh.stretch(a,b)
    big=sh.label('VS1-S13-22',a,22);small=sh.label('VS1-S13-15',b,15)
    A={'nodes':sh.nodes,'stretches':sh.stretches};L=sh.labels;R={'leaders':sh.leaders,'bindings':[],'counts':{}}
    original=deepcopy((A,L,R));seen=[]
    def ask(qs):
        seen.extend(qs)
        return [{'stretch':q['stretch'],'label':small,'designation_idx':0,'ambiguous':False} for q in qs]
    result=run(A,L,R,{'rules':[]},mode='combined',ask=ask)
    assert any(c['label']==big and any(e['kind']=='rule_proposal' for e in c['evidence']) for q in seen for c in q['candidates'])
    assert result['combined']['status']=='COMPLETED'
    assert result['combined']['result']['bindings'][0]['label']==small
    assert len(result['combined']['result']['bindings'])==1
    assert (A,L,R)==original


def test_combined_abstention_keeps_rule_proposal_unconfirmed():
    sh=Sheet();a=sh.node(0,0);b=sh.node(100,0);sh.stretch(a,b);sh.label('VS1-S13-22',a,22)
    def ask(qs):return [{'stretch':q['stretch'],'label':None,'designation_idx':None,'ambiguous':True} for q in qs]
    result=run({'nodes':sh.nodes,'stretches':sh.stretches},sh.labels,{'leaders':sh.leaders,'bindings':[],'counts':{}},{'rules':[]},mode='combined',ask=ask)
    assert result['combined']['result']['bindings']
    assert all(b['confidence']=='low' for b in result['combined']['result']['bindings'])
    assert result['combined']['review_required']>0


def test_combined_requires_model_and_does_not_publish_rule_only_success():
    result=run({'nodes':[],'stretches':[]},[],{'leaders':[],'bindings':[],'counts':{}},{'rules':[]},mode='combined')
    assert result['dimension']['status']=='COMPLETED'
    assert result['combined']['status']=='NOT_CONFIGURED'


def test_abstained_symbol_port_proposal_never_becomes_dimension_fallback():
    sh = Sheet()
    a, b = sh.node(0, 0), sh.node(100, 0)
    sh.stretch(a, b)
    label = sh.label('VV1-X7-25', a, 25)
    c, d = sh.node(200, 0, 'end'), sh.node(300, 0, 'end')
    orphan = sh.stretch(c, d)
    R = {'leaders': sh.leaders, 'bindings': [], 'counts': {},
         'symbol_port_candidates': [{'stretch': orphan, 'label': label,
             'designation_idx': 0, 'confidence': 'low', 'rule': 'symbol_port_candidate:1'}]}
    seen = []
    def ask(qs):
        seen.extend(qs)
        return [{'stretch': q['stretch'], 'label': None,
                 'designation_idx': None, 'ambiguous': True} for q in qs]
    result = run({'nodes': sh.nodes, 'stretches': sh.stretches}, sh.labels,
                 R, {'rules': []}, mode='combined', ask=ask)
    assert any(q['stretch'] == orphan and any(c['label'] == label for c in q['candidates']) for q in seen)
    assert not any(b['stretch'] == orphan for b in result['combined']['result']['bindings'])
