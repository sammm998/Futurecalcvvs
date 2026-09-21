"""Ett bockmärke är litet. Ett streck som är längre än så är en linje, och linjer hör till geometrin.

Läsningen plockar bort bockmärken ur geometrin innan den letar hänvisningslinjer - pilstrecket vid en linjes
ände och krysset över den är märken, inte ritade ledningar. Frågan "är det här ett märke?" ställdes på tre
ställen i textläsningen och besvarades olika: två av dem krävde att klumpen var högst MARK_MAX_PT stor, det
tredje krävde ingenting alls om storleken.

Det tredje stället avgjorde ett riktigt blad. Etiketten S1-P2-75 bar sin hänvisningslinje som ett enda snedstreck
på 14 punkter från etikettramens hörn till röret. Det blev ett märke, försvann ur geometrin, och etiketten stod
utan linje. Röret den pekade på fick då inget eget namn, och grannstråkets grövre dimension tog det: fem meter
flyttade från S1-P2-75 till S1-P2-110 på ett blad där summan ändå stämde, vilket är värre än att summan blir fel.

Samma gräns på alla tre ställena, och storleken är en egenskap hos klumpen - inte hos vilken av de tre frågorna
som råkade ställas först.
"""
from types import SimpleNamespace

from vvs_engine.text.vector_text import MARK_MAX_PT, _is_mark


def _cluster(w: float, h: float, n_segs: int = 1, curves: int = 0, n_comps: int = 1, n_glyphs: int = 1):
    comp = SimpleNamespace(segs=[object()] * n_segs, paths=[SimpleNamespace(n_curves=curves)], w=w, h=h)
    glyph = SimpleNamespace(comps=[comp] * n_comps)
    return SimpleNamespace(glyphs=[glyph] * n_glyphs)


def test_a_tick_at_the_end_of_a_leader_is_a_mark():
    assert _is_mark(_cluster(w=4.1, h=4.0))


def test_a_stroke_longer_than_a_mark_is_not_a_mark():
    assert not _is_mark(_cluster(w=MARK_MAX_PT + 0.5, h=7.2))


def test_the_size_is_measured_on_the_longer_side():
    assert not _is_mark(_cluster(w=2.0, h=MARK_MAX_PT + 0.5))
    assert _is_mark(_cluster(w=MARK_MAX_PT, h=MARK_MAX_PT))


def test_a_shape_of_several_strokes_or_a_curve_is_never_a_mark():
    assert not _is_mark(_cluster(w=4.0, h=4.0, n_segs=3))
    assert not _is_mark(_cluster(w=4.0, h=4.0, curves=1))
    assert not _is_mark(_cluster(w=4.0, h=4.0, n_comps=2))
    assert not _is_mark(_cluster(w=4.0, h=4.0, n_glyphs=2))


def test_every_place_that_decides_what_a_mark_is_asks_the_same_rule():
    import inspect

    from vvs_engine.text import vector_text

    src = inspect.getsource(vector_text)
    assert src.count("max(c.w, c.h) <= MARK_MAX_PT") == 3
    assert "max(c.w, c.h) <= 12.0" not in src
