"""Versioned style packages; profiles contain conventions, never sheet IDs."""
from copy import deepcopy
import math
from .storage import ROOT, data_root, read, write, ident, now, transaction, digest

# All distances are ratios of the sheet's calibrated leader stroke width.
# The ranges cover the pen tables of the style survey (2026-09-08): a Ghostscript
# export with a 0.24 pt leader pen puts the 40 pt straight-gap reach at 167
# leader widths and the 8 pt anchor at 33.
PARAMETERS = {
    'assemble.snap': (0.2, 4.0, 'Endpoint snap / leader width'),
    'assemble.lateral': (0.2, 4.0, 'Collinearity offset / leader width'),
    'assemble.wall_gap': (20.0, 200.0, 'Straight gap reach / leader width'),
    'assemble.mark_merge': (1.0, 16.0, 'Nearby marks / leader width'),
    'assemble.small_ring': (3.0, 18.0, 'Small ring diameter / leader width'),
    'associate.anchor': (4.0, 40.0, 'Label anchor reach / leader width'),
    'associate.landing': (2.0, 16.0, 'Landing reach / leader width'),
    'associate.twin_gap': (10.0, 100.0, 'Parallel pair reach / leader width'),
    'bucket.tick_rel_min': (1.2, 3.0, 'Tick length / pipe width'),
}


def _path():
    return data_root() / 'styles.json'


SHIPPED = ROOT / 'vectorascore/data/styles'
GROUPS = read(ROOT / 'vectorascore/data/style_groups.json', [])
ALIASES = {sid: g['id'] for g in GROUPS for sid in g['members'] if sid != g['id']}


def canonical_id(style_id):
    return ALIASES.get(style_id, style_id)


def group_version(style_id, version):
    if canonical_id(style_id) == style_id or version is None:
        return version
    return next(p['version'] for p in registry()['styles'][canonical_id(style_id)]['releases']
                if p.get('source_style_id') == style_id and p.get('source_version') == version)


def _merge_groups(doc, shipped):
    """One timeline and draft per group; retain original releases for old runs."""
    entries = doc['styles']
    for group in GROUPS:
        sid = group['id']
        target = entries[sid]
        if target.get('merge_revision') == 1:
            continue
        base = deepcopy(shipped[sid])
        draft = deepcopy(target['draft'])
        def combined(field, draft_state):
            values = {}
            for member in group['members']:
                entry = entries[member]
                profile = entry['draft'] if draft_state else next(
                    (p for p in entry['releases'] if p['version'] == entry['active']), {})
                for value in profile.get(field, []):
                    value = deepcopy(value)
                    if field == 'rules':
                        if value['id'] in values and values[value['id']] != value:
                            value['id'] = member + '-' + value['id']
                        values[value['id']] = value
                    elif value.get('pipe_ratios'):
                        values[digest(value)] = value
            return list(values.values())
        released_rules = combined('rules', False)
        released_signatures = combined('signatures', False)
        draft_rules = combined('rules', True)
        draft_signatures = combined('signatures', True)
        for member in group['members']:
            source = entries[member]
            if member != sid:
                for release in source['releases']:
                    historical = deepcopy(release)
                    historical.update(id=sid, version=max(p['version'] for p in target['releases']) + 1,
                                      source_style_id=member, source_version=release['version'])
                    target['releases'].append(historical)
        # Preserve custom primary adjustments; secondary drafts remain in provenance.
        primary = next((p for p in target['releases'] if p['version'] == target['active']), shipped[sid])
        base['calibration'] = deepcopy(primary.get('calibration', {}))
        base['rules'] = released_rules
        base['signatures'] = released_signatures
        base['version'] = max(p['version'] for p in target['releases']) + 1
        base['source_drafts'] = {m: deepcopy(entries[m]['draft']) for m in group['members']}
        validate(base)
        target['releases'].append(deepcopy(base))
        base.update(calibration=deepcopy(draft.get('calibration', {})), rules=draft_rules, signatures=draft_signatures)
        validate(base)
        target.update(draft=base, active=base['version'], merge_revision=1)
    return doc


def shipped_styles():
    """The style packages shipped with the engine (vectorascore/data/styles/*.json):
    style-1, the reference conventions, and one package per drawing style of the
    survey library (built by tools/style_survey/build_studio_styles.py)."""
    out = {}
    for path in sorted(SHIPPED.glob('*.json')):
        base = read(path)
        if base and base.get('id'):
            out[base['id']] = base
    return out


def registry():
    doc = read(_path())
    if doc is None:
        doc = {'styles': {}}
    # a shipped package the registry does not know yet appears as its baseline
    # release (version 1, active), exactly as style-1 always has; a package the
    # registry already holds is never touched - drafts and releases are the
    # experts' record
    shipped = shipped_styles()
    baselines = {p.stem: read(p) for p in (SHIPPED / 'archive').glob('*.json')}
    for sid, base in {**shipped, **baselines}.items():
        if sid not in doc['styles']:
            from .global_rules import apply_patch_to_profile
            for change in doc.get('global_changes', []):
                base = apply_patch_to_profile(base, change['patch'])
            doc['styles'][sid] = {'draft': deepcopy(base), 'releases': [deepcopy(base)], 'active': base.get('version', 1)}
    doc = _merge_groups(doc, shipped)
    # Custom style numbers are persisted, including deleted entries, so a number
    # never changes when another style is added, renamed or removed.
    custom = [e for sid,e in doc['styles'].items() if sid not in shipped and sid not in ALIASES]
    number = max([11] + [e.get('display_number',11) for e in custom])
    changed = False
    for entry in custom:
        if not entry.get('display_number') and not entry.get('deleted_at'):
            number += 1; entry['display_number'] = number; changed = True
    if changed:
        write(_path(), doc)
    return doc


def list_styles():
    return [entry for sid, entry in registry()['styles'].items() if sid not in ALIASES and not entry.get('deleted_at')]


def delete_style(style_id, author='Reviewer'):
    style_id = canonical_id(ident(style_id))
    if style_id == 'style-1':
        raise ValueError('The default fallback style cannot be deleted')
    with transaction():
        doc = registry()
        entry = doc['styles'].get(style_id)
        if entry is None:
            raise ValueError('Unknown style')
        entry.update(deleted_at=now(), deleted_by=author)
        write(_path(), doc)
    return {'id': style_id, 'deleted': True}


def derived_tolerances(C):
    """Engine starting tolerances in PDF points, shared with the survey builder."""
    u, pw, th = C['u_paper'], C['pipe_base'], C['text_height']
    pen = u * min(1.0, pw / 1.2) if pw < 1.2 else u
    return {'assemble.snap': max(0.5 * pen, 0.3), 'assemble.lateral': max(0.6 * pen, 0.3),
            'assemble.wall_gap': 40.0 * u, 'assemble.mark_merge': 3.0 * u, 'assemble.small_ring': 3.5 * u,
            'associate.anchor': (8.0 / 11.0) * th, 'associate.landing': 3.0, 'associate.twin_gap': 20.0,
            'bucket.tick_rel_min': 1.8}


def drawing_parameters(P, ex, boxes=None, stroke_policy=None):
    from vectorascore import bucket, labels, style
    if not boxes:
        det = labels.text_label_boxes(ex, {'label_boxes': []}, text_height=style.text_height(ex)[0])
        boxes = [b['rect'] for b in det['label_boxes']]
    C = bucket.calibrate(P, ex, boxes)
    if stroke_policy is not None:
        from .style_vision import apply_calibration
        apply_calibration(C, stroke_policy)
    unit = leader_unit(C)
    calibration = {}
    for key, value in derived_tolerances(C).items():
        lo, hi, _ = PARAMETERS[key]
        ratio = value if key.endswith('tick_rel_min') else value / unit
        calibration[key] = round(min(hi, max(lo, ratio)), 3)
    return calibration, {key: C.get(key) for key in
        ('pipe_widths', 'leader_width', 'text_height', 'u_paper', 'hairline', 'family_method', 'family_confidence')}


def get_style(style_id='style-1', version=None, draft=False):
    if version is None or draft:
        style_id = canonical_id(style_id)
    entry = registry()['styles'].get(ident(style_id))
    if not entry:
        raise ValueError('Unknown style')
    if draft:
        return deepcopy(entry['draft'])
    version = entry['active'] if version is None else version
    found = next((x for x in entry['releases'] if x['version'] == version), None)
    if not found:
        raise ValueError('Unknown style release')
    return deepcopy(found)


def validate(profile):
    ident(profile['id'])
    if not isinstance(profile.get('name'), str) or not profile['name'].strip():
        raise ValueError('Style name is required')
    for key, value in profile.get('calibration', {}).items():
        if key not in PARAMETERS or type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Unsupported calibration parameter: ' + key)
        lo, hi, _ = PARAMETERS[key]
        if not lo <= value <= hi:
            raise ValueError(f'{key} must be between {lo} and {hi}')
    rules = profile.get('rules', [])
    if not isinstance(rules, list) or len(rules) > 40:
        raise ValueError('At most 40 style rules')
    seen = set()
    for rule in rules:
        ident(rule['id'])
        if rule['id'] in seen:
            raise ValueError('Duplicate rule ID')
        seen.add(rule['id'])
        if rule.get('stage') != 'binding' or not isinstance(rule.get('instruction'), str) or not 5 <= len(rule['instruction']) <= 2500:
            raise ValueError('Rules must be binding instructions (5–2500 characters)')
        # Explicit document/object anchors cannot be promoted as style rules.
        import re
        if re.search(r'\b[A-Z]-\d{2}-|(?:pipe|stretch|label|node|path|sheet|drawing)[ _#:]+\d+|\b[^\s]+\.(?:pdf|dwg|dxf|ifc)\b|\(\s*\d{2,}(?:\.\d+)?\s*,\s*\d{2,}', rule['instruction'], re.I):
            raise ValueError('A style rule cannot refer to sheet IDs, object IDs or absolute coordinates')
    return profile


def save_draft(style_id, changes):
    style_id = canonical_id(style_id)
    with transaction():
        doc = registry()
        entry = doc['styles'].get(ident(style_id))
        if not entry:
            reference = get_style()
            base = {key: deepcopy(reference[key]) for key in ('description', 'calibration', 'rules')}
            base.update(id=style_id, name=style_id, signatures=[], version=0)
            entry = doc['styles'][style_id] = {'draft': base, 'releases': [], 'active': None}
        p = deepcopy(entry['draft'])
        for key in ('name', 'description', 'calibration', 'rules'):
            if key in changes:
                p[key] = changes[key]
        validate(p)
        entry['draft'] = p
        write(_path(), doc)
    return p


def signature(P, ex=None):
    from vectorascore.bucket import calibrate
    c = calibrate(P)
    # Keep existing signatures stable, but let thin/hairline drawings use the
    # same vector calibration as analysis instead of the legacy width cutoff.
    if not c['pipe_widths'] and ex is not None:
        c = calibrate(P, ex)
    lw = max(c['leader_width'], 0.01)
    return {'pipe_ratios': [round(w / lw, 2) for w in c['pipe_widths']],
            'ring_ratio': round(c['circle']['diameter'] / lw, 2) if c['circle'] else 0,
            'layered': c['has_layers']}


def calibrate_style(style_id, profiles):
    style_id = canonical_id(style_id)
    sigs = [signature(p) for p in profiles]
    if not sigs or any(not s['pipe_ratios'] for s in sigs):
        raise ValueError('Select drawings with recognised pipe stroke families')
    with transaction():
        doc = registry(); entry = doc['styles'][ident(style_id)]
        unique = {digest(s): s for s in entry['draft'].get('signatures', []) + sigs}
        entry['draft']['signatures'] = list(unique.values())
        write(_path(), doc)
    return entry['draft']


def match_style(P, ex=None):
    probe = signature(P, ex); scores = []
    for entry in list_styles():
        if entry['active'] is None:
            continue
        style = next(x for x in entry['releases'] if x['version'] == entry['active'])
        distances = []
        for sig in style.get('signatures', []):
            if len(sig['pipe_ratios']) != len(probe['pipe_ratios']) or not sig['pipe_ratios']:
                continue
            ratios = [abs(a-b) / max(a, b, .01) for a, b in zip(sig['pipe_ratios'], probe['pipe_ratios'])]
            ratios += [abs(sig['ring_ratio']-probe['ring_ratio']) / max(sig['ring_ratio'], probe['ring_ratio'], .01)]
            distances.append(sum(ratios) / len(ratios) + (0.3 if sig['layered'] != probe['layered'] else 0))
        if distances:
            scores.append({'style_id': style['id'], 'distance': round(min(distances), 4), 'version': style['version']})
    scores.sort(key=lambda x: x['distance'])
    accepted = bool(scores and scores[0]['distance'] <= .18 and (len(scores) == 1 or scores[1]['distance'] - scores[0]['distance'] >= .05))
    return {'status': 'matched' if accepted else 'needs_style_review', 'style_id': scores[0]['style_id'] if accepted else None,
            'candidates': scores, 'signature': probe, 'method': 'relative-vector-signature-v1'}


def tolerances(profile, stage, P=None, unit=None):
    """The stage's tolerances in points: the style's relative values times the
    sheet's leader stroke width. ``unit`` is that width as the full calibration
    found it (engine.vector_stages); without it the profile-only width rule is
    asked, as before."""
    if unit is None:
        from vectorascore.bucket import calibrate
        unit = calibrate(P)['leader_width']
    return {k.split('.', 1)[1]: (v if k.endswith('tick_rel_min') else round(v * unit, 5))
            for k, v in profile.get('calibration', {}).items() if k.startswith(stage + '.')}


def leader_unit(C):
    """The leader stroke width the relative calibration hangs on. A hairline plot
    (every width 0) has none: the reference ratio of the pipe base is used."""
    lw = C.get('leader_width') or 0.0
    if lw > 0:
        return lw
    return round((C.get('pipe_base') or 1.44) / 3.0, 4)


def activate(style_id, version):
    version = group_version(style_id, version)
    style_id = canonical_id(style_id)
    with transaction():
        doc = registry(); entry = doc['styles'][ident(style_id)]
        if not any(r['version'] == version for r in entry['releases']):
            raise ValueError('Unknown release')
        entry['active'] = version
        write(_path(), doc)
    return get_style(style_id)
