"""Expert-facing next actions derived from captured evidence and tested candidates."""
from collections import defaultdict
from . import evidence, learning, styles, global_rules, style_rules, clarifications
from .storage import data_root, read, write, digest, new_id, now, engine_version, ident


def scope(row):
    if row.get('tab') == 'bindings' or row.get('track') == 'binding':
        if 'review_warnings' in row:
            return row.get('assignmentMethod') or 'unknown'
        methods = learning.assignment_methods([row])
        return next(iter(methods)) if len(methods) == 1 else 'unknown'
    return 'labels' if row.get('track') == 'ocr' else 'shared'


def requests():
    return [read(p) for p in sorted((data_root()/'implementation-requests').glob('*.json'))]


def technical_request(style_id, rows, reason, requires_code=False):
    ids = sorted(r['id'] for r in rows)
    # Repeated preparation of the same evidence does not create duplicate handoffs.
    key = digest({'ids':ids,'reason':reason,'engine':engine_version()})[:24]
    path = data_root()/'implementation-requests'/('update-'+key+'.json')
    existing = read(path)
    if existing:
        return existing
    item = {'id':'update-'+key,'style_id':style_id,'training_ids':ids,
            'status':'requires_app_update' if requires_code else 'technical_review',
            'reason':reason,'created_at':now(),'engine_version':engine_version(),
            'scope':scope(rows[0]) if rows else 'unknown', 'rule_scope':'global',
            'scope_policy':'Implement a global correction first. A style exception requires measured cross-style regressions; insufficient evidence is not a rejection.'}
    write(path,item)
    return item


def ask_expert(request_id, feedback_id, questions, reason=''):
    """The rebuilding AI supplies the question; Studio stores it without another model call."""
    row=next((r for r in evidence.records() if r['id']==ident(feedback_id)),None)
    if not row:raise ValueError('Unknown feedback')
    return clarifications.request([row],questions,reason,origin='app_updates',implementation_id=request_id)


def brief(request_id):
    item=read(data_root()/'implementation-requests'/(ident(request_id)+'.json'))
    if not item:
        raise ValueError('Unknown implementation request')
    selected=[r for r in evidence.records() if r['id'] in item.get('feedback_ids',item['training_ids'])]
    return {'title':'Pipe Studio improvement — '+item['reason'], 'request':item,
            'instructions':[
                'Investigate the root cause before choosing a code change or a configurable rule.',
                'Never create a rule or code exception tied to a drawing, filename, object ID or fixed coordinates.',
                'Use the attached examples only as evidence and regression tests.',
                'Check shared geometry and labels before changing method-specific assignments.',
                'Implement and test a global correction first across all active styles. Only measured regressions in other styles justify a style exception; missing evidence keeps the global change pending. Do not claim universal coverage without evidence.',
                'Preserve original snapshots. Save before/after comparisons for expert review.',
                'Record implementation, validation and deployment evidence before marking this request complete.',
                'Start with rule_scope=global. Only after a saved global attempt shows cross-style regressions may a revised implementation use rule_scope=style; retest the exception and unaffected styles.',
                'Provide comparisons for correct examples across every active style, independent held-out documents and the original corrections. Missing coverage blocks acceptance.',
                'When intent is unclear during rebuilding, YOU write a supportive business question and POST /api/studio/implementation-questions with id (this request), feedback_id (one of the attached open comments), reason, questions: [{question, impact, options: []}]. Prefer one question; reflect your understanding, offer an interpretation and explain the practical consequences. Avoid code, graph topology, thresholds and implementation choices; the expert describes the desired result, not how to program it. Use the expert language. Keep options optional and allow another answer. Do not invent financial or quantity impacts.',
                'Pause work dependent on the answer. Questions appear in App updates. Continue independent work if useful. GET /api/studio/implementation-brief?id=... to read answers in conversations before continuing; never infer an answer from elapsed time. Studio stores answers but does not launch or wake a coding agent. Unanswered questions block attaching and accepting an update.',
                'After updating the app, POST /api/studio/implementation-result with id, validation_summary and comparisons: [{before: original_snapshot_id, after: new_snapshot_id}]. The expert will inspect and accept or reject these results in App updates.'
            ], 'evidence':selected,
            'conversations':{r['id']:read(data_root()/'conversations'/(ident(r['id'])+'.json'),{'messages':[]}) for r in selected}}


def evaluation_state(c):
    report=read(data_root()/'evaluations'/c.get('evaluation','none')/'report.json')
    if c['status']=='published':
        return 'published',None,report
    try:
        methods=learning.candidate_scope(c)
        base=styles.get_style(c['style_id'],c['base_version']) if c.get('base_version') else c['profile']
        binding='astra' if methods=={'llm'} or c['profile']['rules']!=base['rules'] else 'flow' if methods=={'dimension'} else 'preview'
        if not report:
            return 'ready_to_test',binding,None
        rows=learning.evaluation_rows(c)
        current=bool(report and report['engine_version']==engine_version() and report['profile_digest']==learning.profile_digest(c)
                     and report['evidence_digest']==digest(rows) and global_rules.bases_current(c))
        if not current:
            return 'ready_to_test',binding,report
        if report['eligible']:
            return 'ready_to_publish',binding,report
        return ('review_results' if any(x['outcome']=='manual' for x in report['cases']) else 'needs_more_evidence'),binding,report
    except ValueError:
        return 'needs_more_evidence',None,report


def overview_for(row):
    """The part of the flow that decides where ONE comment sits: every technical
    request (they are small) and evaluation state only for the candidates carrying
    this comment. Building the full overview for a single comment is wasteful."""
    ready=[]
    for c in learning.candidates():
        if c['status']=='withdrawn' or row['id'] not in c.get('feedback_ids',c.get('training_ids',[])):
            continue
        state,binding,report=evaluation_state(c)
        ready.append({**c,'workflow_status':state,'test_binding':binding,'report':report})
    return {'batches':[],'candidates':ready,'implementation_requests':[u for u in requests() if u['status']!='withdrawn']}


def overview(rows=None):
    candidates=[c for c in learning.candidates() if c['status']!='withdrawn']; technical=[u for u in requests() if u['status']!='withdrawn']
    consumed={i for c in candidates+technical for i in c.get('feedback_ids',c.get('training_ids',[]))}
    grouped=defaultdict(list)
    for row in (evidence.annotated_records(evidence.records()) if rows is None else rows):
        if row['status']=='open' and row['id'] not in consumed and not clarifications.pending(row['id']) and row.get('snapshot'):
            grouped[(scope(row),row['type'])].append(row)
    batches=[]
    for (kind,typ),rows in grouped.items():
        sid=rows[0]['style_id']
        batches.append({'id':digest([kind,typ])[:16],'style_id':sid,'scope':kind,'title':typ.replace('_',' '),
                       'count':len(rows),'training_ids':[r['id'] for r in rows],
                       'status':'feedback_received'})
    ready=[]
    for c in candidates:
        state,binding,report=evaluation_state(c)
        ready.append({**c,'workflow_status':state,'test_binding':binding,'report':report,
                      'scope_label':('All styles — global rule' if c.get('rule_scope')=='global' else 'Style exception — global test caused regressions' if c.get('rule_scope')=='style' else 'Needs global-first analysis')})
    return {'batches':batches,'candidates':ready,'implementation_requests':technical}


def prepare(batch_id):
    batch=next((b for b in overview()['batches'] if b['id']==batch_id),None)
    if not batch:
        raise ValueError('This feedback group changed or is already being handled. Refresh the queue.')
    rows=[r for r in evidence.records() if r['id'] in batch['training_ids']]
    if batch['scope'] in ('unknown','preview'):
        return technical_request(batch['style_id'],rows,
            'Label-reading feedback needs technical diagnosis.' if batch['scope']=='labels' else 'Assignment provenance needs technical diagnosis.')
    # Reserve one independent source for testing; never train on every drawing.
    first=rows[0]
    source_cache={}
    def source(r):
        if r['snapshot'] in source_cache:
            return source_cache[r['snapshot']]
        saved=read(data_root()/'snapshots'/r['snapshot']/'09_review.json',{})
        sha=saved.get('metadata',{}).get('source_sha256')
        ex=read(data_root()/'snapshots'/r['snapshot']/'01_extract.json',{})
        source_cache[r['snapshot']]=sha or digest({k:v for k,v in ex.items() if k!='sheet'})
        return source_cache[r['snapshot']]
    primary=source(first)
    train=[r['id'] for r in rows if source(r)==primary and r['style_id']==batch['style_id']]
    result=learning.propose(batch['style_id'],train)
    if result.get('status')=='needs_clarification':return result
    result['feedback_ids']=batch['training_ids']
    folder='candidates' if 'profile' in result else 'implementation-requests'
    write(data_root()/folder/(result['id']+'.json'),result)
    return result


def attach_result(request_id, comparisons, validation_summary, rule_scope="global"):
    """Developer handoff back to the expert, with frozen results from the new engine."""
    if rule_scope not in ('global','style'):raise ValueError('Choose global or style scope')
    path=data_root()/'implementation-requests'/(ident(request_id)+'.json')
    item=read(path)
    if not item:
        raise ValueError('Unknown implementation request')
    if clarifications.pending_for_request(item):
        raise ValueError('Wait for the expert answer before attaching implementation results')
    if engine_version()==item['engine_version']:
        raise ValueError('No engine update detected; attach results after implementing and testing the change')
    if not isinstance(validation_summary,str) or len(validation_summary.strip())<10 or not comparisons:
        raise ValueError('Provide a validation summary and saved before/after comparisons')
    allowed={r['snapshot'] for r in evidence.records() if r['status']!='dismissed'}
    verified=[]
    for pair in comparisons:
        before_id=ident(pair['before']); after_id=ident(pair['after'])
        before=read(data_root()/'snapshots'/before_id/'09_review.json')
        after=read(data_root()/'snapshots'/after_id/'09_review.json')
        if before_id not in allowed or not before or not after or before_id==after_id:
            raise ValueError('Choose the original evidence and a new saved analysis')
        bm=before.get('metadata',{}); am=after.get('metadata',{})
        if not bm.get('source_sha256') or bm['source_sha256']!=am.get('source_sha256') or am.get('engine_version')!=engine_version():
            raise ValueError('Comparison must use the same source PDF and the current engine')
        if styles.canonical_id(bm.get('style_id','style-1'))!=styles.canonical_id(am.get('style_id','style-1')):
            raise ValueError('Comparison must preserve the drawing style')
        if item['scope'] in ('dimension','llm') and (bm.get('assignmentMethod')!=item['scope'] or am.get('assignmentMethod')!=item['scope']):
            raise ValueError('Comparison must use the original assignment method')
        verified.append({'before':before_id,'after':after_id,'sheet':before.get('sheet','Drawing')})
    scope_report=global_rules.assess_app_update(item,verified)
    if rule_scope=='style':
        proof=item.get('global_rejection',{})
        if not proof or proof.get('evidence_digest')!=scope_report['evidence_digest']:
            raise ValueError('A style exception needs a recorded global attempt with cross-style regressions on current evidence')
    else:
        target=[x for x in scope_report['cases'] if x['style_id']==item['style_id']]
        regressions=[x for x in scope_report['cases'] if x['style_id']!=item['style_id'] and x['outcome']=='regression']
        if target and all(x['after'] is True for x in target) and regressions:
            item['global_rejection']={'evidence_digest':scope_report['evidence_digest'],'engine':engine_version(),
                'cases':regressions,'comparisons':verified,'reason':'Global code change broke correct examples in other styles.'}
    scope_report['rule_scope']=rule_scope
    item.update(scope_report=scope_report,rule_scope=rule_scope,
                status='review_app_update' if scope_report['eligible'] else 'technical_review',comparisons=verified,validation_summary=validation_summary,
                result_engine=engine_version(),result_at=now())
    write(path,item)
    return item


def review_update(request_id, accepted, author):
    path=data_root()/'implementation-requests'/(ident(request_id)+'.json');item=read(path)
    if not item or item['status']!='review_app_update' or item.get('result_engine')!=engine_version():
        raise ValueError('Current implementation comparisons are required')
    if clarifications.pending_for_request(item):
        raise ValueError('Wait for the expert answer before accepting the update')
    if accepted and not global_rules.assess_app_update(item,item.get('comparisons',[]))['eligible']:
        raise ValueError('Global validation is incomplete or changed; add cross-style comparisons before accepting')
    if type(accepted) is not bool or not author.strip():
        raise ValueError('Provide an expert decision and reviewer name')
    item.update(status='verified' if accepted else 'requires_app_update',reviewed_by=author,reviewed_at=now())
    write(path,item)
    return item


def check_feedback(sheet, progress=None):
    """One expert action: propose and test, without publishing or choosing a method."""
    rows=evidence.records()
    ids={r['id'] for r in rows if not sheet or r.get('sheet')==sheet}
    state=overview(); outcomes=[]
    pending=[b for b in state['batches'] if ids.intersection(b['training_ids'])]
    candidates_to_test=[c for c in state['candidates'] if c['workflow_status']=='ready_to_test'
                        and ids.intersection(c.get('feedback_ids',c.get('training_ids',[])))]
    for index,batch in enumerate(pending):
        if progress: progress(f'Preparing correction {index+1} of {len(pending)}')
        try:
            result=prepare(batch['id'])
            if 'profile' in result:
                candidates_to_test.append(result)
            else:
                outcomes.append({'id':result['id'],'status':result['status']})
        except ValueError as exc:
            outcomes.append({'id':batch['id'],'status':'needs_attention','reason':str(exc)})
    for candidate in candidates_to_test:
        if progress: progress('Checking the proposed correction on saved drawings')
        status,binding,_=evaluation_state(candidate)
        if not binding:
            outcomes.append({'id':candidate['id'],'status':status});continue
        try:
            if candidate.get('style_id') and not global_rules.bases_current(candidate):
                replacement=learning.propose(candidate['style_id'],candidate['training_ids'])
                if replacement.get('status')=='needs_clarification':
                    candidate.update(status='withdrawn',replaced_by=replacement['id'])
                    write(data_root()/'candidates'/(candidate['id']+'.json'),candidate)
                    outcomes.append({'id':replacement['id'],'status':'needs_clarification'});continue
                replacement['feedback_ids']=candidate.get('feedback_ids',candidate['training_ids'])
                folder='candidates' if 'profile' in replacement else 'implementation-requests'
                write(data_root()/folder/(replacement['id']+'.json'),replacement)
                candidate.update(status='withdrawn',replaced_by=replacement['id'])
                write(data_root()/'candidates'/(candidate['id']+'.json'),candidate)
                if 'profile' not in replacement:
                    outcomes.append({'id':replacement['id'],'status':replacement['status']});continue
                candidate=replacement
                _,binding,_=evaluation_state(candidate)
            report=learning.evaluate(candidate['id'],binding,progress)
            if style_rules.restrict_after_global_regression(candidate['id']):
                if progress: progress('Global test caused regressions. Checking a style exception.')
                report=learning.evaluate(candidate['id'],binding,progress)
            outcomes.append({'id':candidate['id'],'evaluation':report['id'],'status':'comparison_ready'})
        except ValueError as exc:
            outcomes.append({'id':candidate['id'],'status':'needs_attention','reason':str(exc)})
    return {'sheet':sheet,'outcomes':outcomes,'published':False}
