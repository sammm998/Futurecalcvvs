"""Vilket segment en etikett beskriver där hänvisningslinjen landar vid en knut.

Ett rörstråk har en läsriktning. Etiketten sätts där stråket börjar och beskriver det som kommer **efter**
den i den riktningen, aldrig det som ligger bakom. Bestäms riktningen försvinner tvetydigheten - och det är
riktningen, inte avståndet, som avgör. Att ta närmaste segment är att svara på en annan fråga än den ställda.

Signalerna, i den ordning ritningen ger dem:

1. **Vattengången** - självfall läses mot högre VG, in mot installationen. Detta följer
   swedish-vvs-drawings/scripts/assign_label.py. Vattnets flöde går åt motsatt håll; läsriktning
   och fysisk flödesriktning får inte blandas ihop. VG avgör före dimension.
2. **Dimensionen** - normalfallet för trycksystem. Rör smalnar av utåt mot tappställen, så den grövre sidan är
   uppströms och den klenare nedströms. Etiketten hör till det segment som är lika med eller mindre än grannen
   uppströms.
3. **Läget i rummet** - reserven. Ritningen läses utifrån och in: det segment som ligger längst från
   inträdespunkten (schakt, stam, rummets ytterkant) är nedströms och tar etiketten.

Höjden säger ingenting om riktningen. CL 3400 ÖFG är centrumhöjd för ett tryckrör - hur högt det hänger, inte
åt vilket håll det går. Bara VG på ett självfallsstråk anger fall. Höjden får däremot avgöra **vilket** stråk
en etikett hör till där rör korsar varandra på olika nivåer: en etikett som säger CL 3400 hör inte till ett rör
vars övriga etiketter säger CL 2300.

Svaret bär alltid sitt skäl och sin konfidens. Under 0,7 är osäkert och ska granskas. Ett självsäkert fel
kostar mer än en ärlig osäkerhet, så "närmast" är ett svar som räknas som osäkert och sägs högt - aldrig ett
tyst standardval.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any
from ..source_rules.systems import is_gravity as source_is_gravity, line_count, permits_unlabelled_twin

# Självfallssystem: de enda där vattengången säger något om riktningen.
GRAVITY_SYSTEMS = frozenset({"S", "SA", "SP", "SF", "D"})

# Cirkulerande system, ritade som ett par fram/retur. Riktningen gäller paret som enhet: lös etiketten mot den
# märkta linjen och kopiera till den omärkta tvillingen. Att skilja fram från retur är inte vår uppgift.
CIRCULATING_SYSTEMS = frozenset({"VP", "VS", "KB", "KM", "ÅV", "FV", "FK", "KP", "VÅV", "FJV", "FJK"})

# System där varje rör har sin egen etikett. Leta ingen tvilling åt dem.
OWN_LABEL_SYSTEMS = frozenset({"KV", "VV", "VVC", "S", "D"})

# Taggar som är vattengång, och taggar som är centrumhöjd. Bara den första säger något om fall.
VG_TAGS = frozenset({"VG"})
CL_TAGS = frozenset({"CL", "C", "CC"})

SURE = 0.95          # signalen är entydig
LIKELY = 0.8         # signalen finns men med en reservation
REVIEW = 0.5         # inget avgjorde: närmaste segment, och det sägs
CONFIDENT_ENOUGH = 0.7


@dataclass(frozen=True)
class Segment:
    """En arm ut från knuten, så mycket av den som riktningsfrågan rör vid."""
    segment_id: str
    dn: int | None = None
    vg: float | None = None            # vattengång på armen, om ritningen skriver den
    cl: float | None = None            # centrumhöjd, som aldrig avgör riktning
    distance_from_entry: float | None = None   # hur långt armen ligger från inträdespunkten
    distance_to_endpoint: float | None = None  # hur nära hänvisningslinjens ände armen ligger


@dataclass(frozen=True)
class Choice:
    """Vilket segment etiketten beskriver, och på vilken grund."""
    segment_id: str | None
    signal: str                  # VG | dimension | position | narmast | ingen
    confidence: float
    reason: str
    upstream: str | None = None
    downstream: str | None = None
    review: bool = True
    considered: tuple[str, ...] = ()

    @property
    def certain(self) -> bool:
        return self.confidence >= CONFIDENT_ENOUGH

    def as_dict(self) -> dict[str, Any]:
        return {"segment_id": self.segment_id, "signal": self.signal,
                "confidence": round(self.confidence, 2), "reason": self.reason,
                "upstream": self.upstream, "downstream": self.downstream,
                "review": self.review, "considered": list(self.considered)}


_ORDINAL = re.compile(r"\d+$")


def system_letters(system: str) -> str:
    """Systemets bokstäver utan dess löpnummer: S1 och S3 är båda S, SA2 är SA, VS21 är VS.

    En svensk beteckning skriver systemet som bokstäver följt av ett nummer som skiljer stammarna åt. Numret
    säger *vilken* stam, bokstäverna vilket *slags* system - och det är bokstäverna som avgör om stråket har
    fall. Läses hela token som system hör S1 inte till självfallen, och vattengången får aldrig svara.
    """
    return _ORDINAL.sub("", (system or "").strip().upper())


def is_gravity(system: str) -> bool:
    return source_is_gravity(system)


def is_circulating(system: str) -> bool:
    return permits_unlabelled_twin(system)


def has_own_label(system: str) -> bool:
    return line_count(system) == 1


def _svar(v: float | None) -> str:
    return "?" if v is None else f"{v:g}"


def _nearest(segments: list[Segment], why: str) -> Choice:
    """Sista utvägen: närmaste segment, med låg konfidens och skälet utskrivet.

    Det här är ett svar, inte ett standardval. Den som läser mängden ska se att ritningen inte avgjorde och
    att raden behöver granskas - inte tro att läsningen visste.
    """
    med = [s for s in segments if s.distance_to_endpoint is not None]
    if not med:
        return Choice(None, "ingen", 0.0, why + " och inget segment gick att mäta avstånd till.",
                      review=True, considered=tuple(s.segment_id for s in segments))
    val = min(med, key=lambda s: (s.distance_to_endpoint, s.segment_id))
    return Choice(val.segment_id, "narmast", REVIEW,
                  why + f" Närmaste segment ({val.distance_to_endpoint:.1f} pt) valdes; raden behöver granskas.",
                  review=True, considered=tuple(s.segment_id for s in segments))


def choose_segment(segments: list[Segment], system: str, label_dn: int | None = None,
                   label_cl: float | None = None) -> Choice:
    """Vilket av knutens segment etiketten beskriver.

    `segments` är armarna ut från knuten. Svaret bär signalen som avgjorde, konfidensen och skälet.
    """
    if not segments:
        return Choice(None, "ingen", 0.0, "Knuten har inga armar att välja mellan.", review=True)
    if len(segments) == 1:
        s = segments[0]
        return Choice(s.segment_id, "ensam", SURE, "Bara ett segment möter hänvisningslinjen.",
                      downstream=s.segment_id, review=False, considered=(s.segment_id,))

    kvar = list(segments)

    # Höjden säger inget om riktningen, men den säger vilket stråk etiketten hör till. Korsar rör varandra på
    # olika nivåer faller de som ligger på en annan höjd än etiketten bort innan riktningen alls avgörs.
    if label_cl is not None:
        samma = [s for s in kvar if s.cl is None or abs(s.cl - label_cl) <= 0.05 * max(1.0, abs(label_cl))]
        if samma and len(samma) < len(kvar):
            kvar = samma
            if len(kvar) == 1:
                return Choice(kvar[0].segment_id, "hojd", LIKELY,
                              f"Etikettens centrumhöjd {_svar(label_cl)} hör ihop med det här stråket; "
                              "de övriga ligger på en annan nivå.",
                              downstream=kvar[0].segment_id, review=False,
                              considered=tuple(s.segment_id for s in segments))

    # 1. vattengången, bara på självfall
    if is_gravity(system):
        med_vg = [s for s in kvar if s.vg is not None]
        if len(med_vg) >= 2:
            ned = min(med_vg, key=lambda s: (s.vg, s.segment_id))
            upp = max(med_vg, key=lambda s: (s.vg, s.segment_id))
            if ned.vg < upp.vg:
                return Choice(upp.segment_id, "VG", SURE,
                              f"Ritningen läses mot högre VG: {_svar(upp.vg)} i stället för {_svar(ned.vg)}. "
                              "Etiketten beskriver sträckan inåt, mot vattnets flödesriktning.",
                              upstream=upp.segment_id, downstream=ned.segment_id, review=False,
                              considered=tuple(s.segment_id for s in kvar))
            # Equal VG supplies no direction: continue to dimension and entry, as the source does.

    # 2. dimensionen, normalfallet för trycksystem
    med_dn = [s for s in kvar if s.dn is not None]
    if len(med_dn) >= 2:
        grovst = max(s.dn for s in med_dn)
        klenast = min(s.dn for s in med_dn)
        if grovst > klenast:
            upp = [s for s in med_dn if s.dn == grovst]
            ned = [s for s in med_dn if s.dn < grovst]
            # etiketten hör till det segment som är lika med eller mindre än grannen uppströms; säger etiketten
            # själv sin dimension väljs det segment som stämmer med den
            if label_dn is not None:
                passar = [s for s in ned if s.dn == label_dn] or [s for s in med_dn if s.dn == label_dn]
                if len(passar) == 1:
                    return Choice(passar[0].segment_id, "dimension", SURE,
                                  f"Etiketten säger DN{label_dn} och det segmentet är klenare än grannen "
                                  f"uppströms (DN{grovst}): rör smalnar av utåt.",
                                  upstream=upp[0].segment_id, downstream=passar[0].segment_id, review=False,
                                  considered=tuple(s.segment_id for s in kvar))
            if len(ned) == 1:
                return Choice(ned[0].segment_id, "dimension", LIKELY,
                              f"DN{ned[0].dn} är klenare än grannen uppströms (DN{grovst}): "
                              "etiketten hör till det nedströms segmentet.",
                              upstream=upp[0].segment_id, downstream=ned[0].segment_id, review=False,
                              considered=tuple(s.segment_id for s in kvar))
            if len(ned) > 1:
                return _nearest(kvar, f"Flera segment är klenare än DN{grovst} och dimensionen skiljer dem inte åt")
        # Equal DN does not stop the entry-distance rule.

    # 3. läget i rummet
    med_lage = [s for s in kvar if s.distance_from_entry is not None]
    if len(med_lage) >= 2:
        langst = max(med_lage, key=lambda s: (s.distance_from_entry, s.segment_id))
        narmast_in = min(med_lage, key=lambda s: (s.distance_from_entry, s.segment_id))
        if langst.distance_from_entry > narmast_in.distance_from_entry:
            return Choice(langst.segment_id, "position", LIKELY,
                          "Ritningen läses utifrån och in: segmentet längst från inträdespunkten "
                          f"({langst.distance_from_entry:.0f} pt mot {narmast_in.distance_from_entry:.0f}) "
                          "är nedströms och tar etiketten.",
                          upstream=narmast_in.segment_id, downstream=langst.segment_id, review=False,
                          considered=tuple(s.segment_id for s in kvar))

    return _nearest(kvar, "Varken vattengång, dimension eller läge skilde segmenten åt")


def water_level(elevations: list[dict] | None) -> float | None:
    """Vattengången ur ett etikettblocks höjdangivelser, i meter, eller None om bladet inte skriver den.

    Bara VG är vattengång. CL är centrumhöjd och säger ingenting om fall, så den läses inte här. Skriver
    bladet flera vattengångar i samma block säger det inte en nivå, och svaret blir None.
    """
    vals: set[float] = set()
    for e in elevations or []:
        if (e.get("tag") or "").strip().upper() not in VG_TAGS:
            continue
        v, unit = e.get("value"), e.get("unit")
        if v is None:
            continue
        if unit == "m":
            vals.add(float(v))
        elif unit == "mm":
            vals.add(float(v) / 1000.0)
        # En siffra utan enhet är ingen nivå. Att gissa meter eller millimeter där gör en halvmeter av femtio.
    return next(iter(vals)) if len(vals) == 1 else None


def flows_downhill(source: float | None, arm: float | None) -> bool | None:
    """Ligger källan uppströms armen? True när den gör det, False när armen ligger högre, None när bladet
    inte skriver vattengång på båda sidor eller skriver samma nivå.

    Detta är signal 1: på ett självfallsstråk avgör fallet riktningen, oavsett dimensioner. None betyder att
    vattengången inte sagt något - inte att den sagt nej - och nästa signal får svara.
    """
    if source is None or arm is None or source == arm:
        return None
    return source > arm


@dataclass
class VerticalMark:
    """Det grova strecket vid dimensionssiffran: vart det vertikala röret tar vägen.

    Streck ovanför siffran betyder att röret bara går nedåt, streck under att det bara går uppåt, båda att det
    stannar inom våningen och inget streck att det går rakt igenom. Går strecket inte att avgöra är svaret
    okänt - aldrig "inget streck", för det är ett påstående ritningen inte gjort.
    """
    above: bool | None = None
    below: bool | None = None

    @property
    def direction(self) -> str:
        if self.above is None or self.below is None:
            return "OKAND"
        if self.above and self.below:
            return "STANNAR_I_VANINGEN"
        if self.above:
            return "BARA_NEDAT"
        if self.below:
            return "BARA_UPPAT"
        return "RAKT_IGENOM"

    @property
    def certain(self) -> bool:
        return self.direction != "OKAND"

    def as_dict(self) -> dict[str, Any]:
        return {"above": self.above, "below": self.below, "direction": self.direction, "certain": self.certain}
