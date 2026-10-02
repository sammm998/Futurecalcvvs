from types import SimpleNamespace

from vvs_engine.pipeline import _is_an_apparatus_tag
from vvs_engine.semantics.legend import DrawingLegend, LegendEntry


def _d(text):
    return SimpleNamespace(text=text, tokens=text.split('-'))


def test_a_valve_tag_with_code_and_dimension_only_is_not_a_pipe():
    assert _is_an_apparatus_tag(_d('AV21-10'), None)
    assert _is_an_apparatus_tag(_d('SV611-10'), None)
    assert _is_an_apparatus_tag(_d('RV61-20'), None)


def test_a_pipe_designation_with_a_material_is_never_a_valve_tag():
    assert not _is_an_apparatus_tag(_d('SV01-51-110'), None)
    assert not _is_an_apparatus_tag(_d('VS1-S13-22'), None)
    assert not _is_an_apparatus_tag(_d('KV1-20'), None)


def test_a_valve_code_the_sheet_lists_as_a_system_stays_a_pipe():
    legend = DrawingLegend(entries=[LegendEntry(code='SV1', description='SPILLVATTEN', heading='', bbox=(0, 0, 1, 1), role='system')])
    assert not _is_an_apparatus_tag(_d('SV1-110'), legend)
