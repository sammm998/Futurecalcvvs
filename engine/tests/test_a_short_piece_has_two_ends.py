"""En rundad böj exporteras som en kedja av mycket korta stycken - en tiondels punkt långa. Nodbygget slår ihop
ändpunkter som ligger inom en sjundedels punkt från varandra, och ett stycke kortare än så fick *båda* sina
ändar i samma nod. Noden räknade stycket två gånger: en vanlig böj kom ut som en fyrarmad knut, identiteten
stannade där i stället för att följa med runt hörnet, och fronten skrevs UNOWNED_CONTINUATION med grad fyra.
På W-50-1-A0134 var det 2 417 sådana slingor.

En linjes två ändar är två ställen, hur kort linjen än är. Nodbygget håller isär ett styckes egna ändar; allt
annat i toleransen slås ihop som förut.
"""
from collections import Counter

from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Prim, build_graph

FAM = "|s|w1.44|c(0.0, 0.0, 0.0)"


def _prim(i, x0, y0, x1, y1):
    return Prim(prim_id=i, pid=f"p{i}", seg_index=i, seg=Seg(x0, y0, x1, y1), family=FAM, layer="", width=1.44)


def _bend():
    """En lodrät ledning som viker av åt höger genom fyra korta stycken, som CAD-exporten ritar en radie."""
    return [
        _prim(0, 100.0, 100.0, 100.0, 140.0),
        _prim(1, 100.0, 140.0, 100.0, 140.12),
        _prim(2, 100.0, 140.12, 100.12, 140.24),
        _prim(3, 100.12, 140.24, 100.24, 140.36),
        _prim(4, 100.24, 140.36, 100.36, 140.36),
        _prim(5, 100.36, 140.36, 140.0, 140.36),
    ]


def test_a_piece_shorter_than_the_touch_tolerance_is_not_a_loop():
    g = build_graph(_bend(), FAM)
    for nid, n in g.nodes.items():
        assert max(Counter(n.prims).values()) == 1, f"nod {nid} räknar samma stycke två gånger: {n.prims}"


def test_the_bend_is_a_chain_and_not_a_junction():
    g = build_graph(_bend(), FAM)
    degrees = sorted(n.degree for n in g.nodes.values())
    assert degrees == [1, 1, 2, 2, 2, 2, 2], f"böjen är en kedja med två fria ändar, ingen knut: {degrees}"
