"""Vilket segment en etikett beskriver där hänvisningslinjen landar vid en knut.

Ett rörstråk har en läsriktning. Etiketten sätts där stråket börjar och beskriver det som kommer **efter** den
i den riktningen, aldrig det som ligger bakom. Att ta närmaste segment är att svara på en annan fråga än den
ställda - och det var så ett stråk som bar sju DN110-etiketter och en DN75 bokfördes som DN75.

Signalerna i tur och ordning: vattengången på ett självfall, dimensionen på ett trycksystem, läget i rummet.
Höjden säger ingenting om riktningen.

Och det som provet är till för lika mycket: att läsningen säger när den inte vet. Under 0,7 i konfidens är
osäkert och ska granskas. Ett självsäkert fel kostar mer än en ärlig osäkerhet.
"""
import pytest

from vvs_engine.pipes.direction import (CONFIDENT_ENOUGH, Choice, Segment, VerticalMark, choose_segment,
                                        has_own_label, is_circulating, is_gravity)


def seg(sid, dn=None, vg=None, cl=None, entry=None, near=None):
    return Segment(segment_id=sid, dn=dn, vg=vg, cl=cl, distance_from_entry=entry, distance_to_endpoint=near)


# ---------------------------------------------------------------- 1. vattengången

def test_sjalvfall_lases_mot_hogre_vg_enligt_kallregeln():
    """Swedish VVS assign_label.py: läsningen går mot högre VG, motsatt vattnets flöde."""
    v = choose_segment([seg("upp", vg=2.30), seg("ned", vg=1.91)], system="S")
    assert v.segment_id == "upp" and v.signal == "VG" and v.certain and not v.review
    assert v.upstream == "upp" and v.downstream == "ned"
    assert "1.91" in v.reason or "1,91" in v.reason


def test_vattengangen_avgor_aven_nar_dimensionerna_sager_motsatsen():
    """Finns VG på båda sidor är den avgörande, oavsett dimensioner."""
    v = choose_segment([seg("upp", dn=110, vg=1.50), seg("ned", dn=160, vg=1.10)], system="S")
    assert v.segment_id == "upp" and v.signal == "VG"


def test_vattengangen_galler_inte_ett_trycksystem():
    """VG hör till självfall. På ett tryckrör är det dimensionen som gäller."""
    v = choose_segment([seg("stam", dn=110, vg=2.0), seg("gren", dn=75, vg=1.0)], system="KV")
    assert v.signal == "dimension" and v.segment_id == "gren"


def test_samma_vattengang_pa_bada_sidor_ar_osakert():
    v = choose_segment([seg("a", vg=1.5, near=2.0), seg("b", vg=1.5, near=9.0)], system="S")
    assert v.signal == "narmast" and not v.certain and v.review and "Varken" in v.reason


# ---------------------------------------------------------------- 2. dimensionen

def test_gren_som_ar_klenare_an_stammen_tar_etiketten():
    """Rör smalnar av utåt: den grövre sidan är uppströms."""
    v = choose_segment([seg("stam", dn=110), seg("gren", dn=75)], system="S1")
    assert v.segment_id == "gren" and v.signal == "dimension" and not v.review
    assert v.upstream == "stam" and v.downstream == "gren"


def test_etikettens_egen_dimension_pekar_ut_segmentet():
    """Står KV1-15 vid en knut där en gren fortsätter som 22 är 15-segmentet det som leder bort från 22."""
    v = choose_segment([seg("fortsatter", dn=22), seg("mot_tvattstall", dn=15)], system="KV", label_dn=15)
    assert v.segment_id == "mot_tvattstall" and v.signal == "dimension" and v.confidence >= 0.9


def test_stammen_far_aldrig_etiketten_fran_en_klenare_gren():
    """Den klenare kan inte vara uppströms den grövre - då vore grenen grövre än det den grenar av från."""
    v = choose_segment([seg("stam", dn=110), seg("gren", dn=75)], system="S1", label_dn=75)
    assert v.segment_id == "gren"
    assert v.upstream == "stam"


def test_lika_dimension_och_ingen_vattengang_ar_osakert():
    """Specialfallet: koppla till närmaste, låg konfidens, flagga för granskning."""
    v = choose_segment([seg("a", dn=110, near=3.0), seg("b", dn=110, near=8.0)], system="KV")
    assert v.segment_id == "a" and v.signal == "narmast"
    assert v.confidence < CONFIDENT_ENOUGH and v.review


def test_flera_klenare_grenar_avgors_inte_av_dimensionen():
    v = choose_segment([seg("stam", dn=110), seg("g1", dn=75, near=4.0), seg("g2", dn=75, near=1.0)], system="S")
    assert v.signal == "narmast" and v.review and v.segment_id == "g2"


# ---------------------------------------------------------------- 3. läget

def test_langst_fran_intradespunkten_tar_etiketten():
    """Ritningen läses utifrån och in."""
    v = choose_segment([seg("vid_schakt", entry=40.0), seg("ut_i_rummet", entry=900.0)], system="KV")
    assert v.segment_id == "ut_i_rummet" and v.signal == "position" and not v.review


def test_laget_anvands_forst_nar_dimensionen_inte_racker():
    v = choose_segment([seg("a", dn=110, entry=10.0), seg("b", dn=75, entry=900.0)], system="KV")
    assert v.signal == "dimension"        # dimensionen är starkare än läget


# ---------------------------------------------------------------- höjden

def test_hojden_avgor_vilket_strak_etiketten_hor_till():
    """CL säger inte riktning, men den säger vilket rör: två rör som korsar på olika nivåer."""
    v = choose_segment([seg("ovan", cl=3.400), seg("under", cl=2.300)], system="KV", label_cl=2.300)
    assert v.segment_id == "under" and v.signal == "hojd"


def test_hojden_anvands_aldrig_som_riktning():
    """Två segment på samma stråk, olika höjd, ingen dimension: höjden får inte avgöra riktningen."""
    v = choose_segment([seg("a", cl=2.300, near=2.0), seg("b", cl=2.300, near=7.0)], system="KV")
    assert v.signal != "hojd"
    assert v.signal == "narmast" and v.review


# ---------------------------------------------------------------- systemen

def test_sjalvfallssystemen_ar_de_som_har_fall():
    for s in ("S", "SA", "SP", "SF", "D"):
        assert is_gravity(s)
    for s in ("KV", "VV", "VVC", "VS", "FJV"):
        assert not is_gravity(s)


def test_cirkulerande_system_kanns_igen():
    for s in ("VP", "VS", "KB", "KM", "ÅV", "FV", "FK", "KP", "VÅV", "FJV", "FJK"):
        assert is_circulating(s)
    assert not is_circulating("KV")


def test_de_som_har_egen_etikett_per_ror_har_ingen_tvilling():
    for s in ("KV", "VV", "VVC", "S", "D"):
        assert has_own_label(s)
    assert not has_own_label("VS")


# ---------------------------------------------------------------- det vertikala strecket

def test_strecket_vid_dimensionssiffran_sager_vart_roret_tar_vagen():
    assert VerticalMark(above=True, below=False).direction == "BARA_NEDAT"
    assert VerticalMark(above=False, below=True).direction == "BARA_UPPAT"
    assert VerticalMark(above=True, below=True).direction == "STANNAR_I_VANINGEN"
    assert VerticalMark(above=False, below=False).direction == "RAKT_IGENOM"


def test_ett_streck_som_inte_gar_att_avgora_ar_okant_och_inte_inget_streck():
    """Att anta 'inget streck' vore att påstå att röret går rakt igenom, vilket ritningen inte sagt."""
    m = VerticalMark(above=None, below=None)
    assert m.direction == "OKAND" and not m.certain
    assert VerticalMark(above=True, below=None).direction == "OKAND"


# ---------------------------------------------------------------- svaret bär alltid sitt skäl

def test_varje_svar_bar_signal_konfidens_och_skal():
    for v in (choose_segment([seg("a", vg=2.0), seg("b", vg=1.0)], "S"),
              choose_segment([seg("a", dn=110), seg("b", dn=75)], "KV"),
              choose_segment([seg("a", entry=10.0), seg("b", entry=90.0)], "KV"),
              choose_segment([seg("a", near=1.0), seg("b", near=5.0)], "KV"),
              choose_segment([], "KV")):
        d = v.as_dict()
        assert d["signal"] and isinstance(d["confidence"], float)
        assert d["reason"].endswith(".") and len(d["reason"]) > 20
        assert d["review"] is (v.confidence < CONFIDENT_ENOUGH)


def test_en_knut_med_ett_enda_segment_ar_inget_val():
    v = choose_segment([seg("ensam", dn=75)], system="KV")
    assert v.segment_id == "ensam" and v.certain and not v.review


def test_utan_segment_ges_inget_svar_och_ingen_konfidens():
    v = choose_segment([], system="KV")
    assert v.segment_id is None and v.confidence == 0.0 and v.review


# ---------------------------------------------------------------- systemets bokstäver, och vattengången ur bladet

def test_systemets_lopnummer_hor_inte_till_vilket_slags_system_det_ar():
    """S1 och S3 är två stammar av samma slag. Läses hela token som system hör ingen av dem till självfallen.

    Det var precis så vattengången kunde stå skriven på sjuttio etiketter utan att någonsin få svara: bladet
    skriver S1, S3, SA2 - bokstäverna säger slaget, siffran säger vilken stam.
    """
    from vvs_engine.pipes.direction import system_letters
    assert system_letters("S1") == "S" and system_letters("SA2") == "SA" and system_letters("VS21") == "VS"
    assert is_gravity("S1") and is_gravity("S3") and is_gravity("SA2")
    assert is_circulating("VS21") and is_circulating("VP2")
    assert has_own_label("KV1") and has_own_label("VVC3")
    assert not is_gravity("VS21") and not is_gravity("")


def test_vattengangen_lases_ur_bladets_egna_hojdangivelser():
    """Bara VG är vattengång, och bara med en enhet bladet faktiskt skrivit."""
    from vvs_engine.pipes.direction import water_level
    assert water_level([{"tag": "VG", "value": 1.47, "unit": "m"}]) == pytest.approx(1.47)
    assert water_level([{"tag": "VG", "value": 1470.0, "unit": "mm"}]) == pytest.approx(1.47)
    assert water_level([{"tag": "CL", "value": 3.4, "unit": "m"}]) is None
    assert water_level([{"tag": "VG", "value": 150.0, "unit": None}]) is None    # varken meter eller millimeter
    assert water_level([]) is None and water_level(None) is None


def test_tva_olika_vattengangar_i_samma_block_ar_ingen_niva():
    """Skriver blocket två fall säger det inte ett, och att välja ett av dem vore att hitta på ritningen."""
    from vvs_engine.pipes.direction import water_level
    assert water_level([{"tag": "VG", "value": 1.47, "unit": "m"},
                        {"tag": "VG", "value": 1.31, "unit": "m"}]) is None


def test_fallet_sager_vad_som_ar_uppstroms_och_tiger_nar_bladet_tiger():
    """True när källan ligger högre, False när armen gör det, None när bladet inte skriver båda."""
    from vvs_engine.pipes.direction import flows_downhill
    assert flows_downhill(1.60, 1.20) is True
    assert flows_downhill(1.20, 1.60) is False
    assert flows_downhill(1.40, 1.40) is None       # samma nivå säger ingen riktning
    assert flows_downhill(1.40, None) is None and flows_downhill(None, 1.40) is None
