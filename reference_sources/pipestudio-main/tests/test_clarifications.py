from copy import deepcopy
import pytest
from studio import clarifications, evidence, learning, improvements, workflow
from studio.storage import data_root,read,write

@pytest.fixture
def feedback(tmp_path,monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path))
    row={'id':'feedback-1','status':'open','style_id':'style-1','sheet':'drawing','snapshot':'snap',
         'type':'false_pipe','tab':'pipes','track':'vectors','note':'Should these be separate?','evidence':{}}
    monkeypatch.setattr(evidence,'records',lambda:[row])
    return row

QUESTIONS=[{'question':'Should these sections be one pipe or separate pipes?',
            'impact':'One pipe joins the sections into a continuous run. Separate pipes keep them as individual elements.',
            'options':['Keep one continuous pipe','Keep separate pipes']}]

def proposal(payload):
    assert 'business reviewer' in payload['clarification_policy']
    return {'implementation':'clarification','questions':QUESTIONS,'rationale':'The intended grouping is unclear.'}

def test_ambiguous_feedback_stays_in_improvements_without_candidate(feedback):
    result=learning.propose('style-1',[feedback['id']],ask=proposal)
    assert result['status']=='needs_clarification'
    assert not learning.candidates() and not improvements.requests()
    assert not improvements.overview()['batches']
    assert workflow.inbox(feedback,{'candidates':[],'implementation_requests':[]})==('review','Your answer needed')
    saved=read(data_root()/'conversations'/'feedback-1.json')
    assert QUESTIONS[0]['impact'] in saved['messages'][0]['text']
    assert saved['messages'][0]['choices']==QUESTIONS[0]['options']

def test_repeated_analysis_does_not_duplicate_pending_question(feedback):
    learning.propose('style-1',[feedback['id']],ask=proposal)
    learning.propose('style-1',[feedback['id']],ask=proposal)
    assert len(read(data_root()/'conversations'/'feedback-1.json')['messages'])==1

def test_answer_is_saved_and_reanalysed_without_publishing(feedback,monkeypatch):
    q=clarifications.request([feedback],QUESTIONS)
    def analyze(sheet,progress):
        assert sheet=='drawing' and not clarifications.pending(feedback['id'])
        examples=learning.abstract_example(feedback)['clarifications']
        assert examples[-1]['text']=='Keep separate pipes'
        assert improvements.overview()['batches']
        return {'published':False}
    monkeypatch.setattr(improvements,'check_feedback',analyze)
    assert clarifications.answer_and_analyze(feedback['id'],q['id'],'Keep separate pipes','Expert')=={'published':False}
    with pytest.raises(ValueError,match='already answered'):
        clarifications.answer_and_analyze(feedback['id'],q['id'],'Duplicate','Expert')

def test_failed_reanalysis_preserves_answer(feedback,monkeypatch):
    q=clarifications.request([feedback],QUESTIONS)
    def fail(*args):raise ValueError('Model unavailable')
    monkeypatch.setattr(improvements,'check_feedback',fail)
    with pytest.raises(ValueError,match='unavailable'):
        clarifications.answer_and_analyze(feedback['id'],q['id'],'Keep separate pipes','Expert')
    assert learning.abstract_example(feedback)['clarifications'][-1]['role']=='expert'
    assert not clarifications.pending(feedback['id'])

def test_label_feedback_can_ask_business_question(feedback):
    feedback.update(track='ocr',tab='labels',type='label_text')
    result=learning.propose('style-1',[feedback['id']],ask=proposal)
    assert result['status']=='needs_clarification' and not improvements.requests()

@pytest.mark.parametrize('questions',[[],['Technical question?'],[{'question':'Should it join?'}]])
def test_question_must_explain_consequences(feedback,questions):
    with pytest.raises(ValueError):clarifications.request([feedback],questions)
    assert not clarifications.pending(feedback['id'])

def test_closed_feedback_cannot_be_answered(feedback):
    q=clarifications.request([feedback],QUESTIONS);feedback['status']='dismissed'
    with pytest.raises(ValueError,match='closed'):
        clarifications.answer_and_analyze(feedback['id'],q['id'],'Separate','Expert')


def test_rebuilding_ai_questions_and_answers_stay_in_app_updates(feedback,monkeypatch):
    item=improvements.technical_request('style-1',[feedback],'Rebuild pipe grouping',True)
    q=improvements.ask_expert(item['id'],feedback['id'],QUESTIONS)
    assert q['origin']=='app_updates'
    assert workflow.inbox(feedback,improvements.overview())==('redeploy','Your answer needed')
    assert improvements.ask_expert(item['id'],feedback['id'],QUESTIONS)['id']==q['id']
    with pytest.raises(ValueError,match='expert answer'):
        improvements.attach_result(item['id'],[],'Implementation completed')
    monkeypatch.setattr(improvements,'check_feedback',lambda *a:pytest.fail('An app update answer must not trigger synthesis'))
    monkeypatch.setattr(workflow,'retry',lambda *a:pytest.fail('The request must stay in App updates'))
    result=clarifications.answer_and_analyze(feedback['id'],q['id'],'Keep separate pipes','Expert')
    assert result['status']=='answer_received' and not result['published']
    assert workflow.inbox(feedback,improvements.overview())==('redeploy','Answer saved — ready for developer')
    brief=improvements.brief(item['id'])
    assert any(m['role']=='expert' and m['text']=='Keep separate pipes' for m in brief['conversations'][feedback['id']]['messages'])
    assert '/api/studio/implementation-questions' in ' '.join(brief['instructions'])
    # A subsequent rebuild can ask a follow-up in the same saved conversation.
    q2=improvements.ask_expert(item['id'],feedback['id'],QUESTIONS)
    assert q2['id']!=q['id']
    assert len(improvements.brief(item['id'])['conversations'][feedback['id']]['messages'])==4


def test_rebuilding_ai_cannot_question_unrelated_or_closed_feedback(feedback):
    item=improvements.technical_request('style-1',[{**feedback,'id':'unrelated'}],'Rebuild grouping',True)
    with pytest.raises(ValueError,match='does not belong'):
        improvements.ask_expert(item['id'],feedback['id'],QUESTIONS)
    assert not clarifications.pending(feedback['id'])
    item=improvements.technical_request('style-1',[feedback],'Rebuild grouping',True)
    item['status']='verified';write(data_root()/'implementation-requests'/(item['id']+'.json'),item)
    with pytest.raises(ValueError,match='open implementation'):
        improvements.ask_expert(item['id'],feedback['id'],QUESTIONS)


def test_questions_do_not_overwrite_other_pending_conversations(feedback):
    existing=clarifications.request([feedback],QUESTIONS)
    item=improvements.technical_request('style-1',[feedback],'Rebuild grouping',True)
    with pytest.raises(ValueError,match='existing question'):
        improvements.ask_expert(item['id'],feedback['id'],QUESTIONS)
    assert clarifications.pending(feedback['id'])['id']==existing['id']


def test_multiple_comments_wait_until_all_questions_are_answered(feedback,monkeypatch):
    second={**feedback,'id':'feedback-2'}
    monkeypatch.setattr(evidence,'records',lambda:[feedback,second])
    item=improvements.technical_request('style-1',[feedback,second],'Rebuild grouping',True)
    q1=improvements.ask_expert(item['id'],feedback['id'],QUESTIONS)
    q2=improvements.ask_expert(item['id'],second['id'],QUESTIONS)
    result=clarifications.answer_and_analyze(feedback['id'],q1['id'],'Separate pipes','Expert')
    assert result['status']=='needs_expert_answer'
    result=clarifications.answer_and_analyze(second['id'],q2['id'],'One pipe here','Expert')
    assert result['status']=='answer_received'


def test_archive_preserves_app_update_conversation(feedback):
    item=improvements.technical_request('style-1',[feedback],'Rebuild grouping',True)
    q=improvements.ask_expert(item['id'],feedback['id'],QUESTIONS)
    clarifications.answer_and_analyze(feedback['id'],q['id'],'Separate pipes','Expert')
    path=data_root()/'implementation-requests'/(item['id']+'.json')
    item=read(path);item.update(status='verified',comparisons=[{'before':feedback['snapshot']}]);write(path,item)
    assert workflow.inbox(feedback,improvements.overview())[0]=='archive'
    assert len(improvements.brief(item['id'])['conversations'][feedback['id']]['messages'])==3


def test_app_update_question_http_roundtrip_uses_no_model_task(feedback,monkeypatch):
    from studio import http
    item=improvements.technical_request('style-1',[feedback],'Rebuild grouping',True)
    q,status=http.dispatch('POST','/api/studio/implementation-questions',{},
        {'id':item['id'],'feedback_id':feedback['id'],'questions':QUESTIONS},'admin')
    assert status==200
    def submit(kind,fn,context):
        assert kind=='feedback-answer'
        return fn(None)
    monkeypatch.setattr(http.tasks,'submit',submit)
    result,status=http.dispatch('POST','/api/studio/feedback-answer',{},
        {'id':feedback['id'],'question_id':q['id'],'message':'Keep separate pipes','author':'Expert'},'review')
    assert status==202 and result['answer_saved']
