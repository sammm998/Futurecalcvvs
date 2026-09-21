"""Text som plottats med ett typsnitt utan teckentabell ska ändå gå att läsa.

En CAD-plott bäddar ofta in sina typsnitt med `Identity-H`: raden pekar ut glyfer med nummer, och vilket
tecken ett nummer betyder står i typsnittets ToUnicode-tabell. Skrivs den inte ut - vilket den ofta inte blir
- står det rätt på skärmen, för glyferna ritas ändå, men den som läser texten ur filen får ingenting: läsaren
svarar med ersättningstecken. På ett blad ur korpusen kom "Längd(m)" ut som åtta stycken U+FFFD, och med den
raden föll hela namnrutan och fördelartabellen bort. Tvärs hela korpusen gällde det vart tionde ord.

Det finns inget att gissa. Läsaren säger själv vilka tecken den inte kunde tyda, och vad glyfen ritar står i
det inbäddade typsnittet - tabellen byggs baklänges ur det, och då går även å, ä och ö tillbaka.

Provet kräver sex saker:

  * ett trasigt typsnitt läses rätt, med svenska tecken och parenteser,
  * ett helt typsnitt på samma sida rörs inte - inte ens när det heter precis samma sak som det trasiga, för
    det var så ett tidigare försök förvandlade "Krets" till "Ircrs",
  * ett blad utan trasiga typsnitt kommer ut ord för ord som förut,
  * namnet får stavas olika på vägen in: sidans typsnittslista och textraden gör inte lika,
  * två typsnitt som heter lika och ritar olika ger inget svar alls - tecknet står hellre otytt än fel,
  * rättningen sitter i utvinningen, så att motorn läser samma text som den som tittar i filen.
"""
import os
import tempfile

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pdf.glyphtext import _norm, page_fonts, repaired_page_text, repairs_for_page

ORD = "Längd(m) Inj.värde Flöde(l/h) 12,5"
HELT = "Krets"


def _blad(trasiga=("Fx",), hela=(), text=ORD):
    """Ett blad där de namngivna typsnitten fått sin ToUnicode struken, och de andra behållit sin."""
    buf = pymupdf.Font("helv").buffer
    d = pymupdf.open()
    p = d.new_page()
    y = 100.0
    for namn in (*trasiga, *hela):
        p.insert_font(fontname=namn, fontbuffer=buf)
        p.insert_text((72, y), text if namn in trasiga else HELT, fontname=namn, fontsize=11)
        y += 30.0
    d2 = pymupdf.open("pdf", d.tobytes())
    # ToUnicode stryks på de utpekade typsnitten - precis det plotten gör
    for f in d2.get_page_fonts(0, full=True):
        if f[4] in trasiga:                       # f[4] är namnet sidan kallar typsnittet vid
            d2.xref_set_key(f[0], "ToUnicode", "null")
    return pymupdf.open("pdf", d2.tobytes())


def test_texten_ur_ett_typsnitt_utan_teckentabell_kommer_tillbaka():
    d = _blad()
    assert ORD not in d[0].get_text("text"), "provet mäter ingenting om filen gick att läsa redan"
    assert repaired_page_text(d[0], d).strip() == ORD


def test_ett_helt_typsnitt_med_samma_namn_rors_inte():
    """Två typsnitt kan heta samma sak, ett trasigt och ett helt. Bara det otydda tecknet slås upp."""
    d = _blad(trasiga=("Fx",), hela=("Fy",))
    ut = repaired_page_text(d[0], d)
    assert ORD in ut
    assert HELT in ut, "det hela typsnittets text skrevs om av en tabell den inte hörde till"


def test_ett_blad_utan_trasiga_typsnitt_andrar_ingenting():
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 100), ORD, fontname="helv", fontsize=11)
    d = pymupdf.open("pdf", d.tobytes())
    assert repairs_for_page(d[0], d) == {}
    assert repaired_page_text(d[0], d).strip() == d[0].get_text("text").strip()


def test_namnet_far_stavas_olika_pa_vagen_in():
    """Typsnittslistan säger "Nimbus Sans Regular" där textraden säger "NimbusSans-Regular"."""
    assert _norm("ABCDEF+Nimbus Sans Regular") == _norm("NimbusSans-Regular") == "nimbussansregular"
    d = _blad()
    listnamn = {f[3] for f in d.get_page_fonts(0, full=True)}
    radnamn = {sp.get("font") for sp in d[0].get_texttrace()}
    assert listnamn != radnamn, "provet mäter ingenting om de två vägarna redan stavar lika"
    assert {_norm(n) for n in listnamn} == {_norm(n) for n in radnamn}


def test_tva_typsnitt_som_heter_lika_och_ritar_olika_ger_inget_svar():
    """Ett tecken står hellre otytt än fel. Bara det båda är överens om skrivs tillbaka.

    Bladet bär två typsnitt under samma namn. Det ena ritar glyf 78 som "m", det andra som "µ" - alltså går
    det inte att veta vilket som stod, och tecknet lämnas som läsaren gav det. Bokstaven L kan bara det ena,
    och den kommer tillbaka.
    """
    d = pymupdf.open()
    p = d.new_page()
    p.insert_font(fontname="Fa", fontbuffer=pymupdf.Font("helv").buffer)
    p.insert_font(fontname="Fb", fontbuffer=pymupdf.Font("symb").buffer)
    p.insert_text((72, 100), "Lm", fontname="Fa", fontsize=11)
    d2 = pymupdf.open("pdf", d.tobytes())
    for f in d2.get_page_fonts(0, full=True):
        d2.xref_set_key(f[0], "ToUnicode", "null")
        d2.xref_set_key(f[0], "BaseFont", "/Samma")           # samma namn, olika glyfordning
    d = pymupdf.open("pdf", d2.tobytes())
    assert len(page_fonts(d[0])["samma"]) == 2, "provet mäter ingenting om namnet pekar ut ett typsnitt"
    assert list(repairs_for_page(d[0], d).values()) == ["L"]


def test_ett_blad_utan_otydda_tecken_packar_aldrig_upp_ett_typsnitt():
    """Kostnaden ligger i att packa upp typsnittet, och den betalas bara när något faktiskt är otytt."""
    d = _blad(trasiga=(), hela=("Fy",))
    assert repairs_for_page(d[0], d) == {}


def test_lasningen_ger_motorn_de_rattade_tecknen():
    """Rättningen sitter i utvinningen, inte bara hos den som råkar läsa namnrutan."""
    d = _blad()
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        d.save(path)
        doc = extract_document(path)
        text = " ".join(s.text for s in doc.pages[0].spans)
        assert "Längd(m)" in text
        assert "Flöde(l/h)" in text
        # tecknen sitter kvar på sina platser, ett för ett
        span = next(s for s in doc.pages[0].spans if "Längd(m)" in s.text)
        assert "".join(c.c for c in span.chars) == span.text
    finally:
        os.unlink(path)
