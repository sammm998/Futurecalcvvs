from copy import deepcopy
import pytest
from studio import workflow, evidence, improvements, learning, styles
from studio.storage import write, read, data_root

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path/'studio'))

def row():return {'id':'feedback-1','style_id':'style-1','snapshot':'snapshot-1','sheet':'drawing','status':'open','type':'wrong_binding','track':'binding','tab':'bindings','assignmentMethod':'llm','evidence':{},'note':'Follow the leader','history':[]}

def flow():return {'candidates':[],'implementation_requests':[]}

def test_inboxes_require_actual_success():
    r=row();f=flow()
    assert workflow.inbox(r,f)[0]=='review'
    u={'status':'requires_app_update','training_ids':[r['id']]};f['implementation_requests']=[u]
    assert workflow.inbox(r,f)[0]=='redeploy'
    u.update(status='review_app_update');assert workflow.inbox(r,f)[0]=='redeploy'
    u.update(status='verified',comparisons=[{'before':'unrelated'}]);assert workflow.inbox(r,f)[0]!='archive'
    u['comparisons']=[{'before':r['snapshot']}];assert workflow.inbox(r,f)[0]=='archive'
    f=flow();c={'workflow_status':'ready_to_publish','training_ids':[r['id']],'report':{'cases':[{'feedback_id':r['id'],'after':True}]}};f['candidates']=[c]
    assert workflow.inbox(r,f)[0]=='review'
    c['workflow_status']='published';assert workflow.inbox(r,f)[0]=='archive'
    c['report']['cases'][0]['after']=False;assert workflow.inbox(r,f)[0]=='review'

def test_conflicting_positive_example_needs_resolution():
    r={**row(),'type':'correct','status':'confirmed','conflicting_feedback':['another']}
    assert workflow.inbox(r,flow())[0]=='review'
    r['conflicting_feedback']=[];assert workflow.inbox(r,flow())[0]=='archive'

def test_chat_persists_and_only_cites_existing_rules(monkeypatch):
    r=row();monkeypatch.setattr(evidence,'records',lambda:[r])
    rule=styles.get_style(draft=True)['rules'][0]
    reply=workflow.discuss(r['id'],'Should this follow the leader?','Expert',ask=lambda p:{'reply':'Check the leader connection.','conflicting_rule_ids':[rule['id'],'invented']})
    assert reply['rule_conflicts']==[rule]
    messages=read(data_root()/'conversations'/(r['id']+'.json'))['messages']
    assert [m['role'] for m in messages]==['expert','app']
    assert learning.abstract_example(r)['clarifications']==messages
    assert not learning.candidates()

def test_failed_chat_keeps_expert_message(monkeypatch):
    r=row();monkeypatch.setattr(evidence,'records',lambda:[r])
    def fail(_):raise ValueError('No response')
    with pytest.raises(ValueError):workflow.discuss(r['id'],'My explanation','Expert',ask=fail)
    messages=read(data_root()/'conversations'/(r['id']+'.json'))['messages']
    assert messages[0]['text']=='My explanation' and messages[1]['role']=='system'

def test_retry_retires_old_proposal_without_losing_evidence(monkeypatch):
    r=row();monkeypatch.setattr(evidence,'records',lambda:[r])
    c=learning.create('style-1','Old proposal',[r['id']]);workflow.retry(r['id'])
    assert learning.candidate(c['id'])['status']=='withdrawn'
    assert improvements.overview()['batches'][0]['training_ids']==[r['id']]
    with pytest.raises(ValueError,match='closed'):learning.evaluate(c['id'])
    with pytest.raises(ValueError,match='closed'):learning.publish(c['id'],'Expert')

def test_style_from_drawing_queues_inspection(monkeypatch,tmp_path):
    from studio import http
    jobs=[]
    monkeypatch.setattr(http.tasks,'submit',lambda kind,work,context:jobs.append((kind,work,context)) or {'id':'job-test'})
    result,status=http.dispatch('POST','/api/studio/style-from-drawing',{}, {'sheet':'drawing','name':'Example'},'review',tmp_path)
    assert status==202 and result['id']=='job-test'
    assert jobs[0][0]=='style-from-drawing' and jobs[0][2]['sheet']=='drawing'


@pytest.mark.parametrize('width', [0.48, 1.44, None])
def test_style_from_pdf_with_thin_or_missing_pipe_families(tmp_path, width):
    import pymupdf
    from vectorascore import extract, profile
    from studio.style_creation import create
    from studio import engine
    from PIL import Image

    pdf = tmp_path/'drawing.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=2384, height=1684)
        if width is not None:
            for i in range(40):
                page.draw_line((100, 100 + i * 20), (500, 100 + i * 20), width=width)
        doc.save(pdf)
    ex = extract.extract(str(pdf))
    P = profile.profile(ex)
    directory = tmp_path/'drawing'
    write(directory/'02_profile.json', P)
    extract.save(ex, directory/'01_extract.json')
    base = styles.get_style()
    if width == 0.48:
        assert styles.signature(P)['pipe_ratios'] == []
        assert styles.signature(P, ex)['pipe_ratios']
    elif width == 1.44:
        assert styles.signature(P, ex) == styles.signature(P)

    Image.new('RGB',(2384,1684),'white').save(directory/'bg.png')
    body={'sheet':'drawing','name':'New drawing style','base_style':base['id']}
    result=create(tmp_path,body)
    created = styles.get_style(result['id'])
    assert created['rules'] == base['rules']
    assert created['calibration'] == styles.drawing_parameters(P, ex)[0]
    assert created['calibration_mode'] == 'auto'
    assert 'library_id' not in created
    assert created['pen_table']['pipe_widths'] == ([] if width is None else [width])
    if width is None:
        assert created['signatures'] == []
        assert 'normal drawing feedback' in created['description']
        assert styles.match_style(P, ex)['style_id'] is None
    else:
        assert created['signatures'] == [styles.signature(P, ex)]
        if width == 0.48:
            assert engine.detect_style(ex, P)['style_id'] == created['id']
    assert engine.resolve_style(directory, created['id'])[0]['id'] == created['id']


def test_apply_refreshes_only_published_style_and_keeps_original_on_failure(monkeypatch,tmp_path):
    from studio import engine,assignment_results
    from studio.storage import write,read
    profile=styles.get_style();profile['version']=2
    monkeypatch.setattr(learning,'publish',lambda *a:profile)
    monkeypatch.setattr(learning,'candidate',lambda _: {'evaluation':'eval','style_id':'style-1'})
    write(data_root()/'evaluations'/'eval'/'report.json',{'binding':'flow'})
    debug=tmp_path/'debug'
    for name,sid in [('one','style-1'),('two','style-1'),('other','bd-ghostscript')]:
        write(debug/name/'09_review.json',{'sheet':name,'metadata':{'style_id':sid},'original':True})
    monkeypatch.setattr(assignment_results,'save',lambda *a:None)
    monkeypatch.setattr(assignment_results,'fingerprint',lambda *a:'key')
    def run(d,p,binding):
        assert binding=='flow'
        if d.name=='two':raise ValueError('Cannot analyse')
        return {'sheet':d.name,'metadata':{'style_id':p['id']},'updated':True}, ({},{},[],{},None)
    monkeypatch.setattr(engine,'reanalyze',run)
    result=workflow.apply_improvement('cand','Expert',debug)
    assert len(result['results'])==2
    assert read(debug/'one'/'09_review.json')['updated']
    assert read(debug/'two'/'09_review.json')['original']
    assert read(debug/'other'/'09_review.json')['original']
    assert result['results'][1]['status']=='error'
    assert read(data_root()/'applications'/'cand.json')['published']

@pytest.mark.parametrize('instruction',['Only apply on drawing V-50-1-A0123','Only use this rule for project.pdf','Connect pipe 42 to the next endpoint'])
def test_drawing_specific_rules_never_enter_style(instruction):
    profile=styles.get_style();profile['rules']=[{'id':'bad','stage':'binding','instruction':instruction}]
    with pytest.raises(ValueError,match='cannot refer'):styles.validate(profile)


def test_open_label_feedback_goes_to_the_label_team_not_the_work_queue():
    from studio import label_report
    r={'id':'fb-l','type':'missing_label','status':'open','snapshot':'s','sheet':'A','ts':'2026-09-10T00:00:00'}
    assert workflow.inbox(r,{'candidates':[],'implementation_requests':[],'batches':[]})[0]=='labels'
    r['status']='resolved';assert workflow.inbox(r,{'candidates':[],'implementation_requests':[],'batches':[]})[0]=='archive'
    rows=[dict(r,status='open',rect=[1,2,30,12],note='third | row',author='Viktor'),
          {'id':'fb-t','type':'label_text','status':'open','snapshot':'s','sheet':'A','ts':'2026-09-10T00:00:00','point':[5,6],'text':'VV1-X31',
           'evidence':{'label':{'text':'VV1EX31'}},'author':'Viktor'},
          {'id':'fb-n','type':'missing_node','status':'open','snapshot':'s','sheet':'A','ts':'2026-09-10T00:00:00'}]
    md=label_report.markdown(rows)
    assert '## A' in md and '| 1 | Missing label | area x 1.0–30.0, y 2.0–12.0 | — | — | third \\| row | Viktor |' in md
    assert '| Wrong label text | point x 5.0, y 6.0 | VV1EX31 | VV1-X31 |' in md and 'fb-n' not in md


def test_every_comment_gets_its_own_reply_with_options(tmp_path, monkeypatch):
    from studio import replies
    from studio.storage import write
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path))
    replies._snapshot.cache_clear()
    write(tmp_path/'snapshots'/'snap'/'09_review.json', {'paths':[{'id':1,'bucket':'thin_other','width':0.72,'layer':'V-T','reason':'tick-shaped stroke with no leader ending on it','segs':[[10,10,12,12]]}],
                                                          'nodes':[{'id':1,'x':16,'y':11,'kind':'circle','joining':True}]})
    a=replies.reply({'type':'missing_node','snapshot':'snap','point':[11,11],'note':'this is a tick joining point'},'redeploy','Developer diagnosis needed')
    b=replies.reply({'type':'false_pipe','snapshot':'snap','point':[40,40],'evidence':{'stretches':{'width':1.44,'line_type':'solid','layer':'A-WALL'}}},'review','Ready to analyse')
    assert 'a thin line the analysis did not take for a leader (0.72 pt, layer V-T) right there' in a['text'] and 'ring 5 pt away' in a['text']
    assert 'I read your note as: "this is a tick joining point"' in a['text'] and 'with the developer' in a['text']
    assert a['options'] and a['detail']=='tick-shaped stroke with no leader ending on it'
    assert '1.44 pt solid line on layer A-WALL' in b['text'] and 'Find improvements' in b['text'] and b['detail'] is None
    assert replies.reply({'type':'correct'},'archive','') is None


def test_reply_is_read_for_one_comment_not_for_the_whole_inbox(tmp_path, monkeypatch):
    from studio import improvements, replies
    from studio.storage import write
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path))
    replies._snapshot.cache_clear()
    rows=[{'id':'fb-a','type':'missing_node','status':'open','snapshot':'snap','sheet':'A','ts':'2026-09-10T00:00:00','point':[11,11]},
          {'id':'fb-b','type':'false_pipe','status':'open','snapshot':'snap','sheet':'A','ts':'2026-09-10T00:00:00'}]
    write(tmp_path/'snapshots'/'snap'/'09_review.json',{'paths':[{'id':1,'bucket':'pipe','width':1.44,'layer':'V','segs':[[10,10,12,12]]}],'nodes':[]})
    flow={'batches':[],'candidates':[],'implementation_requests':[]}
    assert all('reply' not in entry for entry in workflow.conversations(rows,flow).values())
    one=workflow.reply('fb-a',rows,flow)
    assert one['id']=='fb-a' and one['inbox']=='review' and 'a pipe line' in one['reply']['text']
    assert workflow.reply('fb-b',rows)['reply']['options']          # resolves its own flow when none is given
    try:
        workflow.reply('fb-missing',rows,flow)
    except ValueError as exc:
        assert 'Unknown feedback' in str(exc)
    else:
        raise AssertionError('an unknown id must be refused')
