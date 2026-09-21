"""En DN35-stigare möter en vågrät ledning i en knut; strax under den löper en DN22-ledning på pennans
paravstånd. Parregeln såg den vågräta som oägd och parallell med DN22 på rätt avstånd - och gav den DN22.
Stigarens egen ledning stannade då vid en DN-gräns som läsningen själv hade ritat (W-50-1-A0134, VS1-S13-35:
22 av 81 m, med DN22 utan en enda meter i facit).

Grannen tvärs över glappet säger vilket par det är; grannen i noden säger vad ledningen sitter ihop med, och
en förbindelse går före ett avstånd. En oägd ledning som delar nod med en namngiven av annan identitet är
knutens sak att avgöra, inte parets. Provet bygger grafen för hand så att just den regeln prövas.
"""
from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.ownership import PAIRED_REASON, Identity, PrimState, _pair_unowned_runs
from vvs_engine.pipes.representation import Prim, build_graph

FAM = "|s|w1.44|c(0.0, 0.0, 0.0)"
PAIR = 17.0


def _prim(i, x0, y0, x1, y1):
    return Prim(prim_id=i, pid=f"p{i}", seg_index=0, seg=Seg(x0, y0, x1, y1), family=FAM, layer="", width=1.44)


def _graph(with_riser: bool):
    prims = [
        _prim(0, 80, 120, 307, 120), _prim(1, 80, 120 + PAIR, 307, 120 + PAIR),     # bladets bevis: ett DN22-par
        _prim(2, 460, 400, 670, 400),                                                # den vågräta, oägd
        _prim(3, 460, 400 + PAIR, 670, 400 + PAIR),                                  # DN22 på paravståndet under
    ]
    if with_riser:
        prims.append(_prim(4, 500, 250, 500, 400))                                   # stigaren, DN35, in i knuten
    g = build_graph(prims, FAM)
    dn22 = Identity(base="VS1-S13", dn=22, system="VS1", display="VS1-S13-22")
    dn35 = Identity(base="VS1-S13", dn=35, system="VS1", display="VS1-S13-35")
    st = {pid: PrimState() for pid in g.prims}
    for pid, p in g.prims.items():
        y = p.seg.y0
        if abs(y - 120) < 0.1 or abs(y - 120 - PAIR) < 0.1 or abs(y - 400 - PAIR) < 0.1:
            st[pid] = PrimState(state="CONFIRMED", identity=dn22, reason="chain_from_anchor", anchors={"a22"})
        elif abs(p.seg.x0 - 500) < 0.1 and abs(p.seg.x1 - 500) < 0.1:
            st[pid] = PrimState(state="CONFIRMED", identity=dn35, reason="chain_from_anchor", anchors={"a35"})
    return g, st


def _horizontal_states(g, st):
    return {st[pid].state + ":" + (st[pid].identity.display if st[pid].identity else "-")
            for pid, p in g.prims.items() if abs(p.seg.y0 - 400) < 0.1 and abs(p.seg.y1 - 400) < 0.1}


def test_the_horizontal_the_riser_joins_is_left_to_the_junction():
    g, st = _graph(with_riser=True)
    _pair_unowned_runs(g, st)
    assert _horizontal_states(g, st) == {"UNOWNED:-"}, _horizontal_states(g, st)


def test_without_the_riser_the_same_horizontal_is_the_pairs_other_line():
    g, st = _graph(with_riser=False)
    n = _pair_unowned_runs(g, st)
    assert n >= 1 and _horizontal_states(g, st) == {"CONFIRMED:VS1-S13-22"}, _horizontal_states(g, st)
    assert all(st[pid].reason == PAIRED_REASON for pid, p in g.prims.items() if abs(p.seg.y0 - 400) < 0.1 and abs(p.seg.y1 - 400) < 0.1)
