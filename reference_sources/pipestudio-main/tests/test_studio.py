from copy import deepcopy
from types import SimpleNamespace
import pytest
from studio import evidence, learning, styles
from studio.storage import write, read, data_root, drawing_lock
from vectorascore.final_bind import validate_decisions
from vectorascore.review import build_review

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path/'studio'))


def fixture_run(tmp_path, name='one'):
    rv={'sheet':name,'metadata':{'run_id':name,'source_sha256':name,'style_id':'style-1','style_version':1},
        'stretches':[{'id':1,'points':[[0,0],[10,0]],'node_a':1,'node_b':2}],
        'nodes':[{'id':1,'x':0,'y':0,'kind':'tick'},{'id':2,'x':10,'y':0,'kind':'circle'}],
        'labels':[],'leaders':[],'paths':[],'bindings':[]}
    d=tmp_path/name
    for f in evidence.FILES:write(d/f,rv if f=='09_review.json' else {})
    return d,rv


def test_reviewer_can_assign_with_astra(monkeypatch, tmp_path):
    from studio import http
    submitted = []
    monkeypatch.setattr(http.tasks, 'submit', lambda kind, work, **kwargs:
        submitted.append((kind, kwargs)) or {'id': 'test-task'})
    for draft, binding in ((False, "astra"), (True, "preview")):
        result, status = http.dispatch('POST', '/api/studio/replay', {},
            {'sheet': 'drawing', 'binding': binding, 'draft': draft}, 'review', tmp_path)
        assert status == 202 and result['id'] == 'test-task'
    assert submitted == [('replay', {'context': {'sheet': 'drawing'}})] * 2


@pytest.mark.parametrize('action,body', [
    ('replay', {'binding': 'preview'}), ('replay', {}),
    ('style', {}), ('publish', {}), ('activate', {}), ('calibrate', {}),
    ('candidate', {}), ('evaluate', {}), ('experiment-run', {}),
])
def test_unauthenticated_cannot_use_actions(action, body):
    from studio.http import dispatch
    assert dispatch('POST', '/api/studio/' + action, {}, body, None)[1] == 403


def test_unknown_role_cannot_assign_with_astra():
    from studio.http import dispatch
    assert dispatch('POST', '/api/studio/replay', {}, {'binding': 'astra'}, None)[1] == 403


def test_reviewer_upload_starts_initial_analysis(monkeypatch, tmp_path):
    from io import BytesIO
    from vectorascore import serve
    uploaded = tmp_path / 'uploads'
    monkeypatch.setattr(serve, 'UPLOADS', str(uploaded))
    monkeypatch.setattr(serve, 'DEBUG', str(tmp_path / 'debug'))
    monkeypatch.setattr(serve, '_pdf_for', lambda sheet: None)
    starts = []
    monkeypatch.setattr(serve, '_start', lambda sheet, **opts: starts.append((sheet, opts)) or True)
    handler = object.__new__(serve.H)
    handler.path = '/api/upload'
    payload = b'%PDF-1.4\n test upload'
    handler.headers = {'Content-Length': str(len(payload)), 'X-File-Name': 'expert.pdf'}
    handler.rfile = BytesIO(payload)
    handler._role = lambda q: 'review'
    responses = []
    handler._json = lambda obj, code=200: responses.append((obj, code))
    handler._post()
    assert responses == [({'sheet': 'expert', 'started': True}, 200)]
    assert (uploaded / 'expert.pdf').read_bytes() == payload
    assert starts == [('expert', {'use_llm': False, 'style_id': 'auto'})]   # the drawing's style is detected unless the reviewer picked one


def test_final_abstention_never_falls_back():
    q=[{'stretch':1,'candidates':[{'label':2,'designation_idx':0}]}]
    for decisions in ([],[{'stretch':1,'label':None,'designation_idx':None,'ambiguous':False}],
                      [{'stretch':1,'label':99,'designation_idx':0,'ambiguous':False}]):
        bindings,assignments,_=validate_decisions(q,decisions)
        assert bindings==[] and assignments[0]['label'] is None
    d={'stretch':1,'label':2,'designation_idx':0,'ambiguous':False}
    assert len(validate_decisions(q,[d])[0])==1
    assert validate_decisions(q,[d,d])[0]==[]


def test_review_empty_final_is_authoritative():
    args=('test',SimpleNamespace(paths=[],page={}),{}, {'ml_joins':[],'label_boxes':[]},
          {'buckets':{},'calibration':{},'counts':{}},
          {'nodes':[],'stretches':[{'id':1,'line_type':'solid'}],'debris':[],'counts':{}},[],
          {'bindings':[{'stretch':1,'label':2,'designation_idx':0,'confidence':'high','rule':'proposal'}],'leaders':[]})
    assert build_review(*args,{'bindings':[]})['bindings']==[]
    rules=deepcopy(args[-1]);rules['bindings'].append(dict(rules['bindings'][0],label=3))
    assert build_review(*args[:-1],rules)['bindings']==[]


def test_snapshot_stale_feedback_and_lock(tmp_path):
    d,rv=fixture_run(tmp_path)
    record=evidence.add(d,{'type':'correct','tab':'pipes','stretch_id':1,'author':'Expert'},'one')
    rv['stretches'][0]['points'][1]=[20,0];rv['metadata']['run_id']='new';write(d/'09_review.json',rv)
    saved=read(data_root()/'snapshots'/record['snapshot']/'09_review.json')
    assert saved['stretches'][0]['points'][1]==[10,0]
    with pytest.raises(ValueError,match='changed'):
        evidence.add(d,{'type':'correct','stretch_id':1,'author':'Expert'},'one')
    with drawing_lock(d):
        with pytest.raises(ValueError,match='processed'):
            evidence.add(d,{'type':'correct','stretch_id':1,'author':'Expert'},'new')


def test_rules_are_not_sheet_overrides():
    p=styles.get_style();p['rules']=[{'id':'bad','stage':'binding','instruction':'Assign label 42 to stretch 11'}]
    with pytest.raises(ValueError,match='cannot refer'):styles.validate(p)
    p['rules']=[];p['calibration']={'assemble.snap':float('nan')}
    with pytest.raises(ValueError):styles.validate(p)
    styles.save_draft('new-office',{'name':'New office'})
    with pytest.raises(ValueError,match='release'):styles.get_style('new-office')


def test_release_requires_holdout_and_stale_evidence_rejects(tmp_path):
    rows=[]
    for name in ('one','two'):
        d,rv=fixture_run(tmp_path,name)
        rows.append(evidence.add(d,{'type':'correct','tab':'pipes','stretch_id':1,'author':'Expert'},name))
    add_cross_style_checks(tmp_path)
    c=learning.create('style-1','Baseline verification',[rows[0]['id']])
    def replay(d,p,binding):return read(d/'09_review.json')
    report=learning.evaluate(c['id'],runner=replay)
    assert report['eligible'] and report['documents']==2 and report['holdout_cases']>=1
    evidence.update(rows[1]['id'],'confirmed','Expert')
    with pytest.raises(ValueError,match='changed'):learning.publish(c['id'],'Expert')
    learning.evaluate(c['id'],runner=replay)
    assert learning.publish(c['id'],'Expert')['version']==c['base_version']+1
    c=learning.create('style-1','No independent data',[r['id'] for r in rows])
    assert not learning.evaluate(c['id'],runner=replay)['eligible']


@pytest.mark.parametrize('method,binding', [('llm','astra'), ('dimension','flow')])
def test_v2_authentication_and_shared_job(monkeypatch, method, binding):
    from flask import Flask
    from service.studio_api import api
    from service.config import Config
    from studio import tasks, engine
    monkeypatch.setattr(Config,'API_KEY','test-secret')
    app=Flask(__name__);app.register_blueprint(api);client=app.test_client()
    assert client.get('/v2/styles').status_code==401
    headers={'X-API-Key':'test-secret','Content-Type':'application/pdf'}
    assert client.post('/v2/analyses',data=b'%PDF-test',headers=headers).status_code==400
    assert client.post('/v2/analyses?assignmentMethod='+method,data=b'not pdf',headers=headers).status_code==400
    captured={}
    def run(*args,**kwargs):captured.update(kwargs);return {'result':'shared'}
    monkeypatch.setattr(engine,'analyze',run)
    monkeypatch.setattr(engine,'api_result',lambda rv:rv)
    def submit(kind,work):
        work(lambda message:None)
        return {'id':'task-test'}
    monkeypatch.setattr(tasks,'submit',submit)
    response=client.post('/v2/analyses?style=style-1&assignmentMethod='+method,data=b'%PDF-test',headers=headers)
    assert response.status_code==202
    aid=response.json['analysis_id']
    assert client.get('/v2/analyses/'+aid+'/result',headers=headers).json=={'result':'shared'}
    assert captured['style_version']==styles.get_style()['version'] and captured['binding']==binding


def test_manual_assessment_is_audited_and_release_is_portable(tmp_path):
    from studio.release import export_bundle, import_bundle
    from studio.storage import engine_version
    rows=[]
    for name,typ in [('one','correct'),('two','uncertain')]:
        d,_=fixture_run(tmp_path,name)
        rows.append(evidence.add(d,{'type':typ,'tab':'pipes','stretch_id':1,'author':'Expert'},name))
    add_cross_style_checks(tmp_path)
    c=learning.create('style-1','Manual review',[rows[0]['id']])
    report=learning.evaluate(c['id'],runner=lambda d,p,b:read(d/'09_review.json'))
    assert not report['eligible']
    report=learning.review_case(report['id'],rows[1]['id'],True,True,'Expert')
    assert report['eligible'] and report['cases'][1]['expert_reviews'][0]['author']=='Expert'
    learning.publish(c['id'],'Expert')
    path=tmp_path/'released.json';bundle=export_bundle(path)
    assert bundle['engine_version']==engine_version()
    import_bundle(path)
    assert styles.get_style()['version']==c['base_version']+1
    bundle['engine_version']='different';write(path,bundle)
    with pytest.raises(ValueError,match='same engine'):import_bundle(path)


def test_relative_style_signature_and_ambiguous_match(monkeypatch):
    from vectorascore import bucket
    monkeypatch.setattr(bucket,'calibrate',lambda p:{'leader_width':p,'pipe_widths':[2*p],
        'circle':{'diameter':5*p},'has_layers':True})
    assert styles.signature(1)==styles.signature(3)
    assert styles.match_style(1)['style_id'] is None
    registry=styles.registry()
    entry = registry['styles']['style-1']
    next(p for p in entry['releases'] if p['version']==entry['active'])['signatures']=[styles.signature(1)]
    write(styles._path(),registry)
    assert styles.match_style(3)['style_id']=='style-1'
    other=deepcopy(registry['styles']['style-1']);other['draft']['id']='other'
    for release in other['releases']: release['id']='other'
    registry['styles']['other']=other;write(styles._path(),registry)
    assert styles.match_style(3)['style_id'] is None


def test_delete_style_preserves_releases_and_excludes_from_recognition(monkeypatch):
    from studio.http import dispatch
    from vectorascore import bucket
    monkeypatch.setattr(bucket, 'calibrate', lambda p: {
        'leader_width': 1, 'pipe_widths': [7], 'circle': None, 'has_layers': False})
    doc = styles.registry()
    base = styles.get_style()
    base.update(id='custom', name='Custom', signatures=[styles.signature({})])
    doc['styles']['custom'] = {'draft': deepcopy(base), 'releases': [base], 'active': base['version']}
    write(styles._path(), doc)
    assert styles.match_style({})['style_id'] == 'custom'
    result, status = dispatch('POST', '/api/studio/delete-style', {},
        {'style_id': 'custom', 'author': 'Reviewer'}, 'review')
    assert status == 200 and result['deleted']
    assert all(e['draft']['id'] != 'custom' for e in styles.list_styles())
    assert styles.get_style('custom', base['version']) == base
    assert styles.match_style({})['style_id'] is None
    assert dispatch('POST', '/api/studio/delete-style', {}, {'style_id': 'custom'}, None)[1] == 403
    with pytest.raises(ValueError, match='fallback'):
        styles.delete_style('style-1')


def test_deleted_shipped_style_is_not_restored_by_registry():
    sid = next(e['draft']['id'] for e in styles.list_styles() if e['draft']['id'] != 'style-1')
    release = styles.get_style(sid)
    styles.delete_style(sid)
    assert all(e['draft']['id'] != sid for e in styles.list_styles())
    assert styles.get_style(sid, release['version']) == release


def test_astra_usage_counts_cache_and_incomplete_responses(monkeypatch):
    from vectorascore import final_bind
    from types import SimpleNamespace as NS
    import openai
    response=NS(model='gpt-6-astra',status='incomplete',usage=NS(input_tokens=1000,output_tokens=100,
        input_tokens_details=NS(cached_tokens=500),output_tokens_details=NS(reasoning_tokens=30)))
    u=final_bind.response_usage(response)
    assert u['usd']==pytest.approx(.0105)
    monkeypatch.setattr(final_bind,'questions',lambda *args:[{'stretch':1,'candidates':[{'label':2,'designation_idx':0}]}])
    monkeypatch.setattr(openai,'OpenAI',lambda **kwargs:NS(responses=NS(create=lambda **kwargs:response)))
    result=final_bind.bind({}, {}, [], {})
    assert result['errors'] and result['bindings']==[]
    assert result['tokens_in']==1000 and result['cached_tokens']==500
    assert result['usd']==pytest.approx(.0105) and result['usage_complete']
    response.model='unknown-model'
    assert final_bind.response_usage(response)['usd'] is None
    assert final_bind.usage_summary([],1)['cost_status']=='unavailable'
    assert final_bind.usage_summary([u],2)['usage_complete'] is False


def test_wrong_feedback_preserves_selected_object(tmp_path):
    d,_=fixture_run(tmp_path)
    r=evidence.add(d,{'type':'wrong','tab':'pipes','stretch_id':1,'author':'Expert','note':'Not this shape'},'one')
    assert r['status']=='open' and r['evidence']['stretches']['id']==1
    assert learning.check_record(r,read(d/'09_review.json')) is None


def test_assignment_freshness_distinguishes_stale_preview_and_running(tmp_path):
    from studio.freshness import assignment_status
    from studio.storage import engine_version,digest
    d,rv=fixture_run(tmp_path)
    assert assignment_status(d)['status']=='legacy'
    rv['metadata'].update(engine_version=engine_version(),binding_mode='preview')
    write(d/'09_review.json',rv)
    assert assignment_status(d)['status']=='preview'
    rv['metadata'].update(binding_mode='astra',style_digest=digest(dict(styles.get_style(draft=True),profile_state='draft')))
    rv['llm']={'mode':'pipe_final','errors':[],'issues':[]}
    write(d/'09_review.json',rv)
    assert assignment_status(d)['status']=='current'
    styles.save_draft('style-1',{'calibration':{'assemble.snap':2}})
    assert assignment_status(d)['status']=='stale'
    write(data_root()/'tasks'/'running.json',{'sheet':d.name,'status':'running'})
    assert assignment_status(d)['status']=='running'
    write(data_root()/'tasks'/'running.json',{'sheet':d.name,'status':'done'})
    rv['metadata']['engine_version']='older-engine'
    write(d/'09_review.json',rv)
    assert any('engine' in r for r in assignment_status(d)['reasons'])


def test_feedback_requires_valid_designation_and_preserves_explicit_null(tmp_path):
    d, rv = fixture_run(tmp_path)
    rv['labels'] = [{'id': 3, 'rect': [0,0,2,2], 'designations': [{'raw': 'KV1-20'}]}]
    write(d/'09_review.json', rv)
    base = {'type': 'wrong_binding', 'tab': 'bindings', 'stretch_id': 1, 'author': 'Expert'}
    for lid, di in [(3, -1), (3, 1), (3, None), (3, True), (False, 0), (None, 0)]:
        with pytest.raises(ValueError):
            evidence.add(d, dict(base, label_id=lid, designation_idx=di), 'one')
    assert evidence.add(d, dict(base, label_id=3, designation_idx=0), 'one')['label_id'] == 3
    assert evidence.add(d, dict(base, label_id=None, designation_idx=None), 'one')['label_id'] is None


def test_conflicting_feedback_is_manual_not_a_successful_abstention(tmp_path):
    d, rv = fixture_run(tmp_path)
    r = evidence.add(d, {'type': 'wrong_binding', 'tab': 'bindings', 'stretch_id': 1,
                        'label_id': None, 'designation_idx': None, 'author': 'Expert',
                        'note': 'Label 16 is more suitable'}, 'one')
    assert evidence.review_warnings(r)
    assert learning.check_record(r, rv) is None
    r['note'] = 'The drawing has no designation for this main.'
    assert not evidence.review_warnings(r)
    assert learning.check_record(r, rv) is True
    r['note'] = 'Pipe 2 should be merged with pipe 1.'
    assert len(evidence.review_warnings(r)) == 2


def test_removing_a_named_label_is_not_a_contradiction():
    r = {'type':'wrong_binding','label_id':None,'note':'The pipe should be removed from label 175 and left without an assigned label'}
    assert evidence.review_warnings(r) == []
    r['note'] = 'Assign to label 97'
    assert evidence.review_warnings(r)


def test_conflicting_confirmations_are_scoped_to_snapshot_and_block_evaluation(tmp_path):
    d, rv = fixture_run(tmp_path)
    rv['labels']=[{'id':3,'rect':[0,0,2,2],'designations':[{'raw':'KV1-20'}]}]
    write(d/'09_review.json',rv)
    correct = evidence.add(d,{'type':'correct','tab':'bindings','stretch_id':1,'author':'Expert'},'one')
    wrong = evidence.add(d,{'type':'wrong_binding','tab':'bindings','stretch_id':1,'author':'Expert',
                           'label_id':3,'designation_idx':0},'one')
    assert set(evidence.assignment_conflicts([correct,wrong])) == {correct['id'],wrong['id']}
    assert not evidence.assignment_conflicts([correct,dict(wrong,snapshot='another')])
    assert not evidence.assignment_conflicts([correct,dict(wrong,status='dismissed')])
    assert evidence.annotated_records([correct,wrong])[0]['review_warnings']
    c=learning.create('style-1','Check contradictory feedback',[wrong['id']])
    with pytest.raises(ValueError,match='Conflicting assignments'):
        learning.evaluate(c['id'],runner=lambda *args:pytest.fail('Must reject before replay'))


def test_missing_leader_checks_drawn_pieces_and_false_node_uses_saved_location():
    r={'type':'missing_leader','points':[[0,0],[10,0]]}
    rv={'leaders':[{'pieces':[[[0,0],[4,0]],[[4,0],[10,0]]]}]}
    assert learning.check_record(r,rv) is True
    rv['leaders']=[{'pieces':[[[0,0],[0,10]],[[10,10],[10,0]]]}]
    assert learning.check_record(r,rv) is False  # a chord across a gap isn't ink
    r={'type':'false_node','evidence':{'nodes':{'x':5,'y':6}}}
    assert learning.check_record(r,{'nodes':[{'x':5,'y':6,'kind':'tick'}]}) is False
    assert learning.check_record(r,{'nodes':[]}) is True


def test_remove_incorrect_label_note_agrees_with_unassigned_choice():
    from studio.evidence import review_warnings
    for note in ['remove pipe 221 from label 175, this is not correct label.',
                 'remove pipe 219 from label 175, there is not correct label for this pipe.']:
        sid = 221 if '221' in note else 219
        assert review_warnings({'type':'wrong_binding','stretch_id':sid,'label_id':None,'note':note}) == []


def test_duplicate_binding_assertions_keep_history_but_count_once():
    from studio.evidence import duplicate_records,evaluation_records
    a={'id':'a','snapshot':'saved','author':'expert','type':'wrong_binding','tab':'bindings','stretch_id':1,'label_id':0,'designation_idx':0,'note':'include this pipe','status':'open'}
    b=dict(a,id='b',point=[12,34]);c=dict(b,id='c',label_id=2);d=dict(b,id='d',note='merge this pipe with pipe 2')
    assert duplicate_records([a,b,c,d])=={'b':'a'}
    assert [r['id'] for r in evaluation_records([a,b,c,d])]==['a','c','d']
    assert duplicate_records([dict(a,status='dismissed'),b])=={}
    assert duplicate_records([a,dict(b,snapshot='another')])=={}


@pytest.mark.parametrize('key,expected', [('review-test','admin'), ('admin-test','admin'), ('wrong',None), ('',None)])
def test_shared_studio_permissions(monkeypatch, key, expected):
    from vectorascore import serve
    monkeypatch.setattr(serve, '_keys', lambda: ('review-test','admin-test'))
    handler=object.__new__(serve.H)
    handler.client_address=('127.0.0.1',1234)
    handler.headers={'Cf-Connecting-Ip':'192.0.2.1','Cookie':'rk='+key}
    assert handler._role({}) == expected


def test_reviewer_can_publish(monkeypatch):
    from studio import http
    calls=[]
    monkeypatch.setattr(http.learning,'publish',lambda cid,author: calls.append((cid,author)) or {'published':True})
    assert http.dispatch('POST','/api/studio/publish',{}, {'id':'candidate','author':'Expert'},'review') == ({'published':True},200)
    assert calls == [('candidate','Expert')]


def add_cross_style_checks(tmp_path):
    for sid in learning.global_rules.active_profiles():
        if sid=='style-1': continue
        d,rv=fixture_run(tmp_path,'check-'+sid)
        rv['metadata'].update(style_id=sid,style_version=styles.get_style(sid)['version'],source_sha256='two')
        write(d/'09_review.json',rv)
        evidence.add(d,{'type':'correct','tab':'pipes','stretch_id':1,'author':'Expert'},'check-'+sid)


def test_cheap_style_resolution_keeps_the_style_the_drawing_was_analysed_with(tmp_path, monkeypatch):
    from studio.engine import resolve_style
    from studio.storage import write
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path/'studio'))
    d = tmp_path/'drawing'
    write(d/'09_review.json', {'metadata': {'style_id': 'style-1', 'style_match': {'status': 'manual', 'selection': 'manual',
        'style_id': None, 'used_style_id': 'style-1', 'method': 'chosen by the reviewer'}}})
    style, match = resolve_style(d, 'auto', detect=False)
    assert style['id'] == 'style-1' and match['selection'] == 'manual'
