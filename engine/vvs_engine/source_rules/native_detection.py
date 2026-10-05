"""Run PipeStudio's original detection stages on annotation-free drawing ink.

Original source modules stay byte-identical. No expert boxes, feedback or
reference quantities are inputs. The caller owns assignment and measurement.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'reference_sources' / 'pipestudio-main'


def _pdf_digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_runtime():
    source = str(SOURCE)
    if source not in sys.path:
        sys.path.insert(0, source)
    os.environ.setdefault('AI_MODEL_PATH', str(ROOT / 'models/pipestudio-labels.onnx'))
    # Two OCR processes unless the operator says otherwise (PIPE_OCR_WORKERS). The core count is not a safe guide:
    # a container sees every core of its host but not its own memory limit, and eight tesseract processes at once
    # took a Railway service past that limit - it was restarted mid-analysis and every page answered 502.
    os.environ.setdefault('PIPE_OCR_WORKERS', '2')
    os.environ.setdefault('OMP_THREAD_LIMIT', '1')
    os.environ.setdefault('PIPE_STUDIO_DATA', str(ROOT / '.local/native-studio'))
    import pytesseract
    local = ROOT / '.local/tesseract/bin/tesseract'
    if local.exists():
        pytesseract.pytesseract.tesseract_cmd = str(local)
    from vectorascore import extract, profile, detect, labels, style
    from studio.engine import vector_stages
    return extract, profile, detect, labels, style, vector_stages


MIN_LANDINGS = 10        # leader landings on a pen before the sheet's own word can outvote the chosen pipe pen
LANDING_MARGIN = 5       # ...that many times the landings on the chosen pen
LENGTH_MARGIN = 3        # ...and that many times its landed-on length (PipeStudio's own flip rule, bucket.calibrate)


def landed_policy(ex, B):
    """The pens this sheet's own leaders point at, when they contradict the pipe pen the calibration chose.

    The calibration may take a known style's starting values for the pipe pen. A sheet from another office that
    happens to measure like that style then reads its grey building outline as pipes and its real pipes as nothing
    (V-50-1-666340-0113: the 'Arildsson' starting value 0.72 pt, while 32 of the sheet's leaders land on its 1.44 pt
    black pen and 3 on 0.72). Where the leaders say otherwise by PipeStudio's own margin, the pen they land on is
    the pipe pen, their own pen is the leader pen, grey ink is the building, and the other black pens keep their
    ordinary reading. Returned as a stroke policy for PipeStudio's style mechanism; None when nothing contradicts.
    """
    from studio.style_vision import inventory
    C = B.get('calibration') or {}
    land = C.get('landings') or {}
    votes = land.get('votes') or {}
    chosen = {round(float(w), 2) for w in C.get('pipe_widths') or []}
    def width(key):
        return round(float(key.split('|')[0]), 2)
    black = {k: v for k, v in votes.items() if k.endswith('|black')}
    if not black:
        return None
    best_key = max(black, key=lambda k: (black[k]['landings'], black[k]['length']))
    best = black[best_key]
    if width(best_key) in chosen:
        return None
    on_chosen = sum(v['landings'] for k, v in black.items() if width(k) in chosen)
    length_chosen = sum(v['length'] for k, v in black.items() if width(k) in chosen)
    if not (best['landings'] >= MIN_LANDINGS and best['landings'] >= LANDING_MARGIN * max(on_chosen, 1)
            and best['length'] >= LENGTH_MARGIN * max(length_chosen, 1.0)):
        return None
    leaders = land.get('leader_families') or {}
    leader_w = width(max(leaders, key=leaders.get)) if leaders else None
    unit = C.get('u_paper') or 1.0
    pipe_w = width(best_key) / unit
    families = []
    for f in inventory(ex, unit):
        k = f['key']
        grey = bool(k['color']) and max(k['color']) - min(k['color']) < .05 and min(k['color']) > .2
        coloured = bool(k['color']) and max(k['color']) - min(k['color']) >= .05
        if abs(k['width'] - pipe_w) <= .015 and not grey and not coloured:
            role = 'pipe'
        elif leader_w is not None and abs(k['width'] - leader_w / unit) <= .015 and not grey and not coloured:
            role = 'leader'
        elif grey:
            role = 'architecture'
        else:
            role = 'symbol'
        families.append({'key': k, 'role': role})
    if not any(f['role'] == 'pipe' for f in families):
        return None
    return {'policy': {'families': families},
            'report': {'chosen_pipe_widths': sorted(chosen), 'landed_pipe_pen': best_key,
                       'landings': best['landings'], 'landings_on_chosen': on_chosen,
                       'leader_pen': leader_w, 'method': C.get('family_method')}}


def detect_page(pdf_path, page_number=0, style=None, progress=None, artifact_dir=None, strict_original=False):
    import pymupdf
    from ..pdf.extract import _inventory_annotations, _set_markup_aside
    extract, profile, detect, labels, style_module, vector_stages = load_runtime()
    timings = {}
    def save(name, value):
        if artifact_dir:
            target = Path(artifact_dir) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('w') as stream:
                json.dump(value, stream, ensure_ascii=False)
    def stage(name, fn):
        if progress: progress('PIPESTUDIO_' + name.upper())
        start = time.monotonic()
        value = fn()
        timings[name] = round(time.monotonic() - start, 3)
        return value
    with tempfile.TemporaryDirectory(prefix='vvs-native-') as tmp:
        clean = str(Path(tmp) / 'original-ink.pdf')
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                report = _set_markup_aside(page, _inventory_annotations(page), keep=False)
                if report and report.get('partial'):
                    raise ValueError('Cannot isolate original drawing ink for native detection')
            doc.save(clean)
        if strict_original:
            det = stage('detect', lambda: detect.detect(clean, page_number))
        else:
            from .tiled_detection import detect as bounded_detect
            det = stage('detect', lambda: bounded_detect(clean, page_number, progress=progress))
        # Model inference does not need the vector graph. Build it afterwards
        # so its allocations do not overlap the ONNX working set.
        ex = stage('extract', lambda: extract.extract(clean, page_number))
        boxed = {'split': 0}
        if not strict_original:
            from .boxed_leaders import split, reorder_leaders
            label_rects = [b['rect'] for b in det.get('label_boxes', [])]
            ex, boxed = split(ex, label_rects)
            ex, reordered = reorder_leaders(ex, label_rects)
            boxed = dict(boxed, reordered=reordered)
        P = stage('profile', lambda: profile.profile(ex))
        det = labels.text_label_boxes(ex, det, text_height=style_module.text_height(ex)[0])
        L = stage('ocr', lambda: labels.read_labels(clean, det, page_no=page_number))
        rotated_repairs = []
        if not strict_original:
            from .rotated_labels import repair
            with pymupdf.open(clean) as text_doc:
                rotated_repairs = repair(text_doc[page_number], L)
        shelves = {'widened': 0}
        if not strict_original:
            from .label_shelves import extend_to_shelves
            det, L, shelves = extend_to_shelves(ex, det, L)
        save('detection-inputs.json', {'extraction': asdict(ex), 'profile': P,
                                     'detection': det, 'labels': L, 'timings': timings})
        # Unknown styles still use the original automatic measurement/calibration.
        if style is None:
            from studio.engine import detect_style
            from studio.styles import get_style
            match = detect_style(ex, P)
            style = get_style(match['style_id']) if match.get('style_id') else {}
        else:
            match = {'status': 'caller_profile', 'style_id': style.get('id')}
        selected = dict(style)
        selected.setdefault('id', 'auto')
        selected.setdefault('version', 1)
        selected.setdefault('calibration', {})
        selected.setdefault('rules', [])
        selected['calibration_mode'] = 'auto'
        unparsed = [l for l in L if not l.get('designations')]
        if not strict_original:
            # Original associate._split_shared_line calls max() on every OCR
            # designation list. Empty lists crash that stage. Preserve such
            # readings in the audit, but do not treat them as pipe labels.
            excluded = {l['id'] for l in unparsed}
            L = [l for l in L if l['id'] not in excluded]
            det = {**det, 'label_boxes': [b for b in det['label_boxes'] if b['id'] not in excluded]}
        read = L
        B, A, L, R = stage('vector_stages', lambda: vector_stages(ex, P, det, read, selected, mode='auto'))
        landed = None if selected.get('stroke_policy') is not None else landed_policy(ex, B)
        if landed is not None:
            # the matched style was contradicted by the sheet: none of its measures is taken, only the sheet's own
            selected = {'id': 'auto', 'version': 1, 'calibration': {}, 'rules': [], 'calibration_mode': 'auto',
                        'stroke_policy': landed['policy'], 'landed_pens': dict(landed['report'],
                                                                              set_aside_style=selected.get('id'))}
            B, A, L, R = stage('vector_stages_landed', lambda: vector_stages(ex, P, det, read, selected, mode='auto'))
        from .free_end_landings import land_free_ends
        R, rescued = land_free_ends(A, R, L)
        return {'source_pdf_sha256': _pdf_digest(pdf_path), 'free_end_landings': rescued,
                'page': page_number, 'extraction': asdict(ex), 'profile': P,
                'detection': det, 'bucket': B, 'graph': A, 'labels': L,
                'association': R, 'timings': timings, 'style': selected, 'style_match': match,
                'unparsed_labels': unparsed, 'strict_original': strict_original,
                'rotated_text_repairs': rotated_repairs, 'boxed_leaders': boxed, 'label_shelves': shelves,
                'annotations_used': False, 'expert_overrides_used': False}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf'); parser.add_argument('--out', required=True)
    parser.add_argument('--page', type=int, default=0)
    parser.add_argument('--strict-original', action='store_true')
    args = parser.parse_args()
    result = detect_page(args.pdf, args.page, progress=lambda s: print(s, flush=True),
                         artifact_dir=Path(args.out).parent, strict_original=args.strict_original)
    target = Path(args.out); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False))
    print(json.dumps({'timings': result['timings'], 'labels': len(result['labels']),
                      'stretches': len(result['graph']['stretches'])}), flush=True)


if __name__ == '__main__':
    main()
