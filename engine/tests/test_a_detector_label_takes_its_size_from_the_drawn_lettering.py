"""A detector label whose size the OCR lost takes the size the drawing's own lettering states - and only that.

On W-50-1-A-0014 a dimension row "75" drawn between two bars was read by OCR as "715", the size was dropped as
implausible for a drain and the label named no pipe: its stretch went unmeasured. The host engine reads the
same lettering from the strokes as S1-P2 over 75.
"""
from types import SimpleNamespace

from vvs_engine.source_rules.host_label_repair import repair


def _label(text="S1-P2\n715", rect=(963.0, 957.0, 992.0, 979.0)):
    return {'id': 44, 'text': text, 'rect': list(rect), 'usable': False, 'designations': [
        {'raw': 'S1-P2', 'count': 1, 'system': 'S', 'number': '1', 'dimension': None, 'middle': ['P2'],
         'suffix': None, 'venting': False, 'recognised': True, 'partial': True}]}


def _host(text="S1-P2", dn=75, bbox=(967.0, 958.0, 989.0, 965.0), did="des_1"):
    return SimpleNamespace(text=text, dn=dn, bbox=bbox, did=did)


def test_the_lost_size_is_taken_from_the_lettering_in_the_same_box():
    labels = [_label()]
    out = repair(labels, [_host()])
    assert labels[0]['designations'][0]['dimension'] == 75
    assert labels[0]['usable'] is True and labels[0]['designations'][0]['partial'] is False
    assert out and out[0]['host_readings'] == ['des_1']


def test_another_pipe_in_the_box_does_not_lend_its_size():
    labels = [_label()]
    assert repair(labels, [_host(text="S3-R8")]) == []
    assert labels[0]['designations'][0]['dimension'] is None and labels[0]['usable'] is False


def test_two_different_sizes_in_the_box_settle_nothing():
    labels = [_label()]
    assert repair(labels, [_host(dn=75, did="a"), _host(dn=110, did="b")]) == []
    assert labels[0]['designations'][0]['dimension'] is None


def test_lettering_outside_the_box_is_not_this_label():
    labels = [_label()]
    assert repair(labels, [_host(bbox=(1200.0, 958.0, 1222.0, 965.0))]) == []


def test_an_implausible_size_is_not_lent():
    labels = [_label()]
    assert repair(labels, [_host(dn=15)]) == []            # a drain is never DN 15
