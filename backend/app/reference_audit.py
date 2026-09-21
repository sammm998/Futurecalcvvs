"""Post-analysis comparison with PDF annotations, never imported by inference.

Matching totals cannot show whether the right pipes were measured. This audit
compares locations AND exact designations, in displayed PDF points. It describes
agreement with the supplied annotations, not independently certified accuracy.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
from pathlib import Path

import pymupdf
from shapely.geometry import GeometryCollection, LineString
from shapely.ops import unary_union


def compare(reference, predicted, tolerance=1.0):
    """Two directed length overlaps; duplicate prediction length stays explicit."""
    if tolerance <= 0:
        raise ValueError('Tolerance must be positive')
    rows = []
    for name in sorted(set(reference) | set(predicted)):
        ref_lines, pred_lines = reference.get(name, []), predicted.get(name, [])
        ref = unary_union(ref_lines) if ref_lines else GeometryCollection()
        pred = unary_union(pred_lines) if pred_lines else GeometryCollection()
        recovered = ref.intersection(pred.buffer(tolerance)).length if pred_lines else 0.0
        supported = pred.intersection(ref.buffer(tolerance)).length if ref_lines else 0.0
        rows.append({'designation': name, 'reference_pt': ref.length, 'predicted_pt': pred.length,
                     'reference_recovered_pt': recovered, 'prediction_supported_pt': supported,
                     'missed_pt': max(0., ref.length-recovered),
                     'unsupported_pt': max(0., pred.length-supported),
                     'duplicate_prediction_pt': max(0., sum(g.length for g in pred_lines)-pred.length)})
    totals = {k: sum(r[k] for r in rows) for k in ('reference_pt', 'predicted_pt', 'reference_recovered_pt',
              'prediction_supported_pt', 'missed_pt', 'unsupported_pt', 'duplicate_prediction_pt')}
    totals['reference_coverage'] = totals['reference_recovered_pt']/totals['reference_pt'] if totals['reference_pt'] else None
    totals['prediction_support'] = totals['prediction_supported_pt']/totals['predicted_pt'] if totals['predicted_pt'] else None
    return {'tolerance_pt': tolerance, 'totals': totals, 'rows': rows}


def audit(pdf: Path, result_dir: Path, tolerances=(0.5, 1., 2.)):
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    manifest = json.loads((result_dir/'freeze-manifest.json').read_text())
    if digest != manifest['input_pdf_sha256']:
        raise ValueError('The annotated PDF does not match the frozen analysis input')
    pages = []
    with pymupdf.open(pdf) as doc:
        for page in doc:
            ref, pred = defaultdict(list), defaultdict(list)
            accepted, ignored = 0, 0
            for ann in page.annots():
                name = (ann.info.get('subject') or '').strip()
                # Counts, areas, freehand review and clouds are not pipe lengths.
                length_text = re.fullmatch(r'\s*[\d\s.,]+\s*m\s*', ann.info.get('content') or '')
                if ann.type[1] not in ('Line', 'PolyLine') or not name or not length_text:
                    ignored += 1
                    continue
                points = [tuple(pymupdf.Point(p)*page.rotation_matrix) for p in ann.vertices or []]
                if len(points) < 2:
                    ignored += 1
                    continue
                ref[name].append(LineString(points)); accepted += 1
            sheet = result_dir/'sheets'/str(page.number)
            if not ref:
                pages.append({'page': page.number, 'state': 'NO_LENGTH_REFERENCES',
                              'reference_annotations': 0, 'other_annotations': ignored})
                continue
            if not sheet.exists():
                if (result_dir/'sheets').exists():
                    pages.append({'page':page.number,'state':'NOT_ANALYSED','reference_annotations':accepted})
                    continue
                sheet = result_dir
            pipe_file = sheet/'physical-pipes.json'
            if not pipe_file.exists():
                pages.append({'page':page.number,'state':'NO_ARTIFACT','reference_annotations':accepted})
                continue
            pipes = json.loads(pipe_file.read_text())['physical_pipes']
            names = {p['identity']:p['designation'] for p in pipes if p['page'] == page.number}
            for g in json.loads((sheet/'pipe-geometry-inventory.json').read_text())['primitives']:
                if g['state'] != 'CONFIRMED' or g.get('in_hatch'):
                    continue
                name = names.get(g.get('identity'))
                if name:
                    pred[name].append(LineString([(g['x0'],g['y0']),(g['x1'],g['y1'])]))
            outside = {name:sum(g.length for g in ls) for name,ls in pred.items() if name not in ref}
            # A partial annotation set cannot prove that other systems are wrong.
            in_scope = {name:ls for name,ls in pred.items() if name in ref}
            pages.append({'page':page.number,'state':'SCORED' if ref else 'NO_LENGTH_REFERENCES',
                          'reference_annotations':accepted,'other_annotations':ignored,
                          'outside_reference_designations_pt':outside,
                          'comparisons':[compare(ref,in_scope,t) for t in tolerances] if ref else []})
    return {'schema_version':1,'pdf':str(pdf),'pdf_sha256':digest,
            'scope':'Drawn confirmed centreline segments outside hatching, exact annotation subject. '
                    'Dash gaps and vertical metres are excluded. Tolerance is in PDF points. '
                    'Other designations are unscored. No training or inference uses this report.',
            'pages':pages}


def write_report(pdf, result_dir):
    """Run after the frozen engine artifacts exist; failure cannot change quantities."""
    result_dir = Path(result_dir)
    try:
        report = audit(Path(pdf), result_dir, tolerances=(1.,))
        report['state'] = 'COMPLETED'
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Reference annotation comparison failed')
        report = {'schema_version': 1, 'state': 'UNAVAILABLE', 'pages': []}
    target = result_dir/'reference-comparison.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)
    return report
