"""A riser on a heating pipe of connection size is the branch up through the slab to a radiator: 1.0 m, not a storey."""
from vvs_engine.measure.measure import slab_riser_height, SLAB_RISER_M


def test_a_radiator_connection_through_the_slab_is_a_metre():
    assert slab_riser_height({"base": "VS1-S13", "dn": 12}) == SLAB_RISER_M
    assert slab_riser_height({"base": "VS1-S13-W", "dn": 15}) == SLAB_RISER_M


def test_a_heating_stack_a_copper_riser_and_other_systems_are_a_storey():
    assert slab_riser_height({"base": "VS1-S13", "dn": 22}) is None       # a stack, not a connection
    assert slab_riser_height({"base": "VS1-R1", "dn": 12}) is None        # copper heating riser: a full storey
    assert slab_riser_height({"base": "KV1-X31", "dn": 16}) is None       # tap water
    assert slab_riser_height({"base": "S2-P5", "dn": 110}) is None        # waste
    assert slab_riser_height({"base": "VS1-S13", "dn": None}) is None     # no size: nothing said


def test_the_export_counts_a_radiator_connection_as_a_metre():
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    from app.exports import _rows
    row = {"designation": "VS1-S13-12", "base": "VS1-S13", "dn": 12, "confirmed_horizontal_m": 10.0,
           "confirmed_total_m": 10.0, "vertical_m": "UNKNOWN", "ambiguous_m": 0.0, "state": "CONFIRMED",
           "riser_count": 4, "riser_count_from_labels": 4, "riser_height_m": SLAB_RISER_M}
    stack = {**row, "designation": "S2-P5-110", "base": "S2-P5", "dn": 110}
    stack.pop("riser_height_m")
    got = {r["designation"]: r for r in _rows("", 2.8, rows=[row, stack])}
    assert got["VS1-S13-12"]["vertical_m"] == 4.0 and got["VS1-S13-12"]["confirmed_total_m"] == 14.0
    assert "4 genom bjälklag x 1 m" in got["VS1-S13-12"]["vertical_source"]
    assert abs(got["S2-P5-110"]["vertical_m"] - 11.2) < 1e-9


def test_a_row_split_between_storeys_and_slab_counts_each_at_its_own_height():
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    from app.exports import _rows
    row = {"designation": "VS1-S13-12", "base": "VS1-S13", "dn": 12, "confirmed_horizontal_m": 0.0,
           "confirmed_total_m": 0.0, "vertical_m": "UNKNOWN", "ambiguous_m": 0.0, "state": "CONFIRMED",
           "riser_count": 36, "riser_count_from_labels": 36, "riser_height_m": SLAB_RISER_M, "riser_slab_count": 16}
    got = _rows("", 2.8, rows=[row])[0]
    assert (got["risers_storey"], got["risers_slab"]) == (20, 16)
    assert abs(got["vertical_m"] - (20 * 2.8 + 16 * SLAB_RISER_M)) < 1e-9


def test_the_reader_sets_how_many_risers_go_through_the_slab():
    from vvs_engine.corrections import apply
    row = {"designation": "VS1-S13-12", "dn": 12, "confirmed_horizontal_m": 5.0, "confirmed_total_m": 5.0,
           "riser_count": 36, "riser_count_from_labels": 30, "riser_slab_count": 36}
    out = apply([row], [{"kind": "riser_height", "designation": "VS1-S13-12", "payload": {"slab": 16}},
                        {"kind": "riser_height", "designation": "VS1-S13-12", "payload": {"slab": 99}, "created_at": "z"}], None)
    q = out["quantities"][0]
    assert q["riser_slab_count"] == 36 and q["confirmed_horizontal_m"] == 5.0     # clamped to the row's risers
    out = apply([row], [{"kind": "riser_height", "designation": "VS1-S13-12", "payload": {"slab": 16}}], None)
    assert out["quantities"][0]["riser_slab_count"] == 16 and out["applied"][0]["applied"]
    bad = apply([row], [{"kind": "riser_height", "designation": "VS1-S13-12", "payload": {}}], None)
    assert not bad["applied"][0]["applied"]
