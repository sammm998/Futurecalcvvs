"""Reproducible, lossless reference import from the two supplied source archives.

Imported source text is data, never executable policy. Runtime support must be
reviewed separately; imported conventions do not silently change quantities.
"""
from __future__ import annotations
import argparse, ast, hashlib, json, zipfile
from pathlib import Path, PurePosixPath


SWEDISH_TITLES = {'apparatus.json': 'Apparater', 'as_built_requirements.json': 'Relationshandlingar', 'contractor_codes.json': 'Entreprenörskoder', 'control_devices.json': 'Styrdon', 'discipline_codes.json': 'Disciplinkoder', 'document_change_handling.json': 'Ändringar av handlingar', 'document_rules.json': 'Ritningar och beskrivningar', 'document_status.json': 'Handlingsstatus', 'dou_instructions.json': 'Drift och underhåll', 'drainage_wells.json': 'Brunnar', 'drawing_categories.json': 'Ritningskategorier', 'drawing_content_classification.json': 'Ritningens innehåll', 'drawing_numbering.json': 'Ritningsnumrering', 'level_references.json': 'Nivåer och lägen', 'line_types.json': 'Linjetyper', 'meta.json': 'Källinformation', 'pipe_marking_rules.json': 'Rörbeteckningar', 'pipe_symbols.json': 'Rörsymboler', 'sanitary_fixtures.json': 'Sanitetsinredning', 'sensors_instruments.json': 'Givare och instrument', 'side_contractor_equipment.json': 'Sidoentreprenörers utrustning', 'system_designations.json': 'Systembeteckningar', 'valves.json': 'Ventiler', 'vertical_pipe_notation.json': 'Vertikala rör och strecknotation'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(archives, root):
    entries, documents, sources, rules, functions = [], [], [], [], []
    dest = root/'reference_sources'
    for archive in archives:
        source = archive.stem
        records = []
        with zipfile.ZipFile(archive) as z:
            for info in sorted(z.infolist(), key=lambda i:i.filename):
                if info.is_dir(): continue
                parts = PurePosixPath(info.filename).parts
                if len(parts)<2 or parts[0]!=source or any(p in ('.','..') for p in parts) or PurePosixPath(info.filename).is_absolute():
                    raise ValueError(f'Unexpected archive path: {info.filename}')
                name = '/'.join(parts[1:]); data = z.read(info)
                rec = dict(file=name, sha256=sha(data), bytes=len(data))
                # Preserve all source/configuration/document files without importing or running them.
                try: content = data.decode('utf-8')
                except UnicodeDecodeError: content = None
                if content is not None and '\0' not in content:
                    target = dest/source/name; target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                    rec.update(disposition='preserved_source',copy=str(target.relative_to(root)))
                    if name.endswith('.py'):
                        tree=ast.parse(content,filename=name)
                        for node in ast.walk(tree):
                            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                                functions.append(dict(source=source,file=name,name=node.name,line=node.lineno,
                                    docstring=ast.get_docstring(node),runtime_status='source_only_not_automatically_ported'))
                elif name=='models/model_dynamic.onnx' and (root/'models/pipestudio-labels.onnx').exists():
                    assert sha((root/'models/pipestudio-labels.onnx').read_bytes())==rec['sha256']
                    rec.update(disposition='existing_optional_label_detector',copy='models/pipestudio-labels.onnx')
                else:
                    rec.update(disposition='non_rule_binary_not_loaded',reason='UI asset or legacy runtime state; retained in the supplied ZIP')
                records.append(rec)
                swedish = source=='swedish-vvs-drawings-main'
                domain_doc = (swedish and (name.startswith('data/') or name.startswith('references/')) or
                    not swedish and (name.startswith('vectorascore/data/') and name.endswith('.json') or
                    name in ['REVIEW_RULES_MAP.md','PIPE_STUDIO.md','docs/reviews/feedback-2026-09-10.md',
                             'docs/feedback-workflow.md','docs/global-first-learning.md','detection_v2/style-release.json']))
                if not domain_doc: continue
                parsed=json.loads(content) if name.endswith('.json') else None
                title=(parsed.get('description') or parsed.get('name') or parsed.get('category') or name) if isinstance(parsed,dict) else next((l.lstrip('# ') for l in content.splitlines() if l.startswith('# ')),name)
                title = SWEDISH_TITLES.get(name.split('/')[-1], title) if swedish else (parsed.get('name') or name) if isinstance(parsed,dict) else title
                documents.append(dict(id=sha((source+'/'+name).encode())[:24],source=source,file=name,title=title,
                    sha256=rec['sha256'],format='json' if parsed is not None else 'text',content=content,
                    use='reference_only', archived='/archive/' in name))
                if swedish and name.startswith('data/'):
                    for index,e in enumerate(parsed.get('entries',[])):
                        for field in ('code','sensor_code','instrument_code'):
                            if not e.get(field): continue
                            entries.append({**e,'code':e[field],'code_field':field,'entry_index':index,
                                'term_sv':e.get('term_sv') or e.get('quantity_sv') or e.get('title',''),
                                'term_en':e.get('term_en') or e.get('quantity_en') or e.get('title_en',''),
                                'source_file':name.split('/')[-1],'source':source,'source_document':documents[-1]['id']})
                if not swedish and isinstance(parsed,dict):
                    for rule in parsed.get('rules',[]):
                        rules.append(dict(source_file=name,style_id=parsed.get('id'),archived='/archive/' in name,
                                          definition=rule,runtime_status='reference_only_not_executed'))
        sources.append(dict(source=source,archive=archive.name,archive_sha256=sha(archive.read_bytes()),files=records,
                            annotation_files=[r['file'] for r in records if r['file'].lower().endswith(('.xml','.jsonl'))]))
    manifest=dict(schema_version=1,sources=sources,functions=functions,style_rules=rules,
        policy='Every archive member is accounted for. Source snapshots are inert. Reference import is not runtime equivalence or an accuracy claim.')
    dest.mkdir(exist_ok=True)
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    knowledge=dict(source='swedish-vvs-drawings-main',archive_sha256=sources[0]['archive_sha256'],
        files=[dict(file=r['file'].split('/')[-1],sha256=r['sha256']) for r in sources[0]['files'] if r['file'].startswith('data/')],
        entries=entries,documents=documents,
        completeness=dict(swedish_tables=sum(d['source']=='swedish-vvs-drawings-main' and d['file'].startswith('data/') for d in documents),
                          documents=len(documents),source_files=sum(len(s['files']) for s in sources),style_rule_instances=len(rules)),
        policy='Full source definitions and collisions are preserved. The project legend governs interpretation. These references do not automatically alter quantities.')
    (root/'backend/app/data/swedish-vvs-knowledge.json').write_text(json.dumps(knowledge,ensure_ascii=False,indent=2)+'\n')
    return knowledge['completeness']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--swedish',type=Path,required=True);p.add_argument('--pipestudio',type=Path,required=True);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args()
    print(json.dumps(build([a.swedish,a.pipestudio],a.root)))
