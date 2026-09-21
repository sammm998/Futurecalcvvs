"""An explicit pair of connections names the terminating runs, not the symbol stem."""
from types import SimpleNamespace as NS
from test_zero_length_strokes_do_not_hide_pipes import path
from vvs_engine.semantics.attachment import GeometryIndex, family_of, leader_contacts
from vvs_engine.semantics.leaders import Leader


def test_pair_points_to_transverse_ports_instead_of_overprinted_stem():
    def square(pid,y):
        return path(pid,[(98.6,y-1.4),(101.4,y-1.4),(101.4,y+1.4),(98.6,y+1.4),(98.6,y-1.4)])
    objects=[square('first',100),square('second',102),
             path('stem',[(100,80),(100,130)],width=.5),
             path('supply',[(50,100),(98.6,100)],width=1.),
             path('return',[(50,102),(98.6,102)],width=.5)]
    index=GeometryIndex(NS(paths=objects),set(),set())
    leader=Leader('L',0,'B',[],[(100,75),(100,102)],(100,75),(100,102),'underline_end','notes',.25)
    contacts=leader_contacts(leader,index,{family_of(p) for p in objects},{p.pid:p for p in objects})
    assert {c.pid for c in contacts}=={'supply','return'}
    assert all(c.mark_id.startswith('explicit_symbol:') for c in contacts)
