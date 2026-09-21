"""Notes remain metadata; explicitly printed service suffixes remain part of the identity."""
from vvs_engine.semantics.annotation import Designation


def _des(text: str, row: str | None, dn: int = 160, source: str = "row") -> Designation:
    return Designation(did="d", page=0, block_id="b", row_index=0, text=text, raw_text=text, pattern="A9-A9",
                       tokens=text.split("-"), system_token=text.split("-")[0], dn=dn, dn_source=source,
                       dn_row_index=1, dn_row_text=row, multiplier=1, bbox=(0.0, 0.0, 1.0, 1.0), angle=0.0,
                       layer="", source="stroke", glyph_scores=[], unknown_chars=0)


def test_a_service_suffix_is_kept_in_the_pipe_name():
    d = _des("S3-P2", "160(L)")
    assert d.display_text == "S3-P2-160 (L)"
    assert d.aside == "(L)" and d.dimension_text == "160"


def test_an_ordinary_note_is_available_without_becoming_the_pipe_name():
    d = _des("S3-P2", "160(NOTE)")
    assert d.display_text == "S3-P2-160" and d.aside == "(NOTE)"


def test_service_suffixes_are_not_completed_onto_unmarked_pipes():
    from vvs_engine.pipes.ownership import identity_from_text, complete_identities
    plain = identity_from_text('S3-P2-160', 160, 'S3', 2)
    vent = identity_from_text('S3-P2-160 (L)', 160, 'S3', 2)
    fused = identity_from_text('S3-P2-160L', 160, 'S3', 2)
    assert vent.key == fused.key and vent.key != plain.key
    assert not vent.compatible(plain)
    completed = complete_identities({'plain':plain, 'vent':vent})
    assert completed['plain'].key == plain.key


def test_a_dimension_row_without_an_aside_is_unchanged():
    d = _des("KV2-X31", "16", dn=16)
    assert d.display_text == "KV2-X31-16" and d.aside == "" and d.dimension_text == "16"


def test_a_bracket_that_is_the_whole_row_leaves_the_code_alone():
    """Ingen siffra kvar när tillägget tagits bort: raden var inget mått, och koden står som den står."""
    d = _des("S3-P2", "(L)", dn=None)
    assert d.display_text == "S3-P2"


def test_an_inline_dimension_is_not_touched():
    d = _des("S3-P2-160", None, source="inline")
    assert d.display_text == "S3-P2-160" and d.aside == ""
