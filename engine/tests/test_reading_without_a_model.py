"""The final assignment answered from the drawing's own evidence, and framed leaders taken apart."""
import sys
from dataclasses import dataclass

from vvs_engine.source_rules.boxed_leaders import split
from vvs_engine.source_rules.native_detection import SOURCE
from vvs_engine.source_rules.rule_answer import answer

if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))


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


def test_a_leader_stored_around_its_end_mark_is_walked_from_the_label():
    from vvs_engine.source_rules.boxed_leaders import reorder_leaders
    # V-50-1-666340-0113, KV2-K1-22/S2: leader to the pipe, its end slash, then the shelf under the text
    items = [['l', 1355, 586, 1253, 698], ['l', 1251, 696, 1255, 700], ['l', 1355, 586, 1420, 586]]
    ex = Ex([P(0, 's', .48, [0, 0, 0], None, '[] 0', '', False, [1251, 586, 1420, 700], items)])
    out, report = reorder_leaders(ex, [[1356.7, 575.2, 1418.3, 586.2]])
    assert report['reordered'] == 1
    leader, mark = out.paths
    assert leader.items == [['l', 1420, 586, 1355, 586], ['l', 1355, 586, 1253, 698]]
    assert mark.items == [items[1]]


def test_a_ladder_is_left_as_it_was_drawn():
    from vvs_engine.source_rules.boxed_leaders import reorder_leaders
    fork = [['l', 0, 0, 50, 50], ['l', 50, 50, 90, 50], ['l', 50, 50, 50, 90], ['l', 91, 51, 89, 49]]
    ex = Ex([P(0, 's', .48, [0, 0, 0], None, '[] 0', '', False, [0, 0, 91, 90], fork)])
    assert reorder_leaders(ex, [[-5, -5, 5, 5]])[1]['reordered'] == 0


@dataclass
class T:
    text: str
    bbox: list


@dataclass
class ExT:
    paths: list
    texts: list


def test_a_label_box_reaches_its_shelf_and_its_whole_text():
    from vvs_engine.source_rules.label_shelves import extend_to_shelves, SHORT_OF_END
    # V-50-2-666339-0001: VV1-K1-22/S3 written on a shelf that runs 18 pt past the text, its leader starting there
    shelf = P(0, 's', .48, [0, 0, 0], None, '[] 0', '', False, [523, 657, 698, 657], [['l', 698, 657, 523, 657]])
    ex = ExT([shelf], [T('VV1-K1-22/S3', [527.3, 630.0, 679.6, 657.5])])
    det = {'label_boxes': [{'id': 1, 'rect': [527.3, 630.0, 679.6, 657.5]}]}
    labels = [{'id': 1, 'rect': [527.3, 630.0, 679.6, 657.5]}]
    det, labels, report = extend_to_shelves(ex, det, labels)
    assert det['label_boxes'][0]['rect'][2] == labels[0]['rect'][2] == 698 - SHORT_OF_END
    # a box the tiled detector cut at a tile edge covers its whole text again
    ex = ExT([], [T('VS2-S13-35/S4', [1496.5, 626.0, 1566.5, 637.0])])
    det = {'label_boxes': [{'id': 2, 'rect': [1496.5, 626.0, 1536.0, 637.0]}]}
    det, _, _ = extend_to_shelves(ex, det, [])
    assert det['label_boxes'][0]['rect'][2] == 1566.5


def test_a_leader_without_a_landing_lands_where_its_free_end_meets_a_pipe():
    from vvs_engine.source_rules.free_end_landings import land_free_ends
    A = {'nodes': [{'id': 7, 'x': 445.9, 'y': 689.3, 'stretches': [1]}, {'id': 8, 'x': 1344.5, 'y': 733.4, 'stretches': [2]}]}
    R = {'tolerances': {'landing': 3.0}, 'leaders': [
        # from the corner of a two-row label frame straight up to its pipe (VS2-S13-12/S4)
        {'id': 0, 'label': 9, 'anchor': [446, 720], 'points': [[446, 689], [446, 720]], 'landings': []},
        # a shelf from the text straight to the pipe beside it, anchored at the pipe end (KV2-K1-35/S2)
        {'id': 1, 'label': 46, 'anchor': [1344.5, 733.4], 'points': [[1276.6, 733.4], [1344.5, 733.4]], 'landings': []},
        # a leader that landed is left as it was read
        {'id': 2, 'label': 3, 'anchor': [0, 0], 'points': [[0, 0], [445, 689]], 'landings': [{'point': [9, 9], 'node': 99}]}]}
    labels = [{'id': 46, 'rect': [1278.9, 722.8, 1342.7, 733.9]}]
    R, report = land_free_ends(A, R, labels)
    assert [g['node'] for g in R['leaders'][0]['landings']] == [7]
    assert [g['node'] for g in R['leaders'][1]['landings']] == [8]
    assert [g['node'] for g in R['leaders'][2]['landings']] == [99] and report['landed'] == 2


def test_a_leader_lands_on_the_slash_drawn_where_it_meets_its_pipe():
    from vvs_engine.source_rules.free_end_landings import land_free_ends
    # V-50-2-666339-0001, VS1-S13-54/V3: the leader touches the pipe ink 3.8 pt from the slash between the walls
    A = {'nodes': [{'id': 635, 'x': 1006.08, 'y': 785.68, 'kind': 'tick', 'stretches': [803]},
                   {'id': 9, 'x': 1006.08, 'y': 794.0, 'kind': 'end', 'stretches': [5]}]}
    R = {'tolerances': {'landing': 3.0}, 'leaders': [
        {'id': 0, 'label': 3, 'anchor': [927.1, 572.0], 'points': [[1006.08, 789.52], [927.1, 572.0]],
         'landings': [{'point': [1006.08, 789.52], 'node': None}]}]}
    R, report = land_free_ends(A, R, [])
    assert [g['node'] for g in R['leaders'][0]['landings'] if g['node'] is not None] == [635]


def test_a_split_form_with_a_suffix_is_read_joined():
    # V-50-1-666339-0123: 'VV1-K1/S3' over a bare '22' is VV1-K1-22/S3; a label that reads as something stays
    from vvs_engine.source_rules.text_labels import rejoin
    riser = {'text': 'VV1-K1/S3\n22', 'designations': [], 'score': .9}
    stack = {'text': 'VS2-S13/S4\n35', 'designations': [], 'score': .9}
    other = {'text': 'APPARATSKÅP', 'designations': [], 'score': .9}
    labels, n = rejoin([riser, stack, other])
    assert n == 2
    assert [d['raw'] for d in riser['designations']] == ['VV1-K1-22/S3']
    assert [d['raw'] for d in stack['designations']] == ['VS2-S13-35/S4']
    assert other['designations'] == []


def test_dashed_pipes_in_the_leader_pen_keep_every_other_pen_as_read():
    # V-50-1-666340-0111: the pipe pen stands; the dashed 0.48 pt strokes become pipe, the plain 0.48 pt leaders
    from vvs_engine.source_rules.native_detection import kept_policy
    pipe = P(0, 's', 1.44, [0, 0, 0], None, '[] 0', 'P', False, [0, 0, 100, 0], [['l', 0, 0, 100, 0]])
    wall = P(1, 's', .25, [.5, .5, .5], None, '[] 0', 'A', False, [0, 9, 100, 9], [['l', 0, 9, 100, 9]])
    dash = P(2, 's', .5, [0, 0, 0], None, '[] 0', 'S', False, [0, 50, 90, 50], [['l', 0, 50, 17, 50]])
    lead = P(3, 's', .48, [0, 0, 0], None, '[] 0', 'S', False, [5, 50, 5, 80], [['l', 5, 50, 5, 80]])
    B = {'calibration': {'u_paper': 1.0, 'pipe_widths': [1.44]},
         'buckets': {'0': 'pipe', '1': 'architecture', '2': 'thin_other', '3': 'thin_other'}}
    roles = {f['key']['width']: f['role'] for f in kept_policy(Ex([pipe, wall, dash, lead]), B, .5, .48)['policy']['families']}
    assert roles == {1.44: 'pipe', .25: 'architecture', .5: 'pipe', .48: 'leader'}
