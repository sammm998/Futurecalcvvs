"""Global-first learning: executable policy, independent of the model's opinion."""
from copy import deepcopy
import pytest
from studio import engine, learning, global_rules, style_rules, styles, evidence, improvements
from studio.storage import data_root, read, write

@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path/'studio'))
    base=styles.get_style('style-1')
    a=deepcopy(base);a.update(id='alpha',name='Alpha',version=1,calibration={'assemble.snap':1.0})
    b=deepcopy(base);b.update(id='beta',name='Beta',version=1,calibration={'assemble.snap':1.5,'assemble.lateral':2.0})
    monkeypatch.setattr(styles,'GROUPS',[]);monkeypatch.setattr(styles,'ALIASES',{})
    monkeypatch.setattr(styles,'shipped_styles',lambda:{'alpha':a,'beta':b})
    # Archive baselines are excluded from the active test registry.
    monkeypatch.setattr(styles,'SHIPPED',tmp_path/'no-shipped-files')
    pipe={'id':1,'points':[[0,0],[10,0]],'width':1,'length':10,'node_a':1,'node_b':2}
    rows=[]
    for name,sid,typ in [('bad','alpha','false_pipe'),('good','alpha','correct'),('other','beta','correct')]:
        rv={'sheet':name,'metadata':{'style_id':sid,'style_version':1,'source_sha256':name,'run_id':name},
            'stretches':[pipe],'nodes':[],'labels':[],'leaders':[],'paths':[],'bindings':[]}
        d=tmp_path/name
        for f in evidence.FILES:write(d/f,rv if f=='09_review.json' else {})
        rows.append(evidence.add(d,{'type':typ,'tab':'pipes','stretch_id':1,'author':'Expert'},name))
    def create():
        p=styles.get_style('alpha');p['calibration']['assemble.snap']=2.5
        return learning.create('alpha','Join convention',[rows[0]['id']],p)
    def runner(regression=False):
        def run(d,p,binding):
            rv=read(d/'09_review.json')
            if p['calibration']['assemble.snap']==2.5 and (rv['sheet']=='bad' or regression and p['id']=='beta'):
                rv['stretches']=[]
            return rv
        return run
    return rows,create,runner


def test_global_patch_tests_and_publishes_every_style(world):
    rows,create,runner=world;c=create()
    assert c['rule_scope']=='global'
    assert c['profiles']['beta']['calibration']['assemble.lateral']==2
    report=learning.evaluate(c['id'],runner=runner())
    assert report['eligible'] and set(report['tested_styles'])=={'alpha','beta'}
    assert not style_rules.restrict_after_global_regression(c['id'])
    learning.publish(c['id'],'Expert')
    for sid in ('alpha','beta'):
        assert styles.get_style(sid)['calibration']['assemble.snap']==2.5
        assert styles.get_style(sid)['version']==2
        assert styles.get_style(sid,1)['calibration']['assemble.snap']!=2.5
    assert styles.registry()['global_changes'][0]['candidate_id']==c['id']


def test_missing_other_style_evidence_stays_global_even_after_manual_check(world):
    rows,create,runner=world
    evidence.update(rows[2]['id'],'dismissed','Expert')
    c=create();r=learning.evaluate(c['id'],runner=runner())
    assert r['missing_styles']==['beta'] and not r['eligible']
    assert not style_rules.restrict_after_global_regression(c['id'])
    r=learning.review_case(r['id'],rows[0]['id'],False,True,'Expert')
    assert not r['eligible']
    with pytest.raises(ValueError,match='gate'):learning.publish(c['id'],'Expert')
    assert learning.candidate(c['id'])['rule_scope']=='global'


def test_regression_allows_tested_style_exception_only(world):
    rows,create,runner=world;c=create()
    global_report=learning.evaluate(c['id'],runner=runner(True))
    assert not global_report['eligible']
    assert style_rules.restrict_after_global_regression(c['id'])
    c=learning.candidate(c['id'])
    assert c['global_rejection']['evaluation']==global_report['id']
    with pytest.raises(ValueError,match='gate'):learning.publish(c['id'],'Expert')
    report=learning.evaluate(c['id'],runner=runner(True))
    assert report['eligible'] and report['rule_scope']=='style'
    learning.publish(c['id'],'Expert')
    assert styles.get_style('alpha')['version']==2
    assert styles.get_style('beta')['version']==1
    assert not styles.registry().get('global_changes')


def test_unfixed_source_never_becomes_style_exception(world):
    rows,create,runner=world;c=create()
    learning.evaluate(c['id'],runner=lambda d,p,b:read(d/'09_review.json'))
    assert not style_rules.restrict_after_global_regression(c['id'])


def test_new_style_invalidates_global_publication(world):
    rows,create,runner=world;c=create();learning.evaluate(c['id'],runner=runner())
    doc=styles.registry();entry=deepcopy(doc['styles']['beta'])
    for p in entry['releases']+[entry['draft']]:p['id']='gamma'
    doc['styles']['gamma']=entry;write(styles._path(),doc)
    with pytest.raises(ValueError,match='changed'):learning.publish(c['id'],'Expert')


def test_changed_other_style_evidence_invalidates_publish(world):
    rows,create,runner=world;c=create();learning.evaluate(c['id'],runner=runner())
    evidence.update(rows[2]['id'],'confirmed','Another expert')
    with pytest.raises(ValueError,match='changed'):learning.publish(c['id'],'Expert')


def test_grouping_collects_feedback_across_styles(world):
    rows,_,_=world
    groups=improvements.overview(rows=[{**r,'status':'open','type':'false_pipe'} for r in rows])['batches']
    assert len(groups)==1 and groups[0]['count']==3


def test_assignment_rules_cannot_change_shared_geometry(world,monkeypatch):
    monkeypatch.setattr(evidence,'annotated_records',lambda rs:rs)
    _,_,_=world;p=styles.get_style('alpha');base=deepcopy(p)
    p['calibration']['assemble.snap']=2.5
    for method in ('dimension','llm'):
        r={'track':'binding','tab':'bindings','assignmentMethod':method,'review_warnings':[]}
        with pytest.raises(ValueError,match='shared geometry'):
            learning.validate_feedback_scope(p,base,[r])


def test_shared_evaluation_does_not_judge_assignments_in_preview(world,monkeypatch):
    rows,create,_=world;c=create()
    extra={**rows[2],'id':'binding-row','track':'binding','tab':'bindings','assignmentMethod':'llm'}
    monkeypatch.setattr(evidence,'records',lambda:rows+[extra])
    assert extra['id'] not in {r['id'] for r in learning.evaluation_rows(c)}


def test_method_specific_global_evaluation_keeps_other_method_out(world,monkeypatch):
    rows,_,_=world
    a={**rows[0],'track':'binding','tab':'bindings','assignmentMethod':'llm'}
    b={**rows[2],'track':'binding','tab':'bindings','assignmentMethod':'dimension'}
    monkeypatch.setattr(evidence,'records',lambda:[a,rows[1],b])
    # Method provenance normally comes from frozen metadata; use explicit annotated fixtures.
    monkeypatch.setattr(evidence,'annotated_records',lambda rs:rs)
    c=learning.create('alpha','LLM convention',[a['id']])
    assert c['feedback_domain']=='llm'
    assert {r['id'] for r in learning.evaluation_rows(c)}=={a['id'],rows[1]['id']}


def test_new_shipped_style_inherits_published_global_patch(world,monkeypatch):
    _,create,runner=world;c=create();learning.evaluate(c['id'],runner=runner());learning.publish(c['id'],'Expert')
    prior=styles.shipped_styles()
    extra=deepcopy(prior['beta']);extra.update(id='gamma',name='Gamma')
    monkeypatch.setattr(styles,'shipped_styles',lambda:{**prior,'gamma':extra})
    assert styles.get_style('gamma')['calibration']['assemble.snap']==2.5


def test_rebuilt_global_change_requires_and_accepts_cross_style_proof(world,monkeypatch):
    rows,_,_=world
    item=improvements.technical_request('alpha',[rows[0]],'Change pipe classification',True)
    monkeypatch.setattr(improvements,'engine_version',lambda:'rebuilt-engine')
    pairs=[]
    for i,r in enumerate(rows):
        rv=read(data_root()/'snapshots'/r['snapshot']/'09_review.json')
        rv['metadata']['engine_version']='rebuilt-engine'
        if i==0:rv['stretches']=[]
        after='rebuilt-'+str(i)
        write(data_root()/'snapshots'/after/'09_review.json',rv)
        pairs.append({'before':r['snapshot'],'after':after})
    pending=improvements.attach_result(item['id'],pairs[:2],'Target style checks passed')
    assert pending['status']=='technical_review'
    with pytest.raises(ValueError,match='global attempt'):
        improvements.attach_result(item['id'],pairs,'All checks passed',rule_scope='style')
    ready=improvements.attach_result(item['id'],pairs,'All active style checks passed')
    assert ready['status']=='review_app_update'
    assert improvements.review_update(item['id'],True,'Expert')['status']=='verified'


def test_acceptance_automatically_publishes_a_validated_global_rule(world,monkeypatch,tmp_path):
    from studio import workflow
    rows,create,runner=world
    c=create();report=learning.evaluate(c['id'],runner=runner())
    assert report['eligible']
    def apply(cid,author,debug,progress,retry_failed=False):
        learning.publish(cid,author)
        return {'published':True,'results':[{'sheet':rows[0]['sheet'],'status':'updated'}]}
    monkeypatch.setattr(workflow,'apply_improvement',apply)
    result=workflow.accept_comparison(report['id'],rows[0]['id'],'Expert',tmp_path)
    assert result['inbox']=='archive'
    assert learning.candidate(c['id'])['status']=='published'
    assert styles.get_style('alpha')['version']==2
    assert styles.get_style('beta')['version']==2
