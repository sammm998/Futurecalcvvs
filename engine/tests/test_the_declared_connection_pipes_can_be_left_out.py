"""De förklarade kopplingsledningarna går att räkna bort - utan att läsningen ändras.

Bladet namnger dem i ord i stället för med en etikett: "kopplingsledningar från fördelare till apparat enligt
tabell". Ritningen säger att de är där, så de räknas med som förval. Men en mängdförteckning behöver inte ha dem
med - de kan vara prissatta per apparat eller mätta på ett annat blad - och på ett blad i korpusen är det
skillnaden mellan 72 m och 0,5 m. Valet hör hemma hos den som räknar, som kryssrutan för skrafferade ytor, och
filen måste visa samma summa som skärmen den togs från.
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import exports  # noqa: E402


ROWS = [
    {"designation": "KV01-X31-16", "dn": 16, "physical_pipe_count": 3, "confirmed_horizontal_m": 71.8,
     "confirmed_total_m": 71.8, "vertical_m": "UNKNOWN", "ambiguous_m": 0.0, "declared_m": 71.8,
     "in_hatched_area_m": 0.0, "label_count": 0, "state": "CONFIRMED"},
    {"designation": "VS21-S13-15", "dn": 15, "physical_pipe_count": 4, "confirmed_horizontal_m": 32.4,
     "confirmed_total_m": 32.4, "vertical_m": "UNKNOWN", "ambiguous_m": 0.0, "declared_m": 0.0,
     "in_hatched_area_m": 2.0, "label_count": 12, "state": "CONFIRMED"},
    {"designation": "VV01-X31-16", "dn": 16, "physical_pipe_count": 5, "confirmed_horizontal_m": 42.8,
     "confirmed_total_m": 42.8, "vertical_m": "UNKNOWN", "ambiguous_m": 0.0, "declared_m": 41.4,
     "in_hatched_area_m": 0.0, "label_count": 7, "state": "CONFIRMED"},
]


def _rows(**kw):
    return {r["designation"]: r for r in exports._rows("", rows=[dict(r) for r in ROWS], **kw)}


def test_by_default_the_sheets_own_rule_counts():
    r = _rows()
    assert r["KV01-X31-16"]["confirmed_horizontal_m"] == 71.8
    assert r["VV01-X31-16"]["confirmed_horizontal_m"] == 42.8


def test_left_out_only_the_declared_metres_go():
    r = _rows(include_declared=False)
    assert r["KV01-X31-16"]["confirmed_horizontal_m"] == 0.0          # varje meter var förklarad
    assert r["VV01-X31-16"]["confirmed_horizontal_m"] == 1.4          # 42,8 - 41,4: det en etikett pekade ut
    assert r["VS21-S13-15"]["confirmed_horizontal_m"] == 32.4         # rör ingen regel namngav rörs inte
    assert r["KV01-X31-16"]["confirmed_total_m"] == 0.0


def test_the_two_choices_do_not_cancel_each_other():
    """Skrafferat räknas in och förklarat räknas bort på samma rad: båda gäller, var för sig."""
    r = _rows(include_hatched=True, include_declared=False)
    assert r["VS21-S13-15"]["confirmed_horizontal_m"] == 34.4
    assert r["KV01-X31-16"]["confirmed_horizontal_m"] == 0.0


def test_a_row_without_declared_metres_is_untouched():
    a = _rows()["VS21-S13-15"]
    b = _rows(include_declared=False)["VS21-S13-15"]
    assert a["confirmed_horizontal_m"] == b["confirmed_horizontal_m"] == 32.4
