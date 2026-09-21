"""Offline model double for API lifecycle tests; not an accuracy benchmark."""
from contextlib import contextmanager
import pytest

@contextmanager
def offline_source_service():
    # Offline provider double: API lifecycle tests never call a paid model.
    from app import source_model, analysis_worker
    from vvs_engine.cli import analyze_pdf
    def offline_model(qs):
        out=[]
        for q in qs:
            candidates=q['candidates']
            preferred=[c for c in candidates if any(e['kind']=='rule_proposal' for e in c['evidence'])]
            c=(preferred or candidates)[0]
            out.append(dict(stretch=q['stretch'],label=c['label'],designation_idx=c['designation_idx'],ambiguous=False))
        return out
    def offline_analysis(*args, **kwargs):
        kwargs.pop('rule_values',None);kwargs.pop('label_audit',None);kwargs.pop('second_reader_enabled',None)
        kwargs.pop('native_detection',None)  # Real detector has separate integration/geometry tests.
        kwargs['source_ask']=offline_model
        result = analyze_pdf(*args, **kwargs)
        from app.reference_audit import write_report
        write_report(args[0], args[1])
        return result
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(source_model, 'configured', lambda: True)
        mp.setattr(analysis_worker, 'analyze_isolated', offline_analysis)
        yield
