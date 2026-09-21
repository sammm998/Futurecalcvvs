from copy import deepcopy
import pytest
from studio import learning, styles

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path))

def row(method):
    return {'id':method, 'style_id':'style-1', 'status':'open', 'track':'binding',
            'tab':'bindings', 'assignmentMethod':method, 'type':'uncertain', 'evidence':{}}

def changed_prompt():
    base=styles.get_style()
    changed=deepcopy(base)
    changed['rules'].append({'id':'new-convention','stage':'binding','instruction':'Prefer the connected branch designation.'})
    return base, changed

@pytest.mark.parametrize('method', ['dimension', None])
def test_non_llm_feedback_cannot_change_prompt(method):
    base, changed=changed_prompt()
    with pytest.raises(ValueError, match='Only LLM'):
        learning.validate_feedback_scope(changed, base, [row(method)])

def test_llm_feedback_can_change_prompt():
    base, changed=changed_prompt()
    assert learning.validate_feedback_scope(changed, base, [row('llm')]) == {'llm'}

def test_dimension_feedback_can_change_shared_calibration():
    base=styles.get_style(); changed=deepcopy(base)
    changed['calibration']['assemble.snap']=1.1
    assert learning.validate_feedback_scope(changed, base, [row('dimension')]) == {'dimension'}

def test_mixed_methods_rejected():
    base=styles.get_style()
    with pytest.raises(ValueError, match='separate candidates'):
        learning.validate_feedback_scope(base, base, [row('dimension'),row('llm')])

def test_proposal_cannot_bypass_scope(monkeypatch):
    base, changed=changed_prompt()
    monkeypatch.setattr(learning.evidence,'records',lambda:[row('dimension')])
    def ask(payload):
        assert payload['examples'][0]['assignmentMethod']=='dimension'
        assert 'Preserve rules exactly' in payload['scope_constraint']
        return {'title':'Invalid change','rationale':'Test', 'calibration':base['calibration'],'rules':changed['rules']}
    with pytest.raises(ValueError, match='Only LLM'):
        learning.propose('style-1',['dimension'],ask=ask)

def test_evaluation_rechecks_legacy_candidate(monkeypatch):
    base, changed=changed_prompt()
    monkeypatch.setattr(learning.evidence,'records',lambda:[row('dimension')])
    monkeypatch.setattr(learning,'candidate',lambda _: {'style_id':'style-1','base_version':1,'profile':changed,'training_ids':['dimension']})
    with pytest.raises(ValueError, match='Only LLM'):
        learning.evaluate('legacy', binding='flow')

def test_publish_rechecks_legacy_candidate(monkeypatch):
    base, changed=changed_prompt()
    monkeypatch.setattr(learning.evidence,'records',lambda:[row('dimension')])
    monkeypatch.setattr(learning,'candidate',lambda _: {'style_id':'style-1','base_version':1,'profile':changed,'training_ids':['dimension']})
    with pytest.raises(ValueError, match='Only LLM'):
        learning.publish('legacy','Reviewer')

@pytest.mark.parametrize('method,binding', [('dimension','astra'),('llm','flow')])
def test_evaluation_requires_original_method(monkeypatch, method, binding):
    monkeypatch.setattr(learning.evidence,'records',lambda:[row(method)])
    monkeypatch.setattr(learning,'candidate',lambda _: {'style_id':'style-1','base_version':1,'profile':styles.get_style(),'training_ids':[method]})
    with pytest.raises(ValueError, match='Evaluate'):
        learning.evaluate('candidate',binding=binding)
