"""Mängden är hela handlingen, och rättelsen mäts i det blad den ritades på.

En uppladdad PDF bär ofta hela handlingen: plan 1 till plan 26 i en fil. Läsningen läste alla blad, men
kalkylen och anbudet läste `quantities.json`, som är det **första** bladets rader. Det är att mäta
bottenvåningen och kalla det huset. Uppmätt på tre blad ur en verklig handling, samma läsning:

| läst ur | rader | meter |
|---|---|---|
| `quantities.json` (blad 1) | 0 | 0,00 |
| `document-quantities.json` (handlingen) | 4 | 64,91 |

Med det följde två fällor som bara syns när raderna kommer från flera blad:

* Handlingens rader hålls isär på **beteckning och DN** - `VS1` i DN 22 och `VS1` i DN 35 är två mängder.
  Rättelserna höll dem isär på enbart beteckningen, så den andra raden tog tyst den förstas plats och dess
  meter lämnade mängden utan ett ord.
* Ett blad har sin **egen skala**. En rättelse ritad på en detalj i 1:20 och en på en plan i 1:100 blir vitt
  skilda längder av samma streck.
"""
import pytest

from vvs_engine.corrections import apply


def rad(des, dn, m):
    return {"designation": des, "base": des.split("-")[0], "dn": dn, "state": "CONFIRMED",
            "confirmed_horizontal_m": m, "confirmed_vertical_m": 0.0, "confirmed_total_m": m}


def ratt(kid, kind, des, page=None, **payload):
    return {"id": kid, "kind": kind, "designation": des, "page": page, "created_at": f"2026-01-0{kid}",
            "payload": payload, "undone": False}


def test_samma_beteckning_i_tva_dimensioner_ar_tva_rader():
    """Två DN under ett namn: båda ska stå kvar, med sina egna meter."""
    ut = apply([rad("VS1", 22, 10.0), rad("VS1", 35, 81.0)], [], 0.01)["quantities"]
    assert [(r["designation"], r["dn"], r["confirmed_total_m"]) for r in ut] == [("VS1", 22, 10.0), ("VS1", 35, 81.0)]
    assert ut[1]["engine_total_m"] == 81.0


def test_en_rattelse_som_inte_sager_vilken_dimension_avvisas_med_skalet():
    """Vilken av de två raderna rättelsen menar är inte vårt att gissa - och ingen av dem får ändras."""
    r = apply([rad("VS1", 22, 10.0), rad("VS1", 35, 81.0)],
              [ratt(1, "quantity", "VS1", meters=50.0)], 0.01)
    assert r["applied"][0]["applied"] is False
    assert "DN22" in r["applied"][0]["why"] and "DN35" in r["applied"][0]["why"]
    assert [q["confirmed_total_m"] for q in r["quantities"]] == [10.0, 81.0]


def test_en_entydig_beteckning_rattas_som_forr():
    """Regeln får inte röra det som redan fungerade: ett namn, en rad, rättelsen går fram."""
    r = apply([rad("KV1-16", 16, 10.0)], [ratt(1, "quantity", "KV1-16", meters=12.5)], 0.01)
    assert r["applied"][0]["applied"] is True
    assert r["quantities"][0]["confirmed_total_m"] == 12.5
    assert r["quantities"][0]["engine_total_m"] == 10.0


def test_en_beteckning_lasningen_aldrig_fann_far_en_egen_rad():
    r = apply([rad("KV1-16", 16, 10.0)], [ratt(1, "quantity", "VV2-20", meters=4.0)], 0.01)
    ny = [q for q in r["quantities"] if q["designation"] == "VV2-20"][0]
    assert ny["from_correction"] is True and ny["confirmed_total_m"] == 4.0


def test_omflyttning_fran_en_tvetydig_kalla_avvisas():
    """Metrarna får inte lämna en rad som inte är utpekad."""
    r = apply([rad("VS1", 22, 10.0), rad("VS1", 35, 81.0), rad("KV1", 16, 0.0)],
              [ratt(1, "retag", "KV1", meters=5.0, **{"from": "VS1"})], 0.01)
    assert r["applied"][0]["applied"] is False
    assert "VS1" in r["applied"][0]["why"]
    kvar = {(q["designation"], q["dn"]): q["confirmed_total_m"] for q in r["quantities"]}
    assert kvar == {("VS1", 22): 10.0, ("VS1", 35): 81.0, ("KV1", 16): 0.0}


def test_bladets_egen_skala_matter_rattelsen_som_ritades_dar():
    """Samma streck på två blad: 1:100-bladet ger tio gånger 1:20-bladets meter."""
    strack = {"points": [[0.0, 0.0], [100.0, 0.0]]}
    r = apply([rad("KV1", 16, 0.0), rad("VV1", 16, 0.0)],
              [ratt(1, "draw", "KV1", page=3, **strack), ratt(2, "draw", "VV1", page=7, **strack)],
              None, {3: 0.01, 7: 0.1})
    ut = {q["designation"]: q["confirmed_total_m"] for q in r["quantities"]}
    assert ut["KV1"] == pytest.approx(1.0)
    assert ut["VV1"] == pytest.approx(10.0)


def test_lasningens_egen_skala_ar_reserven_for_ett_blad_utan_egen():
    r = apply([rad("KV1", 16, 0.0)],
              [ratt(1, "draw", "KV1", page=9, points=[[0.0, 0.0], [100.0, 0.0]])], 0.02, {3: 0.01})
    assert r["quantities"][0]["confirmed_total_m"] == pytest.approx(2.0)


def test_utan_skala_pa_bladet_och_utan_reserv_star_rattelsen_kvar_oanvand():
    """Ett streck utan skala har ingen längd att försvara, och noll vore en osann tillämpning."""
    r = apply([rad("KV1", 16, 0.0)],
              [ratt(1, "draw", "KV1", page=9, points=[[0.0, 0.0], [100.0, 0.0]])], None, {3: 0.01})
    assert r["applied"][0]["applied"] is False
    assert "skala" in r["applied"][0]["why"]
    assert r["quantities"][0]["confirmed_total_m"] == 0.0
