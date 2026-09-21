"""Closed outline bows remain punctuation; straight and slanted bars do not."""
import math
from types import SimpleNamespace
import pytest
from vvs_engine.geometry.core import Seg
from vvs_engine.text.vector_text import _structural_char


def outline(bow, angle, slope=0):
    # Same uniform stroke thickness, filled as a closed polygon. No font or
    # vocabulary tells the reader whether the figure is punctuation.
    pts = [(bow*4*t*(1-t)+slope*t+side, 10*t)
           for side, values in ((-.25, range(21)), (.25, range(20,-1,-1)))
           for i in values for t in (i/20,)]
    a = math.radians(angle)
    pts = [(x*math.cos(a)-y*math.sin(a), x*math.sin(a)+y*math.cos(a)) for x,y in pts]
    segs = [Seg(*p,*q) for p,q in zip(pts,pts[1:]+pts[:1])]
    return SimpleNamespace(comps=[SimpleNamespace(kind='f')],kind='f',segs=segs)


@pytest.mark.parametrize('angle',[0,-90,30])
@pytest.mark.parametrize('bow,char',[(-1.2,'('),(1.2,')'),(0,None)])
def test_outline_bow_is_read_from_its_ink(angle,bow,char):
    assert _structural_char(outline(bow,angle),SimpleNamespace(height=8.5,angle=angle)) == char


def test_slanted_bar_is_not_a_parenthesis():
    assert _structural_char(outline(0,0,slope=1.2),SimpleNamespace(height=8.5,angle=0)) is None
