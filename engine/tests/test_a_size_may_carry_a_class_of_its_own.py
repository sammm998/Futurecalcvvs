"""Måttraden får bära en klass med en siffra i: "22-F60" är dimension 22 med isolerklass F60.

En etikett skriver koden på en rad och måttet på nästa. Måttet får ha ett tillägg - "75/W", "160(L)", "50-F" -
och regeln krävde att tillägget var sifferfritt. Isolerklasser heter F50 och F60, så raden "22-F60" föll utanför
och lästes som en egen beteckning: koden ovanför blev kvar utan dimension, och på ett blad i korpusen tog
DN15-grenarnas namn hela DN22-stammen bredvid - åttio meter under fel rubrik.

Vad som skiljer en klass från ett andra mått är att den börjar med en bokstav: "22-F60" är ett mått med en
klass, "600X300" är två mått, och krysset mellan dem är ingen klass.
"""
from vvs_engine.semantics.annotation import _QUALIFIED_SIZE, _row_role


class _Row:
    underline: list = []


def _role(text: str) -> str:
    return _row_role(text, _Row(), None)


def test_a_size_with_a_class_is_a_dimension_row():
    assert _role("22-F60") == "dn"
    assert _role("15-F50") == "dn"


def test_a_size_with_a_wordless_tail_is_still_a_dimension_row():
    assert _role("75/W") == "dn"
    assert _role("160") == "dn"
    assert _role("110L") == "dn"


def test_two_measurements_are_not_a_size_with_a_class():
    assert _role("600X300") != "dn"
    assert _role("500x300") != "dn"


def test_the_pattern_admits_a_class_and_refuses_a_second_measurement():
    assert _QUALIFIED_SIZE.fullmatch("-F60") and _QUALIFIED_SIZE.fullmatch("-PE1")
    assert not _QUALIFIED_SIZE.fullmatch("X300") and not _QUALIFIED_SIZE.fullmatch("x300")
    assert not _QUALIFIED_SIZE.fullmatch("-50")
