"""Ett före och ett efter får aldrig hittas på.

Det här är den regel som avgör om en projektanalys är värd något. Ett filnamn är inte en revision: `Hus A
(1).pdf` och `Hus A (2).pdf` säger ingenting om vad som kom först, det är vad en webbläsare gör när man laddar
ned samma fil två gånger. Och två handlingar från samma dag med samma status är inte ett revisionspar - en
arkitektritning och en VVS-ritning, båda relationshandling samma datum, är två discipliner i samma skede.

Kallas de före och efter uppstår en diff som beskriver skillnaden mellan två yrkens ritningar som om den vore
en projektändring. Varje rad i den är fel, och den ser exakt ut som en riktig ändringslista.

Så: ett par påstås bara när handlingarna själva bär ordningen - en revisionsbeteckning, ett revisionsdatum,
ett handlingsdatum eller ett skede som skiljer dem åt. Annars står det att det inte gick att avgöra, med vad
de verkar vara i stället.
"""
import pymupdf
import pytest

from vvs_engine.handling import Handling, Field, as_report, pair_versions, read_handling


def _doc(path, lines, w=842, h=595):
    """Ett blad med text i namnrutan, nere till höger där svenska ritningar bär den."""
    d = pymupdf.open()
    pg = d.new_page(width=w, height=h)
    y = 0.62 * h
    for t in lines:
        pg.insert_text((0.60 * w, y), t, fontsize=9, fontname="helv")
        y += 13
    d.save(path)
    d.close()
    return path


def _h(number=None, disc=None, building=None, rev=None, rdate=None, ddate=None, status=None, order=None,
       filename="x.pdf"):
    o = Handling(path=filename, filename=filename)
    o.number = Field(number, "", "namnruta", 0.9 if number else 0.0)
    o.discipline = Field(disc, "", "ritningsnummer", 0.8 if disc else 0.0)
    o.building = Field(building, "", "namnruta", 0.9 if building else 0.0)
    o.revision = Field(rev, "", "namnruta", 0.8 if rev else 0.0)
    o.revision_date = Field(rdate, "", "namnruta", 0.8 if rdate else 0.0)
    o.document_date = Field(ddate, "", "namnruta", 0.8 if ddate else 0.0)
    o.status = Field(status, "", "namnruta", 0.9 if status else 0.0)
    o.stage_order = order
    return o


# ------------------------------------------------------------------------------------------------------------
# vad som ALDRIG blir ett par
# ------------------------------------------------------------------------------------------------------------

def test_two_disciplines_on_the_same_day_are_not_a_revision_pair():
    """Testfallet ur verkligheten: arkitekt och VVS, båda relationshandling 2025-05-14."""
    a = _h("V-50-1-A0112", "Arkitekt", "A", ddate="2025-05-14", status="RELATIONSHANDLING", order=9,
           filename="ark.pdf")
    v = _h("V-50-1-A0112", "VVS", "A", ddate="2025-05-14", status="RELATIONSHANDLING", order=9,
           filename="vvs.pdf")
    pairs, unclear = pair_versions([a, v])
    assert not pairs, "två discipliner är inte två versioner"
    assert unclear and unclear[0].reading == "parallella discipliner"
    assert "disciplin" in unclear[0].why


def test_a_file_number_in_the_name_is_not_a_revision():
    """`Hus A (1).pdf` och `Hus A (2).pdf` bär ingen ordning alls."""
    a = _h("V-50-1-A0112", "VVS", "A", ddate="2025-05-14", status="RELATIONSHANDLING", order=9,
           filename="Hus A (1).pdf")
    b = _h("V-50-1-A0112", "VVS", "A", ddate="2025-05-14", status="RELATIONSHANDLING", order=9,
           filename="Hus A (2).pdf")
    pairs, unclear = pair_versions([a, b])
    assert not pairs, "ett tal i filnamnet får aldrig bli ett före och ett efter"
    assert unclear and unclear[0].reading == "samma projektskede"


def test_a_sheet_that_stands_alone_is_no_pair_at_all():
    """Tjugonio olika ritningar är tjugonio ritningar, inte fjorton par."""
    docs = [_h(f"V-50-1-A01{i:02d}", "VVS", "A", status="BYGGHANDLING", order=6) for i in range(11, 25)]
    pairs, unclear = pair_versions(docs)
    assert not pairs and not unclear


# ------------------------------------------------------------------------------------------------------------
# ...och vad som blir det
# ------------------------------------------------------------------------------------------------------------

def test_a_revision_letter_orders_the_pair():
    a = _h("V-50-1-A0112", "VVS", "A", rev="A", ddate="2024-02-12", filename="a.pdf")
    b = _h("V-50-1-A0112", "VVS", "A", rev="B", ddate="2024-05-07", filename="b.pdf")
    pairs, _ = pair_versions([a, b])
    assert len(pairs) == 1
    p = pairs[0]
    assert p.before.revision.value == "A" and p.after.revision.value == "B"
    assert p.confidence >= 0.9
    assert any("revision A före B" in w for w in p.why)


def test_a_date_orders_a_pair_with_no_revision_letters():
    a = _h("V-50-1-A0112", "VVS", "A", ddate="2024-02-12", filename="a.pdf")
    b = _h("V-50-1-A0112", "VVS", "A", ddate="2025-05-14", filename="b.pdf")
    pairs, _ = pair_versions([a, b])
    assert len(pairs) == 1 and pairs[0].before.document_date.value == "2024-02-12"


def test_the_stage_orders_a_pair_when_nothing_else_does():
    """Bygghandling före relationshandling: projektets egen ordning, inte uppladdningens."""
    a = _h("V-50-1-A0112", "VVS", "A", status="RELATIONSHANDLING", order=9, filename="rel.pdf")
    b = _h("V-50-1-A0112", "VVS", "A", status="BYGGHANDLING", order=6, filename="bygg.pdf")
    pairs, _ = pair_versions([a, b])
    assert len(pairs) == 1
    assert pairs[0].before.status.value == "BYGGHANDLING"
    assert pairs[0].after.status.value == "RELATIONSHANDLING"


def test_every_pair_says_why_it_is_one():
    a = _h("V-50-1-A0112", "VVS", "A", rev="A", filename="a.pdf")
    b = _h("V-50-1-A0112", "VVS", "A", rev="B", filename="b.pdf")
    pairs, _ = pair_versions([a, b])
    assert pairs[0].why, "ett par utan skäl är ett påstående ingen kan pröva"


# ------------------------------------------------------------------------------------------------------------
# att läsa bladet, inte filnamnet
# ------------------------------------------------------------------------------------------------------------

def test_a_pipe_designation_is_not_a_drawing_number(tmp_path):
    """`S13-12` på ritningen är ett rör av stål i tolv millimeter, inte en styrritning."""
    p = _doc(str(tmp_path / "V-50-1-020.pdf"),
             ["V-50-1-020", "HUS B, PLAN 1, RÖRINSTALLATIONER", "BYGGHANDLING", "2024-05-07", "1:50",
              "S13-12", "KV01-X7-16"])
    h = read_handling(p)
    assert h.number.value == "V-50-1-020"
    assert h.discipline.value == "VVS"


def test_a_reference_to_another_drawing_is_not_this_one(tmp_path):
    """En VVS-ritning som hänvisar till en konstruktionsritning är fortfarande en VVS-ritning."""
    p = _doc(str(tmp_path / "V-50-1-020.pdf"),
             ["SE K-20-2-001 FOR BJALKLAG", "V-50-1-020", "HUS B, PLAN 1", "BYGGHANDLING", "2024-05-07"])
    h = read_handling(p)
    assert h.number.value == "V-50-1-020", f"bladets eget nummer, inte hänvisningens; fick {h.number.value}"
    assert h.discipline.value == "VVS"
    assert h.number.confidence >= 0.9, "numret står både på bladet och i filnamnet: det är starkt"


def test_the_drawing_name_says_which_building_it_is(tmp_path):
    """En översiktsritning bär gärna grannhusets bokstav i en hänvisning. Ritningsnamnet handlar om bladet."""
    p = _doc(str(tmp_path / "V-50-1-010.pdf"),
             ["ANSLUTNING MOT HUS C", "V-50-1-010", "HUS B, OVERSIKT, RORINSTALLATIONER", "BYGGHANDLING"])
    h = read_handling(p)
    assert h.building.value == "B", f"ritningsnamnet säger hus B; fick {h.building.value}"
    assert h.building.where == "ritningsnamn"


def test_what_cannot_be_read_says_so(tmp_path):
    """Ett blad utan namnruta får inga påhittade fält."""
    p = _doc(str(tmp_path / "tom.pdf"), ["nagon text utan betydelse"])
    h = read_handling(p)
    assert h.number.value is None and h.building.value is None and h.status.value is None
    assert h.number.confidence == 0.0


def test_the_report_counts_what_it_found(tmp_path):
    docs = [_h("V-50-1-A0111", "VVS", "A", status="BYGGHANDLING", order=6),
            _h("V-50-1-B0112", "VVS", "B", status="BYGGHANDLING", order=6)]
    r = as_report(docs)
    assert r["totals"]["documents"] == 2
    assert r["buildings"] == ["A", "B"]
    assert r["disciplines"] == ["VVS"]
    assert r["totals"]["pairs"] == 0
