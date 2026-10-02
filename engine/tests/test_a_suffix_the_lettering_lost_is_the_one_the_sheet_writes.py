"""OCR read `VP1-S13-42/W` as `VP1-S13-42/` on W-50-1-A-0114, and one line became two rows in the quantity."""
from vvs_engine.source_rules.lost_suffix import restore


def _label(i, raw, suffix, dim=42, middle=('S13',)):
    return {'id': i, 'designations': [{'raw': raw, 'system': 'VP', 'number': '1', 'middle': list(middle),
                                       'dimension': dim, 'suffix': suffix}]}


def test_a_trailing_slash_takes_the_suffix_the_sheet_writes_for_that_line_and_size():
    labels = [_label(0, 'VP1-S13-42/W', 'W'), _label(1, 'VP1-S13-42/', None)]
    repairs = restore(labels)
    assert labels[1]['designations'][0]['raw'] == 'VP1-S13-42/W'
    assert labels[1]['designations'][0]['suffix'] == 'W'
    assert repairs == [{'label': 1, 'before': 'VP1-S13-42/', 'after': 'VP1-S13-42/W'}]


def test_two_suffixes_for_that_line_and_size_leave_it_alone():
    labels = [_label(0, 'VP1-S13-42/W', 'W'), _label(1, 'VP1-S13-42/WB', 'WB'), _label(2, 'VP1-S13-42/', None)]
    assert restore(labels) == []
    assert labels[2]['designations'][0]['raw'] == 'VP1-S13-42/'


def test_another_size_says_nothing_about_this_one():
    labels = [_label(0, 'VP1-S13-28/WB', 'WB', dim=28), _label(1, 'VP1-S13-42/', None)]
    assert restore(labels) == []


def test_a_label_without_a_slash_is_never_given_a_suffix():
    labels = [_label(0, 'VP1-S13-42/W', 'W'), _label(1, 'VP1-S13-42', None)]
    assert restore(labels) == []
