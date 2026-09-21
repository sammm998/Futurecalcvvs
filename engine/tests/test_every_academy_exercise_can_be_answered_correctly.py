"""Varje övning i akademin ska gå att svara rätt på, och fel svar ska underkännas.

En övning vars facit inte går att träffa är värre än ingen övning: eleven svarar rätt, får underkänt, och har
ingen väg att förstå varför. Det går inte att se i innehållet - fältnamnen i facit och fältnamnen rättningen
läser är två olika listor, och de glider isär tyst så fort någon skriver en ny övning.

Provet bygger rätt svar ur varje övnings **eget** facit och lämnar in det. Det är ingen dubblering av
rättningen: det säger bara att facit och rättningen talar samma språk. En mängdningsövning går ett steg längre
och bygger svaret ur bladets geometri - samma stråk eleven ska följa - så att facit och ritning också hänger
ihop.

Och åt andra hållet: ett tomt svar ska aldrig bli godkänt. En övning som godkänner ingenting mäter ingenting.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend"))

from app.academy_grading import grade                      # noqa: E402
from app.academy_plans import PLANS                        # noqa: E402
from app.academy_seed import EXERCISES                      # noqa: E402


def ratt_svar(ex: dict) -> dict:
    """Det svar som är rätt, byggt ur övningens eget facit - aldrig ur ett tal skrivet i provet."""
    a, k, d = ex["answer"], ex["kind"], ex["data"]
    if k == "mangda":
        # ur bladet: de stråk övningen pekar ut, ritade som eleven skulle rita dem
        p = PLANS.get(d.get("plan"))
        sysf, dnf = d.get("highlight_sys"), d.get("highlight_dn")
        runs = [r for r in (p.runs if p else [])
                if (sysf is None or r["sys"] == sysf) and (dnf is None or r["dn"] == dnf)]
        return {"runs": [r["points"] for r in runs]}
    if k in ("markera", "hitta-fel", "ritningsquiz"):
        return {"picked": a.get("picked")}
    if k in ("dimension", "symbol"):
        return {"index": a.get("index")}
    if k == "matcha":
        return {"pairs": a.get("pairs")}
    if k == "bygg":
        return {"order": a.get("order")}
    if k == "kalkyl":
        return {"steps": a.get("steps")}
    if k == "numerisk":
        return {"value": a.get("value")}
    if k == "kategorisera":
        return {"buckets": a.get("buckets")}
    if k == "rum":
        return {"items": a.get("items")}
    raise AssertionError(f"provet känner inte till övningstypen {k!r} - lägg till den här när den byggs")


def _grade(ex, given):
    return grade({"kind": ex["kind"], "data": ex["data"], "answer": ex["answer"],
                  "tolerance": ex.get("tolerance", 0.0)}, given)


@pytest.mark.parametrize("ex", EXERCISES, ids=[e["slug"] for e in EXERCISES])
def test_ratt_svar_ger_godkant(ex):
    score, ok, fb = _grade(ex, ratt_svar(ex))
    assert ok, f"{ex['slug']} ({ex['kind']}): rätt svar underkändes - {fb.get('text')}"
    assert score == pytest.approx(1.0)


@pytest.mark.parametrize("ex", [e for e in EXERCISES if e["kind"] != "rum"],
                         ids=[e["slug"] for e in EXERCISES if e["kind"] != "rum"])
def test_tomt_svar_ger_underkant(ex):
    """Den som inte svarar ska inte klara sig. En övning som godkänner tomt mäter ingenting."""
    _, ok, _ = _grade(ex, {})
    assert not ok, f"{ex['slug']} ({ex['kind']}) godkände ett tomt svar"


def test_varje_ovning_hor_till_en_kurs_och_en_modul():
    from app.academy_seed import COURSES
    par = {(c["slug"], m["slug"]) for c in COURSES for m in c["moduler"]}
    for e in EXERCISES:
        assert (e["course"], e["module"]) in par, \
            f"{e['slug']} pekar på {e['course']}/{e['module']} som inte finns"


def test_varje_ovning_hor_till_en_lektion_som_finns():
    from app.academy_seed import COURSES
    lek = {(c["slug"], m["slug"], l["slug"])
           for c in COURSES for m in c["moduler"] for l in m["lektioner"]}
    for e in EXERCISES:
        assert (e["course"], e["module"], e["lesson"]) in lek, \
            f"{e['slug']} pekar på lektionen {e['lesson']} som inte finns i {e['module']}"


def test_tentan_har_nog_med_uppgifter_i_varje_del():
    """En del som saknar uppgifter blir en del ingen kan klara, och section_min_pct gör den till ett stopp."""
    from app.academy_seed import COURSES, EXAM
    fragor: dict[str, int] = {}
    for c in COURSES:
        for m in c["moduler"]:
            for f in m.get("fragor") or []:
                if f.get("in_exam"):
                    fragor[f.get("area", "teori")] = fragor.get(f.get("area", "teori"), 0) + 1
    ovn: dict[str, int] = {}
    for e in EXERCISES:
        a = (e["data"] or {}).get("exam_area")
        if a:
            ovn[a] = ovn.get(a, 0) + 1
    for sec in EXAM["sections"]:
        finns = fragor.get(sec["area"], 0) + ovn.get(sec["area"], 0)
        assert finns >= sec["n"], \
            f"{sec['area']} behöver {sec['n']} uppgifter men har {finns}"


def test_modulernas_forkunskaper_finns_i_samma_kurs():
    from app.academy_seed import COURSES
    for c in COURSES:
        egna = {m["slug"] for m in c["moduler"]}
        for m in c["moduler"]:
            krav = m.get("requires") or ""
            assert not krav or krav in egna, \
                f"{c['slug']}/{m['slug']} kräver {krav!r} som inte finns i kursen"
