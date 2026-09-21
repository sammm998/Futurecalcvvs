"""Explicit connection-pipe codes are rules only inside their written scope."""
import pymupdf
import pytest

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.semantics.declarations import read_declarations
from test_a_table_written_short_still_declares_the_connection_pipes import _row
from test_a_sheet_table_names_the_connection_pipes import _sheet


def _note(codes, x=30, y=30):
    return [_row("KOPPLINGSLEDNINGAR", x, y),
            _row("FÖLJANDE GÄLLER OM EJ ANNAT ANGES:", x, y+12),
            _row(codes, x, y+24)]


def test_full_codes_and_shared_suffixes_keep_the_explicit_pipe_size():
    rows = _note("RAD1-X31-16? KV1/VV1-X31-16.")
    rows += [_row("ANSL KV VV S", 30, 66), _row("BL 12 15 75", 30, 78)]
    d = read_declarations(rows)
    assert {p.text for p in d.connection_pipes} == {"RAD1-X31-16", "KV1-X31-16", "VV1-X31-16"}
    assert all(p.dns == (16,) for p in d.connection_pipes)
    assert rows[2].text in d.statement


@pytest.mark.parametrize("text", ["KV1-X31-?6", "KV1-X31-16 VID TVÄTTSTÄLL", "KV1-X31-16/20", "KV1-X31-1600"])
def test_damaged_conditional_or_ambiguous_codes_do_not_set_a_default(text):
    assert not read_declarations(_note(text))


def test_a_nearby_label_without_the_written_default_is_not_a_declaration():
    assert not read_declarations([_row("KOPPLINGSLEDNINGAR", 30, 30), _row("KV1-X31-16", 30, 54)])
    assert not read_declarations(_note("ANSL KV VV S") + [_row("KV1-X31-16", 300, 54)])


def test_conflicting_written_defaults_keep_both_sizes_and_choose_neither():
    d = read_declarations(_note("KV1-X31-16") + _note("KV1-X31-20", y=130))
    assert len(d.connection_pipes) == 1
    assert d.connection_pipes[0].dn is None
    assert d.connection_pipes[0].dns == (16, 20)


@pytest.mark.parametrize("layered", [True, False])
def test_inline_rules_name_only_runs_with_independent_system_evidence(tmp_path, layered):
    source = _sheet(str(tmp_path / "base.pdf"), declare=False)
    doc = pymupdf.open(source)
    page = doc[0]
    for i, text in enumerate(("KOPPLINGSLEDNINGAR", "OM EJ ANNAT ANGES", "KV01-X31-16, VV01-X31-16.")):
        page.insert_text((520, 80+13*i), text, fontsize=9)
    path = tmp_path / "inline.pdf"
    doc.save(path)
    doc.close()
    raw = extract_document(str(path)).pages[0]
    if not layered:
        for p in raw.paths:
            p.layer = ""
    pa = analyze_page(raw)
    assert {d.text for d in pa.declarations.connection_pipes} == {"KV01-X31-16", "VV01-X31-16"}
    rows = {q["designation"]: q for q in pa.quantities}
    if layered:
        assert 11 <= rows["KV01-X31-16"]["declared_m"] <= 13
        assert any(n.startswith("KV01-X7") for n in rows)
    else:
        assert not any(q.get("declared_m", 0) for q in rows.values())
    assert "VV01-X31-16" not in rows
