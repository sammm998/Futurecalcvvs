"""Registret får aldrig säga något annat än koden.

En lista över reglerna är bara värd något om den stämmer. Skrivs en gräns om i modulen där den används och inte
här, ljuger gränssnittet för den som försöker förstå varför en mängd blev fel - och det är värre än att inte
visa något alls. Provet håller de två lika.
"""
import pytest

from vvs_engine import rules


def test_every_rule_matches_the_code():
    wrong = []
    for r in rules.RULES:
        live = rules.live_default(r)
        if live != r.default:
            wrong.append(f"{r.id}: registret säger {r.default!r}, koden säger {live!r}")
    assert not wrong, "registret har glidit från koden:\n  " + "\n  ".join(wrong)


def test_ids_are_unique_and_described():
    assert len(rules.BY_ID) == len(rules.RULES)
    for r in rules.RULES:
        assert r.title and r.why and r.group, r.id
        assert r.tunable or r.fixed_why, f"{r.id} går inte att ändra men säger inte varför"
        if r.lo is not None and r.hi is not None:
            assert r.lo <= r.default <= r.hi, r.id


def test_overrides_bind_to_the_reading_and_are_let_go():
    r = next(x for x in rules.RULES if x.tunable and x.unit == "pt")
    assert rules.value(r.id, r.default) == r.default
    with rules.using({r.id: 42.0}):
        assert rules.value(r.id, r.default) == 42.0
    assert rules.value(r.id, r.default) == r.default


def test_a_rule_that_may_not_be_changed_is_not_changed():
    fixed = next(x for x in rules.RULES if not x.tunable)
    with rules.using({fixed.id: 999}):
        assert rules.value(fixed.id, fixed.default) == fixed.default


def test_catalogue_is_complete():
    cat = rules.catalogue()
    assert cat["n_rules"] == len(rules.RULES)
    seen = {x["id"] for g in cat["groups"] for x in g["rules"]}
    assert seen == set(rules.BY_ID)
