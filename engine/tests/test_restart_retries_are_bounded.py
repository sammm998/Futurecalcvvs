from types import SimpleNamespace


def test_crashing_job_stops_but_waiting_job_does_not_spend_a_retry(monkeypatch):
    from app import jobs
    rows = [SimpleNamespace(id='crash', status='RUNNING', stage='REVIEWING',
                            summary={'resubmitted_after_restart': 2}, error=None),
            SimpleNamespace(id='waiting', status='QUEUED', stage='QUEUED',
                            summary={'resubmitted_after_restart': 2}, error=None)]
    class DB:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def query(self, *args): return self
        def filter(self, *args): return self
        def all(self): return rows
        def commit(self): pass
    submitted, settled = [], []
    monkeypatch.setattr(jobs, 'SessionLocal', DB)
    monkeypatch.setattr(jobs, 'submit', submitted.append)
    monkeypatch.setattr(jobs, '_settle_credits', settled.append)
    assert jobs.resubmit_unfinished() == 1
    assert submitted == ['waiting'] and settled == ['crash']
    assert rows[0].status == 'FAILED' and rows[0].finished_at
    assert 'omstarter' in rows[0].error
    assert rows[1].summary['resubmitted_after_restart'] == 2
