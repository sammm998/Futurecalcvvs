"""Förklaringslistan får inte intyga att den känner bladet genom att peka på sina egna rader.

Bladets egen lista avgör vilka koder som är rörbeteckningar (se test_the_legend_decides_what_names_a_pipe).
Regeln är med flit smal: den gäller bara när listan bevisligen känner igen bladets eget ordförråd, för en lista
som inte gör det säger ingenting om bladet och ska då inte stänga ute någonting.

Men listans rader läses som beteckningar de också. Varje kod i listan står alltså två gånger i läsningen: en
gång som en rad i listan, en gång - om ritningen använder koden - som en etikett ute på planen. Raderna
stämmer med listan av bara farten, och räknas de som bevis intygar listan sig själv.

Det är precis vad som hände på ett blad vars lista bara handlar om ventiler och material: tolv rader gav tolv
"kända" koder, villkoret var uppfyllt, och därefter refuserades varenda rörbeteckning bladet faktiskt ritar.
Hundra tretton etiketter, fyrtiotvå rörnamn, noll meter.

Frågan "känner listan det här bladet?" ska ställas till etiketterna ute på ritningen.
"""
from vvs_engine.pipeline import _unknown_to_the_legend
from vvs_engine.semantics.legend import DrawingLegend, LegendEntry


class _Des:
    def __init__(self, did, text, bbox, head=None):
        self.did, self.text, self.bbox = did, text, bbox
        self.system_token = head if head is not None else text.split("-")[0]


# en lista över ventiler och material, uppe i högerkanten: kod efter kod i en smal kolumn
VENTILER = ["SA01", "SP01", "D001", "PN", "P1", "P2", "R1", "R2", "R61", "R71", "S1", "S2"]


def _list_at(x: float, y0: float) -> DrawingLegend:
    return DrawingLegend(column_x=x, entries=[
        LegendEntry(code=c, description="", heading="BETECKNINGAR KOMPONENTER", role="material",
                    role_from="usage", page=0, bbox=(x, y0 + i * 14.0, x + 28.0, y0 + i * 14.0 + 8.0))
        for i, c in enumerate(VENTILER)])


def _rows_of_the_list(lg: DrawingLegend):
    """Listans egna rader, så som läsningen ser dem: en beteckning per rad, på radens plats."""
    return [_Des(f"lg{i}", e.code, e.bbox) for i, e in enumerate(lg.entries)]


def _pipes_out_on_the_drawing():
    return [_Des("p1", "KV01-S13-22", (300.0, 400.0, 372.0, 410.0)),
            _Des("p2", "VV01-S13-18", (500.0, 300.0, 572.0, 310.0)),
            _Des("p3", "VVC01-S13-15", (700.0, 520.0, 778.0, 530.0)),
            _Des("p4", "VS21-S13-35", (900.0, 610.0, 978.0, 620.0))]


def test_the_lists_own_rows_do_not_make_it_knowledgeable():
    """Listan känner inga av ritningens rörkoder. Då stänger den inte ute något - sina egna rader till trots."""
    lg = _list_at(2049.0, 330.0)
    des = _rows_of_the_list(lg) + _pipes_out_on_the_drawing()
    assert _unknown_to_the_legend(lg, des) == set(), (
        "listan intygade sig själv och raderade bladets alla rörbeteckningar")


def test_a_list_that_knows_the_drawing_still_refuses_what_it_never_mentions():
    """Rättningen får inte slå av regeln. Känner listan etiketterna ute på planen gäller den som förut."""
    lg = _list_at(2049.0, 330.0)
    known = [_Des("k1", "P1-22", (300.0, 400.0, 340.0, 410.0)),
             _Des("k2", "R1-18", (500.0, 300.0, 540.0, 310.0)),
             _Des("k3", "S2-110", (700.0, 520.0, 744.0, 530.0))]
    stray = _Des("c1", "C09-07", (800.0, 200.0, 844.0, 210.0))
    assert _unknown_to_the_legend(lg, _rows_of_the_list(lg) + known + [stray]) == {"c1"}


def test_a_label_without_a_place_is_still_weighed():
    """En beteckning utan ruta kan inte ligga i listan, och ska räknas som förut."""
    lg = _list_at(2049.0, 330.0)
    known = [_Des("k1", "P1-22", None), _Des("k2", "R1-18", None), _Des("k3", "S2-110", None)]
    stray = _Des("c1", "C09-07", None)
    assert _unknown_to_the_legend(lg, _rows_of_the_list(lg) + known + [stray]) == {"c1"}


def test_a_borrowed_list_lends_no_geometry():
    """En lista från ett annat blad har ingen ruta här, och ska inte diskvalificera etiketter som råkar ligga där."""
    lg = _list_at(300.0, 380.0)
    lg.own = False
    assert lg.bbox() is None
    assert not lg.holds((300.0, 400.0, 340.0, 410.0))
