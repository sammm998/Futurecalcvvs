"""Att förlänga ett rör är att följa ritningen, inte att lägga till meter.

Ett rör slutar av ett skäl, och läsningen skriver ned skälet. Fyra av skälen är ritningens egna - dimensionen
byts, systemet byts, ledningen går upp i en stigare, den lämnar bladet - och ett rör som slutar av ett sådant
skäl slutar där det är ritat att sluta. Tre är läsningen som tar slut: pennan fortsätter och ingen etikett når
dit, ett gap gick inte att sluta, linjen fortsätter på en annan penna.

"Förläng den" ska bara gå att genomföra i det andra fallet. Att förlänga över en riktig gräns vore att ta
metrar från röret på andra sidan och ge dem till det här - och bladet har redan sagt vems de är.

Metrarna kommer ur läsningen: det oägda bläcket bortom änden, mätt i bladets skala. Inget tal ur frågan blir
någonsin en meter.
"""
import pytest

from vvs_engine.agent import edits, tools as T
from vvs_engine.corrections import apply


class Modell:
    """Så mycket av en läsning som förlängningen rör vid."""

    def __init__(self, pipes, frontiers, mpp=0.02):
        self.pipes = pipes
        self.meters_per_pt = mpp
        self.pipe_by_id = {p["physical_pipe_id"]: p for p in pipes}
        self.frontiers_by_pipe = {}
        for f in frontiers:
            self.frontiers_by_pipe.setdefault(f["pipe"], []).append(f)
        self.frontiers = frontiers


def ror(pid="p1", des="KV1-20", m=12.0):
    return {"physical_pipe_id": pid, "designation": des, "dn": 20, "page": 0, "horizontal_m": m}


def kant(pid, reason, pt=None, x=100.0, y=200.0):
    return {"pipe": pid, "reason": reason, "x": x, "y": y,
            "detail": {"unowned_pt": pt} if pt is not None else {}}


def test_ett_ror_som_slutar_dar_lasningen_tog_slut_gar_att_forlanga():
    m = Modell([ror()], [kant("p1", "UNOWNED_CONTINUATION", pt=150.0)])
    ut = T.run("foresla_forlang_ror", m, {"ror_id": "p1"})
    assert ut["tillstand"] == "FORESLAGEN"
    f = ut["forslag"][0]
    assert f["kind"] == "extend" and f["designation"] == "KV1-20"
    assert f["payload"]["meters"] == pytest.approx(3.0)      # 150 pt * 0,02 m/pt


def test_ett_ror_som_slutar_dar_ritningen_slutar_forlangs_inte():
    """En riktig gräns är ritningens besked. Att gå förbi den vore att ta grannens meter."""
    for skal in ("REAL_DN_BOUNDARY", "REAL_SYSTEM_BOUNDARY", "VERTICAL", "SHEET_EDGE", "SYMBOL", "FREE_END"):
        m = Modell([ror()], [kant("p1", skal, pt=150.0)])
        ut = T.run("foresla_forlang_ror", m, {"ror_id": "p1"})
        assert ut["tillstand"] == "AVBOJD", skal
        assert not ut.get("forslag")
        assert skal in ut["kanter"]


def test_utan_ritat_blackk_bortom_anden_finns_inga_meter_att_lagga_till():
    m = Modell([ror()], [kant("p1", "UNOWNED_CONTINUATION", pt=0.0)])
    ut = T.run("foresla_forlang_ror", m, {"ror_id": "p1"})
    assert ut["tillstand"] == "AVBOJD" and "fortsätter" in ut["skal"]


def test_utan_skala_forlangs_ingenting():
    """En ritad sträcka utan skala har ingen längd att försvara."""
    m = Modell([ror()], [kant("p1", "BROKEN_CONTINUITY", pt=150.0)], mpp=None)
    ut = T.run("foresla_forlang_ror", m, {"ror_id": "p1"})
    assert ut["tillstand"] == "AVBOJD" and "skala" in ut["skal"]


def test_en_orimligt_stor_forlangning_avbojs_med_sitt_tal():
    """Femtio meter är inte en rättelse av ett rör; den ska inte gå att godta på en rads sammanfattning."""
    m = Modell([ror()], [kant("p1", "UNOWNED_CONTINUATION", pt=5000.0)])
    ut = T.run("foresla_forlang_ror", m, {"ror_id": "p1"})
    assert ut["tillstand"] == "AVBOJD" and ut["meter"] == pytest.approx(100.0)


def test_ett_okant_ror_far_ett_svar_och_inte_ett_krasch():
    m = Modell([ror()], [kant("p1", "UNOWNED_CONTINUATION", pt=150.0)])
    assert T.run("foresla_forlang_ror", m, {"ror_id": "p9"})["tillstand"] == "AVBOJD"


def test_kandidatlistan_rangordnar_efter_vad_som_ligger_bortom_anden():
    m = Modell([ror("p1", "KV1-20", 12.0), ror("p2", "VV1-20", 8.0), ror("p3", "S1-110", 4.0)],
               [kant("p1", "UNOWNED_CONTINUATION", pt=50.0),
                kant("p2", "BROKEN_CONTINUITY", pt=400.0),
                kant("p3", "REAL_DN_BOUNDARY", pt=900.0)])
    ut = T.run("hitta_ror_att_forlanga", m, {})
    assert [k["ror_id"] for k in ut["kandidater"]] == ["p2", "p1"]    # p3 slutar där ritningen slutar
    assert ut["kandidater"][0]["bortom_anden_m"] == pytest.approx(8.0)


def test_forlangningen_ar_en_rattelse_som_lagger_till_sina_egna_meter():
    """Hela vägen: förslaget skrivs som en rättelse och mängden växer med precis de metrarna."""
    m = Modell([ror()], [kant("p1", "UNOWNED_CONTINUATION", pt=150.0)])
    f = T.run("foresla_forlang_ror", m, {"ror_id": "p1"})["forslag"][0]
    rader = [{"designation": "KV1-20", "dn": 20, "confirmed_horizontal_m": 12.0,
              "confirmed_vertical_m": 0.0, "confirmed_total_m": 12.0}]
    r = apply(rader, [{"id": 1, "kind": f["kind"], "designation": f["designation"],
                       "payload": f["payload"], "created_at": "2026-01-01"}], None)
    assert r["applied"][0]["applied"] is True
    assert r["quantities"][0]["confirmed_total_m"] == pytest.approx(15.0)
    assert r["quantities"][0]["engine_total_m"] == pytest.approx(12.0)


def test_forlangningen_ar_registrerad_som_en_andring():
    """Den ska gå genom ändringsvägen, inte frågevägen."""
    assert T.writes("foresla_forlang_ror") is True
    assert T.writes("hitta_ror_att_forlanga") is False
