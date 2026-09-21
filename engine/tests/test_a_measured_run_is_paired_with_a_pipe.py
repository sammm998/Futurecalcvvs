"""Mängdarens enskilda dragningar parade mot läsningens enskilda rör, inte summa mot summa.

En referensarbetsbok har en rad per dragning mängdaren gjorde. Summan per beteckning döljer vad raderna
säger: två stråk på 8,7 m och ett enda på 17,4 m ger samma summa, fast bara det ena är ritat så. Parningen i
engine/tools/pipe_audit.py packar upp summan igen, och det är den som avgör om en avvikelse kallas hopslagen,
uppdelad, kort, lång eller saknad. Klassen styr vilken slutsats en granskare drar, så den är värd ett prov.

Provet är räknat, inte mätt: längderna nedan är påhittade tal, och ingen referensfil öppnas här.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from pipe_audit import pair_runs  # noqa: E402


def pipes(*ms):
    return [{"m": m, "id": f"pp_{i}", "frontier_reasons": []} for i, m in enumerate(ms)]


def classes(pairs):
    return sorted(p["class"] for p in pairs)


def test_two_runs_and_two_pipes_of_the_same_length_are_the_same_two_runs():
    assert classes(pair_runs([8.7, 8.7], pipes(8.64, 8.59))) == ["SAME_RUN", "SAME_RUN"]


def test_one_pipe_that_covers_four_measured_runs_is_merged_not_missing():
    p = pair_runs([5.9, 2.4, 0.9, 0.6], pipes(10.04))
    assert classes(p) == ["MERGED"]
    assert sorted(p[0]["reference"], reverse=True) == [5.9, 2.4, 0.9, 0.6]


def test_two_pipes_that_share_one_measured_run_are_split_not_short():
    p = pair_runs([12.0], pipes(7.0, 5.0))
    assert classes(p) == ["SPLIT"]
    assert len(p[0]["ours"]) == 2


def test_a_pipe_that_stops_halfway_is_short_and_one_that_runs_on_is_long():
    assert classes(pair_runs([20.0], pipes(8.0))) == ["SHORT_RUN"]
    assert classes(pair_runs([8.0], pipes(20.0))) == ["LONG_RUN"]


def test_a_stub_of_a_centimetre_does_not_pass_for_a_run_of_three_decimetres():
    assert classes(pair_runs([0.3], pipes(0.01))) == ["SHORT_RUN"]


def test_a_measured_run_without_any_pipe_is_missing_and_a_pipe_without_one_is_extra():
    assert classes(pair_runs([4.0, 3.0], [])) == ["MISSING_RUN", "MISSING_RUN"]
    assert classes(pair_runs([], pipes(4.0))) == ["EXTRA_RUN"]


def test_the_longest_pipe_answers_for_the_longest_run_however_the_rows_arrive():
    a = pair_runs([20.0, 4.0], pipes(15.0, 1.0))
    b = pair_runs([4.0, 20.0], pipes(1.0, 15.0))
    assert [(p["class"], sum(p["reference"])) for p in a] == [(p["class"], sum(p["reference"])) for p in b]
    assert classes(a) == ["SHORT_RUN", "SHORT_RUN"]
    longest = next(p for p in a if sum(p["reference"]) == 20.0)
    assert longest["ours"] == [0]


def test_a_sheet_with_nothing_measured_and_nothing_read_pairs_to_nothing():
    assert pair_runs([], []) == []
