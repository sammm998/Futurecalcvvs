"""Score original and integrated engines against identical PDF annotations.

Never supplies annotations to inference. Native predictions contain only
original path ink intersecting assigned stretches; dash gaps are excluded.
"""
from collections import defaultdict
from copy import deepcopy
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'backend')]


def canonical(d):
    from vvs_engine.source_rules.swedish import designation_text
    return designation_text(d)


def score_native(pdf, native, bindings):
    import re
    import pymupdf
    from shapely.geometry import LineString, MultiLineString
    from app.reference_audit import compare
    from vvs_engine.source_rules.pipestudio.geom import flatten
    if hashlib.sha256(Path(pdf).read_bytes()).hexdigest() != native['source_pdf_sha256']:
        raise ValueError('Native input and reference PDF differ')
    labels = {l['id']:l for l in native['labels']}
    paths = {p['id']:p for p in native['extraction']['paths']}
    stretches = {s['id']:s for s in native['graph']['stretches']}
    predicted = defaultdict(list)
    for b in bindings:
        s = stretches[b['stretch']]
        if b['confidence'] == 'low' or s.get('in_wall') or s.get('entry'): continue
        d = labels[b['label']]['designations'][b['designation_idx']]
        if not d.get('dimension') or len(s['points']) < 2: continue
        route = LineString(s['points'])
        for pid in s.get('path_ids', []):
            ink = MultiLineString(list(flatten(paths[pid]['items'])))
            part = ink.intersection(route.buffer(.5, cap_style=2))
            if not part.is_empty: predicted[canonical(d)].append(part)
    reference = defaultdict(list)
    with pymupdf.open(pdf) as doc:
        page = doc[native['page']]
        for ann in page.annots():
            name = (ann.info.get('subject') or '').strip()
            if ann.type[1] not in ('Line','PolyLine') or not name or not re.fullmatch(r'\s*[\d\s.,]+\s*m\s*', ann.info.get('content') or ''): continue
            points = [tuple(pymupdf.Point(p)*page.rotation_matrix) for p in ann.vertices or []]
            if len(points) >= 2: reference[name].append(LineString(points))
    outside = {name:sum(g.length for g in parts) for name,parts in predicted.items() if name not in reference}
    return {'pdf_sha256': native['source_pdf_sha256'], 'page': native['page'],
            'scope': 'Exact designation, original confirmed ink only, 1 PDF point tolerance; dash gaps and wall/entry stretches excluded',
            'outside_reference_designations_pt': outside,
            'comparison': compare(reference, {n:p for n,p in predicted.items() if n in reference}, 1.)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('native'); p.add_argument('pdf'); p.add_argument('--out',required=True)
    p.add_argument('--model',action='store_true')
    args = p.parse_args()
    if args.model:
        from app.source_model import connection_settings
        key, model = connection_settings()
        if not key: raise RuntimeError('Model connection required')
        os.environ['OPENAI_API_KEY'] = key
        os.environ['OPENAI_MODEL'] = model
    from vvs_engine.source_rules.native_detection import load_runtime
    load_runtime()
    from vectorascore import flow_assign, final_bind
    native = json.loads(Path(args.native).read_text()); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    modes = [('dimension',lambda: flow_assign.assign(deepcopy(native['graph']),deepcopy(native['labels']),deepcopy(native['association'])))]
    if args.model:
        # Use the ORIGINAL request packing, candidate validation and transport.
        modes.append(('model',lambda:final_bind.bind(deepcopy(native['graph']),deepcopy(native['association']),deepcopy(native['labels']),native['style'])))
    for name,run in modes:
        result = run()
        (out/(name+'-assignments.json')).write_text(json.dumps(result,ensure_ascii=False))
        if result.get('errors') or result.get('issues'): raise RuntimeError('Native model did not complete')
        report = score_native(args.pdf,native,result['bindings'])
        (out/(name+'-comparison.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(name,json.dumps(report['comparison']['totals']),flush=True)


if __name__ == '__main__': main()
