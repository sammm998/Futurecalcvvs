"""Per-task usage, including proposals and before/after assignment calls."""
from contextvars import ContextVar
from threading import Lock

_current = ContextVar('studio_usage', default=None)


def begin():
    meter={'calls':0,'responses':[],'lock':Lock()}
    return meter,_current.set(meter)


def start_call():
    meter=_current.get()
    if meter is not None:
        with meter['lock']:meter['calls']+=1


def record_response(response):
    meter=_current.get()
    if meter is not None and getattr(response,'usage',None) is not None:
        from vectorascore.final_bind import response_usage
        item=response_usage(response)
        with meter['lock']:meter['responses'].append(item)


def finish(meter, token):
    _current.reset(token)
    from vectorascore.final_bind import usage_summary
    result=usage_summary(meter['responses'],meter['calls'])
    result['calls']=meter['calls']
    result['tokens_total']=result['tokens_in']+result['tokens_out']
    if meter['calls'] and not meter['responses']:
        result['tokens_total']=None
    return result
