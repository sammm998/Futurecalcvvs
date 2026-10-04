"""A file exported without CAD layers: the pen stands in for the layer, and a connection tube takes its system
from the labelled pipe it joins."""
from types import SimpleNamespace

from vvs_engine.pipes.ownership import PrimState, _declared_by_join, identity_from_text
from vvs_engine.source_rules.native_assignment import PEN_LAYER, pen_layers


def test_a_stretch_without_a_layer_is_shown_with_its_pen():
    A = {"nodes": [], "stretches": [{"id": 0, "layer": "", "width": 1.44}, {"id": 1, "layer": "V-52BB", "width": 2.04}]}
    got = pen_layers(A)
    assert got["stretches"][0]["layer"] == f"{PEN_LAYER}1.44 pt"
    assert got["stretches"][1]["layer"] == "V-52BB"
    assert A["stretches"][0]["layer"] == ""                       # the reading's own graph is not changed


def test_a_layered_graph_is_passed_as_it_is():
    A = {"nodes": [], "stretches": [{"id": 0, "layer": "V-52BB", "width": 1.44}]}
    assert pen_layers(A) is A


def _row(text, system):
    return SimpleNamespace(text=text, dn=16, system_token=system, stem=text.rsplit("-", 1)[0])


def _graph(owner_system):
    # prim 0 and 1: the unlabelled tube; prim 2: the labelled pipe it joins at node 1
    g = SimpleNamespace(prim_nodes={0: (0, 1), 1: (1, 2), 2: (1, 3)})
    owned = PrimState(state="CONFIRMED", identity=identity_from_text(f"{owner_system}-X7-20", 20, owner_system, None))
    return g, {0: PrimState(), 1: PrimState(), 2: owned}


def test_a_tube_takes_the_declared_pipe_of_the_one_system_it_joins():
    declared = [_row("KV1-X31-16", "KV1"), _row("VV1-X31-16", "VV1")]
    g, st = _graph("KV1")
    assert _declared_by_join(g, st, [0, 1], declared).text == "KV1-X31-16"


def test_a_tube_joining_no_declared_system_gets_nothing():
    declared = [_row("KV1-X31-16", "KV1"), _row("VV1-X31-16", "VV1")]
    g, st = _graph("VS1")
    assert _declared_by_join(g, st, [0, 1], declared) is None
