"""Två andraläsare avgör ett öppet fall bara när de säger samma sak.

Ett fall som geometrin förklarat öppet har flera rimliga kandidater. En ensam modell som väljer fel förvandlar
ett ärligt tvetydigt fall till ett självsäkert fel, och det är den dyraste sortens fel i en mängdning: det ser
ut som ett svar. Två oberoende läsare kan inte göra det. De kan enas om ett av ritningens egna alternativ,
eller lämna fallet öppet - och öppet är ett giltigt svar.

Provet håller fyra löften: enighet avgör, oenighet avgör inte, en läsare som inte svarar tystar panelen i
stället för att göra den andra till ensam röst, och ingen kombination av svar kan namnge något som inte står
bland kandidaterna.

Ingen av modellerna nås här. Läsarna är vanliga funktioner, och det är just poängen - panelen vet ingenting
om vem som svarar.
"""
import pytest

from tools.readers import panel_transport
from vvs_engine.semantics.astra import Question, verify

Q = Question(case_id="anc_1", kind="attachment", evidence="två familjer vid ledarens ände",
             candidates=("lager-A|s|w1.44", "lager-B|s|w0.72"))


def choice(asks):
    ask = panel_transport(asks=asks)
    return verify(Q, ask(Q)).choice


def says(text):
    return lambda _q: text


def test_two_readers_that_agree_settle_the_case():
    assert choice({"a": says("lager-A|s|w1.44\nledaren slutar på den"),
                   "b": says("lager-A|s|w1.44")}) == "lager-A|s|w1.44"


def test_two_readers_that_disagree_leave_it_open():
    assert choice({"a": says("lager-A|s|w1.44"), "b": says("lager-B|s|w0.72")}) is None


def test_one_that_abstains_is_a_disagreement():
    assert choice({"a": says("lager-A|s|w1.44"), "b": says("OKLART")}) is None


def test_a_reader_that_cannot_be_reached_silences_the_panel():
    def boom(_q):
        raise RuntimeError("nätet")
    assert choice({"a": says("lager-A|s|w1.44"), "b": boom}) is None


def test_a_single_configured_reader_answers_as_before():
    assert choice({"a": says("lager-B|s|w0.72")}) == "lager-B|s|w0.72"


def test_agreement_on_something_that_is_not_a_candidate_settles_nothing():
    both = "lager-C|s|w2.04"
    assert choice({"a": says(both), "b": says(both)}) is None


def test_agreement_that_both_refused_settles_nothing():
    assert choice({"a": says(""), "b": says("")}) is None


def test_an_empty_panel_is_no_transport_at_all():
    assert panel_transport(asks={}) is None


def test_the_trail_names_who_said_what():
    ask = panel_transport(asks={"astra": says("lager-A|s|w1.44"), "claude": says("lager-B|s|w0.72")})
    raw = ask(Q)
    assert "astra" in raw and "claude" in raw
    assert raw.splitlines()[0].startswith("OKLART")
