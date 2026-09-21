"""En vanlig vågrät etikett är ingen stigare.

Ritningen säger själv vilken sorts rör en etikett namnger: står dimensionen på raden under är det ett lodrätt
rör vid den punkten - fallet ned till en golvbrunn, en stam - medan en dimension inne i raden namnger den
vågräta sträckan. `_is_vertical_label` är det provet.

Felet det här provet håller fast: filtret gjorde sitt jobb, och sedan blandades varje annan etikett tillbaka in
igen när de korta namnen skulle kompletteras ur de långa. Efter den kompletteringen innehöll kandidatlistan
alla etiketter bladet har, och nästa slinga - som bara skulle gå igenom kandidaterna - gick igenom allihop. En
vågrät etikett med sin dimension inne i raden räknades då som en stigare, och stigarantalet blev bladets
etikettantal.

Stigare är antal, aldrig meter, men antalet blir våningshöjder i mängden så snart någon sätter en höjd. Ett för
högt antal är därför för många meter, och det syns ingenstans i geometrin.
"""
from vvs_engine.pipeline import _risers_from_dn_rows
from vvs_engine.pipes.ownership import Identity


class _D:
    """En läst beteckningsrad, med bara det stigarprovet läser."""

    def __init__(self, did, text, dn, dn_source, multiplier=1):
        self.did, self.text, self.dn, self.dn_source, self.multiplier = did, text, dn, dn_source, multiplier


class _A:
    def __init__(self, anchor_id, designation_id, designation, dn, state="VERIFIED_PIPE_ATTACHMENT"):
        self.anchor_id, self.designation_id = anchor_id, designation_id
        self.designation = self.designation_display = designation
        self.dn, self.state = dn, state
        self.system_token = designation.split("-")[0]
        self.leader_id = f"ld-{anchor_id}"


class _L:
    def __init__(self, lid, end):
        self.lid, self.end = lid, end


def test_a_label_with_its_dimension_inline_is_never_counted_as_a_riser():
    # två etiketter av samma system: en stigare (dimensionen på raden under) och en vanlig vågrät (inline)
    stack = _D("d1", "S01-P5", 110, "row")
    flat = _D("d2", "KV01-X31-25", 25, "inline")
    designations = [stack, flat]
    anchors = [_A("a1", "d1", "S01-P5", 110), _A("a2", "d2", "KV01-X31-25", 25)]
    leaders = [_L("ld-a1", (100.0, 100.0)), _L("ld-a2", (400.0, 400.0))]
    identities = {
        "a1": Identity(base="S01-P5", dn=110, system="S", display="S01-P5-110"),
        "a2": Identity(base="KV01-X31", dn=25, system="KV", display="KV01-X31-25"),
    }

    risers = _risers_from_dn_rows(designations, anchors, leaders, identities)

    assert "KV01-X31|DN25" not in risers, "en vågrät etikett blev en stigare"
    assert sum(len(v) for v in risers.values()) == 1, risers
    assert [r["designation"] for r in risers["S01-P5|DN110"]] == ["S01-P5"]


def test_a_sheet_with_no_vertical_labels_has_no_labelled_risers():
    flat = _D("d1", "KV01-X31-25", 25, "inline")
    anchors = [_A("a1", "d1", "KV01-X31-25", 25)]
    leaders = [_L("ld-a1", (10.0, 10.0))]
    identities = {"a1": Identity(base="KV01-X31", dn=25, system="KV", display="KV01-X31-25")}

    assert _risers_from_dn_rows([flat], anchors, leaders, identities) == {}


def test_two_ways_of_writing_the_same_stack_land_on_one_row():
    """Kompletteringen ska finnas kvar: `S01-P5` vid stammen och `S01-P5-110` en bit bort är samma stam, och
    deras stigare hör till samma rad i mängden. Det är därför kompletteringen körs över hela bladet."""
    short = _D("d1", "S01-P5", 110, "row")
    full = _D("d2", "S01-P5-110", 110, "row")
    anchors = [_A("a1", "d1", "S01-P5", 110), _A("a2", "d2", "S01-P5-110", 110)]
    leaders = [_L("ld-a1", (100.0, 100.0)), _L("ld-a2", (400.0, 400.0))]
    identities = {
        # den korta etiketten lämnade dimensionen osagd i sin identitet; bladet säger den en enda gång
        "a1": Identity(base="S01-P5", dn=None, system="S", display="S01-P5"),
        "a2": Identity(base="S01-P5", dn=110, system="S", display="S01-P5-110"),
    }

    risers = _risers_from_dn_rows([short, full], anchors, leaders, identities)

    assert list(risers) == ["S01-P5|DN110"], risers
    assert len(risers["S01-P5|DN110"]) == 2, "de två skrivsätten är samma stam och hör till samma rad"
