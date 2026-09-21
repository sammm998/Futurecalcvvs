from types import SimpleNamespace
import pytest
from vvs_engine.text.ocr_assist import resolve_unknown_glyphs


@pytest.mark.parametrize('vector,ocr,confidence,expected',[
    ('SpIIIVa??en','Spillvatten',.99,'SpILLVaTTen'),
    ('An?nin9sIu??','Andningsluft',.99,'AnDninGsLuFT'),
    ('SpIIIVa??en','Spillvatten',.90,'SpIIIVa??en'),
    ('KV-1?-9','KV-l2-g',.99,'KV-1?-9'),
    ('syst9-?0','systg-10',.99,'syst9-?0'),
    ('SpIIIVa??en','Spollvatten',.99,'SpIIIVa??en'),
])
def test_prose_twins_need_local_ocr_agreement(monkeypatch,vector,ocr,confidence,expected):
    row=SimpleNamespace(glyphs=[SimpleNamespace(char=c,bbox=(i*10,0,i*10+8,7),
                        source='outline',score=.1) for i,c in enumerate(vector)],text=vector)
    monkeypatch.setattr('vvs_engine.review.ocr_check.ocr_words',
                        lambda *a,**k:[(ocr,[0,0,len(vector)*10,7],confidence)])
    report=resolve_unknown_glyphs(SimpleNamespace(),[row])
    assert row.text==expected
    assert report['resolved'] == vector.count('?')-expected.count('?')
    assert all('previous' in a and 'reason' in a for a in report['adopted'])
