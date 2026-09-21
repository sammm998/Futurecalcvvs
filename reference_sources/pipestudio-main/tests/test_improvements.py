from copy import deepcopy
import pytest
from studio import improvements, learning, styles, evidence
from studio.storage import write, data_root, digest, engine_version

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path))

def row(i, method=None, tab='pipes', track='vectors', style='style-1'):
    return {'id':str(i),'style_id':style,'status':'open','snapshot':'snap'+str(i),'type':'missing_pipe',
            'tab':tab,'track':track,'assignmentMethod':method,'evidence':{},'sheet':'drawing'+str(i)}

def test_shared_feedback_is_not_split_by_assignment_method(monkeypatch):
    rows=[row(1,'llm'),row(2,'dimension'),row(3,'llm','bindings','binding'),row(4,'dimension','bindings','binding')]
    monkeypatch.setattr(evidence,'records',lambda:rows)
    groups=improvements.overview()['batches']
    assert len(groups)==3
    assert next(b for b in groups if b['scope']=='shared')['count']==2

def test_labels_can_be_clarified_before_technical_diagnosis(monkeypatch):
    rows=[row(1,tab='labels',track='ocr')]
    monkeypatch.setattr(evidence,'records',lambda:rows)
    monkeypatch.setattr(learning,'propose',lambda sid,ids:improvements.technical_request(sid,rows,'Label-reading feedback needs technical diagnosis.'))
    result=improvements.prepare(improvements.overview()['batches'][0]['id'])
    assert result['status']=='technical_review'
    brief=improvements.brief(result['id'])
    assert brief['evidence']==rows
    assert 'Never create a rule' in brief['instructions'][1]
    assert not improvements.overview()['batches']

def test_training_reserves_an_independent_drawing(monkeypatch):
    rows=[row(1),row(2)]
    monkeypatch.setattr(evidence,'records',lambda:rows)
    for r in rows:
        write(data_root()/'snapshots'/r['snapshot']/'09_review.json',{'metadata':{'source_sha256':r['sheet']}})
    def propose(sid,ids):
        assert ids==['1']
        return {'id':'cand','profile':{},'training_ids':ids}
    monkeypatch.setattr(learning,'propose',propose)
    result=improvements.prepare(improvements.overview()['batches'][0]['id'])
    assert result['feedback_ids']==['1','2']

def test_code_routing_cannot_create_a_publishable_candidate(monkeypatch):
    rows=[row(1)]
    monkeypatch.setattr(evidence,'records',lambda:rows)
    result=learning.propose('style-1',['1'],ask=lambda payload:{'implementation':'code','rationale':'Endpoint topology needs a new algorithm.'})
    assert result['status']=='requires_app_update'
    assert not learning.candidates()

def test_shared_geometry_cannot_be_repaired_by_prompt(monkeypatch):
    rows=[row(1)]
    monkeypatch.setattr(evidence,'records',lambda:rows)
    base=styles.get_style(draft=True);rules=deepcopy(base['rules'])
    rules.append({'id':'bad-route','stage':'binding','instruction':'Change pipe endpoints in assignment output.'})
    with pytest.raises(ValueError,match='Only LLM'):
        learning.propose('style-1',['1'],ask=lambda payload:{'title':'wrong','rationale':'wrong','calibration':base['calibration'],'rules':rules})

def test_stale_report_never_shows_ready_to_publish(monkeypatch):
    c=learning.create('style-1','Settings review')
    write(data_root()/'evaluations'/'eval'/'report.json',{'engine_version':'old','eligible':True})
    c['evaluation']='eval'
    status,binding,_=improvements.evaluation_state(c)
    assert status=='ready_to_test' and binding=='preview'


def test_implementation_requires_new_engine_and_matching_source(monkeypatch):
    rows=[row(1)]
    monkeypatch.setattr(evidence,'records',lambda:rows)
    item=improvements.technical_request('style-1',rows,'Code change required',True)
    with pytest.raises(ValueError,match='No engine update'):
        improvements.attach_result(item['id'],[],'Tests completed')
    monkeypatch.setattr(improvements,'engine_version',lambda:'updated-engine')
    write(data_root()/'snapshots'/'snap1'/'09_review.json',{'sheet':'drawing','metadata':{'source_sha256':'source'}})
    write(data_root()/'snapshots'/'after'/'09_review.json',{'metadata':{'source_sha256':'other','engine_version':'updated-engine'}})
    with pytest.raises(ValueError,match='same source'):
        improvements.attach_result(item['id'],[{'before':'snap1','after':'after'}],'Regression tests passed')
    write(data_root()/'snapshots'/'after'/'09_review.json',{'metadata':{'source_sha256':'source','engine_version':'updated-engine'}})
    result=improvements.attach_result(item['id'],[{'before':'snap1','after':'after'}],'Regression tests passed')
    assert result['status']=='technical_review'
    assert not result['scope_report']['eligible']
    with pytest.raises(ValueError,match='comparisons'):
        improvements.review_update(item['id'],True,'Expert')


def test_one_action_prepares_and_tests_without_publishing(monkeypatch):
    r=row(1);r['sheet']='drawing1'
    monkeypatch.setattr(evidence,'records',lambda:[r])
    monkeypatch.setattr(improvements,'overview',lambda:{'batches':[{'id':'b','training_ids':['1']}],'candidates':[]})
    monkeypatch.setattr(improvements,'prepare',lambda bid:{'id':'c','profile':{},'training_ids':['1']})
    monkeypatch.setattr(improvements,'evaluation_state',lambda c:('ready_to_test','flow',None))
    called=[]
    monkeypatch.setattr(learning,'evaluate',lambda cid,binding,progress:called.append((cid,binding)) or {'id':'e'})
    monkeypatch.setattr(learning,'publish',lambda *a:pytest.fail('Must not publish automatically'))
    result=improvements.check_feedback('drawing1')
    assert called==[('c','flow')] and result['published'] is False


def test_one_action_keeps_technical_work_out_of_evaluation(monkeypatch):
    r=row(1);r['sheet']='drawing1'
    monkeypatch.setattr(evidence,'records',lambda:[r])
    monkeypatch.setattr(improvements,'overview',lambda:{'batches':[{'id':'b','training_ids':['1']}],'candidates':[]})
    monkeypatch.setattr(improvements,'prepare',lambda bid:{'id':'u','status':'technical_review'})
    monkeypatch.setattr(learning,'evaluate',lambda *a:pytest.fail('No configuration to evaluate'))
    assert improvements.check_feedback('drawing1')['outcomes']==[{'id':'u','status':'technical_review'}]


def test_unevaluated_candidate_does_not_scan_all_evaluation_evidence(monkeypatch):
    c=learning.create('style-1','New candidate')
    monkeypatch.setattr(evidence,'evaluation_records',lambda *a:pytest.fail('No report: nothing to validate'))
    assert improvements.evaluation_state(c)==('ready_to_test','preview',None)


def test_snapshot_provenance_is_reused_and_invalidated(tmp_path,monkeypatch):
    path=tmp_path/'snapshots'/'snapshot'/'09_review.json'
    write(path,{'metadata':{'binding_mode':'astra'}})
    r={'id':'a','type':'uncertain','snapshot':'snapshot','tab':'bindings','status':'open','sheet':'s'}
    real=evidence.read;calls=[]
    monkeypatch.setattr(evidence,'read',lambda p,*a: calls.append(str(p)) or real(p,*a))
    assert evidence.annotated_records([r])[0]['assignmentMethod']=='llm'
    assert evidence.annotated_records([r])[0]['assignmentMethod']=='llm'
    assert len(calls)==1
    write(path,{'metadata':{'binding_mode':'flow'}})
    assert evidence.annotated_records([r])[0]['assignmentMethod']=='dimension'
    assert len(calls)==2
