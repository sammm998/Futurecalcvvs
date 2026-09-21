"""Kommatecknet mellan två koder på samma rad hör till raden, inte till koden.

En rad som räknar upp flera rör skriver dem med komma emellan: `KV0175-32, VV0175-32`. Läsningen delade raden
på mellanslag och behöll skiljetecknet, så den första koden blev `KV0175-32,`. Tecknen är desamma som i
`KV0175-32`, och tokenerna blir desamma - men mönstret blir inte det: `A9-9,` mot `A9-9`. Bladets egen grammatik
räknar familjer per mönster, så ett rör som skrivs både med och utan komma blir två familjer, ingendera med nog
många medlemmar för att bära röret. På ett blad ur ett projekt läsningen aldrig sett stod fjorton beteckningar
med ett komma på slutet, och ingen av dem fick en meter.

Bara sist i ordet. Ett komma inne i ordet kan vara en decimal - `32,5` är ett mått, inte två koder - och den
delen av raden rörs inte.
"""
from vvs_engine.semantics.grammar import compress_pattern, is_code_like, split_tokens, strip_row_separator


def test_the_comma_that_separates_two_codes_is_not_part_of_the_first():
    assert strip_row_separator("KV0175-32,") == "KV0175-32"
    assert strip_row_separator("VV0175-32;") == "VV0175-32"


def test_a_code_written_with_and_without_the_separator_is_one_family():
    """Det är det här som kostade metrarna: samma rör i två grammatikfamiljer."""
    with_comma = compress_pattern(strip_row_separator("KV0175-32,"))
    without = compress_pattern(strip_row_separator("KV0175-32"))
    assert with_comma == without == "A9-9"
    assert split_tokens(strip_row_separator("KV0175-32,")) == split_tokens("KV0175-32")


def test_a_comma_inside_the_word_is_left_alone():
    """En decimal är inte ett skiljetecken."""
    assert strip_row_separator("32,5") == "32,5"
    assert strip_row_separator("KV0,5-16") == "KV0,5-16"


def test_a_word_that_is_only_separators_is_left_as_it_is():
    """Inget att skala bort till: hellre oförändrad än tom."""
    assert strip_row_separator(",") == ","
    assert strip_row_separator(",,;") == ",,;"


def test_the_stripped_code_is_still_a_code():
    assert is_code_like(strip_row_separator("KV0175-32,"))


def test_a_row_of_several_codes_yields_the_codes_without_their_separators():
    """Så som raden delas i annotation.py: mellanslag delar, skiljetecknet faller bort."""
    row = "KV0175-32, VV0175-32, VVC0175-25"
    words = [strip_row_separator(w) for w in row.split(" ")]
    assert words == ["KV0175-32", "VV0175-32", "VVC0175-25"]
    assert all(is_code_like(w) for w in words)
    assert len({compress_pattern(w) for w in words}) == 1
