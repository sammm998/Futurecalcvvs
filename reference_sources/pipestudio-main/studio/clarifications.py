"""Expert questions pause rule synthesis; answers become evidence, never rules."""
from .storage import data_root, read, write, ident, new_id, now, transaction


def pending(fid):
    question=read(data_root()/'conversations'/(ident(fid)+'.json'),{}).get('clarification')
    return question if question and question['status']=='awaiting_answer' else None


def request(rows, questions, reason='', *, origin='improvements', implementation_id=None):
    if origin not in ('improvements','app_updates'):
        raise ValueError('Unknown clarification origin')
    if origin=='app_updates' and not implementation_id:
        raise ValueError('An app update question needs an implementation request')
    if not isinstance(questions,list) or not 1<=len(questions)<=3:
        raise ValueError('Clarification needs one to three short questions')
    for q in questions:
        if not isinstance(q,dict) or any(not isinstance(q.get(k),str) or not 5<=len(q[k].strip())<=1000 for k in ('question','impact')):
            raise ValueError('Each question needs plain-language wording and an explanation of its consequences')
        options=q.get('options',[])
        if not isinstance(options,list) or len(options)>3 or any(not isinstance(o,str) or not 1<=len(o.strip())<=250 for o in options):
            raise ValueError('Use up to three short answer options')
    # The question belongs to the actual training example, not a drawing-specific rule.
    row=rows[0];fid=row['id']
    with transaction():
        from . import evidence
        current=next((r for r in evidence.records() if r['id']==fid),None)
        if not current or current['status']!='open':raise ValueError('Choose open feedback')
        item=None
        if origin=='app_updates':
            item_path=data_root()/'implementation-requests'/(ident(implementation_id)+'.json')
            item=read(item_path)
            if not item or item['status'] in ('verified','withdrawn'):
                raise ValueError('Choose an open implementation request')
            if fid not in item.get('feedback_ids',item.get('training_ids',[])):
                raise ValueError('Feedback does not belong to this implementation request')
        path=data_root()/'conversations'/(ident(fid)+'.json')
        thread=read(path,{'messages':[]})
        old=thread.get('clarification')
        if old and old['status']=='awaiting_answer':
            if old.get('origin','improvements')!=origin or old.get('implementation_id')!=implementation_id:
                raise ValueError('Answer the existing question before starting a different clarification')
            return old
        q={'id':new_id('question'),'status':'awaiting_answer','feedback_id':fid,
           'origin':origin,'implementation_id':implementation_id,'questions':questions,'reason':str(reason)[:2000],'at':now()}
        thread['clarification']=q
        text='\n\n'.join(item['question'].strip()+'\n'+item['impact'].strip() for item in q['questions'])
        thread['messages'].append({'role':'app','origin':origin,'kind':'clarification','question_id':q['id'],'text':text,'choices':questions[0].get('options',[]) if len(questions)==1 else [],'at':now()})
        write(path,thread)
        if item is not None:
            item.update(status='needs_expert_answer',question_at=now())
            write(item_path,item)
    return q


def answer_and_analyze(fid, question_id, message, author, progress=None):
    from . import evidence, workflow, improvements
    if not isinstance(message,str) or not 1<=len(message.strip())<=4000 or not isinstance(author,str) or not author.strip():
        raise ValueError('Enter your answer and reviewer name')
    with transaction():
        row=next((r for r in evidence.records() if r['id']==ident(fid)),None)
        if not row or row['status']!='open':raise ValueError('This feedback is closed')
        path=data_root()/'conversations'/(fid+'.json');thread=read(path,{'messages':[]})
        q=thread.get('clarification')
        if not q or q['status']!='awaiting_answer' or q['id']!=question_id:
            raise ValueError('This question changed or was already answered. Refresh the conversation.')
        app_update=q.get('origin')=='app_updates'
        if app_update:
            item_path=data_root()/'implementation-requests'/(ident(q['implementation_id'])+'.json')
            item=read(item_path)
            if not item or item['status'] in ('verified','withdrawn'):
                raise ValueError('This implementation request is closed')
        thread['messages'].append({'role':'expert','text':message.strip(),'author':author.strip(),'at':now(),'reply_to':question_id})
        q.update(status='answered',answered_at=now())
        if app_update:
            thread['messages'].append({'role':'system','text':'Your answer is saved for the AI rebuilding the app. The update stays here until it is ready for you to check.','at':now()})
        write(path,thread)
        if app_update:
            item.update(status='needs_expert_answer' if pending_for_request(item) else 'answer_received',answer_at=now())
            write(item_path,item)
    if app_update:
        return {'id':q['implementation_id'],'status':item['status'],'answer_saved':True,'published':False}
    workflow.retry(fid)
    # Saving precedes synthesis: a failed model request cannot lose the answer.
    return improvements.check_feedback(row['sheet'],progress)


def pending_for_request(item):
    return [q for fid in item.get('feedback_ids',item.get('training_ids',[]))
            if (q:=pending(fid)) and q.get('origin')=='app_updates' and q.get('implementation_id')==item['id']]
