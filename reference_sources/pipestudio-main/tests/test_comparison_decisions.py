import pytest
from studio import workflow, evidence, learning
from studio.storage import data_root, write, read

@pytest.fixture
def comparison(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path))
    row={'id':'f1','status':'open','style_id':'style-1','snapshot':'s1','type':'missing_node','tab':'nodes','track':'vectors'}
    monkeypatch.setattr(evidence,'records',lambda:[row])
    monkeypatch.setattr(learning,'candidate',lambda _: {'id':'c1','evaluation':'e1','status':'evaluated','title':'Trial'})
    report={'id':'e1','candidate_id':'c1','engine_version':'saved-engine','eligible':True,
            'cases':[{'feedback_id':'f1','snapshot':'s1','before':False,'after':True,'outcome':'fixed'}]}
    write(data_root()/'evaluations/e1/report.json',report)
    for side in ('before','after'):write(data_root()/f'evaluations/e1/s1-{side}.json',{'original':side})
    return row

def test_no_routes_once_preserves_feedback_and_blocks_acceptance(comparison):
    result=workflow.reject_comparison('e1','f1','Expert')
    assert result['inbox']=='redeploy'
    request=read(data_root()/'implementation-requests'/(result['request_id']+'.json'))
    assert request['feedback_ids']==['f1']
    assert request['rejected_comparison']['evaluation']=='e1'
    assert comparison['status']=='open'
    report=read(data_root()/'evaluations/e1/report.json')
    assert not report['eligible'] and report['cases'][0]['after'] is False
    assert report['cases'][0]['automated_result']['after'] is True
    assert workflow.reject_comparison('e1','f1','Expert')==result
    assert len(list((data_root()/'implementation-requests').glob('*.json')))==1
    assert len(read(data_root()/'conversations/f1.json')['messages'])==1
    assert read(data_root()/'evaluations/e1/s1-after.json')=={'original':'after'}

def test_rejected_positive_check_leaves_archive(comparison):
    comparison.update(type='correct',status='confirmed')
    result=workflow.reject_comparison('e1','f1','Expert')
    request=read(data_root()/'implementation-requests'/(result['request_id']+'.json'))
    assert workflow.inbox(comparison,{'candidates':[],'implementation_requests':[request]})[0]=='redeploy'

def test_missing_results_do_not_record_decision(comparison):
    (data_root()/'evaluations/e1/s1-after.json').unlink()
    with pytest.raises(ValueError,match='Both saved'):workflow.reject_comparison('e1','f1','Expert')
    assert not (data_root()/'implementation-requests').exists()

def test_replaced_comparison_is_rejected(comparison,monkeypatch):
    monkeypatch.setattr(learning,'candidate',lambda _: {'id':'c1','evaluation':'new','status':'evaluated'})
    with pytest.raises(ValueError,match='replaced'):workflow.reject_comparison('e1','f1','Expert')

@pytest.fixture
def acceptance(comparison,monkeypatch,tmp_path):
    from studio import global_rules
    from studio.storage import digest,engine_version
    candidate={'id':'c1','evaluation':'e1','status':'evaluated','title':'Trial','rule_scope':'global'}
    monkeypatch.setattr(learning,'candidate',lambda _:candidate)
    monkeypatch.setattr(learning,'evaluation_rows',lambda _:[comparison])
    monkeypatch.setattr(learning,'profile_digest',lambda _:'profile')
    monkeypatch.setattr(global_rules,'bases_current',lambda _:True)
    monkeypatch.setattr(global_rules,'scope_gate',lambda report,*_:report)
    monkeypatch.setattr(learning,'_gate',lambda report,_:report.update(eligible=all(c['after'] for c in report['cases'])))
    report=read(data_root()/'evaluations/e1/report.json')
    report.update(engine_version=engine_version(),profile_digest='profile',evidence_digest=digest([comparison]))
    write(data_root()/'evaluations/e1/report.json',report)
    comparison['sheet']='drawing'
    report['evidence_digest']=digest([comparison]);write(data_root()/'evaluations/e1/report.json',report)
    calls=[]
    def apply(cid,author,debug,progress,retry_failed=False):
        calls.append(cid)
        candidate['status']='published'
        result={'published':True,'results':[{'sheet':'drawing','status':'updated','before':'s1','after':'new'}]}
        write(data_root()/'applications/c1.json',result)
        return result
    monkeypatch.setattr(workflow,'apply_improvement',apply)
    return comparison,candidate,calls


def test_yes_applies_then_archives_without_changing_training_evidence(acceptance,tmp_path):
    row,candidate,calls=acceptance
    result=workflow.accept_comparison('e1','f1','Expert',tmp_path)
    assert result['inbox']=='archive' and calls==['c1']
    request=read(data_root()/'implementation-requests'/(result['request_id']+'.json'))
    assert request['status']=='deployed'
    assert workflow.inbox(row,{'candidates':[],'implementation_requests':[request]})[0]=='archive'
    assert row['status']=='open'
    assert workflow.accept_comparison('e1','f1','Expert',tmp_path)==result
    assert calls==['c1']
    assert len(read(data_root()/'conversations/f1.json')['messages'])==1


def test_yes_with_other_failures_waits_for_deployment(acceptance,tmp_path):
    row,candidate,calls=acceptance
    report=read(data_root()/'evaluations/e1/report.json')
    report['cases'].append({'feedback_id':'other','after':False,'outcome':'fail'})
    write(data_root()/'evaluations/e1/report.json',report)
    result=workflow.accept_comparison('e1','f1','Expert',tmp_path)
    assert not calls and result['inbox']=='redeploy'
    request=read(data_root()/'implementation-requests'/(result['request_id']+'.json'))
    assert request['status']=='awaiting_deployment'
    assert 'Other examples' in request['reason']
    assert workflow.inbox(row,{'candidates':[],'implementation_requests':[request]})==('redeploy','Solution accepted — awaiting deployment')


def test_yes_stale_result_records_acceptance_without_deploying(acceptance,tmp_path):
    _,_,calls=acceptance
    report=read(data_root()/'evaluations/e1/report.json');report['engine_version']='old'
    write(data_root()/'evaluations/e1/report.json',report)
    result=workflow.accept_comparison('e1','f1','Expert',tmp_path)
    assert not calls and result['inbox']=='redeploy' and 'Revalidate' in result['reason']


def test_yes_refresh_failure_does_not_archive_and_retry_completes(acceptance,monkeypatch,tmp_path):
    row,_,_=acceptance
    monkeypatch.setattr(workflow,'apply_improvement',lambda *a,**k:{'published':True,'results':[{'sheet':'drawing','status':'error','reason':'Refresh failed'}]})
    result=workflow.accept_comparison('e1','f1','Expert',tmp_path)
    request=read(data_root()/'implementation-requests'/(result['request_id']+'.json'))
    assert request['status']=='deployment_failed' and result['inbox']=='redeploy'
    assert workflow.inbox(row,{'candidates':[],'implementation_requests':[request]})[0]=='redeploy'
    workflow._finish_deployments('c1',{'published':True,'results':[{'sheet':'drawing','status':'updated'}]})
    request=read(data_root()/'implementation-requests'/(result['request_id']+'.json'))
    assert workflow.inbox(row,{'candidates':[],'implementation_requests':[request]})[0]=='archive'


def test_yes_submission_dispatches_background_application(acceptance,monkeypatch,tmp_path):
    from studio import http
    jobs=[]
    monkeypatch.setattr(http.tasks,'submit',lambda kind,work,context:jobs.append((kind,work,context)) or {'id':'job'})
    result,status=http.dispatch('POST','/api/studio/accept-comparison',{}, {'evaluation':'e1','feedback_id':'f1','author':'Expert'},'review',tmp_path)
    assert status==202 and jobs[0][0]=='accept-comparison'
    assert jobs[0][2]['feedback_id']=='f1'
    assert jobs[0][1](lambda _:None)['inbox']=='archive'


def test_accepted_app_update_archives_only_after_verified_comparison(acceptance,tmp_path):
    row,_,_=acceptance
    report=read(data_root()/'evaluations/e1/report.json');report['engine_version']='old'
    write(data_root()/'evaluations/e1/report.json',report)
    result=workflow.accept_comparison('e1','f1','Expert',tmp_path)
    request=read(data_root()/'implementation-requests'/(result['request_id']+'.json'))
    request.update(status='review_app_update',comparisons=[{'before':'s1','after':'new'}])
    assert workflow.inbox(row,{'candidates':[],'implementation_requests':[request]})[0]=='redeploy'
    request['status']='verified'
    assert workflow.inbox(row,{'candidates':[],'implementation_requests':[request]})[0]=='archive'
