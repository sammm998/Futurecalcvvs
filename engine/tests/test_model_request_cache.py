from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
import pytest
from app.model_request_cache import ModelRequestCache
from app.source_model import AssignmentTransport


def test_concurrent_identical_requests_are_paid_only_once():
    cache = ModelRequestCache()
    entered, release = threading.Event(), threading.Event()
    calls = []
    def produce():
        calls.append(1); entered.set(); release.wait(2)
        return 'validated response'
    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(cache.run, {'model':'same','image':'all pixels'}, produce)
        assert entered.wait(2)
        b = pool.submit(cache.run, {'image':'all pixels','model':'same'}, produce)
        release.set()
        assert a.result() == ('validated response', False)
        assert b.result() == ('validated response', True)
    assert len(calls) == 1
    assert cache.run({'model':'different','image':'all pixels'}, produce)[1] is False
    assert cache.run({'model':'same','image':'changed pixel'}, produce)[1] is False


def test_failures_are_not_cached():
    cache = ModelRequestCache()
    def failed(): raise ValueError('failed')
    with pytest.raises(ValueError): cache.run({'input':'same'}, failed)
    assert cache.run({'input':'same'},lambda:'valid') == ('valid',False)


def test_transport_reuses_same_request_but_tracks_zero_new_tokens():
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status='completed',output_text='{"decisions":[]}',model='test',id='one',
            usage=SimpleNamespace(input_tokens=100,output_tokens=20,input_tokens_details=SimpleNamespace(cached_tokens=50)))
    t=AssignmentTransport(SimpleNamespace(responses=SimpleNamespace(create=create)),'test')
    other=t.for_style({'rules':[]})
    assert t([])==other([])==[]
    assert len(calls)==1
    assert t.usage[0]['cached_tokens']==50
    assert other.usage[0]['request_reused'] is True
    assert other.usage[0]['tokens_in']==other.usage[0]['tokens_out']==0
    # A new analysis does not inherit earlier decisions.
    AssignmentTransport(t.client,'test')([])
    assert len(calls)==2
