import json
from copy import deepcopy
import pytest
from studio import experiments, evidence, styles, engine
from studio.storage import write, read
from tests.test_assignment_payload import question, expand


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path))
    qs=[question(i) for i in range(26)]
    rv={'sheet':'test','metadata':{'style_id':'style-1','source_sha256':'source'},'stretches':[], 'labels':[], 'nodes':[], 'leaders':[]}
    write(tmp_path/'snapshots/saved/09_review.json',rv)
    monkeypatch.setattr(engine,'reanalyze',lambda *a,**k:(deepcopy(rv),({}, {}, [], {}, None)))
    monkeypatch.setattr(styles,'get_style',lambda *a,**k:{'id':'style-1','rules':[]})
    monkeypatch.setattr(experiments.final_bind,'questions',lambda *a:qs)
    monkeypatch.setattr(evidence,'records',lambda:[])
    return experiments.prepare(['saved'])


def answer(system,payload):
    p=json.loads(payload);qs=expand(p) if p.get('format') else p['questions']
    ds=[{'stretch':q['stretch'],'label':0,'designation_idx':0,'ambiguous':False} for q in qs]
    return {'status':'completed','output_text':json.dumps({'decisions':ds}),'usage':None}


def test_preparation_freezes_identical_questions_and_settings(prepared):
    f=read(experiments.directory(prepared['id'])/'inputs.json');doc=f['documents'][0]
    for b,c in zip(doc['variants']['baseline']['requests'],doc['variants']['compact']['requests']):
        assert json.loads(b)['questions']==expand(json.loads(c))
    assert prepared['quality']=='Not measured'
    assert prepared['runs']==[]


def test_fresh_trials_record_results_without_reusing_answers(prepared):
    calls=[]
    def ask(s,p):calls.append((s,p));return answer(s,p)
    first=experiments.run(prepared['id'],ask=ask)
    second=experiments.run(prepared['id'],ask=ask)
    assert len(calls)==8
    assert first['id']!=second['id']
    assert first['assignment_changes']==[]
    assert first['status']=='completed'
    assert first['publication_eligible'] is False
    assert first['usage']['baseline']['usd'] is None
    assert 'INPUT FORMAT' not in calls[0][0] and 'INPUT FORMAT' in calls[4][0]


def test_failed_calls_cannot_be_scored_as_success(prepared):
    def fail(s,p):return {'status':'incomplete','output_text':'','usage':None}
    report=experiments.run(prepared['id'],ask=fail)
    assert report['status']=='incomplete'
    assert len(report['errors'])==4
    assert not report['assignment_changes']


def test_tampered_inputs_rejected_before_call(prepared):
    p=experiments.directory(prepared['id'])/'inputs.json';f=read(p);f['model']='changed';write(p,f)
    with pytest.raises(ValueError,match='changed'):
        experiments.run(prepared['id'],ask=lambda *a:pytest.fail('No request allowed'))


def test_paid_endpoint_requires_acknowledgement():
    from studio.http import dispatch
    with pytest.raises(ValueError,match='Acknowledge'):
        dispatch('POST','/api/studio/experiment-run',{}, {'id':'example'},'admin')


def test_report_distinguishes_regression_from_changed_decision(prepared, monkeypatch):
    from studio import learning
    from studio.storage import digest
    root=experiments.directory(prepared['id']);f=read(root/'inputs.json')
    f['documents'][0]['feedback']=[{'id':'fb-one','track':'binding','type':'correct'}]
    write(root/'inputs.json',f);m=read(root/'manifest.json');m['input_digest']=digest(f);write(root/'manifest.json',m)
    monkeypatch.setattr(learning,'check_record',lambda rec,rv: any(b['stretch']==0 for b in rv['bindings']))
    def ask(s,p):
        response=answer(s,p)
        if 'INPUT FORMAT' in s:
            ds=json.loads(response['output_text'])
            for d in ds['decisions']:
                if d['stretch']==0:d.update(label=None,designation_idx=None)
            response['output_text']=json.dumps(ds)
        return response
    r=experiments.run(prepared['id'],ask=ask)
    assert r['counts']=={'regression':1}
    assert len(r['assignment_changes'])==1
    assert r['cases'][0]['baseline'] is True and r['cases'][0]['compact'] is False


def test_legacy_snapshot_uses_captured_style(prepared, monkeypatch):
    root=experiments.data_root();p=root/'snapshots/saved/09_review.json';rv=read(p);rv.pop('metadata');write(p,rv)
    monkeypatch.setattr(evidence,'records',lambda:[{'id':'legacy','snapshot':'saved','style_id':'style-1','status':'open','type':'uncertain'}])
    result=experiments.prepare(['saved'],'Legacy comparison')
    assert result['documents'][0]['sheet']=='test'
