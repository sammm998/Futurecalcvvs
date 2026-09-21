"""Historiken kommer utifrån och får aldrig gå vidare som den är.

En webbsida skickar med vad som sagts tidigare. Skickar den en rad utan roll blir rollen tom, och modellen
svarar med ett fel innan frågan ens ställts - hela turen faller på ett 502. Här läses bara det som går att läsa:
en av de fyra rollerna modellen känner (agentens egen heter assistant), en text som är text, och rader som inte
säger något hoppas över.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.agent import _history, run_turn


def test_a_row_without_a_role_never_reaches_the_model():
    assert _history([{"text": "hej"}]) == [{"role": "user", "content": "hej"}]
    assert _history([{"roll": "", "text": ""}]) == []
    assert _history(["skräp", None, 7]) == []


def test_the_agents_own_voice_is_the_assistant():
    assert _history([{"roll": "agent", "text": "svar"}]) == [{"role": "assistant", "content": "svar"}]
    assert _history([{"role": "assistant", "content": "svar"}]) == [{"role": "assistant", "content": "svar"}]


def test_an_unknown_role_is_read_as_the_person_asking():
    assert _history([{"role": "kund", "content": "hej"}]) == [{"role": "user", "content": "hej"}]


def test_only_the_last_rounds_are_carried():
    many = [{"role": "user", "content": str(i)} for i in range(40)]
    out = _history(many)
    assert len(out) == 20 and out[0]["content"] == "20"


def test_the_turn_carries_the_history_into_the_model():
    seen = {}

    def ask(items, tools, prev=None):
        seen["items"] = items
        return {"calls": [], "text": "ok", "id": "r1"}

    class T:
        @staticmethod
        def schemas():
            return []

        @staticmethod
        def run(name, ctx, args):
            return {}

    out = run_turn(None, ask, "vad kostar rören?", history=[{"roll": "user", "text": "hej"}, {"roll": "", "text": ""}], tools=T)
    assert out["svar"] == "ok"
    assert [i["role"] for i in seen["items"]] == ["user", "user"]
    assert seen["items"][0]["content"] == "hej"
