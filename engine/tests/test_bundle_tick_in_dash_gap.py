from types import SimpleNamespace as NS
import pymupdf
from vvs_engine.pdf.extract import extract_document
from vvs_engine.semantics.leaders import Leader
from vvs_engine.semantics.attachment import GeometryIndex, leader_contacts, family_of


def contacts(tmp_path, tick=True, gap=4):
    pdf=tmp_path/'bundle.pdf'
    with pymupdf.open() as doc:
        p=doc.new_page(width=200,height=200)
        p.draw_line((20,50),(180,50),width=1)
        p.draw_line((20,70),(100-gap/2,70),width=1.5)
        p.draw_line((100+gap/2,70),(180,70),width=1.5)
        doc.save(pdf)
    page=extract_document(str(pdf)).pages[0]
    leader=Leader('leader',0,'label',[],[(100,100),(100,50)],(100,100),(100,50),
                  'underline_end','text',.3,
                  crossing_marks=[NS(mid='tick',bbox=(99,69,101,71))] if tick else [])
    families={family_of(p) for p in page.paths}
    return leader_contacts(leader,GeometryIndex(page,set(),set()),families,{p.pid:p for p in page.paths})


def test_bundle_retains_explicit_tick_in_gap_after_another_pipe_was_hit(tmp_path):
    found=contacts(tmp_path)
    assert len({c.family for c in found})==2
    assert len([c for c in found if c.mark_id=='tick'])==2


def test_unmarked_crossing_does_not_add_another_pipe(tmp_path):
    assert len({c.family for c in contacts(tmp_path,tick=False)})==1


def test_tick_does_not_bridge_an_arbitrarily_large_break(tmp_path):
    assert len({c.family for c in contacts(tmp_path,gap=25)})==1
