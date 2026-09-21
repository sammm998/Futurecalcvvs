"""Separate pointers on one leader, with nearby unrelated pipework."""
from types import SimpleNamespace

import pytest

from test_zero_length_strokes_do_not_hide_pipes import path
from vvs_engine.semantics.attachment import GeometryIndex, family_of, leader_contacts, resolve_block
from vvs_engine.semantics.leaders import Leader


def reading(off_line=False, fork=False):
    def square(pid, x, y):
        return path(pid, [(x-1.4,y-1.4),(x+1.4,y-1.4),(x+1.4,y+1.4),(x-1.4,y+1.4),(x-1.4,y-1.4)])
    y2 = 105 if off_line else 100
    first, second = square('first',100,100), square('second',110,y2)
    supply = path('supply',[(100,98.6),(100,50)],width=.5)
    ret = path('return',[(110,y2-1.4),(110,50)],width=1.0)
    # This thick bypass ends INSIDE the second circle, away from the leader
    # and its centre. It has no rim connection to the indicated riser.
    bypass = path('bypass',[(109.1,y2-.7),(109.1,150)],width=2.)
    objects = [first,second,supply,ret,bypass]
    if fork:
        objects.append(path('other-system',[(111.4,y2),(170,y2)],width=2.))
    paths = {p.pid:p for p in objects}
    index = GeometryIndex(SimpleNamespace(paths=objects),set(),set())
    leader = Leader('L',0,'B',[],[(140,100),(100,100)],(140,100),(100,100),
                    'underline_end','',.5,color=(0.,0.,0.))
    contacts = leader_contacts(leader,index,{family_of(p) for p in objects},paths)
    row = SimpleNamespace(did='D',page=0,text='RAD1-X31-16',display_text='RAD1-X31-16',
                          system_token='RAD1',dn=16,multiplier=1,row_index=0)
    anchors = resolve_block(SimpleNamespace(bid='B'),[row],leader,contacts,{'RAD1'},paths=paths,gidx=index)
    return contacts, anchors


def test_one_label_names_both_explicit_risers_across_two_pens():
    contacts, anchors = reading()
    assert {c.pid for c in contacts} == {'supply','return'}
    assert all(c.mark_id.startswith('explicit_symbol:') for c in contacts)
    assert len(anchors) == 1
    assert anchors[0].state == 'VERIFIED_PIPE_ATTACHMENT'
    assert anchors[0].reason == 'single_row_explicit_symbol_pointers'


def test_a_nearby_riser_off_the_leader_is_not_named():
    contacts, anchors = reading(off_line=True)
    assert {c.pid for c in contacts} == {'supply'}
    assert anchors[0].state == 'VERIFIED_PIPE_ATTACHMENT'


def test_an_ambiguous_pointer_does_not_name_both_families():
    contacts, anchors = reading(fork=True)
    assert 'other-system' in {c.pid for c in contacts}
    assert anchors[0].state == 'AMBIGUOUS_PIPE_ATTACHMENT'
