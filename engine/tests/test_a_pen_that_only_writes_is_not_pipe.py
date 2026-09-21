"""En penna vars varenda streck börjar eller slutar vid en beteckningsruta skriver, den ritar inte.

Ett lagernamn som liknar rörlagrens räckte för att släppa in en penna som rörgeometri. På ett blad blev
tvåhundrafemtio meter hänvisningslinje därmed "ritad som rör, men ingen beteckning nådde hit" - och den som
granskar letar efter ett tappat rör som aldrig fanns. Pennan bar noll bekräftade meter; det var inte mängden
som blev fel utan bilden av vad ritningen innehåller.

Skillnaden står i bladet självt. På de tätaste bladen ligger mellan 46 och 82 procent av rörpennornas streck
an mot en etikettruta - en ledning passerar ofta nära en etikett - men aldrig alla. Där varenda streck gör
det drar pennan bladets hänvisningslinjer. Villkoret har därför ingen tröskel att ställa in: antingen finns
ett streck som är fritt från bladets etiketter eller så finns det inte.
"""
from types import SimpleNamespace

from vvs_engine.pipeline import _writing_pens

FAM_PIPE = "L|s|w1.44|c(0.0, 0.0, 0.0)"
FAM_PEN = "L|s|w0.72|c(0.0, 0.0, 0.0)"


def _seg(x0, y0, x1, y1):
    return SimpleNamespace(x0=x0, y0=y0, x1=x1, y1=y1)


def _path(pid, width, segs):
    return SimpleNamespace(pid=pid, kind="s", layer="L", width=width, color=(0.0, 0.0, 0.0),
                           segs=[_seg(*s) for s in segs])


def _block(x0, y0, x1, y1):
    return SimpleNamespace(rows=[SimpleNamespace(line=SimpleNamespace(bbox=(x0, y0, x1, y1)))])


BLOCKS = [_block(100.0, 100.0, 160.0, 112.0)]


def _page(paths):
    return SimpleNamespace(paths=paths)


def _writing(paths, families=(FAM_PIPE, FAM_PEN)):
    return _writing_pens(_page(paths), set(families), BLOCKS)


def test_en_penna_dar_varenda_streck_gar_fran_en_etikett_ritar_inte():
    """Tio hänvisningslinjer, alla från rutan ut i ritningen."""
    paths = [_path(f"w{i}", 0.72, [(130.0, 112.0, 300.0 + i, 400.0)]) for i in range(10)]
    assert _writing(paths) == {FAM_PEN}


def test_ett_enda_fritt_streck_racker_for_att_pennan_ska_rita():
    """Ritningen har sagt att pennan gör något annat än att peka, och då döms den inte."""
    paths = [_path(f"w{i}", 0.72, [(130.0, 112.0, 300.0 + i, 400.0)]) for i in range(10)]
    paths.append(_path("fri", 0.72, [(600.0, 600.0, 700.0, 600.0)]))
    assert _writing(paths) == set()


def test_en_rorpenna_som_ofta_passerar_en_etikett_doms_inte():
    """Hälften av strecken ligger an mot en ruta - det är vad ett tätt blad ser ut som."""
    paths = [_path(f"p{i}", 1.44, [(130.0, 112.0, 300.0, 400.0)]) for i in range(5)]
    paths += [_path(f"f{i}", 1.44, [(500.0, 500.0, 600.0, 500.0)]) for i in range(5)]
    assert _writing(paths) == set()


def test_en_penna_med_for_fa_streck_doms_inte_av_en_slump():
    """Två streck som råkar börja vid en ruta säger ingenting om vad pennan är till för."""
    paths = [_path(f"w{i}", 0.72, [(130.0, 112.0, 300.0 + i, 400.0)]) for i in range(2)]
    assert _writing(paths) == set()


def test_utan_beteckningsrutor_doms_ingen_penna():
    """Finns inga etiketter på bladet finns inget att mäta mot, och då är svaret inget."""
    paths = [_path(f"w{i}", 0.72, [(130.0, 112.0, 300.0 + i, 400.0)]) for i in range(10)]
    assert _writing_pens(_page(paths), {FAM_PEN}, []) == set()
