"""Exported point strokes must not block a leader's route through a fitting."""
from types import SimpleNamespace

import pytest

from vvs_engine.geometry.core import Seg
from vvs_engine.pdf.extract import RawPath
from vvs_engine.semantics.attachment import GeometryIndex, family_of, leader_contacts
from vvs_engine.semantics.leaders import Leader


def path(pid, points, width=.5):
    return RawPath(pid=pid, seqno=0, page=0, layer="", layer_id=0, kind="s",
                   width=width, color=(0., 0., 0.), fill=None, closed=False,
                   segs=[Seg(*a, *b) for a, b in zip(points, points[1:])],
                   bbox=(min(x for x, y in points), min(y for x, y in points),
                         max(x for x, y in points), max(y for x, y in points)),
                   n_items=len(points)-1, n_curves=0, n_subpaths=1)


@pytest.mark.parametrize("known_families", [False, True])
def test_point_at_fitting_centre_does_not_prevent_reaching_pipe(known_families):
    # A six-point fitting, a pipe ending at its rim and a leader to its centre.
    symbol = path("fitting", [(97, 97), (103, 97), (103, 103), (97, 103), (97, 97)])
    pipe = path("pipe", [(103, 100), (180, 100)], width=2.)
    dot = path("exported-point", [(100, 100), (100, 100)], width=.72)
    lead = path("leader", [(70, 70), (100, 100)])
    paths = {p.pid: p for p in [symbol, pipe, dot, lead]}
    index = GeometryIndex(SimpleNamespace(paths=list(paths.values())), set(), set())
    leader = Leader("L", 0, "B", [SimpleNamespace(pid=lead.pid)],
                    [(70, 70), (100, 100)], (70, 70), (100, 100), "underline_end", "", .5,
                    color=(0., 0., 0.))
    contacts = leader_contacts(leader, index, {family_of(pipe)} if known_families else None, paths)
    assert "pipe" in {c.pid for c in contacts}
    assert "exported-point" not in {c.pid for c in contacts}
    assert all(c.kind == "via_symbol" for c in contacts if c.pid == "pipe")
    assert all(c.point == (103., 100.) for c in contacts if c.pid == "pipe")


def test_zero_segment_is_ignored_without_discarding_rest_of_path():
    mixed = path("mixed", [(0, 0), (0, 0), (10, 0)])
    index = GeometryIndex(SimpleNamespace(paths=[mixed]), set(), set())
    assert [(p.pid, k) for p, k, s in index.items] == [("mixed", 1)]
    assert index.hits(5, 0)[0][0].pid == "mixed"


def test_real_direct_pipe_contact_still_takes_precedence():
    symbol = path("fitting", [(97, 97), (103, 97), (103, 103), (97, 103), (97, 97)])
    direct = path("direct", [(70, 100), (130, 100)], width=2.)
    other = path("other", [(100, 103), (100, 150)], width=2.)
    paths = {p.pid: p for p in [symbol, direct, other]}
    index = GeometryIndex(SimpleNamespace(paths=list(paths.values())), set(), set())
    leader = Leader("L", 0, "B", [], [(70, 70), (100, 100)], (70, 70), (100, 100),
                    "underline_end", "", .5, color=(0., 0., 0.))
    contacts = leader_contacts(leader, index, None, paths)
    assert {c.pid for c in contacts} == {"direct"}


def test_a_verified_symbol_contact_reaches_the_ownership_seed():
    from vvs_engine.pipes.ownership import _seed_prims
    symbol = path("symbol", [(96.9, 96.9), (103.1, 96.9), (103.1, 103.1), (96.9, 103.1), (96.9, 96.9)])
    pipe = path("pipe", [(103.1, 100), (180, 100)], width=2.)
    paths = {p.pid:p for p in [symbol, pipe]}
    index = GeometryIndex(SimpleNamespace(paths=list(paths.values())), set(), set())
    leader = Leader("L", 0, "B", [], [(70, 70), (100, 100)], (70, 70), (100, 100),
                    "underline_end", "", .5, color=(0., 0., 0.))
    contacts = leader_contacts(leader, index, {family_of(pipe)}, paths)
    graph = SimpleNamespace(prims={0:SimpleNamespace(pid=pipe.pid, seg_index=0, seg=pipe.segs[0])})
    seeded = _seed_prims(SimpleNamespace(contacts=contacts), {family_of(pipe):graph})
    assert seeded[family_of(pipe)][0][0] == 0


@pytest.mark.parametrize('known', [False, True])
def test_a_pipe_beside_the_symbol_is_not_its_pipe(known):
    symbol = path('symbol', [(97, 97), (103, 97), (103, 103), (97, 103), (97, 97)])
    pipe = path('pipe', [(103.1, 100), (180, 100)], width=.5)
    # The bypass falls inside the old radius + .6 reach but never touches the
    # square. Its nearby endpoint must not qualify through the marker helper.
    bypass = path('bypass', [(103.4, 98), (103.4, 150)], width=2.)
    paths = {p.pid:p for p in [symbol, pipe, bypass]}
    index = GeometryIndex(SimpleNamespace(paths=list(paths.values())), set(), set())
    leader = Leader('L', 0, 'B', [], [(70, 70), (100, 100)], (70, 70), (100, 100),
                    'underline_end', '', .5, color=(0., 0., 0.))
    contacts = leader_contacts(leader, index, {family_of(pipe),family_of(bypass)} if known else None, paths)
    assert {c.pid for c in contacts} == {'pipe'}
    assert contacts[0].via == 'symbol'
