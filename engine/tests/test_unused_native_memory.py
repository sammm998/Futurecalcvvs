from types import SimpleNamespace
from vvs_engine import memory


def test_linux_reclaims_unused_memory_without_changing_live_objects(monkeypatch):
    calls = []
    live = [b'keep this analysis']
    monkeypatch.setattr(memory.sys, 'platform', 'linux')
    monkeypatch.setattr(memory.gc, 'collect', lambda: calls.append('gc'))
    def trim(pad):
        calls.append(pad)
    monkeypatch.setattr(memory.ctypes, 'CDLL', lambda _: SimpleNamespace(malloc_trim=trim))
    memory.release_unused_memory()
    assert calls == ['gc', 0]
    assert live == [b'keep this analysis']


def test_optional_allocator_hook_is_not_required(monkeypatch):
    monkeypatch.setattr(memory.sys, 'platform', 'linux')
    monkeypatch.setattr(memory.ctypes, 'CDLL', lambda _: SimpleNamespace())
    memory.release_unused_memory()
    monkeypatch.setattr(memory.sys, 'platform', 'darwin')
    monkeypatch.setattr(memory.ctypes, 'CDLL', lambda _: (_ for _ in ()).throw(AssertionError()))
    memory.release_unused_memory()
