"""Detached contour caps overlap the body; diacritics sit above it."""
import math
from types import SimpleNamespace

import pytest

from test_zero_length_strokes_do_not_hide_pipes import path
from vvs_engine.text.strokes import StrokeComponent, _split_and_order


def components(strokes, angle):
    th=math.radians(angle)
    transform=lambda x,y:(50+x*math.cos(th)-y*math.sin(th),50+x*math.sin(th)+y*math.cos(th))
    result=[]
    for i, pts in enumerate(strokes):
        p=path(str(i),[transform(*pt)for pt in pts])
        result.append(StrokeComponent(str(i),'','s|w0.5',[p],p.segs,p.bbox,'s'))
    return result


@pytest.mark.parametrize('angle',[0,30,-30])
def test_a_stencil_oval_does_not_acquire_a_diacritic(angle):
    strokes=[[(1,.2),(.3,1.2),(0,3),(.3,4.8),(1,5.8)],
             [(2,5.8),(2.7,4.8),(3,3),(2.7,1.2),(2,.2)],
             [(1.2,.3),(1.3,.1),(1.5,0),(1.7,.1),(1.8,.3)],
             [(1.2,5.7),(1.3,5.9),(1.5,6),(1.7,5.9),(1.8,5.7)]]
    rows=_split_and_order(SimpleNamespace(info=SimpleNamespace(index=0)),components(strokes,angle),6.,angle)
    glyphs=[g for r in rows for g in r.glyphs]
    assert len(glyphs)==1
    assert len(glyphs[0].path_ids)==4
    assert glyphs[0].n_diacritics==0


@pytest.mark.parametrize('dots',[1,2])
def test_separate_marks_above_a_body_are_still_diacritics(dots):
    strokes=[[(0,0),(3,0),(3,6),(0,6),(0,0)]]
    strokes += [[(.5+i,-.8),(.7+i,-.8)] for i in range(dots)]
    rows=_split_and_order(SimpleNamespace(info=SimpleNamespace(index=0)),components(strokes,0),6.,0)
    glyphs=[g for r in rows for g in r.glyphs]
    assert len(glyphs)==1 and glyphs[0].n_diacritics==dots


def test_a_detached_zero_cap_still_produces_a_numeric_pipe_size(tmp_path):
    import pymupdf
    from tests.conftest import draw_hershey_text
    from vvs_engine.pdf.extract import extract_document
    from vvs_engine.pipeline import prepare_page
    doc=pymupdf.open();page=doc.new_page(width=250,height=200)
    shape=page.new_shape()
    for y in (40,75,110,145):
        x=draw_hershey_text(shape,'KV13-5',20,y,6)[2]
        strokes=[[(1,.2),(.3,1.2),(0,3),(.3,4.8),(1,5.8)],
                 [(2,5.8),(2.7,4.8),(3,3),(2.7,1.2),(2,.2)],
                 [(1.2,.3),(1.3,.1),(1.5,0),(1.7,.1),(1.8,.3)],
                 [(1.2,5.7),(1.3,5.9),(1.5,6),(1.7,5.9),(1.8,5.7)]]
        for pts in strokes:
            shape.draw_polyline([(x+a,y-6+b)for a,b in pts])
            shape.finish(width=.5,color=(0,0,0),closePath=False)
        shape.draw_line((20,y+2),(x+4,y+2))
        shape.finish(width=.5,color=(0,0,0),closePath=False)
    shape.commit();pdf=tmp_path/'zero.pdf';doc.save(pdf);doc.close()
    result=prepare_page(extract_document(str(pdf)).pages[0])
    assert len(result.designations)==4
    assert {(d.display_text,d.dn)for d in result.designations}=={('KV13-50',50)}
