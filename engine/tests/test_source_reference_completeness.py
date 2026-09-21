"""Imported references retain the meanings that a flat code list used to discard."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_every_preserved_archive_member_matches_its_hash():
    manifest=json.loads((ROOT/'reference_sources/manifest.json').read_text())
    for source in manifest['sources']:
        assert len({r['file'] for r in source['files']})==len(source['files'])
        for r in source['files']:
            if 'copy' in r:
                p=ROOT/r['copy']
                assert p.is_file(),r
                assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
            else:
                assert r['disposition']=='non_rule_binary_not_loaded'
                assert not r['file'].endswith(('.py','.json','.md','.xml','.jsonl'))


def test_all_tables_and_prose_are_lossless_in_the_app_reference():
    kb=json.loads((ROOT/'backend/app/data/swedish-vvs-knowledge.json').read_text())
    source=ROOT/'reference_sources/swedish-vvs-drawings-main'
    expected={str(p.relative_to(source)):p for folder in ['data','references'] for p in (source/folder).iterdir() if p.is_file()}
    actual={d['file']:d for d in kb['documents'] if d['source']=='swedish-vvs-drawings-main'}
    assert actual.keys()==expected.keys()
    for name,p in expected.items():assert actual[name]['content']==p.read_text()
    assert kb['completeness']['swedish_tables']==24
    for d in kb['documents']:assert isinstance(d['title'],str)


def test_collisions_and_instrument_codes_keep_their_separate_meanings():
    kb=json.loads((ROOT/'backend/app/data/swedish-vvs-knowledge.json').read_text())
    db=[e for e in kb['entries'] if e['code']=='DB']
    assert {e['source_file'] for e in db}=={'sanitary_fixtures.json','drainage_wells.json'}
    assert all(e['notes'] for e in db)
    for code,field in [('GF','sensor_code'),('MF','instrument_code')]:
        item=next(e for e in kb['entries'] if e['code']==code and e['code_field']==field)
        assert item['term_sv']=='Flöde'
    for d in kb['documents']:
        assert d['use']=='reference_only'


def test_annotation_import_keeps_custom_attributes_metadata_and_bluebeam(tmp_path):
    spec=importlib.util.spec_from_file_location('training_index',ROOT/'tools/build_training_index.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    src=tmp_path/'source';src.mkdir();out=tmp_path/'out'
    content='''<annotations><meta><task><name>Example</name></task></meta>
    <image id="1" name="drawing.png" width="100" height="100"><box label="pipe" xtl="1" ytl="2" xbr="10" ybr="20" group_id="3"><attribute name="DN">75</attribute><attribute name="DN">110</attribute></box></image></annotations>'''
    (src/'cvat.xml').write_text(content)
    (src/'bb.xml').write_text('<MarkupSummary Document="A.pdf"><Markup><Ämne>S3-110</Ämne><Längd unit="m">1,25</Längd></Markup></MarkupSummary>')
    report=module.convert(src,out)
    assert not report['errors'];assert report['records']==1;assert report['bluebeam_records']==1
    row=json.loads((out/'annotations.jsonl').read_text())
    assert [r['text'] for r in row['annotation_children']]==['75','110']
    assert row['attributes']['group_id']=='3'
    raw=out/'source_xml'/(hashlib.sha256(content.encode()).hexdigest()+'.xml')
    assert raw.read_text()==content
    source=next(s for s in json.loads((out/'sources.json').read_text()) if s['path']=='cvat.xml')
    assert source['metadata']['children'][0]['children'][0]['text']=='Example'
    bb=json.loads((out/'bluebeam.jsonl').read_text())
    assert bb['record']['children'][1]['attributes']=={'unit':'m'}
    assert bb['record']['children'][1]['text']=='1,25'
