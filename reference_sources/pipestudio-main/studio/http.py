"""Studio HTTP actions, used by the existing review server."""
from pathlib import Path
from .storage import ROOT, data_root, read, write, ident, digest, now, new_id
from . import styles, evidence, learning, tasks, experiments, improvements, workflow


def dispatch(method, path, q, body, role, debug_root=None):
    if not path.startswith('/api/studio/'):
        return None
    debug=Path(debug_root or ROOT/'debug')
    action=path.removeprefix('/api/studio/')
    if role not in ('admin', 'review'):
        return {'error':'No access'},403
    if method=='GET':
        if action=='suggest-style-name':
            from .style_creation import suggested_name
            return suggested_name(debug,q['sheet']),200
        if action=='overview':
            records=evidence.records()
            annotated=evidence.annotated_records(records)
            flow=improvements.overview(annotated)
            return {'styles':styles.list_styles(),'parameters':styles.PARAMETERS,
                'feedback':annotated,'legacy':evidence.legacy_records(),'candidates':learning.candidates(),
                'vector_previews':[read(p) for p in sorted((data_root()/'vector-previews').glob('*.json'))],
                'experiments':experiments.listings(),
                'tasks':sorted([read(p) for p in (data_root()/'tasks').glob('*.json')],key=lambda t:t.get('created_at',''))[-20:],
                'counts':{'captured':len(records),'confirmed':sum(r['type']=='correct' for r in records),
                          'open':sum(r['status']=='open' for r in records),'ocr':sum(r['track']=='ocr' for r in records)},
                'improvements':flow, 'conversations':workflow.conversations(annotated,flow), 'applications':[read(p) for p in (data_root()/'applications').glob('*.json')],
                'quality':'Not measured — absence of feedback is not confirmation'},200
        if action=='reply':
            return workflow.reply(q['id'],evidence.annotated_records(evidence.records())),200
        if action=='implementation-brief':
            return improvements.brief(q['id']),200
        if action=='analysis-status':
            if q.get('style_id')=='auto':
                # "auto" means the style the saved analysis was detected with
                from .engine import resolve_style
                q=dict(q,style_id=resolve_style(debug/ident(q['sheet']),'auto',draft=True,detect=False)[0]['id'])
            from .freshness import assignment_status
            return assignment_status(debug/ident(q['sheet']),q.get('style_id')),200
        if action=='experiment-report':
            report=read(experiments.directory(q['id'])/ident(q['trial'])/'report.json')
            return (report,200) if report else ({'error':'Not found'},404)
        if action=='experiment-result':
            if q.get('variant') not in ('baseline','compact'):
                raise ValueError('Unknown experiment variant')
            result=read(experiments.directory(q['id'])/ident(q['trial'])/(ident(q['snapshot'])+'-'+q['variant']+'-review.json'))
            return (result,200) if result else ({'error':'Not found'},404)
        if action=='queue':
            rv=read(debug/ident(q['sheet'])/'09_review.json')
            return evidence.review_queue(rv) if rv else [],200
        if action=='task':
            return tasks.get(q['id']),200
        if action=='evaluation':
            result=read(data_root()/'evaluations'/ident(q['id'])/'report.json')
            return (result,200) if result else ({'error':'Not found'},404)
        if action=='snapshot':
            result=read(data_root()/'snapshots'/ident(q['id'])/'09_review.json')
            return (result,200) if result else ({'error':'Not found'},404)
        if action=='evaluation-result':
            if q.get('side') not in ('before','after'):
                raise ValueError('Choose before or after')
            result=read(data_root()/'evaluations'/ident(q['id'])/(ident(q['snapshot'])+'-'+q['side']+'.json'))
            return (result,200) if result else ({'error':'Not found'},404)
        if action=='label-report':
            from . import label_report
            # exactly the rows the App updates page lists (a saved conversation may have closed one)
            annotated=evidence.annotated_records(evidence.records())
            boxes=workflow.conversations(annotated,improvements.overview(annotated))
            rows=[r for r in annotated if boxes[r['id']]['inbox']=='labels']
            return {'filename':'label-recognition-feedback.md','count':len(rows),'markdown':label_report.markdown(rows)},200
        if action=='ocr-export':
            return {'schema_version':1,'purpose':'OCR evaluation and supervised training; never automatic text overrides',
                'examples':[r for r in evidence.records() if r['track']=='ocr' and r['status']!='dismissed']},200
    elif method=='POST':
        if action=='delete-style':
            return styles.delete_style(body['style_id'],body.get('author','Reviewer')),200
        if action=='retry-application':
            return tasks.submit('accept-improvement',lambda progress:workflow.apply_improvement(body['id'],body.get('author',''),debug,progress,retry_failed=True)),202
        if action=='accept-improvement':
            return tasks.submit('accept-improvement',lambda progress:workflow.apply_improvement(body['id'],body.get('author',''),debug,progress)),202
        if action=='feedback-answer':
            from . import clarifications
            question=clarifications.pending(body['id'])
            kind='feedback-answer' if question and question.get('origin')=='app_updates' else 'check-feedback'
            return tasks.submit(kind,lambda progress:clarifications.answer_and_analyze(body['id'],body['question_id'],body['message'],body.get('author',''),progress),context={'feedback_id':body['id']}),202
        if action=='feedback-discuss':
            return tasks.submit('feedback-discuss',lambda progress:workflow.discuss(body['id'],body['message'],body.get('author','')),context={'feedback_id':body['id']}),202
        if action=='feedback-retry':
            return workflow.retry(body['id']),200
        if action=='style-from-drawing':
            from .style_creation import create
            ident(body['sheet'])
            return tasks.submit('style-from-drawing',lambda progress:create(debug,dict(body),progress),
                                context={'sheet':body['sheet']}),202
        if action=='save-style-preview':
            from .style_preview import save
            return save(debug,body),201
        if action=='check-feedback':
            from .storage import transaction
            sheet=body.get('sheet')
            if sheet is not None:
                ident(sheet)
            with transaction():
                for path in (data_root()/'tasks').glob('*.json'):
                    existing=read(path,{})
                    if existing.get('kind')=='check-feedback' and existing.get('status') in ('running','queued'):
                        return existing,202
                return tasks.submit('check-feedback',lambda progress:improvements.check_feedback(sheet,progress),
                                    context={'feedback_sheet':sheet}),202
        if action=='implementation-questions':
            return improvements.ask_expert(body['id'],body['feedback_id'],body.get('questions'),body.get('reason','')),200
        if action=='implementation-result':
            return improvements.attach_result(body['id'],body.get('comparisons',[]),body.get('validation_summary',''),body.get('rule_scope','global')),200
        if action=='review-implementation':
            return improvements.review_update(body['id'],body.get('accepted'),body.get('author','')),200
        if action=='prepare-improvement':
            return tasks.submit('prepare-improvement',lambda progress:improvements.prepare(body['id'])),202
        if action=='select-assignment':
            from .assignment_results import select
            from .storage import drawing_lock
            from .engine import resolve_style
            directory=debug/ident(body['sheet'])
            style,_=resolve_style(directory,body.get('style_id','style-1'),draft=True,detect=False)
            with drawing_lock(directory):
                return select(directory,body.get('binding'),style),200
        if action=='experiment-prepare':
            return tasks.submit('experiment-prepare',lambda progress:experiments.prepare(body.get('snapshots',[]),body.get('title','Request format comparison'))),202
        if action=='experiment-run':
            if body.get('paid_run_acknowledged') is not True:
                raise ValueError('Acknowledge sending frozen drawing context to Astra and API charges')
            return tasks.submit('experiment-run',lambda progress:experiments.run(body['id'],progress)),202
        if action=='feedback':
            return evidence.add(debug/ident(body['sheet']),body['record'],body.get('run_id')),201
        if action=='feedback/status':
            return evidence.update(body['id'],body['status'],body.get('author','')),200
        if action=='style':
            return styles.save_draft(ident(body['style_id']),body),200
        if action=='calibrate':
            ps=[read(debug/ident(s)/'02_profile.json') for s in body.get('sheets',[])]
            if not ps or any(p is None for p in ps):
                raise ValueError('Choose processed drawings')
            return styles.calibrate_style(body['style_id'],ps),200
        if action=='candidate':
            return learning.create(body['style_id'],body['title'],body.get('training_ids',[])),201
        if action=='propose':
            return tasks.submit('propose',lambda progress:learning.propose(body['style_id'],body.get('training_ids',[]))),202
        if action=='evaluate':
            return tasks.submit('evaluate',lambda progress:learning.evaluate(body['id'],body.get('binding','preview'),progress)),202
        if action=='accept-comparison':
            return tasks.submit('accept-comparison',lambda progress:workflow.accept_comparison(body['evaluation'],body['feedback_id'],body.get('author',''),debug,progress),context={'feedback_id':body['feedback_id']}),202
        if action=='reject-comparison':
            return workflow.reject_comparison(body['evaluation'],body['feedback_id'],body.get('author','')),200
        if action=='review-case':
            return learning.review_case(body['evaluation'],body['feedback_id'],body['before'],body['after'],body.get('author','')),200
        if action=='publish':
            return learning.publish(body['id'],body.get('author','')),200
        if action=='activate':
            return styles.activate(body['style_id'],body['version']),200
        if action=='replay':
            from .engine import reanalyze, resolve_style
            directory=debug/ident(body['sheet'])
            # "auto": detect the style from the stored drawing (an unknown style runs as style-1, flagged)
            style,style_match=resolve_style(directory,body.get('style_id','style-1'),draft=bool(body.get('draft')))
            style['profile_state']='draft' if body.get('draft') else 'published'
            binding=body.get('binding','preview')
            if binding not in ('preview','flow','astra'):
                raise ValueError('Unknown binding mode')
            def locked_work(progress):
                from . import evidence
                from .storage import transaction
                with transaction():
                    evidence.snapshot(directory)
                progress({'preview':'Running shared vector engine','flow':'Running vectors and the flow-direction assignment'}.get(binding,'Running vectors and final Astra assignments'))
                from . import assignment_results
                assignment_results.save(directory)
                result_key=assignment_results.fingerprint(directory,style)
                rv,stages=reanalyze(directory,style,binding,match=style_match)
                B,A,L,R,llm=stages
                for name,data in [('04_bucket',B),('05_assemble',A),('06_labels',L),('07_associate',R),('08_llm',llm),('09_review',rv)]:
                    write(directory/(name+'.json'),data)
                assignment_results.save(directory,result_key)
                return {'sheet':body['sheet'],'run_id':rv['metadata']['run_id'],'model_errors':(llm or {}).get('errors',[]), 'usage': {k:v for k,v in (llm or {}).items() if k in ('seconds','tokens_in','tokens_out','cached_tokens','usd','cost_status','usage_complete')}}
            def work(progress):
                from .storage import drawing_lock
                with drawing_lock(directory):
                    return locked_work(progress)
            return tasks.submit('replay',work,context={'sheet':body['sheet']}),202
    return {'error':'Unknown Studio endpoint'},404
