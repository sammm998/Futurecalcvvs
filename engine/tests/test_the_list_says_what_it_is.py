"""Listan skriver ut vad varje kod betyder. Läs det.

Resten av läsningen kan ingen svenska med flit: en beteckningslista hittas på sin form och tolkas på hur
ritningen använder den, och det är vad som gör att den fungerar på ett kontor den aldrig sett. Men listan
skriver också ut vad koderna betyder, med ingenjörens egna ord, och att inte läsa dem är att kasta bort det
starkaste beviset som finns på bladet.

Vad det kostade att inte läsa dem: på ett ventilationsblad skrivs ett tilluftsdon `TD102-100`, med
anslutningsmåttet efter koden. Läsningen såg en dimension, drog slutsatsen att koden öppnar ett rörsystem, och
räknade trettio don, spjäll och ljuddämpare som trettio rörsystem utan meter. Täckningen läste 51 % på ett blad
där den var 80 %, och femtio meter kanal låg under ett don.

Svenskan gör det ovanligt lätt: ett sammansatt ord bär huvudordet sist. Ett BRANDGASSPJÄLL är ett SPJÄLL, ett
TILLUFTSDON är ett DON, en CIRKULATIONSFLÄKT är en FLÄKT. Så det räcker att se vad ordet slutar på.

Och där orden inte räcker får de inte gissa. `RENSRÖR MED LOCK` slutar på RÖR och mäts i stycken; `STUPRÖR`
slutar likadant och mäts i meter. Där avgör ritningens egen användning som förut.
"""
import pytest

from vvs_engine.semantics.legend import (DrawingLegend, LegendEntry, assign_roles, role_from_words)


def _entry(code, description, role="material"):
    return LegendEntry(code=code, description=description, heading="", bbox=(0.0, 0.0, 1.0, 1.0), role=role)


class _D:
    """En beteckning som ritningen skriver, så mycket av den som rollsättningen läser."""

    def __init__(self, text, system_token, dn=None, bbox=(500.0, 500.0, 560.0, 510.0)):
        self.text, self.system_token, self.dn, self.bbox = text, system_token, dn, bbox
        self.did, self.family, self.pattern = text, "f", "p"


@pytest.mark.parametrize("description,expected", [
    ("= TILLUFSDON, VENTIL", "component"),
    ("=FRÅNLUFTSDON, KONTROLLVENTIL", "component"),
    ("= BRAND/BRANDGASSPJÄLL, CIRK. E60", "component"),
    ("= INJUST./MÄTSPJÄLL, CIRK. - MANUELLT", "component"),
    ("= LJUDDÄMPARE, CIRK. - 50mm", "component"),
    ("=CIRKULATIONSFLÄKT", "component"),
    ("= RENSLUCKA EN.RITN.- BRANDKLASS LIKA KANAL", "component"),
    ("=TAKGENOMFÖRING, REKT. EI30", "component"),
    ("GOLVBRUNN", "component"),
    ("VATTENLÅS", "component"),
    ("TVATTSTALL", "component"),
    ("= TILLUFT", "system"),
    ("= FRÅNLUFT", "system"),
    ("TAPPKALLVATTEN", "system"),
    ("SPILLVATTEN", "system"),
    ("= FÖRZINKAD PLÅT", "material"),
    ("= KONDENS 30mm + AL.FOLIE", "material"),
    ("= BRAND EI30", "material"),
])
def test_the_words_say_what_a_code_is(description, expected):
    assert role_from_words(description) == expected


@pytest.mark.parametrize("description", [
    "RENSRÖR MED LOCK",     # slutar på RÖR och mäts i stycken
    "STUPRÖR",              # slutar likadant och mäts i meter
    "PEX ROR",
    "MA ROR",
    "= VÄRME 100mm",
    "OBS! SAMORDNAS MED EL",
])
def test_the_words_stand_down_where_they_cannot_tell(description):
    """Ett ord som inte avgör saken får inte låtsas göra det. Då avgör användningen, som förut."""
    assert role_from_words(description) is None


def test_a_terminal_with_a_connection_size_is_not_a_pipe():
    """Det felet som kostade mest: ett don med sitt anslutningsmått läst som ett rörsystem."""
    lg = DrawingLegend(entries=[
        _entry("T", "= TILLUFT"), _entry("F", "= FRÅNLUFT"),
        _entry("B101", "= BRAND EI15"), _entry("K403", "= KONDENS 30mm + AL.FOLIE"),
        _entry("TD102", "= TILLUFSDON, VENTIL"), _entry("SP101", "= INJUST./MÄTSPJÄLL, CIRK."),
        _entry("LD101", "= LJUDDÄMPARE, CIRK. - 50mm"),
    ])
    assign_roles(lg, [_D("T1-200-B101", "T", 200), _D("TD102-100", "TD102", 100),
                      _D("SP101-200", "SP101", 200)])
    assert "T" in lg.systems() and "F" in lg.systems()
    assert {"TD102", "SP101", "LD101"} <= lg.components()
    assert not lg.names_a_pipe(_D("TD102-100", "TD102", 100)), "ett tilluftsdon är aldrig meter"
    assert not lg.names_a_pipe(_D("SP101-200", "SP101", 200)), "ett spjäll är aldrig meter"
    assert lg.names_a_pipe(_D("T1-200-B101", "T", 200)), "kanalen är det"


def test_the_longest_code_wins_over_the_shortest():
    """En lista med både `T` för tilluft och `TD102` för ett don måste läsa `TD102-100` som donet.

    Prövat kortaste först blev varje don ett system: koden `T` är början på `TD102` också, och en enbokstavskod
    slukade hela listan.
    """
    lg = DrawingLegend(entries=[_entry("T", "= TILLUFT"), _entry("TD102", "= TILLUFSDON, VENTIL")])
    assign_roles(lg, [_D("T1-200", "T", 200), _D("TD102-100", "TD102", 100)])
    assert lg.code_for("TD102-100") == "TD102"
    assert lg.code_for("T1-200") == "T"
    assert lg.role_of_head("TD102-100") == "component"


def test_a_material_token_lets_the_sheet_overrule_the_words():
    """Där bladet skriver koden som ett rör avgör bladet - men bara på listans eget bevis.

    `TS1-X7-16` är ett tvättställ enligt orden och en PEX-ledning enligt bladet, för X7 står i listan som ett
    material. `TD102-100` bär inget material alls, bara ett mått, och förblir ett don. Det är den skillnaden
    som skiljer en ledning från en pryl med ett mått, och den är hämtad ur listan.
    """
    lg = DrawingLegend(entries=[
        _entry("KV01", "TAPPKALLVATTEN"), _entry("X7", "PEX ROR"), _entry("TS1", "TVATTSTALL"),
    ])
    assign_roles(lg, [_D("KV01-X7-16", "KV01", 16), _D("TS1-X7-16", "TS1", 16)])
    assert "TS1" in lg.systems(), "bladet skriver TS1 med ett materialled: det mängdar på koden"

    lg2 = DrawingLegend(entries=[
        _entry("T", "= TILLUFT"), _entry("K403", "= KONDENS 30mm"), _entry("TD102", "= TILLUFSDON"),
    ])
    assign_roles(lg2, [_D("T1-200-K403", "T", 200), _D("TD102-100", "TD102", 100)])
    assert "TD102" in lg2.components(), "ett mått är inget material: donet står kvar som don"


def test_a_row_read_twice_is_one_row():
    """Ett blad kan bära sin lista två gånger, som text i filen och som strecken som ritar den.

    Läsningen såg två listor lagda på varandra och tog båda: sextio rader där bladet har trettio, och den
    sämre halvan full av koder som inte finns - `RL1O1` bredvid `RL101`, `LD1OZ` bredvid `LD102`. Varje sådan
    kod blev sedan ett rörnamn som mängden redovisade som ett rör den aldrig hittade.
    """
    from vvs_engine.semantics.legend import _one_per_line

    class _Row:
        def __init__(self, text, y0, y1, source, unknown=0):
            self.text, self.bbox, self.source, self.unknown_chars = text, (100.0, y0, 300.0, y1), source, unknown
            self.glyphs = ()

    good = _Row("RL101 = RENSLUCKA", 344.1, 354.5, "text")
    bad = _Row("RL1O1 = RENSLUCKA", 346.5, 352.9, "vector", unknown=1)
    assert [r.text for r in _one_per_line([good, bad])] == ["RL101 = RENSLUCKA"]
    assert [r.text for r in _one_per_line([bad, good])] == ["RL101 = RENSLUCKA"]

    apart = _Row("LD102 = LJUDDÄMPARE", 504.4, 515.4, "text")
    assert len(_one_per_line([good, apart])) == 2, "två olika rader är fortfarande två rader"
