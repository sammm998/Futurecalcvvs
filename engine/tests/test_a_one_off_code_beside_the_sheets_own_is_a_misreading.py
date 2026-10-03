from types import SimpleNamespace as NS
from vvs_engine.source_rules.unattested_codes import set_aside


def label(i, system, number, middle, dn):
    return {'id': i, 'text': f'{system}{number}-{middle}-{dn}', 'usable': True, 'rect': [0, 0, 1, 1],
            'designations': [{'system': system, 'number': number, 'middle': [middle], 'dimension': dn}]}


def sheet(odd):
    return [label(i, 'VS', '1', 'S13', 12) for i in range(6)] + [odd]


def test_a_code_read_once_one_character_from_the_sheets_own_names_nothing():
    # `VS1-S13-22/W` under a room name, read as `VS1-S43-45/W`
    labels = sheet(label(9, 'VS', '1', 'S43', 45))
    out = set_aside(labels, [])
    assert [o['label'] for o in out] == [9]
    assert labels[-1]['designations'] == [] and labels[-1]['usable'] is False


def test_a_code_the_lettering_also_writes_is_kept():
    labels = sheet(label(9, 'VS', '1', 'S43', 45))
    assert set_aside(labels, [NS(tokens=['VS1', 'S43'])]) == []
    assert labels[-1]['designations']


def test_a_rare_code_with_no_common_neighbour_is_kept():
    labels = [label(1, 'SHG', '615', 'VS2', 15), label(2, 'SHG', '615', 'V52', 15)]
    assert set_aside(labels, []) == []


def test_a_code_read_twice_is_the_sheets_own():
    labels = sheet(label(9, 'VS', '1', 'S43', 45)) + [label(10, 'VS', '1', 'S43', 45)]
    assert set_aside(labels, []) == []
