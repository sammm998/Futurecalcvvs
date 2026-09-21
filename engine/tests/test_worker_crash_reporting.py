"""A worker may close its pipe before the parent can observe its exit status."""
import multiprocessing
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app import analysis_worker


def _exit_without_result(connection):
    connection.close()
    os._exit(7)


def test_pipe_eof_is_followed_by_reaping_before_reporting(monkeypatch):
    monkeypatch.setattr(analysis_worker, '_oom_kills', lambda: None)
    ctx = multiprocessing.get_context('spawn')
    receive, send = ctx.Pipe(duplex=False)
    child = ctx.Process(target=_exit_without_result, args=(send,))
    child.start()
    send.close()
    try:
        assert receive.poll(10)
        try:
            receive.recv()
        except EOFError:
            error = analysis_worker._worker_failure(child, None, 'NATIVE_DETECTION')
        else:
            raise AssertionError('Expected pipe closure without result')
        assert 'kod 7' in str(error)
        assert 'NATIVE_DETECTION' in str(error)
        assert 'None' not in str(error)
    finally:
        receive.close()
        child.join(2)
        if child.is_alive():
            child.kill(); child.join()
        child.close()


class KilledProcess:
    exitcode = -signal.SIGKILL
    def join(self, timeout):
        pass


def test_sigkill_does_not_claim_proven_memory_exhaustion(monkeypatch):
    monkeypatch.setattr(analysis_worker, '_oom_kills', lambda: 4)
    message = str(analysis_worker._worker_failure(KilledProcess(), 4, None))
    assert 'SIGKILL' in message and 'möjlig' in message
    assert '(OOM)' not in message


def test_increased_oom_counter_reports_container_memory_stop(monkeypatch):
    monkeypatch.setattr(analysis_worker, '_oom_kills', lambda: 5)
    message = str(analysis_worker._worker_failure(KilledProcess(), 4, 'EXTRACT'))
    assert '(OOM)' in message
    assert 'EXTRACT' in message
