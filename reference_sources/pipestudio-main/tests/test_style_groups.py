"""Consolidation joins the learning history without losing historical releases."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from studio import styles, evidence, learning
from studio.storage import write


def test_groups_share_history_and_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path))
    entries = styles.registry()['styles']
    assert len(styles.list_styles()) == 11
    assert styles.get_style('priorn-shx')['id'] == 'style-1'
    assert styles.get_style('lopoglan-booklet')['id'] == 'bd-ghostscript'
    assert styles.get_style('priorn-shx', 1)['id'] == 'priorn-shx'
    history = entries['style-1']['releases']
    assert {p.get('source_style_id') for p in history} >= {'priorn-shx', 'hyllie-ghostscript'}
    write(styles._path(), styles.registry())
    assert styles.registry()['styles'] == entries  # repeat reads never duplicate history
    rows = [{'id': f'f{i}', 'style_id': sid, 'status': 'captured', 'track':'pipes'}
            for i, sid in enumerate(['style-1','priorn-shx','hyllie-ghostscript'])]
    write(tmp_path/'feedback.json', {'records': rows})
    assert {r['style_id'] for r in evidence.records()} == {'style-1'}
    candidate = learning.create('style-1', 'Shared feedback', [r['id'] for r in rows])
    assert len(candidate['training_ids']) == 3
    old = deepcopy(candidate)
    old.update(id='old', style_id='priorn-shx', base_version=1)
    old['profile'] = styles.get_style('priorn-shx', 1)
    write(tmp_path/'candidates/old.json', old)
    merged = learning.candidate('old')
    assert merged['style_id'] == 'style-1'
    assert styles.get_style('style-1', merged['base_version'])['source_style_id'] == 'priorn-shx'


def test_existing_custom_rule_and_original_release_survive(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path))
    original = json.loads((styles.SHIPPED/'archive/priorn-shx.json').read_text())
    draft = deepcopy(original)
    draft['rules'].append({'id':'custom', 'stage':'binding', 'instruction':'Keep reviewed topology boundaries.'})
    write(styles._path(), {'styles': {'priorn-shx': {'draft':draft,'active':1,'releases':[original]}}})
    assert styles.get_style('priorn-shx',1) == original
    assert any(r['id']=='custom' for r in styles.get_style(draft=True)['rules'])
    assert not any(r['id']=='custom' for r in styles.get_style()['rules'])


def test_source_folders_and_lookup():
    from tools.style_survey.build_library import ENTRIES, find_pdf
    root = Path(__file__).resolve().parents[1]/'style-source-pdfs'
    manifest = json.loads((root/'manifest.json').read_text())
    assert len(manifest) == 11
    assert len(manifest[0]['files']) == 3
    assert len(manifest[4]['files']) == 2
    # PDFs are private, ignored assets; validate their integrity when present.
    for folder in manifest:
        for file in folder['files']:
            p = root/folder['folder']/file['name']
            if p.exists():
                assert hashlib.sha256(p.read_bytes()).hexdigest() == file['sha256']
    for sid, name, *_ in ENTRIES:
        p = find_pdf(sid, name, [])
        if any(root.glob('*/*.pdf')):
            assert p, sid


def test_library_matches_resolve_to_shared_groups(tmp_path, monkeypatch):
    from studio import engine
    from vectorascore import style as library
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path))
    monkeypatch.setattr(engine, 'match_style', lambda p, ex=None: {'style_id':None})
    monkeypatch.setattr(library, 'units', lambda *a: {})
    monkeypatch.setattr(library, 'measure', lambda *a: {})
    for group in styles.GROUPS:
        for sid in group['library_ids']:
            monkeypatch.setattr(library, 'match', lambda *a, sid=sid: {'style':sid,'candidates':[]})
            assert engine.detect_style(None, {})['style_id'] == group['id']


def test_new_style_has_independent_history(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path))
    source=styles.get_style('bd-ghostscript', draft=True)
    new=styles.save_draft('new-office', {'name':'New office', 'calibration':source['calibration'], 'rules':source['rules']})
    assert new['signatures']==[]
    assert not {'merged_members','source_drafts','library_id','library_ids'} & new.keys()
    entry=styles.registry()['styles']['new-office']
    assert entry['releases']==[] and entry['active'] is None
    assert new['rules']==source['rules']
