"""Frozen, paired assignment experiments. Stored runs are audit records, never cache."""
from copy import deepcopy
from collections import Counter
import json
import os
from .storage import data_root, read, write, new_id, now, digest, engine_version, ident, drawing_lock
from . import evidence, styles
from vectorascore import final_bind
from vectorascore.assignment_payload import pack, serialize, FORMAT


def directory(eid):
    return data_root()/'experiments'/ident(eid)


def listings():
    return [read(p) for p in sorted((data_root()/'experiments').glob('*/manifest.json'))]


def prepare(snapshot_ids, title='Assignment request format comparison'):
    from .engine import reanalyze
    if not snapshot_ids or len(snapshot_ids)>20:
        raise ValueError('Choose between one and twenty saved analyses')
    if not title.strip():
        raise ValueError('Enter an experiment title')
    if len(set(snapshot_ids)) != len(snapshot_ids):
        raise ValueError('Choose each saved analysis once')
    eid=new_id('experiment'); documents=[]
    for sid in snapshot_ids:
        d=data_root()/'snapshots'/ident(sid)
        old=read(d/'09_review.json')
        if not old:
            raise ValueError('Unknown saved analysis')
        rows=evidence.evaluation_records([x for x in evidence.records() if x['snapshot']==sid and x['status']!='dismissed'])
        style_id=old.get('metadata',{}).get('style_id')
        if not style_id:
            captured_styles={x['style_id'] for x in rows}
            if len(captured_styles)!=1:
                raise ValueError('Legacy analysis needs an unambiguous captured drawing style')
            style_id=captured_styles.pop()
        profile=styles.get_style(style_id)
        rv,(_,a,l,r,_)=reanalyze(d,profile,binding='preview')
        qs=final_bind.questions(a,r,l); active=[q for q in qs if q['candidates']]
        chunks=[active[i:i+24] for i in range(0,len(active),24)]
        system=final_bind.SYSTEM+'\nSTYLE CONVENTIONS:\n'+serialize(profile.get('rules',[]))
        variants={
            'baseline': {'system':system,'requests':[json.dumps({'questions':c},ensure_ascii=False) for c in chunks]},
            'compact': {'system':system+'\n'+FORMAT,'requests':[serialize(pack(c)) for c in chunks]}}
        source=old.get('metadata',{}).get('source_sha256') or digest({k:v for k,v in read(d/'01_extract.json',{}).items() if k!='sheet'})
        documents.append({'snapshot':sid,'sheet':old['sheet'],'source':source,
            'profile':profile,'review':rv,'questions':qs,'variants':variants,'feedback':rows,
            'conflicts':evidence.assignment_conflicts(rows),
            'chars':{k:sum(len(v['system'])+len(s) for s in v['requests']) for k,v in variants.items()}})
    frozen={'documents':documents,'model':os.environ.get('OPENAI_MODEL','gpt-6-astra'),
            'reasoning_effort':os.environ.get('STUDIO_ASTRA_EFFORT','medium'),
            'max_output_tokens':12000,'schema':deepcopy(final_bind.SCHEMA),'engine_version':engine_version()}
    manifest={'id':eid,'title':title,'created_at':now(),'status':'prepared','kind':'request_format',
              'input_digest':digest(frozen),'engine_version':frozen['engine_version'],'model':frozen['model'],
              'documents':[{'snapshot':d['snapshot'],'sheet':d['sheet'],'chars':d['chars'],
                            'calls_per_variant':len(d['variants']['baseline']['requests'])} for d in documents],
              'quality':'Not measured','runs':[],'split':'Development — not an independent holdout'}
    write(directory(eid)/'inputs.json',frozen);write(directory(eid)/'manifest.json',manifest)
    return manifest


def run(eid, progress=None, ask=None):
    """Each invocation makes fresh calls for both variants; no saved answer reuse."""
    from .learning import check_record
    d=directory(eid); manifest=read(d/'manifest.json'); frozen=read(d/'inputs.json')
    if not manifest or not frozen or digest(frozen)!=manifest['input_digest']:
        raise ValueError('Frozen inputs are missing or have changed')
    if frozen['engine_version']!=engine_version():
        raise ValueError('Engine changed. Prepare a new experiment before running.')
    if ask is None:
        from openai import OpenAI
        client=OpenAI(timeout=180,max_retries=0)
        def ask(system, payload):
            response=client.responses.create(model=frozen['model'],service_tier='default',
                reasoning={'effort':frozen['reasoning_effort']},max_output_tokens=frozen['max_output_tokens'],
                input=[{'role':'system','content':system},{'role':'user','content':payload}],
                text={'format':{'type':'json_schema','name':'pipe_assignments','strict':True,'schema':frozen['schema']}})
            usage=final_bind.response_usage(response) if response.usage else None
            return {'status':response.status,'output_text':response.output_text,'usage':usage}
    with drawing_lock(d):
        manifest=read(d/'manifest.json')
        rid=new_id('trial'); root=d/rid; cases=[]; outcomes=[]; errors=[]; usage=[]
        write(root/'started.json',{'created_at':now(),'input_digest':manifest['input_digest']})
        for doc in frozen['documents']:
            results={}
            # Alternate first variant on successive trials to reduce order bias.
            order=['baseline','compact'] if len(manifest['runs'])%2==0 else ['compact','baseline']
            for variant in order:
                spec=doc['variants'][variant]; decisions=[]; failed=False
                for i,payload in enumerate(spec['requests']):
                    if progress:progress(f"{doc['sheet']} · {variant} · {i+1}/{len(spec['requests'])}")
                    call={'variant':variant,'snapshot':doc['snapshot'],'batch':i}
                    try:
                        response=ask(spec['system'],payload);call['response']=response
                        if response.get('usage'): usage.append(dict(response['usage'],variant=variant))
                        if response['status']!='completed':raise ValueError('Incomplete response')
                        ds=json.loads(response['output_text'])['decisions']
                        if not isinstance(ds,list):raise ValueError('Invalid decisions')
                        # Validate against this batch, not all questions in the drawing.
                        # Requests are frozen in the same 24-question order in both arms.
                        batch=[q for q in doc['questions'] if q['candidates']][i*24:(i+1)*24]
                        _,_,issues=final_bind.validate_decisions(batch,ds)
                        if issues:raise ValueError('Invalid or missing batch decisions')
                        decisions.extend(ds)
                    except Exception as exc:
                        failed=True;call['error']=type(exc).__name__;errors.append({**{k:call[k] for k in ('variant','snapshot','batch')},'error':type(exc).__name__})
                    write(root/(doc['snapshot']+'-'+variant+'-'+str(i)+'.json'),call)
                bindings,assignments,issues=final_bind.validate_decisions(doc['questions'],decisions)
                rv=deepcopy(doc['review']);rv['bindings']=bindings;rv['assignments']=assignments
                write(root/(doc['snapshot']+'-'+variant+'-review.json'),rv)
                results[variant]=None if failed or issues else rv
            for f in doc['feedback']:
                values={k:check_record(f,v) if v is not None and f['id'] not in doc['conflicts'] else None for k,v in results.items()}
                b,a=values['baseline'],values['compact']
                outcome='manual_or_incomplete' if b is None or a is None else 'regression' if b and not a else 'fixed' if not b and a else 'pass' if a else 'fail'
                cases.append({'feedback_id':f['id'],'snapshot':doc['snapshot'],'sheet':doc['sheet'],'track':f['track'],
                              'baseline':b,'compact':a,'outcome':outcome})
            if all(v is not None for v in results.values()):
                def owners(v):return {x['stretch']:(x['label'],x['designation_idx']) for x in v['assignments']}
                b,a=owners(results['baseline']),owners(results['compact'])
                outcomes.extend({'snapshot':doc['snapshot'],'stretch':sid,'baseline':b[sid],'compact':a[sid]} for sid in b if b[sid]!=a[sid])
        calls=sum(len(doc['variants']['baseline']['requests']) for doc in frozen['documents'])
        summary={v:final_bind.usage_summary([u for u in usage if u['variant']==v],calls) for v in ('baseline','compact')}
        report={'id':rid,'experiment':eid,'created_at':now(),'input_digest':manifest['input_digest'],'cases':cases,
                'counts':dict(Counter(c['outcome'] for c in cases)),'assignment_changes':outcomes,'usage':summary,'errors':errors,
                'status':'incomplete' if errors else 'completed','publication_eligible':False,
                'note':'Development comparison only. A changed decision is not automatically an improvement. No independent holdout or publication approval.'}
        write(root/'report.json',report)
        manifest['runs'].append(rid);manifest['status']=report['status'];manifest['quality']='See trial report'
        write(d/'manifest.json',manifest)
        return report
