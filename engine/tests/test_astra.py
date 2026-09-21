"""What a second reader is allowed to do to a reading - and, more importantly, what it is not.

A language model in a measurement path is exactly how a takeoff starts lying: it answers confidently, its answer
is indistinguishable from a reading, and nobody can tell afterwards which metres came from the drawing. These
tests are the fence. Each one is a way the fence could be climbed.
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vvs_engine.semantics.astra import (Answer, Question, Settlement, apply_answers, questions_for, settle, verify)

Q = Question(case_id="anc_1", kind="attachment",
             evidence="ledaren slutar mellan två rör av samma familj",
             candidates=("KV1-X31-16", "VV1-X31-16"))


def test_an_answer_that_is_not_a_candidate_is_not_an_answer():
    """The whole guarantee in one line: a model cannot name a pipe the drawing never offered."""
    for invented in ("S3-R8-110", "KV1-X31-20", "ett nytt rör", "KV1", ""):
        a = verify(Q, invented)
        assert a.choice is None, f"tog emot {invented!r}, som inte är någon av kandidaterna"


def test_a_candidate_is_taken_when_it_is_named_exactly():
    a = verify(Q, "VV1-X31-16\nledarlinjen möter det varma röret först")
    assert a.choice == "VV1-X31-16" and "varma" in a.why


def test_an_answer_naming_two_candidates_stays_ambiguous():
    """A case a second reader cannot narrow to one is exactly the case that should stay open."""
    a = verify(Q, "Det är antingen KV1-X31-16 eller VV1-X31-16, omöjligt att säga.")
    assert a.choice is None and "flera" in a.refused


def test_the_model_may_decline():
    a = verify(Q, "OKLART\nbevisen räcker inte")
    assert a.choice is None and not a.refused


def test_a_candidate_quoted_inside_a_sentence_still_counts_when_it_is_the_only_one():
    a = verify(Q, "Efter att ha följt ledaren är svaret KV1-X31-16 eftersom ticken sitter där.")
    assert a.choice == "KV1-X31-16"


def test_without_a_transport_nothing_is_asked_and_nothing_changes():
    """The engine's default: no network, no second reader, every ambiguous case still ambiguous."""
    assert settle([Q]) == []


def test_a_question_with_no_candidates_is_never_asked():
    asked = []
    empty = Question(case_id="x", kind="attachment", evidence="e", candidates=())
    settle([empty], ask=lambda q: asked.append(q) or "vad som helst")
    assert asked == [], "en fråga utan kandidater är ingen fråga någon får svara på"


def test_a_second_reader_that_cannot_be_reached_changes_nothing():
    def boom(q):
        raise RuntimeError("nätverket nere")
    out = settle([Q], ask=boom)
    assert len(out) == 1 and out[0].choice is None and out[0].refused == "RuntimeError"


def test_every_settled_case_records_that_a_model_chose_it():
    """A settled case has to stay distinguishable from one the geometry settled."""
    s = Settlement(answers=settle([Q], ask=lambda q: "KV1-X31-16\nför att"))
    assert s.settled == {"anc_1": "KV1-X31-16"}
    d = s.as_dict()
    assert d["asked"] == 1 and d["settled"] == 1
    assert d["answers"][0]["source"] == "language_model_among_the_drawings_own_candidates"


def test_the_question_carries_the_candidates_and_asks_for_one_of_them():
    p = Q.as_prompt()
    assert "KV1-X31-16" in p and "VV1-X31-16" in p
    assert "OKLART" in p and "Hitta aldrig på" in p


def test_a_refused_answer_is_counted_and_visible():
    s = Settlement(answers=settle([Q], ask=lambda q: "S3-R8-110"))
    d = s.as_dict()
    assert d["settled"] == 0 and d["refused"] == 1
    assert s.settled == {}, "ett avvisat svar får inte läcka in i resultatet"


class _A:
    """A stand-in anchor: only the fields the composer and the applier are allowed to look at."""
    def __init__(self, aid, state, reason, contacts, dn=110):
        self.anchor_id, self.state, self.reason = aid, state, reason
        self.contacts, self.dn = contacts, dn
        self.designation = self.designation_display = "S3-R8-110"
        self.system_token, self.endpoint, self.evidence = "S3", (10.0, 20.0), {"leader_family": "bent|w0.48"}
        self.candidate_families = sorted({c.family for c in contacts})


class _C:
    def __init__(self, family, kind="end_tick"):
        self.family, self.kind = family, kind


def test_only_open_cases_with_a_real_choice_are_asked():
    anchors = [
        _A("ok", "VERIFIED_PIPE_ATTACHMENT", "fine", [_C("f1")]),
        _A("nothing", "AMBIGUOUS_PIPE_ATTACHMENT", "several_vector_families_at_leader_no_token_discrimination", []),
        _A("one", "AMBIGUOUS_PIPE_ATTACHMENT", "several_vector_families_at_leader_no_token_discrimination", [_C("f1")]),
        _A("two", "AMBIGUOUS_PIPE_ATTACHMENT", "several_vector_families_at_leader_no_token_discrimination",
           [_C("f1"), _C("f2")]),
    ]
    qs = questions_for(anchors)
    assert [q.case_id for q in qs] == ["two"], "en bekräftad läsning, och ett fall utan val, ska aldrig frågas"
    assert qs[0].candidates == ("f1", "f2")


def test_an_answer_naming_geometry_the_leader_never_touched_is_refused_at_the_point_of_use():
    """The second fence: verify() passed it, but this leader does not touch that family."""
    a = _A("x", "AMBIGUOUS_PIPE_ATTACHMENT", "system_conflict:layer", [_C("f1"), _C("f2")])
    applied = apply_answers([a], [Answer("x", "f3")])
    assert applied == [] and a.state == "AMBIGUOUS_PIPE_ATTACHMENT"


def test_a_verified_answer_narrows_the_case_and_says_where_it_came_from():
    a = _A("x", "AMBIGUOUS_PIPE_ATTACHMENT", "system_conflict:layer", [_C("f1"), _C("f2")])
    applied = apply_answers([a], [Answer("x", "f2", why="ticken sitter på f2")])
    assert a.state == "VERIFIED_PIPE_ATTACHMENT"
    assert [c.family for c in a.contacts] == ["f2"], "kontakterna ska smalna till den valda familjen"
    assert a.reason.startswith("settled_by_second_reader")
    assert a.evidence["second_reader"]["chose"] == "f2"
    assert applied and applied[0]["anchor"] == "x"


def test_a_case_the_engine_already_settled_is_never_overwritten():
    a = _A("x", "VERIFIED_PIPE_ATTACHMENT", "chain_from_anchor", [_C("f1"), _C("f2")])
    apply_answers([a], [Answer("x", "f2")])
    assert a.reason == "chain_from_anchor", "en läsning motorn kunde försvara får aldrig skrivas över"


def test_the_pipeline_runs_the_second_reader_only_when_it_is_given_one(synthetic_pdf):
    """The wiring, not the module: analyze_page must be unchanged without a transport, and must report with one.

    This is the property every reference run depends on - the engine's answer is its own geometry - so it is
    asserted against the real pipeline rather than trusted from the module's defaults.
    """
    from vvs_engine.pdf.extract import extract_document
    from vvs_engine.pipeline import analyze_page

    pg = extract_document(synthetic_pdf).pages[0]

    plain = analyze_page(pg)
    assert plain.second_reader is None, "utan transport ska ingen andra läsare ha varit inblandad"

    asked: list = []

    def never(q):
        asked.append(q)
        return "OKLART"

    with_reader = analyze_page(pg, second_reader=never)
    assert with_reader.second_reader is not None
    assert with_reader.second_reader["settled"] == 0
    # a reader that answers OKLART must leave the takeoff exactly as it was
    a = {q["designation"]: q["confirmed_total_m"] for q in plain.quantities}
    b = {q["designation"]: q["confirmed_total_m"] for q in with_reader.quantities}
    assert a == b, "ett OKLART-svar får inte flytta en enda meter"


def _backend():
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    from app import jobs
    from app.config import settings
    return jobs, settings


def test_a_reading_is_offline_unless_this_installation_can_reach_a_second_reader(monkeypatch):
    """No key and no proxy is no network. A takeoff that quietly calls out is not one anybody can check."""
    jobs, settings = _backend()
    monkeypatch.setattr(settings, "second_reader", None, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    on, why = jobs.second_reader_state()
    assert on is False and "OPENAI_API_KEY" in why
    assert jobs._second_reader() is None


def test_a_key_in_the_environment_is_the_operator_saying_yes(monkeypatch):
    """The service has exactly one use for an OpenAI key. Requiring a second flag only makes the case where
    someone sets the key and nothing whatsoever happens - which is what production did."""
    jobs, settings = _backend()
    monkeypatch.setattr(settings, "second_reader", None, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-inte-en-riktig-nyckel")
    on, why = jobs.second_reader_state()
    assert on is True and "OPENAI_API_KEY" in why


def test_an_explicit_no_wins_over_a_key(monkeypatch):
    """An operator who says false means false, whatever else is lying around in the environment."""
    jobs, settings = _backend()
    monkeypatch.setattr(settings, "second_reader", False, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-inte-en-riktig-nyckel")
    on, _ = jobs.second_reader_state()
    assert on is False
    assert jobs._second_reader() is None


def test_a_second_reader_that_cannot_be_reached_never_fails_the_analysis(monkeypatch):
    """Turned on and unreachable is a configuration problem, not a reason to lose a drawing's metres."""
    jobs, settings = _backend()
    monkeypatch.setattr(settings, "second_reader", True, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    assert jobs._second_reader() is None


def test_the_build_stamp_never_reports_a_placeholder_as_an_answer(monkeypatch):
    """The image bakes in a word when nothing was passed at build time. Taking it as an answer stopped the search
    before the platform's own commit variable was ever read, and production reported "unknown" for weeks."""
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    from app.main import _build_stamp

    _build_stamp.cache_clear()      # the answer is cached for the life of the process; a test is not one process
    monkeypatch.setenv("VVS_BUILD", "unknown")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc1234567890def")
    assert _build_stamp()["build"] == "abc123456789"

    _build_stamp.cache_clear()
    monkeypatch.setenv("VVS_BUILD", "deadbeef")
    assert _build_stamp()["build"] == "deadbeef"
    _build_stamp.cache_clear()


def test_the_transport_sends_a_key_only_when_this_machine_holds_one(monkeypatch):
    """Behind a proxy the credential is attached after the request leaves; in a container it must be sent."""
    from tools.astra_transport import _auth, available

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    assert _auth() == {}
    assert available()[0] is False

    monkeypatch.setenv("OPENAI_API_KEY", "sk-inte-en-riktig-nyckel")
    h = _auth()
    assert h["Authorization"].startswith("Bearer ")
    assert available()[0] is True


def test_the_transport_needs_no_program_that_may_not_be_installed(monkeypatch):
    """It used to shell out to curl, which a slim image does not carry.

    Every question to the second reader then died with "No such file or directory: 'curl'" - a strange way for a
    drawing to fail, and one no test could have caught because the tests run where curl exists. httpx is a
    dependency of the service, and a dependency cannot go missing.
    """
    import tools.astra_transport as t
    src = open(t.__file__, encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "subprocess" not in body, "transporten startar ett program som kanske inte finns"
    assert "httpx" in body
