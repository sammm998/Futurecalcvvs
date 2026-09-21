import base64
from io import BytesIO
from types import SimpleNamespace as NS

import pymupdf
from PIL import Image

import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))

from app.drawing_evidence import visual_evidence
from app.source_model import AssignmentTransport


def test_model_images_exclude_reference_annotations_and_preserve_original_file(tmp_path):
    path=tmp_path/'drawing.pdf'
    doc=pymupdf.open();page=doc.new_page(width=400,height=400)
    page.draw_line((20,20),(300,20),color=(0,0,0),width=2)
    mark=page.add_rect_annot((40,40,200,200));mark.set_colors(stroke=(1,0,0),fill=(1,0,0));mark.update()
    doc.save(path);doc.close();original=path.read_bytes()
    parts,audit=visual_evidence(path,0,[{'points':[[20,20],[300,20]]}])
    assert 1<len(audit)<=7 and all(not a['annotations_included'] for a in audit)
    for part in parts:
        if part['type']!='input_image':continue
        im=Image.open(BytesIO(base64.b64decode(part['image_url'].split(',')[1]))).convert('RGB')
        assert not any(r>g+30 and r>b+30 for r,g,b in im.getdata())
    assert path.read_bytes()==original
    with pymupdf.open(path) as check:assert len(list(check[0].annots()))==1


def test_page_context_survives_style_binding_and_image_audit_is_recorded(monkeypatch):
    import app.drawing_evidence as evidence
    monkeypatch.setattr(evidence,'visual_evidence',lambda *args:([{'type':'input_text','text':'image context'}],[{'annotations_included':False}]))
    calls=[]
    def create(**kw):
        calls.append(kw)
        return NS(status='completed',output_text='{"decisions":[]}',usage=None,model='test',id='test')
    t=AssignmentTransport(NS(responses=NS(create=create)),'test').for_page(NS(source_path='drawing.pdf',info=NS(index=2))).for_style({'rules':[]})
    t([{'stretch':1,'points':[[0,0],[10,0]],'candidates':[]}])
    assert calls[0]['input'][1]['content'][0]['type']=='input_text'
    assert t.usage[0]['drawing_images']==[{'annotations_included':False}]
