"""Keep one result per assignment method, with content-based freshness checks.

Callers hold drawing_lock while preserving or selecting results. Switching never
calls an assignment engine; generation is an explicit, separate replay task.
"""
from pathlib import Path
import os
from .storage import read, write, digest, engine_version

STAGES = ('04_bucket', '05_assemble', '06_labels', '07_associate', '08_llm', '09_review')
METHODS = {'flow', 'astra'}


def fingerprint(directory, style):
    directory = Path(directory)
    profile = {k:v for k,v in style.items() if k != 'profile_state'}
    inputs = {name:read(directory/(name+'.json')) for name in
              ('01_extract', '02_profile', '03_detect', '06_labels_input')}
    # Very old drawings lack separate label inputs; use the actual fallback
    # consumed by reanalyze. New analyses always have 06_labels_input.
    if not inputs['06_labels_input']:
        inputs['06_labels_input'] = read(directory/'06_labels.json')
    source = read(directory/'09_review.json', {}).get('metadata', {}).get('source_sha256')
    return digest({'engine':engine_version(), 'style':profile, 'inputs':inputs, 'source':source,
                   'model':os.environ.get('OPENAI_MODEL', 'gpt-6-astra'),
                   'effort':os.environ.get('STUDIO_ASTRA_EFFORT', 'medium')})


def save(directory, key=None):
    directory = Path(directory)
    rv = read(directory/'09_review.json', {})
    binding = rv.get('metadata', {}).get('binding_mode')
    if binding not in METHODS:
        return
    path = directory/'.assignment-results'/(binding+'.json')
    previous = read(path, {})
    if key is None and previous.get('stages', {}).get('09_review') == rv:
        return  # Never replace a generation fingerprint when just switching.
    if key is None:
        # Adopt an existing result only if its existing freshness checks pass.
        from .freshness import assignment_status
        from .styles import get_style
        meta = rv.get('metadata', {})
        if assignment_status(directory).get('status') == 'current':
            key = fingerprint(directory, get_style(meta.get('style_id', 'style-1'), draft=True))
    write(path, {'fingerprint':key, 'stages':{name:read(directory/(name+'.json')) for name in STAGES}})


def select(directory, binding, style):
    if binding not in METHODS:
        raise ValueError('Choose Dimension or LLM')
    directory = Path(directory)
    current = read(directory/'09_review.json')
    if not current:
        raise ValueError('No drawing analysis is available')
    save(directory)
    entry = read(directory/'.assignment-results'/(binding+'.json'))
    if not entry:
        return {'available':False, 'fresh':False, 'binding':binding}
    key = fingerprint(directory, style)
    result = entry['stages']['09_review']
    # a result computed with another style is no result for this one: restoring it
    # would silently swap the reviewer's chosen style for the old one
    from .styles import canonical_id
    if canonical_id(result.get('metadata', {}).get('style_id', 'style-1')) != canonical_id(style.get('id', 'style-1')):
        return {'available':False, 'fresh':False, 'binding':binding}
    if result != current:
        from . import evidence
        evidence.snapshot(directory)
        for name in STAGES:
            write(directory/(name+'.json'), entry['stages'][name])
    return {'available':True, 'fresh':bool(entry.get('fingerprint') and entry['fingerprint']==key),
            'binding':binding, 'run_id':result.get('metadata', {}).get('run_id')}
