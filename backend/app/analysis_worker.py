"""A PDF analysis can be terminated even while a single page is being read."""
from __future__ import annotations

import multiprocessing
import time
import traceback
from copy import deepcopy


def _cached_detector(output_dir, detect_page):
    """Reuse expensive extraction, but isolate each scale pass's graph edits."""
    import json
    from pathlib import Path
    detected = {}

    def detector(pdf, page, **options):
        key = (str(Path(pdf).resolve()), page)
        if key not in detected:
            target = Path(output_dir) / 'native-detection' / str(page)
            result = detect_page(pdf, page, artifact_dir=target, **options)
            target.mkdir(parents=True, exist_ok=True)
            (target / 'result.json').write_text(json.dumps(result, ensure_ascii=False))
            detected[key] = deepcopy(result)
        return deepcopy(detected[key])

    return detector


def _child(connection, args, kwargs, rule_values):
    try:
        label_audit = kwargs.pop('label_audit', False)
        from vvs_engine.cli import analyze_pdf
        from vvs_engine import rules
        if kwargs.pop('second_reader_enabled', False):
            from tools.readers import panel_transport
            kwargs['second_reader'] = panel_transport()
        if kwargs.get('source_mode') in ('model', 'compare', 'combined'):
            from .source_model import transport
            kwargs['source_ask'] = transport()
        if kwargs.pop('native_detection', False):
            from vvs_engine.source_rules.native_detection import detect_page
            kwargs['source_detector'] = _cached_detector(args[1], detect_page)
        kwargs['progress']=lambda *a:connection.send(('progress',a))
        kwargs['film_sink']=lambda *a:connection.send(('film',a))
        with rules.using(rule_values):
            result=analyze_pdf(*args,**kwargs)
        # Annotations were removed before inference; this report is never fed back.
        from .reference_audit import write_report
        write_report(args[0], args[1])
        if label_audit:
            import json
            from pathlib import Path
            try:
                from vvs_engine.label_detector import audit
                reports = audit(args[0], args[1], Path(__file__).resolve().parents[2]/'models/pipestudio-labels.onnx')
                audit_status = {'state':'COMPLETED','pages':len(reports),
                                'unmatched_proposals':sum(r['unmatched_proposals'] for r in reports)}
            except Exception as e:
                audit_status = {'state':'UNAVAILABLE','reason':str(e)}
            (Path(args[1])/'label-audit-status.json').write_text(json.dumps(audit_status))
            result['summary']['label_audit'] = audit_status
        connection.send(('result',result))
    except Exception as e:
        connection.send(('error',{'type':type(e).__name__,'message':str(e),
                                  'traceback':traceback.format_exc(),
                                  'pages':getattr(e,'classifications',[])}))
    finally:
        connection.close()


def analyze_isolated(*args, progress=None, film_sink=None, rule_values=None, **kwargs):
    from vvs_engine.cli import AnalysisTookTooLong
    from vvs_engine.pdf.extract import UnsupportedInputError
    budget=kwargs.get('deadline_s')
    deadline=time.monotonic()+budget if budget is not None else float('inf')
    context=multiprocessing.get_context('spawn')
    receive,send=context.Pipe(duplex=False)
    process=context.Process(target=_child,args=(send,args,kwargs,rule_values or {}),daemon=True)
    process.start();send.close()
    try:
        while True:
            left=deadline-time.monotonic()
            if left<=0:
                raise AnalysisTookTooLong(f'Analysen avbröts efter tidsgränsen {budget:g} sekunder. Ingen ofullständig mängd publiceras.')
            if receive.poll(min(.25,left)):
                try:
                    kind,payload=receive.recv()
                except EOFError:
                    raise RuntimeError(f'Analysprocessen avslutades utan resultat (kod {process.exitcode})') from None
                if kind=='result':
                    return payload
                if kind=='error':
                    if payload['type']=='UnsupportedInputError':
                        raise UnsupportedInputError(payload['message'],payload['pages'])
                    if payload['type']=='AnalysisTookTooLong':
                        raise AnalysisTookTooLong(payload['message'])
                    raise RuntimeError(payload['type']+': '+payload['message'])
                if kind=='progress' and progress:
                    progress(*payload)
                if kind=='film' and film_sink:
                    film_sink(*payload)
            elif not process.is_alive():
                raise RuntimeError(f'Analysprocessen avslutades utan resultat (kod {process.exitcode})')
    finally:
        receive.close()
        process.join(timeout=.2)
        if process.is_alive():
            process.terminate();process.join(timeout=2)
        if process.is_alive():
            process.kill();process.join(timeout=2)
        process.close()
