"""On W-50-1-A-0314 the stroke reader read `VS1-S13` right, and the sheet's pattern statistics flipped it to
`VS1-513`: three such labels outvoted the one `VS1-S13-22/W`. A flip that invents a number no pipe has is not
taken; a flip that repairs a size still is."""
from vvs_engine.semantics.grammar import DesignationGrammar, WordReading, compress_pattern


def _r(text, flips):
    return WordReading(text, compress_pattern(text), flips, 0.01 * flips)


def test_a_material_code_is_not_flipped_into_a_number_no_pipe_has():
    g = DesignationGrammar()
    g.pattern_weight["A9-9"] = 10.0          # the wrong shape is the common one on this sheet
    assert g.choose([_r("VS1-S13", 0), _r("VS1-513", 1)]).text == "VS1-S13"


def test_a_flip_that_repairs_a_size_is_still_taken():
    g = DesignationGrammar()
    g.pattern_weight["A9-9"] = 10.0
    assert g.choose([_r("KV1-11O", 0), _r("KV1-110", 1)]).text == "KV1-110"
