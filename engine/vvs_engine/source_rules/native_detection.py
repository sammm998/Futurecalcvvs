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
        P = stage('profile', lambda: profile.profile(ex))
        det = labels.text_label_boxes(ex, det, text_height=style_module.text_height(ex)[0])
        L = stage('ocr', lambda: labels.read_labels(clean, det, page_no=page_number))
        rotated_repairs = []
        if not strict_original:
            from .rotated_labels import repair
            with pymupdf.open(clean) as text_doc:
                rotated_repairs = repair(text_doc[page_number], L)
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
        B, A, L, R = stage('vector_stages', lambda: vector_stages(ex, P, det, L, selected, mode='auto'))
        return {'source_pdf_sha256': _pdf_digest(pdf_path),
                'page': page_number, 'extraction': asdict(ex), 'profile': P,
                'detection': det, 'bucket': B, 'graph': A, 'labels': L,
                'association': R, 'timings': timings, 'style': selected, 'style_match': match,
                'unparsed_labels': unparsed, 'strict_original': strict_original,
                'rotated_text_repairs': rotated_repairs,
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
