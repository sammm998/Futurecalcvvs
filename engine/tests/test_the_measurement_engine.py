"""Mätmotorn mot kända värden.

En mängd är ett påstående om verkligheten, och det enda som gör den kontrollerbar är att den går att räkna
efter för hand. Varje prov här har ett facit någon kan räkna ut på ett papper: en tiometerslinje i 1:50, en
tio gånger tio meters ruta med ett hål i, en detalj i 1:20 i hörnet av ett blad i 1:50.

Det viktigaste provet är det sista: zoomen finns inte i mätmotorn, och samma form ger samma mängd vid varje
förstoring. En mängd som ändrar sig när någon zoomar är inte en mängd.
"""
import math

import pytest

from vvs_engine.takeoff import (Scale, Viewport, convert, evaluate, measure, order_of_evaluation,
                                scale_from_two_points)
from vvs_engine.takeoff.formulas import FormulaError, evaluate_all
from vvs_engine.takeoff.geometry import angle_between, area_with_holes, centroid, point_in_ring
from vvs_engine.takeoff.measure import ScaleError

PT_PER_M_50 = 1.0 / (0.0003527777777777778 * 50)      # punkter per meter i skala 1:50


def test_a_scale_is_what_the_drawing_says_it_is():
    s = Scale.from_ratio(50)
    assert abs(s.ratio - 50) < 1e-9 and s.label == "1:50"
    assert abs(s.meters_per_point - 0.0176389) < 1e-6
    assert abs(Scale.from_ratio(100).meters_per_point - 2 * s.meters_per_point) < 1e-12
    with pytest.raises(ScaleError):
        Scale(meters_per_point=0.0)
    with pytest.raises(ScaleError):
        Scale.from_ratio(-1)


def test_a_calibration_is_the_line_someone_drew_over_something_they_knew():
    s = scale_from_two_points((0, 0), (100, 0), 10.0)
    assert abs(s.meters_per_point - 0.1) < 1e-12 and s.source == "UPPMÄTT"
    assert abs(scale_from_two_points((0, 0), (100, 0), 10_000, unit="mm").meters_per_point - 0.1) < 1e-12
    with pytest.raises(ScaleError):
        scale_from_two_points((0, 0), (2, 0), 10.0)          # för kort att mäta på
    with pytest.raises(ScaleError):
        scale_from_two_points((0, 0), (100, 0), 0)


def test_ten_metres_in_1_to_50_is_ten_metres():
    s = Scale.from_ratio(50)
    m = measure("langd", [(0, 0), (10 * PT_PER_M_50, 0)], s)
    assert abs(m.value - 10.0) < 1e-6 and m.unit == "m"
    assert m.steps["ratt_m"] == pytest.approx(10.0, abs=1e-4)
    # samma sträcka i 1:100 är dubbelt så många meter
    assert abs(measure("langd", [(0, 0), (10 * PT_PER_M_50, 0)], Scale.from_ratio(100)).value - 20.0) < 1e-5


def test_a_square_of_ten_by_ten_is_a_hundred_square_metres():
    s = Scale.from_ratio(50)
    d = 10 * PT_PER_M_50
    a = measure("area", [(0, 0), (d, 0), (d, d), (0, d)], s)
    assert a.value == pytest.approx(100.0, abs=1e-3) and a.unit == "m²"
    assert a.extra["perimeter"] == pytest.approx(40.0, abs=1e-3)


def test_a_hole_is_taken_out_of_the_area_and_a_hole_outside_it_is_not():
    s = Scale.from_ratio(50)
    d = 10 * PT_PER_M_50
    hole = [(2 * PT_PER_M_50, 2 * PT_PER_M_50), (4 * PT_PER_M_50, 2 * PT_PER_M_50),
            (4 * PT_PER_M_50, 4 * PT_PER_M_50), (2 * PT_PER_M_50, 4 * PT_PER_M_50)]
    a = measure("area", [(0, 0), (d, 0), (d, d), (0, d)], s, holes=[hole])
    assert a.value == pytest.approx(96.0, abs=1e-3), "hundra kvadratmeter minus fyra"
    assert a.extra["holes"] == pytest.approx(4.0, abs=1e-3)
    far = [(p[0] + 20 * PT_PER_M_50, p[1]) for p in hole]
    b = measure("area", [(0, 0), (d, 0), (d, d), (0, d)], s, holes=[far])
    assert b.value == pytest.approx(100.0, abs=1e-3), "ett hål utanför ytan är inget hål"


def test_a_volume_is_an_area_with_a_depth():
    s = Scale.from_ratio(50)
    d = 10 * PT_PER_M_50
    v = measure("volym", [(0, 0), (d, 0), (d, d), (0, d)], s, depth=0.25)
    assert v.value == pytest.approx(100.0, abs=1e-3)
    assert v.extra["volume"] == pytest.approx(25.0, abs=1e-3)
    assert v.steps["djup_m"] == 0.25


def test_a_count_is_a_count_and_needs_no_scale():
    m = measure("antal", [(0, 0), (1, 1), (2, 2)], None)
    assert m.value == 3 and m.unit == "st" and m.scale_source == "EJ_TILLÄMPLIG"
    assert measure("antal", [(0, 0), (1, 1)], None, multiplier=2).value == 4


def test_multiplier_addition_and_waste_are_each_written_out():
    s = Scale.from_ratio(50)
    m = measure("langd", [(0, 0), (10 * PT_PER_M_50, 0)], s, multiplier=2, addition=1.5, waste=10)
    assert m.raw == pytest.approx(10.0, abs=1e-4)
    assert m.value == pytest.approx(21.5, abs=1e-4)
    assert m.extra["with_waste"] == pytest.approx(23.65, abs=1e-3)
    assert m.steps["multiplikator"] == 2 and m.steps["tillagg"] == 1.5 and m.steps["spill_pct"] == 10


def test_without_a_scale_the_measure_stays_in_the_drawings_own_points():
    m = measure("langd", [(0, 0), (100, 0)], None)
    assert m.unit == "pt" and m.value == 100.0 and m.scale_source == "INGEN"
    assert any("ingen skala" in w for w in m.warnings)


def test_a_detail_in_another_scale_is_measured_in_its_own():
    """Ett blad i 1:50 med en detalj i 1:20 i hörnet: formen mäts i den skala den ligger i."""
    plan = Scale.from_ratio(50)
    detail = Viewport(name="Detalj A", ring=[(500, 500), (900, 500), (900, 900), (500, 900)],
                      scale=Scale.from_ratio(20))
    inside = measure("langd", [(600, 600), (700, 600)], plan, viewports=[detail])
    outside = measure("langd", [(100, 100), (200, 100)], plan, viewports=[detail])
    assert inside.viewport == "Detalj A" and outside.viewport == ""
    assert inside.value == pytest.approx(100 * 0.0003527778 * 20, abs=1e-4)
    assert outside.value == pytest.approx(100 * 0.0003527778 * 50, abs=1e-4)
    assert inside.value < outside.value, "samma form är färre meter i en finare skala"


def test_overlapping_viewports_are_settled_the_same_way_every_time():
    a = Viewport(name="A", ring=[(0, 0), (100, 0), (100, 100), (0, 100)], scale=Scale.from_ratio(50), order=1)
    b = Viewport(name="B", ring=[(0, 0), (100, 0), (100, 100), (0, 100)], scale=Scale.from_ratio(20), order=0)
    for order in ([a, b], [b, a]):
        m = measure("langd", [(10, 10), (60, 10)], None, viewports=order)
        assert m.viewport == "B", "den lägsta ordningen vinner, oavsett i vilken ordning de sparades"


def test_units_convert_both_ways_and_by_the_right_power():
    assert convert(1, "m", "mm") == 1000.0
    assert convert(2.5, "m", "cm") == 250.0
    assert convert(1, "m", "cm", power=2) == 10_000.0
    assert convert(1, "m", "mm", power=3) == 1e9
    assert convert(convert(7.3, "m", "fot"), "fot", "m") == pytest.approx(7.3, abs=1e-9)
    m = measure("langd", [(0, 0), (10 * PT_PER_M_50, 0)], Scale.from_ratio(50), unit="mm")
    assert m.value == pytest.approx(10_000.0, abs=1e-1) and m.unit == "mm"


def test_the_zoom_can_never_change_the_measure():
    """Motorn känner inte till någon zoom. Samma koordinater ger samma mängd, punkt slut."""
    s = Scale.from_ratio(50)
    pts = [(0, 0), (137.4, 22.9), (200.1, 180.5)]
    first = measure("langd", pts, s).value
    for _ in range(5):
        assert measure("langd", pts, s).value == first
    # och en form som ritats om i en annan ordning mäter lika mycket
    assert measure("langd", list(reversed(pts)), s).value == pytest.approx(first, abs=1e-9)


def test_an_angle_is_read_at_its_vertex():
    assert measure("vinkel", [(0, 10), (0, 0), (10, 0)], None).value == pytest.approx(90.0, abs=1e-6)
    assert angle_between((1, 0), (0, 0), (-1, 0)) == pytest.approx(180.0, abs=1e-6)


def test_the_geometry_answers_what_a_person_can_check_by_eye():
    ring = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_ring((5, 5), ring) and not point_in_ring((15, 5), ring)
    assert point_in_ring((0, 5), ring), "kanten räknas som innanför"
    assert centroid(ring) == pytest.approx((5.0, 5.0))
    assert area_with_holes(ring, [[(2, 2), (4, 2), (4, 4), (2, 4)]]) == pytest.approx(96.0)


def test_a_formula_is_read_as_arithmetic_and_never_run_as_code():
    assert evaluate("Yta * Spill", {"Yta": 100, "Spill": 1.1}) == pytest.approx(110.0)
    assert evaluate("om(Mangd > 10; Mangd * 0.9; Mangd)", {"Mangd": 20}) == pytest.approx(18.0)
    assert evaluate("round(sqrt(Yta), 2)", {"Yta": 2}) == pytest.approx(1.41)
    for bad in ("__import__('os').system('ls')", "open('/etc/passwd')", "Yta.__class__",
                "[x for x in range(10)]", "lambda: 1", "Yta if Yta else exit()"):
        with pytest.raises(FormulaError):
            evaluate(bad, {"Yta": 1})
    with pytest.raises(FormulaError):
        evaluate("Yta / 0", {"Yta": 1})
    with pytest.raises(FormulaError):
        evaluate("Okand + 1", {"Yta": 1})


def test_formulas_are_computed_in_dependency_order_and_a_circle_is_named():
    f = {"Total": "Material + Arbete", "Material": "Yta * Apris", "Arbete": "Timmar * Timpris"}
    order = order_of_evaluation(f, ["Yta", "Apris", "Timmar", "Timpris"])
    assert order.index("Total") > order.index("Material") and order.index("Total") > order.index("Arbete")
    out = evaluate_all(f, {"Yta": 10, "Apris": 100, "Timmar": 4, "Timpris": 650})
    assert out["Material"] == 1000 and out["Arbete"] == 2600 and out["Total"] == 3600
    with pytest.raises(FormulaError) as e:
        order_of_evaluation({"A": "B + 1", "B": "A + 1"})
    assert "cirkel" in str(e.value) and "A" in str(e.value)


def test_a_broken_formula_says_so_instead_of_emptying_the_column():
    out = evaluate_all({"Fel": "Yta / 0", "Bra": "Yta * 2"}, {"Yta": 5})
    assert out["Bra"] == 10 and out["Fel"] is None
    assert "Fel" in out["_fel"] and "noll" in out["_fel"]["Fel"]
