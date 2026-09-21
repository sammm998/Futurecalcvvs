"""En rad som visar 0,00 m ser ut som ett missat rör. Ibland är den i stället ett rör som inte är bladets.

Skrafferingen är hur en ritning säger att en del inte redovisas här: en angränsande byggnadsdel, ett annat
skede, någon annans entreprenad. Den som mängdar mäter inte i den - på de fem blad där mängdarens egna
mätlinjer finns ligger 0,1-1,2 procent av hennes meter inne i skraffering - och läsningen räknar därför inte
heller där.

Men den räknade tyst. En beteckning vars enda stråk låg helt inne i skrafferingen kom ut som BEKRÄFTAD med
0,00 m och en sträcka, och det är två påståenden som motsäger varandra: en sträcka finns, och den är noll lång.
Femtionio rader i korpusen såg ut så, och den som läser tabellen har ingen chans att se skillnad på dem och ett
rör läsningen verkligen missat.

Nu säger raden vad den vet: stråket är hittat, det ligger i skrafferad yta, och metrarna står i sin egen kolumn.
Ingen meter flyttar - de var borträknade förut också.
"""
from types import SimpleNamespace

from vvs_engine.measure.measure import HATCHED_ONLY, aggregate


def _pipe(key="VS1-S13|DN22", display="VS1-S13-22"):
    ident = SimpleNamespace(key=key, display=display, base=display.rsplit("-", 1)[0], dn=22, system="VS1")
    return SimpleNamespace(identity=ident, physical_pipe_id=f"pp_{abs(hash(key)) % 10**8}", evidence=[])


def _measure(state, horizontal_m, hatched_m, pipe=None):
    return SimpleNamespace(pipe=pipe or _pipe(), state=state, horizontal_m=horizontal_m, horizontal_pdf_units=0.0,
                           hatched_m=hatched_m, vertical_m=None, twin_of=None, twin_pdf_units=0.0)


def test_a_row_whose_every_run_lies_in_hatching_says_so():
    rows = aggregate([_measure(HATCHED_ONLY, 0.0, 6.2)], {}, 0.0176)
    assert len(rows) == 1
    assert rows[0]["state"] == HATCHED_ONLY
    assert rows[0]["physical_pipe_count"] == 1
    assert rows[0]["confirmed_horizontal_m"] == 0.0
    assert rows[0]["in_hatched_area_m"] == 6.2


def test_a_row_with_one_run_outside_the_hatching_is_still_confirmed():
    a, b = _pipe(), _pipe()
    b.physical_pipe_id = "pp_other"
    rows = aggregate([_measure(HATCHED_ONLY, 0.0, 6.2, a), _measure("CONFIRMED", 4.0, 0.0, b)], {}, 0.0176)
    assert rows[0]["state"] == "CONFIRMED"
    assert rows[0]["confirmed_horizontal_m"] == 4.0
    assert rows[0]["in_hatched_area_m"] == 6.2


def test_the_state_never_hides_a_scale_that_is_missing():
    rows = aggregate([_measure("NO_SCALE", None, None)], {}, None)
    assert rows[0]["state"] == "NO_SCALE"


def test_the_bookkeeping_key_does_not_leak_into_the_row():
    rows = aggregate([_measure(HATCHED_ONLY, 0.0, 6.2)], {}, 0.0176)
    assert "hatched_only_pipes" not in rows[0]


def test_no_metre_moves_because_of_the_state():
    """Raden hette bekräftad och visade noll; nu heter den skrafferad och visar noll. Mängden är densamma."""
    rows = aggregate([_measure(HATCHED_ONLY, 0.0, 6.2)], {}, 0.0176)
    assert rows[0]["confirmed_total_m"] == 0.0
