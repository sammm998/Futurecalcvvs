"""One vector analysis engine for Studio experiments and the production API."""
from copy import deepcopy
import hashlib
import json
from time import perf_counter
from pathlib import Path
from .storage import engine_version, digest, now, write, read
from .styles import get_style, match_style, tolerances, leader_unit


def vector_stages(ex, P, det, labels, style, mode='auto'):
    from vectorascore import bucket, assemble, associate
    from vectorascore import labels as la, vvs
    if style.get('calibration_mode') == 'auto':
        mode = 'auto'
    L = deepcopy(labels); det = deepcopy(det)
    for label in L:
        # Saved OCR inputs may predate the current dimension checks. Apply the
        # same validation as a fresh read before they affect graph assignment.
        label['designations'] = [vvs.sanitize_dimension(d) for d in label['designations']]
        label['valid'] = la.label_valid(label['designations'], label.get('score'))
        label['usable'] = any(d.get('dimension') for d in label['designations'])
    # the unit of the style's relative calibration is the leader pen the sheet's own
    # calibration found (labels included), not the profile-only width rule's guess
    valid_boxes = [b['rect'] for b in det['label_boxes'] if any(l['id'] == b['id'] and l['valid'] for l in L)]
    # a Studio style built from the drawing-style library carries its library id:
    # the reviewer's choice then applies that style's starting values and
    # conventions (style-1 has none and calibrates as always)
    # mode "manual" (the reviewer chose the style): no detection, the style's own
    # configuration only; "auto": detect from the drawing
    hint = style.get('library_id')
    C = bucket.calibrate(P, ex, valid_boxes or [b['rect'] for b in det['label_boxes']], style_hint=hint, mode=mode)
    if style.get('stroke_policy') is not None:
        from .style_vision import apply_calibration
        apply_calibration(C, style['stroke_policy'])
    unit = leader_unit(C)
    def classify():
        return bucket.bucket(ex, P, det, tol=tolerances(style, 'bucket', unit=unit),
            invalid_labels=[l['id'] for l in L if not l['valid']],
            label_systems={l['id']: l.get('layer_system') for l in L}, style_hint=hint, mode=mode,
            stroke_policy=style.get('stroke_policy'))
    B = classify()
    la.share_ladder_notes(L, ex, B['buckets']); la.layer_systems(L, ex, B['buckets'])
    for l in L:
        if not l['valid'] and l.get('layer_system'):
            la.repair_from_layer(l)
    if any(l.get('repaired_from_layer') for l in L):
        B = classify()
    from .style_preview import apply as apply_style_corrections
    B = apply_style_corrections(ex, B, style)
    la.refresh_stroke_notation(L, ex, B['buckets'])
    for l in L:
        l['in_wall'] = l['id'] in set(B.get('wall_labels', []))
    A = assemble.assemble(ex, B, tol=tolerances(style, 'assemble', unit=unit),
        label_boxes=[{'rect': l['rect'], 'system': l.get('layer_system')} for l in L])
    R = associate.associate(ex, B, A, L, tol=tolerances(style, 'associate', unit=unit))
    return B, A, L, R


# the reviewer-facing name of each binding mode (the assignmentMethod toggle in Pipe Studio)
ASSIGNMENT_METHOD = {'astra': 'llm', 'flow': 'dimension', 'preview': None}


def build_result(sheet, ex, P, det, L, style, binding='preview', source_hash=None, ask=None, mode='auto'):
    """Binding modes (the reviewer picks one with the mode toggle in Pipe Studio):
      preview  the vector stages only (rule bindings of associate.py)
      astra    Main Branch Mode - the Astra final assignment exactly as on main
      flow     Dimension-Based Mode - the flow-direction rules
               (vectorascore/flow_assign.py) decide the assignment and the
               pipes between joining points; no model
    """
    from vectorascore import review, final_bind
    B, A, L, R = vector_stages(ex, P, det, L, style, mode=mode)
    if binding == 'flow':
        from vectorascore import flow_assign
        R = flow_assign.assign(A, L, R)          # also rewrites stretch.pipe = the pipe between joining points
    llm = final_bind.bind(A, R, L, style, ask=ask) if binding == 'astra' else None
    rv = review.build_review(sheet, ex, P, det, B, A, L, R, llm)
    rv['metadata'] = {'schema_version': 2, 'engine_version': engine_version(),
        'style_id': style['id'], 'style_version': style['version'], 'style_digest': digest(style),
        'source_sha256': source_hash, 'created_at': now(), 'binding_mode': binding,
        'assignmentMethod': ASSIGNMENT_METHOD.get(binding),
        'coordinate_system': {'unit': 'pdf_point', 'origin': 'top_left', 'y_axis': 'down'},
        'assignment_unit': 'stretch', 'profile_state': style.get('profile_state', 'published')}
    rv['metadata']['run_id'] = digest({'source': source_hash, 'style': digest(style), 'engine': engine_version(),
                                      'graph': A, 'bindings': rv['bindings'], 'labels': L, 'binding_mode': binding, 'assignments': rv['assignments']})[:24]
    return rv, (B, A, L, R, llm)


# library styles whose Studio package has another id (the reference family IS style-1)
from .styles import GROUPS
LIBRARY_TO_STUDIO = {lid: g['id'] for g in GROUPS for lid in g['library_ids']}


def detect_style(ex, P):
    """Which published Studio style a drawing belongs to: Studio's vector signature
    first, then the drawing-style library (vectorascore/style.py). Returns the
    match record with ``style_id`` (None when neither is sure), ``method`` and
    ``library`` (the library's nearest style and distance, always reported)."""
    from vectorascore import style as vstyle_lib
    from .styles import list_styles
    match = match_style(P, ex)
    lib = vstyle_lib.match(vstyle_lib.measure(ex, P, vstyle_lib.units(ex, P)))
    match['library'] = {k: v for k, v in lib.items() if k != 'candidates'}
    match['library']['nearest'] = lib['candidates'][0] if lib['candidates'] else None
    if not match['style_id'] and lib['style']:
        sid = LIBRARY_TO_STUDIO.get(lib['style'], lib['style'])
        published = {s['draft']['id'] for s in list_styles() if s['active'] is not None}
        if sid in published:
            match.update(style_id=sid, status='matched', method='drawing-style-library-v1')
    return match


def analyze(pdf_path, output, style_id='auto', style_version=None, binding='astra', progress=None, studio=False, ask=None, render_preview=True, fallback=None):
    """``style_id`` 'auto' detects the style (``detect_style``); with ``fallback``
    set (the Studio app: 'style-1') an undetected style runs with the fallback
    and is reported as such instead of failing; the API keeps failing explicitly."""
    from vectorascore import extract, profile, detect, labels, review
    def step(n, name):
        if progress:
            progress(n, name)
    from vectorascore import style as vstyle
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    path = Path(pdf_path)
    # a booklet carries covers and lists before the plans: pick the drawing page
    page_no, pages = vstyle.select_page(str(path))
    step(1, 'extract'); ex = extract.extract(str(path), page_no); extract.save(ex, out/'01_extract.json')
    if not ex.paths and path.suffix.lower() != '.svg':
        raise ValueError('This endpoint requires a vector drawing')
    step(2, 'profile'); P = profile.profile(ex); P['pages'] = pages; P['page_no'] = page_no; write(out/'02_profile.json', P)
    if style_id == 'auto':
        match = detect_style(ex, P)
        match['selection'] = 'auto' if match['style_id'] else 'fallback'
    else:
        # a chosen style: nothing is detected, the drawing is analysed with it as it is
        match = {'status': 'manual', 'selection': 'manual', 'style_id': None, 'method': 'chosen by the reviewer'}
    if style_id == 'auto':
        if not match['style_id'] and fallback is None:
            write(out/'style_match.json', match)
            raise ValueError('Unknown or ambiguous style; calibrate it in FutureCalc Pipe Studio or select a published style explicitly')
        style_id = match['style_id'] or fallback
    match['used_style_id'] = style_id
    style = get_style(style_id, style_version)
    step(3, 'detect'); det = detect.detect(str(path), page_no)
    det = labels.text_label_boxes(ex, det, text_height=vstyle.text_height(ex)[0]); write(out/'03_detect.json', det)
    # Expert boxes are training inputs only, never hidden production overrides.
    if studio:
        det = labels.add_missing_boxes(det, labels.load_missing_boxes(path.stem))
    step(4, 'labels')
    from pipe_types import ocr_workers
    ocr_start = perf_counter()
    L = labels.read_labels(str(path), det, page_no=page_no)
    ocr_metrics = {'seconds': round(perf_counter() - ocr_start, 3),
                   'workers': ocr_workers(), 'labels': len(L)}
    print(json.dumps({'event': 'ocr_completed', **ocr_metrics}), flush=True)
    write(out/'03_detect.json', det); write(out/'06_labels_input.json', L)
    step(5, 'vector rules' if binding == 'preview' else 'vector rules and Astra')
    rv, (B,A,L,R,llm) = build_result(path.stem, ex, P, det, L, style, binding,
        hashlib.sha256(path.read_bytes()).hexdigest(), ask=ask, mode='manual' if match['selection'] == 'manual' else 'auto')
    rv['metadata']['style_match'] = match
    rv['metadata']['ocr'] = ocr_metrics
    for name, data in [('04_bucket',B),('05_assemble',A),('06_labels',L),('07_associate',R),('08_llm',llm),('09_review',rv)]:
        write(out/(name+'.json'), data)
    step(9, 'review')
    if render_preview:
        review.render_background(str(path), str(out/'bg.png'), rv['scale'], page_no=page_no)
    return rv


AUTO = 'auto'


def resolve_style(directory, style_id=AUTO, draft=False, fallback='style-1', detect=True):
    """The Studio style a stored drawing is analysed with, from the reviewer's
    choice: a style id, or ``auto`` - detect it from the stored extraction
    (``detect_style``); an undetected style runs as ``fallback`` and is reported
    as such. Returns (style, match) where match carries ``selection``
    ('manual', 'auto' or 'fallback'), the detected ``style_id`` and
    ``used_style_id``. With ``detect`` false the last analysis' detection is
    reused (cheap: status checks and result selection)."""
    from vectorascore import extract
    d = Path(directory)
    old = read(d/'09_review.json', {}) or {}
    meta = old.get('metadata', {})
    if style_id != AUTO:
        # a chosen style: nothing is detected
        return get_style(style_id, draft=draft), {'status': 'manual', 'selection': 'manual', 'style_id': None,
                                                   'used_style_id': style_id, 'method': 'chosen by the reviewer'}
    prior = meta.get('style_match') or {}
    # a cheap call (status checks, result selection) answers about the drawing as it
    # stands: the style the last analysis used, chosen by the reviewer or detected.
    # Detecting here would judge the drawing against a style it is not analysed with.
    if not detect and (prior.get('used_style_id') or meta.get('style_id')):
        sid = prior.get('used_style_id') or meta['style_id']
        return get_style(sid, draft=draft), dict(prior) or {'status': 'manual', 'selection': 'manual',
            'style_id': None, 'used_style_id': sid, 'method': 'style of the saved analysis'}
    if not ((d/'01_extract.json').exists() and (d/'02_profile.json').exists()):
        sid = meta.get('style_id') or fallback
        return get_style(sid, draft=draft), {'selection': 'fallback', 'style_id': None, 'used_style_id': sid, 'method': 'no stored extraction'}
    match = detect_style(extract.load(d/'01_extract.json'), read(d/'02_profile.json'))
    match['selection'] = 'auto' if match['style_id'] else 'fallback'
    sid = match['style_id'] or fallback
    match['used_style_id'] = sid
    return get_style(sid, draft=draft), match


def reanalyze(directory, style=None, binding='preview', ask=None, match=None):
    from vectorascore import extract
    d = Path(directory)
    old = read(d/'09_review.json', {})
    style = style or get_style(old.get('metadata', {}).get('style_id', 'style-1'))
    mode = 'manual' if (match or {}).get('selection', 'manual') == 'manual' else 'auto'
    rv, stages = build_result(old.get('sheet', d.name), extract.load(d/'01_extract.json'), read(d/'02_profile.json'),
        read(d/'03_detect.json'), read(d/'06_labels_input.json') or read(d/'06_labels.json'), style, binding,
        old.get('metadata', {}).get('source_sha256'), ask=ask, mode=mode)
    # how the style was chosen (auto / manual / fallback) and what the drawing
    # matches, carried on every re-analysis so the review page can show both
    rv['metadata']['style_match'] = match or dict(old.get('metadata', {}).get('style_match') or {}, selection='manual', used_style_id=style['id'])
    return rv, stages


def api_result(rv):
    # Canonical ownership comes from review.build_review, never from list order in a client.
    owner = {b['stretch']: b for b in rv['bindings']}
    meta = dict(rv.get('metadata', {}))
    meta.setdefault('assignmentMethod', ASSIGNMENT_METHOD.get(meta.get('binding_mode')))
    return {'schemaVersion': 2, 'metadata': meta, 'page': rv['page'],
        'pipes': [dict(s, label_id=owner[s['id']]['label'] if s['id'] in owner else None,
                       designation_idx=owner[s['id']]['designation_idx'] if s['id'] in owner else None)
                  for s in rv['stretches']],
        'joiningPoints': rv['nodes'], 'leadingLines': rv['leaders'], 'labels': rv['labels'],
        'assignments': rv.get('assignments', []), 'unresolved': rv['unbound_stretches'],
        'issues': rv.get('binding_conflicts', []) + rv.get('llm', {}).get('issues', []),
        'modelErrors': rv.get('llm', {}).get('errors', [])}
