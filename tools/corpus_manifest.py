"""Read-only inventory of drawing sources and annotations. Never imported by inference."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import zipfile
import pymupdf
from defusedxml import ElementTree


def inventory(root: Path):
    documents, annotations, other, archives = [], [], [], []
    seen = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or not path.stat().st_size:
            continue
        data=path.read_bytes(); sha=hashlib.sha256(data).hexdigest()
        rec={'path':str(path.relative_to(root)),'sha256':sha,'bytes':len(data)}
        ext=path.suffix.lower()
        if ext=='.pdf':
            if sha in seen:
                rec.update(duplicate_of=seen[sha]['path'],pages=seen[sha].get('pages'),annotation_count=seen[sha].get('annotation_count'))
            else:
                try:
                    with pymupdf.open(stream=data,filetype='pdf') as doc:
                        rec.update(pages=len(doc),encrypted=bool(doc.needs_pass))
                        if not doc.needs_pass:
                            rec['annotation_count']=sum(sum(1 for _ in page.annots()) for page in doc)
                            rec['sizes']=[[round(p.rect.width,2),round(p.rect.height,2)] for p in doc]
                except Exception as e:
                    rec['error']=str(e)
                seen[sha]=rec
            rec['role']='marked_reference' if rec.get('annotation_count',0) else 'unmarked_candidate'
            # A name-group keeps marked/unmarked variants and re-exports together.
            rec['drawing_group']=re.sub(r'[^A-Z0-9]','',path.stem.upper().replace('PROCESSED','').replace('CLEAR',''))
            documents.append(rec)
        elif ext=='.xml':
            try:
                xml=ElementTree.fromstring(data)
                rec['format']=xml.tag
                if xml.tag=='annotations':
                    rec['images']=[{'name':im.get('name'),'width':im.get('width'),'height':im.get('height'),
                                    'shapes':dict(Counter(x.tag for x in im)),
                                    'labels':dict(Counter(x.get('label') for x in im))} for im in xml.findall('image')]
                elif xml.tag=='MarkupSummary':
                    rec['document']=xml.get('Document')
                    totals=defaultdict(float)
                    for item in xml.findall('Markup'):
                        node=item.find('Längd')
                        if node is not None and node.get('unit')=='m' and node.text:
                            totals[item.findtext('Ämne') or 'UNKNOWN']+=float(node.text.replace(' ','').replace(',','.'))
                    rec['reference_total_m_by_designation']={k:round(v,6) for k,v in totals.items()}
                annotations.append(rec)
            except Exception as e:
                rec['error']=str(e);annotations.append(rec)
        elif ext=='.zip':
            with zipfile.ZipFile(path) as z:
                rec['members']=[{'name':i.filename,'bytes':i.file_size} for i in z.infolist() if not i.is_dir()]
            archives.append(rec)
        else:
            other.append(rec)
    return {'schema_version':1,'source_root':str(root.resolve()),'documents':documents,
            'annotations':annotations,'archives':archives,'other':other,
            'summary':{'pdf_files':len(documents),'unique_pdf_bytes':len(seen),
                       'pdf_duplicates':len(documents)-len(seen),'xml_files':len(annotations),
                       'cvat_files':sum(r.get('format')=='annotations' for r in annotations),
                       'bluebeam_files':sum(r.get('format')=='MarkupSummary' for r in annotations),
                       'archive_pdf_members':sum(m['name'].lower().endswith('.pdf') for a in archives for m in a['members']),
                       'errors':sum('error' in r for r in documents+annotations)}}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=inventory(a.root);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result['summary'],ensure_ascii=False))
