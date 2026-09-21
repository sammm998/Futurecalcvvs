from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from types import SimpleNamespace
from studio import usage


def test_counts_proposal_and_parallel_evaluation_calls(monkeypatch):
    from vectorascore import final_bind
    monkeypatch.setattr(final_bind,'response_usage',lambda r:{'tokens_in':100,'tokens_out':20,'cached_tokens':10,'reasoning_tokens':0,'usd':.002})
    meter,token=usage.begin()
    response=SimpleNamespace(usage=True)
    usage.start_call();usage.record_response(response)
    context=copy_context()
    def run(_):usage.start_call();usage.record_response(response)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda n:context.copy().run(run,n),range(4)))
    result=usage.finish(meter,token)
    assert result['calls']==5 and result['tokens_total']==600
    assert result['usd']==.01 and result['usage_complete']
    # No leakage into the next task.
    meter,token=usage.begin();result=usage.finish(meter,token)
    assert result['calls']==0 and result['tokens_total']==0 and result['usd']==0


def test_failed_request_does_not_claim_zero_usage():
    meter,token=usage.begin();usage.start_call()
    result=usage.finish(meter,token)
    assert result['tokens_total'] is None and result['usd'] is None
    assert not result['usage_complete']


def test_partial_bill_is_identified(monkeypatch):
    from vectorascore import final_bind
    monkeypatch.setattr(final_bind,'response_usage',lambda r:{'tokens_in':10,'tokens_out':5,'cached_tokens':0,'reasoning_tokens':0,'usd':.001})
    meter,token=usage.begin();usage.start_call();usage.record_response(SimpleNamespace(usage=True));usage.start_call()
    result=usage.finish(meter,token)
    assert result['tokens_total']==15 and result['cost_status']=='partial'
    assert not result['usage_complete']
