"""En nothöjd i etikettrutan ska inte kräva ett eget rör.

Etikettrutan på ett VVS-blad bär rörnamnen och under dem ofta en höjd: "CL 3060 REL", "CL=2500". Höjden säger
var röret ligger, inte att där finns ytterligare ett rör. Men raden har samma form som en beteckning, så
läsningen räknade den som en rad till som skulle ha en ritad sträcka. Då gick avbildningen inte ihop - två
rader mot en sträcka - och kravet på ett-till-ett gjorde **båda** tvetydiga. Rörnamnet bredvid noten tappade
alltså sitt rör för att noten stod där.

Uppmätt på fyra W-blad mot facit, samma indata före och efter:

| blad | tvetydiga före → efter | utan rör före → efter | täckning före → efter |
|------|------------------------|------------------------|------------------------|
| W-50-1-A0111 | 81 → 51 | 67 → 53 | 62,2 % → 62,2 % |
| W-50-1-A0113 | 76 → 47 | 45 → 33 | 70,0 % → 70,0 % |
| W-50-1-A0132 | 104 → 42 | 21 → 14 | 79,0 % → 79,1 % |
| W-50-1-A0134 | 62 → 30 | 7 → 6 | 64,5 % → 64,9 % |

Metrarna rör sig knappt - noten ägde aldrig några meter - och falskt ägande stiger som mest 0,4
procentenheter. Det som blir bättre är att rören bredvid noten får sina namn i stället för ett frågetecken: en
fjärdedel av bladets fästen stod som "tvetydig" för den skull.

Provet prövar regeln själv: vilka rader i en ruta som ska ha var sin ritad sträcka. Det ritade fallet täcks av
grinden ovan, som kördes på riktiga blad med facit.
"""
from dataclasses import dataclass

from vvs_engine.pipeline import rows_needing_a_pipe


@dataclass
class Rad:
    """Så mycket av en beteckning som regeln rör vid."""
    did: str
    text: str


ROR = Rad("d1", "KV1-X7-16")
ROR2 = Rad("d2", "VV1-X7-16")
NOT = Rad("d9", "CL 3060 REL")
NOT2 = Rad("d8", "CL=2500")


def test_hojdraden_raknas_inte_med_nar_rutan_har_ett_rornamn():
    """Ett rörnamn och en höjd: bara rörnamnet ska paras mot det som är ritat."""
    assert rows_needing_a_pipe([ROR, NOT], {"d1"}) == [ROR]


def test_flera_hojdrader_faller_bort_pa_samma_satt():
    assert rows_needing_a_pipe([ROR, NOT, NOT2], {"d1"}) == [ROR]


def test_tva_rornamn_med_en_not_behaller_bada_rornamnen():
    """Bunten är fortfarande en bunt - regeln tar bort noten, inte raderna som ska ha rör."""
    assert rows_needing_a_pipe([ROR, ROR2, NOT], {"d1", "d2"}) == [ROR, ROR2]


def test_en_ruta_med_bara_noter_lamnas_orord():
    """Utan ett rörnamn att lämna åt rörs rutan inte, så att den redovisas som den olösta rad den är."""
    rader = [NOT, NOT2]
    assert rows_needing_a_pipe(rader, set()) == rader


def test_en_ruta_med_bara_rornamn_ar_oforandrad():
    """Regeln får inte ändra det som redan fungerade."""
    rader = [ROR, ROR2]
    assert rows_needing_a_pipe(rader, {"d1", "d2"}) == rader


def test_en_tom_ruta_ar_tom():
    assert rows_needing_a_pipe([], {"d1"}) == []


def test_ordningen_star_kvar():
    """Raderna paras mot sträckorna i den ordning de står i rutan; regeln får inte kasta om dem."""
    assert rows_needing_a_pipe([ROR, NOT, ROR2], {"d1", "d2"}) == [ROR, ROR2]
