"""Executable interpretations of the supplied Swedish VVS tables.

Tables are evidence, not universal validation constraints. Local legends win;
unrecognised codes and conflicting meanings stay explicit.
"""
from functools import lru_cache
import json
from pathlib import Path
import re

DATA = Path(__file__).resolve().parents[3] / 'reference_sources/swedish-vvs-drawings-main/data'


def designation_text(d):
    """Preserve the drawing's separators, venting spelling and service suffix."""
    from .pipestudio.vvs import parse_designation
    raw = re.sub(r'^\s*\d+\s*[xX]\s*', '', d.get('raw', '')).split('+')[0].strip()
    parsed = parse_designation(raw, allow_partial=True) if raw else None
    if parsed and parsed.dimension == d.get('dimension') and parsed.dimension is not None:
        return raw
    name = '-'.join([d['system']+(d.get('number') or '')] + d.get('middle', []) + [str(d['dimension'])])
    if d.get('venting'): name += '(L)'
    if d.get('suffix'): name += '/' + d['suffix']
    return name


@lru_cache(maxsize=1)
def tables():
    return {p.stem: json.loads(p.read_text()) for p in sorted(DATA.glob('*.json'))}


def lookup(code, legend=None):
    if legend is not None and code in legend:
        return {'state': 'LOCAL_LEGEND', 'meanings': [legend[code]], 'source': 'drawing_legend'}
    meanings = [{'table': name, 'entry': entry} for name, table in tables().items()
                for entry in table.get('entries', []) if any(entry.get(field) == code for field in ('code', 'sensor_code', 'instrument_code'))]
    return {'state': 'UNKNOWN' if not meanings else 'AMBIGUOUS' if len(meanings) > 1 else 'KNOWN',
            'meanings': meanings, 'source': 'swedish-vvs-drawings-main'}


def vertical_notation(over, under, *, is_vertical, height_m=None):
    if not is_vertical:
        return {'state': 'NOT_APPLICABLE', 'length_m': None}
    code = 'stroke_above_and_below' if over and under else 'stroke_above' if over else 'stroke_below' if under else 'no_stroke'
    entry = next(e for e in tables()['vertical_pipe_notation']['entries'] if e['code'] == code)
    return {'state': 'INTERPRETED', 'source': 'vertical_pipe_notation/' + code,
            'penetrates_slab_above': entry['penetrates_slab_above'],
            'penetrates_slab_below': entry['penetrates_slab_below'],
            # Stroke notation states slab passage, never a numeric length.
            'length_m': height_m if height_m is not None and height_m >= 0 else None}


def label_facts(label, legend=None):
    result = []
    for d in label.get('designations', []):
        code = d.get('system', '')
        match = lookup(code, legend)
        system = next((e for e in tables()['system_designations']['entries'] if e['code'] == code), {})
        result.append({'raw': d.get('raw'), 'system': code, 'lookup': match,
                       'line_count': system.get('line_count') if match['state'] != 'LOCAL_LEGEND' else (legend[code].get('line_count') if isinstance(legend[code], dict) else None),
                       'index_meaning': 'project_defined',
                       'material': None, 'jointing': None, 'insulation_specification': None,
                       'unresolved_middle_fields': d.get('middle', []),
                       'components': [{'code': c, 'lookup': lookup(re.sub(r'\d+$', '', c), legend)} for c in d.get('components', [])],
                       'level_can_indicate_flow': code.startswith(('S', 'D')) and code != 'SL'})
    notation = label.get('stroke_notation')
    return {'designations': result, 'vertical_notation': vertical_notation(
        bool(notation and notation.get('over')), bool(notation and notation.get('under')),
        is_vertical=notation is not None)}


def specification_conflict(drawing_value, specification_value, *, contract_type=None):
    if drawing_value == specification_value:
        return {'state': 'AGREES', 'value': drawing_value}
    if drawing_value is None or specification_value is None:
        return {'state': 'MISSING_INPUT', 'value': None}
    return {'state': 'CONFLICT', 'value': specification_value if contract_type == 'utförandeentreprenad' else None,
            'review_required': True, 'source': 'document_rules/precedence_drawing_vs_spec',
            'drawing_value': drawing_value, 'specification_value': specification_value}
