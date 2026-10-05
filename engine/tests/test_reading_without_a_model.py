"""The final assignment answered from the drawing's own evidence, and framed leaders taken apart."""
from dataclasses import dataclass

from vvs_engine.source_rules.boxed_leaders import split
from vvs_engine.source_rules.rule_answer import answer


def cand(label, raw, *evidence):
    return {'label': label, 'designation_idx': 0, 'designation': {'raw': raw}, 'text': raw, 'evidence': list(evidence)}


def test_the_nearest_landing_names_the_stretch():
    q = {'stretch': 1, 'candidates': [
        cand(7, 'VS2-S13-12/S4', {'kind': 'connected_run', 'via_stretches': [1, 2, 3, 4]}),
        cand(8, 'VS2-S13-22/S4', {'kind': 'leader_landing', 'node': 5})]}
    d, = answer([q])
    assert (d['label'], d['ambiguous']) == (8, False)


def test_a_shorter_run_wins_and_a_tie_is_marked_for_review():
    near = cand(7, 'KV1-K1-28', {'kind': 'connected_run', 'via_stretches': [1, 2]})
    far = cand(8, 'VV1-K1-28', {'kind': 'connected_run', 'via_stretches': [1, 2, 3]})
    assert answer([{'stretch': 1, 'candidates': [far, near]}])[0]['label'] == 7
    tie = cand(9, 'VVC1-K1-18', {'kind': 'connected_run', 'via_stretches': [4, 5]})
    d, = answer([{'stretch': 1, 'candidates': [near, tie]}])
    assert d['ambiguous'] is True


def test_a_stretch_without_candidates_stays_unnamed():
    assert answer([{'stretch': 3, 'candidates': []}]) == [
        {'stretch': 3, 'label': None, 'designation_idx': None, 'ambiguous': False}]


@dataclass
class P:
    id: int
    kind: str
    width: float
    color: list
    fill: object
    dashes: str
    layer: str
    closed: bool
    rect: list
    items: list
    duplicate_of: object = None


@dataclass
class Ex:
    paths: list


def test_a_frame_drawn_with_its_leader_is_split_into_frame_and_leader():
    # V-50-1-666340-0113: leader up to the pipe, its end mark, the underline and the frame - one stroke
    items = [['l', 659, 1257, 659, 1334], ['l', 661, 1259, 657, 1255], ['l', 659, 1334, 589, 1334],
             ['l', 589, 1349, 659, 1349], ['l', 659, 1349, 659, 1334]]
    ex = Ex([P(0, 's', .48, [0, 0, 0], None, '[] 0', '', False, [589, 1255, 661, 1349], items)])
    out, report = split(ex, [[588.1, 1323.1, 660.0, 1349.7]])
    assert report['split'] == 1
    frame, leader, mark = out.paths
    assert frame.items == items[2:]
    assert leader.items == [items[0]] and mark.items == [items[1]]
    assert sorted(it for p in out.paths for it in p.items) == sorted(items)


def test_grey_ink_is_never_split():
    items = [['l', 0, 0, 10, 0], ['l', 10, 0, 10, 10], ['l', 10, 10, 50, 50]]
    ex = Ex([P(0, 's', .48, [.6, .6, .6], None, '[] 0', '', False, [0, 0, 50, 50], items)])
    assert split(ex, [[-1, -1, 11, 11]])[1]['split'] == 0
