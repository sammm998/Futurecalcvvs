"""A vent written on a pipe - `S1-P2 / 75(L)` - is that pipe in the takeoff, not a system of its own."""
from vvs_engine.measure.measure import _fold_vent_rows


def row(designation, base, dn, m=0.0, pipes=0, labels=1, risers=1):
    return {"designation": designation, "base": base, "dn": dn, "physical_pipe_count": pipes, "confirmed_horizontal_m": m,
            "confirmed_total_m": m, "ambiguous_pdf_units": 0.0, "pipe_ids": [f"p{designation}"] if pipes else [],
            "label_count": labels, "riser_count_from_labels": risers, "riser_count": risers}


def test_a_vent_label_with_nothing_measured_is_no_row():
    rows = {"S1-P2-(L)|DN75": row("S1-P2-(L)", "S1-P2-(L)", 75), "S1-P2|DN75": row("S1-P2-75", "S1-P2", 75, 4.5, 3, 8, 4)}
    _fold_vent_rows(rows)
    assert list(rows) == ["S1-P2|DN75"]
    assert rows["S1-P2|DN75"]["riser_count_from_labels"] == 4 and rows["S1-P2|DN75"]["label_count"] == 8


def test_a_vents_metres_go_to_the_pipe_it_vents():
    rows = {"S2-P5-(L)|DN110": row("S2-P5-110 (L)", "S2-P5-(L)", 110, 0.4, 1), "S2-P5|DN110": row("S2-P5-110", "S2-P5", 110, 10.0, 4)}
    _fold_vent_rows(rows)
    assert list(rows) == ["S2-P5|DN110"]
    assert abs(rows["S2-P5|DN110"]["confirmed_horizontal_m"] - 10.4) < 1e-9 and rows["S2-P5|DN110"]["physical_pipe_count"] == 5


def test_a_measured_vent_with_no_plain_row_becomes_the_plain_row():
    rows = {"S3-R8-(L)|DN110": row("S3-R8-110L", "S3-R8-(L)", 110, 0.6, 1)}
    _fold_vent_rows(rows)
    assert list(rows) == ["S3-R8|DN110"] and rows["S3-R8|DN110"]["designation"] == "S3-R8-110"
