"""Knippet är den sortens tvetydighet en andraläsare har något att titta på.

Tre rör ritade parallellt i samma penna, med en stapel etiketter över sig. Radordningen följer oftast stråkens
ordning, och läsningen prövar redan det. De fall som blir kvar - counts som inte går ihop, en stapel som inte
stämmer med knippet - stod förut som tvetydiga utan att någon fick frågan, för frågan som ställdes handlade om
*pennor*, och knippets stråk ligger alla i samma penna. Det fanns aldrig två kandidater att välja mellan.

Nu ställs frågan om stråk i stället, med läget som enda upplysning. Provet håller det som gör frågan ofarlig:
kandidaterna kommer ur läsningens egen knippebeskrivning, ett svar utanför listan avvisas, ett stråk ledaren
inte rörde avvisas vid dörren, och ett knippe där varje rad säger samma sak frågas inte alls.
"""
from types import SimpleNamespace

from vvs_engine.semantics.astra import Answer, apply_answers, questions_for, verify


def _contact(pid, seg, point, family="lager|s|w1.44"):
    return SimpleNamespace(pid=pid, seg_index=seg, point=point, family=family, kind="end_tick")


def _anchor(pos=0, n=3, runs=None, reason="multi_row_bundle_awaiting_elimination", all_agree=False):
    runs = runs if runs is not None else [[["p1", 0]], [["p2", 0]], [["p3", 0]]]
    pts = {"p1": (100.0, 200.0), "p2": (100.0, 212.0), "p3": (100.0, 224.0)}
    bundle = {"pos": pos, "n": n, "runs": runs}
    if all_agree:
        bundle["all_rows_agree"] = True
    return SimpleNamespace(
        anchor_id="anc_bundle", state="AMBIGUOUS_PIPE_ATTACHMENT", reason=reason,
        designation="VV1-X7", designation_display="VV1-X7-20/W", system_token="VV1", dn=20,
        endpoint=(88.0, 212.0), contacts=[_contact(pid, seg, pts.get(pid, (0.0, 0.0)))
                                          for r in runs for pid, seg in r],
        candidate_families=["lager|s|w1.44"], evidence={"leader_family": "straight|diagonal", "bundle": bundle})


def test_the_stack_gets_one_question_with_one_candidate_per_run():
    a = _anchor()
    qs = questions_for([a])
    assert len(qs) == 1
    q = qs[0]
    assert q.kind == "bundle"
    assert q.candidates == ("stråk 1", "stråk 2", "stråk 3")
    assert "rad 1 av 3" in q.evidence
    assert "VV1-X7-20/W" in q.evidence


def test_a_bundle_where_every_row_says_the_same_is_not_asked():
    assert questions_for([_anchor(all_agree=True)]) == []


def test_a_bundle_of_one_run_is_not_a_choice():
    assert questions_for([_anchor(runs=[[["p1", 0]]])]) == []


def test_a_settled_run_narrows_the_anchor_to_that_run():
    a = _anchor()
    applied = apply_answers([a], [Answer("anc_bundle", "stråk 2", why="det mellersta")])
    assert applied and applied[0]["chose"] == "stråk 2"
    assert a.state == "VERIFIED_PIPE_ATTACHMENT"
    assert [(c.pid, c.seg_index) for c in a.contacts] == [("p2", 0)]
    assert a.evidence["second_reader"]["chose"] == "stråk 2"


def test_a_run_the_leader_never_touched_is_refused_at_the_door():
    a = _anchor()
    a.contacts = [c for c in a.contacts if c.pid != "p3"]
    assert apply_answers([a], [Answer("anc_bundle", "stråk 3")]) == []
    assert a.state == "AMBIGUOUS_PIPE_ATTACHMENT"


def test_an_answer_outside_the_list_never_becomes_a_choice():
    q = questions_for([_anchor()])[0]
    assert verify(q, "stråk 9").choice is None
    assert verify(q, "lager|s|w1.44").choice is None
    assert verify(q, "OKLART").choice is None
    assert verify(q, "stråk 2\nmellersta").choice == "stråk 2"


def test_the_question_says_that_open_is_allowed():
    assert "OKLART" in questions_for([_anchor()])[0].evidence
