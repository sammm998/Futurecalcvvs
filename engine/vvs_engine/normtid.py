"""Normtid VVS: grundtider, tillägg och avvikelseanalys.

En mängd är meter och antal. Ett anbud är tid och pengar. Det här är bron: normtidslistans grundtider per meter
rör och per apparat, tilläggen som beror på hur och var arbetet utförs, och avvikelseanalysen som väger in vad
just det här objektet har för förutsättningar.

Räknesättet är listans eget:

    timmar = grundtid × mängd × (1 + Σ tillägg) × (1 + avvikelse)

Grundtiden kommer ur en tabell, tilläggen ur hur röret fogas och hur högt det sitter, och avvikelsen ur en
bedömning av objektet som en människa gör och som därför alltid ska stå utskriven bredvid summan.

VARIFRÅN TALEN KOMMER. Tabellerna är avlästa ur Normtid VVS (Införlag), med sidnummer och utgåvodatum på varje
tabell. De är avlästa ur bilder av boken, inte ur en maskinläsbar källa, så de ska kontrolleras mot boken innan
ett anbud lämnas - och de går att rätta i gränssnittet utan att koden byggs om. Ett tal som inte gick att läsa
säkert står inte här alls: en gissad normtid är värre än ingen, för den ser ut som ett besked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Table:
    """En tabell ur boken, med var den står."""
    id: str
    title: str
    unit: str                      # tim/m | tim/st | tim/kvm
    source: str                    # kapitel och sida
    revised: str                   # utgåvodatum tabellen bär
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "unit": self.unit, "source": self.source,
                "revised": self.revised, "columns": list(self.columns),
                "rows": [list(r) for r in self.rows], "note": self.note}


# ---------------------------------------------------------------------------------------------------------
# 7 Stammar - grundtid per meter, efter dimension och material
# ---------------------------------------------------------------------------------------------------------
STAMMAR = Table(
    id="stammar", title="Stammar", unit="tim/m", source="7 Stammar, s. 30", revised="2022-01-15",
    columns=("dy mm", "metall och hårda kopparrör", "plaströr", "inskärning tim/st"),
    rows=((22, 0.20, 0.20, 0.70), (35, 0.24, 0.24, 0.95), (48.3, 0.27, 0.27, 1.15), (60.3, 0.29, 0.29, 1.30),
          (76.1, 0.32, 0.42, 1.50), (88.9, 0.35, 0.45, 1.65), (114.3, 0.42, 0.55, 1.95),
          (139.7, 0.48, 0.62, 2.20), (168.3, 0.54, 0.70, 2.50), (219.1, 0.65, 0.84, 2.75)),
    note="Omfattar stammar med stamförskjutningar på högst en meter. Tiderna gäller för normal klamring, "
         "sammanfogning och bockning, rörhylsor samt provtryckning en gång.")

# ---------------------------------------------------------------------------------------------------------
# 9 Sanitära installationer
# ---------------------------------------------------------------------------------------------------------
KOPPLINGSLEDNING = Table(
    id="kopplingsledning", title="Fördelnings- och kopplingsledningar", unit="tim/m",
    source="9 Sanitära installationer, s. 33", revised="2017-09-15",
    columns=("dy mm", "förkromade samt hårda kopparrör"),
    rows=((22.0, 0.30), (35.0, 0.35)),
    note="Tiden per enhet gäller komplett montering och inkoppling till rörsystem. Inkl. bockning av rör, "
         "normal klamring, ventiler, rörhylsor, sammanfogning samt provtryckning en gång.")

SANITET = Table(
    id="sanitet", title="Sanitära enheter", unit="tim/st",
    source="9 Sanitära installationer, s. 33", revised="2017-09-15",
    columns=("timmar", "enhet"),
    rows=((1.9, "Badkar inkl. väggblandare och duschstång"),
          (1.5, "Utslagsback och tvättbänk inkl. blandare"),
          (1.4, "Tvättställspaket"),
          (1.3, "Inbyggnadscistern komplett med fixtur, tryckknapp och skål"),
          (1.0, "Duschblandare med duschstång; bidé inkl. blandare och dusch"),
          (0.9, "Ink. blandare/vattenlås till diskbänk; brandkran inkl. slang och skåp"),
          (0.8, "Vattenklosett; handdukstork; nödduschar"),
          (0.6, "Väggvattenutkastare"),
          (0.5, "Blandare för tratt och spolplats"),
          (0.3, "Montering av blandare och bottenventil på tvättställ"),
          (0.2, "Tappkran; slanghylla; fixturer"),
          (0.1, "Silikontätning per apparat och armatur samt per våtrumsenhet")))

VATRUMSKASSETT = Table(
    id="vatrumskassett", title="Våtrumskassett", unit="tim/st",
    source="9 Sanitära installationer, s. 34", revised="2022-01-15",
    columns=("moment", "tim/st"),
    rows=(("Montering kassett", 3.80), ("Montering plåtar", 0.50)),
    note="Kassetten är levererad komplett med installerade VA-rör och avlopp som ska anpassas.")

# ---------------------------------------------------------------------------------------------------------
# 10 Värmare
# ---------------------------------------------------------------------------------------------------------
RADIATORER = Table(
    id="radiatorer", title="Radiatorer och konvektorer", unit="tim/st",
    source="10 Värmare, s. 35", revised="2013-12-01",
    columns=("vikt i kg, upp till", "tim/st"),
    rows=((60, 0.80), (95, 1.80)),
    note="Komplett montering av radiatorer och konvektorer inklusive montering av radiatorkoppel samt "
         "inkoppling till rörsystem.")

VARMARE_MOMENT = Table(
    id="varmare_moment", title="Värmare, enstaka moment", unit="tim/st",
    source="10 Värmare, s. 35", revised="2013-12-01",
    columns=("moment", "tid", "enhet"),
    rows=(("Inkoppling fönsterapparater, färdigplacerade värmare, kyl- och värmebafflar, utöver 2 st rör per radiator", 0.15, "tim/rör"),
          ("Från- och tillkoppling vid målning", 0.25, "tim/radiator"),
          ("Byte av radiatorventil, inkl. kopplingsdel", 0.30, "tim/st"),
          ("Byte av radiatorventil, exkl. kopplingsdel", 0.20, "tim/st"),
          ("Montering av tilluftsdon bakom radiator", 0.40, "tim/st"),
          ("Intagskanal", 0.20, "tim/st")))

GOLVVARME = Table(
    id="golvvarme", title="Golvvärme, pex-rör med diffusionsspärr", unit="tim/kvm",
    source="10 Värmare, s. 36", revised="2017-09-15",
    columns=("förläggning", "dy mm", "tim/kvm", "tim/m"),
    rows=(("Ingjutna", 20.0, 0.080, 0.025), ("Med plåtar i träbjälklag", 20.0, 0.100, 0.030)),
    note="Tiderna gäller vid förläggning av rören med c/c 300 mm och för en per objekt genomsnittlig "
         "böjfrekvens av 1,2-1,9 böj/kvm.")

FORDELARE = Table(
    id="fordelare", title="Skåp och fördelare", unit="tim/st",
    source="10 Värmare, s. 36", revised="2017-09-15",
    columns=("moment", "tid", "enhet"),
    rows=(("Montering fördelarskåp med förmonterade fördelare", 0.50, "tim/st"),
          ("Montering fördelarskåp", 0.50, "tim/st"),
          ("Montering per fördelare", 0.25, "tim/st"),
          ("Inkoppling per fördelare", 0.15, "tim/ink")))

# ---------------------------------------------------------------------------------------------------------
# 8 Pann- och apparatrum samt fläktrum
# ---------------------------------------------------------------------------------------------------------
APPARATER = Table(
    id="apparater", title="Apparater", unit="tim/st",
    source="8 Pann- och apparatrum samt fläktrum, s. 32", revised="2022-01-15",
    columns=("vikt i kg, upp till", "tim/st"),
    rows=((35, 0.50), (95, 1.00), (125, 1.50), (250, 2.50), (500, 4.00), (700, 5.00)),
    note="Med apparater avses ej exempelvis ventiler och smutsfilter.")

ANSLUTNING = Table(
    id="anslutning", title="Anslutning och inkoppling", unit="tim/st",
    source="8 Pann- och apparatrum samt fläktrum, s. 32", revised="2022-01-15",
    columns=("dy mm, upp till", "tim/st"),
    rows=((22, 0.30), (60.3, 0.45), (139.7, 1.00), (219.1, 1.50)))

# ---------------------------------------------------------------------------------------------------------
# 13 Rivning
# ---------------------------------------------------------------------------------------------------------
RIVNING_ROR = Table(
    id="rivning_ror", title="Rivning: smidda rör, tubrör, koppar och tunnväggiga stålrör", unit="tim/m",
    source="13 Rivning, s. 39", revised="2013-12-01",
    columns=("dy mm, upp till", "tim/m"),
    rows=((35.0, 0.08), (48.3, 0.13), (76.1, 0.16), (114.3, 0.22)),
    note="I tiderna ingår uttransport. Tiderna gäller inte för anläggningar med asbest.")

RIVNING_AVLOPP = Table(
    id="rivning_avlopp", title="Rivning: avloppsrör", unit="tim/m",
    source="13 Rivning, s. 39", revised="2013-12-01",
    columns=("dy mm, upp till", "plast tim/m", "gjutjärn tim/m"),
    rows=((170, 0.08, 0.15), (274, 0.16, 0.30)))

RIVNING_APPARATER = Table(
    id="rivning_apparater", title="Rivning: apparater", unit="tim/st",
    source="13 Rivning, s. 39", revised="2013-12-01",
    columns=("vikt i kg, upp till", "tim/apparat"),
    rows=((15, 0.25), (35, 0.35), (60, 0.45), (95, 0.60), (125, 0.80), (250, 2.00), (300, 2.50)),
    note="Separat armatur 0,25 tim/st.")

TABLES: tuple[Table, ...] = (
    STAMMAR, KOPPLINGSLEDNING, SANITET, VATRUMSKASSETT, RADIATORER, VARMARE_MOMENT, GOLVVARME,
    FORDELARE, APPARATER, ANSLUTNING, RIVNING_ROR, RIVNING_AVLOPP, RIVNING_APPARATER,
)
BY_ID = {t.id: t for t in TABLES}


# ---------------------------------------------------------------------------------------------------------
# Tillägg: hur röret fogas, och hur högt det sitter
# ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Supplement:
    id: str
    group: str
    label: str
    pct: float
    source: str
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "group": self.group, "label": self.label, "pct": self.pct,
                "source": self.source, "note": self.note}


S_JOINT = "Skarvmetod"
S_HEIGHT = "Höjd över färdigt golv"
S_REBUILD = "Ombyggnadsprojekt"

SUPPLEMENTS: tuple[Supplement, ...] = (
    Supplement("svets", S_JOINT, "Svetsning, gängfog, rillfog", 0.45, "7 Stammar, s. 30"),
    Supplement("lodning", S_JOINT, "Lödning, fusionssvets", 0.30, "7 Stammar, s. 30"),
    Supplement("pressfog", S_JOINT, "Pressfog, kopplingsfog", 0.15, "7 Stammar, s. 30"),
    Supplement("pushfog", S_JOINT, "Pushfog", 0.10, "7 Stammar, s. 30"),
    Supplement("rostfri_svets", S_JOINT, "Rostfri svets med skyddsgas", 0.95, "7 Stammar, s. 30"),
    Supplement("lodning_skyddsgas", S_JOINT, "Lödning med skyddsgas", 0.50, "7 Stammar, s. 30"),

    Supplement("under_1_8", S_HEIGHT, "Under 1,8 m", 0.25, "7 Stammar, s. 30",
               "Under 1,8 m avser höjd mellan golv och tak."),
    Supplement("over_3", S_HEIGHT, "Över 3 m", 0.20, "7 Stammar, s. 30"),
    Supplement("over_4_5", S_HEIGHT, "Över 4,5 m", 0.35, "7 Stammar, s. 30"),
    Supplement("over_7", S_HEIGHT, "Över 7 m", 0.50, "7 Stammar, s. 30"),

    Supplement("omb_stammar", S_REBUILD, "Stammar", 0.26, "7 Stammar, s. 44"),
    Supplement("omb_avsattningar", S_REBUILD, "Avsättningar", 0.25, "Avloppsledningar, s. 42"),
    Supplement("omb_stammar_avlopp", S_REBUILD, "Avloppsstammar", 0.20, "Avloppsledningar, s. 42"),
    Supplement("omb_ovriga", S_REBUILD, "Övriga tim/m rör", 0.07, "Avloppsledningar, s. 42"),
    Supplement("omb_tak", S_REBUILD, "Takförlagda ledningar", 0.22, "Takförlagda ledningar, s. 43"),
)
SUPPLEMENT_BY_ID = {s.id: s for s in SUPPLEMENTS}


# ---------------------------------------------------------------------------------------------------------
# Avvikelseanalys: vad just det här objektet har för förutsättningar
# ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Factor:
    """En faktor i avvikelseanalysen, med skalan boken sätter för den.

    Skalan är -4, -2, 0, +2, +4 procent, där minus är arbete som går fortare än normalt och plus är arbete som
    går långsammare. Vad som är normalt står utskrivet, så att en bedömning går att ifrågasätta.
    """
    id: str
    group: str
    label: str
    less: str                    # vad som gör att tiden minskar
    normal: str
    more: str                    # ...och vad som gör att den ökar
    scale: tuple[int, ...] = (-4, -2, 0, 2, 4)
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "group": self.group, "label": self.label, "less": self.less,
                "normal": self.normal, "more": self.more, "scale": list(self.scale), "source": self.source}


F_RESOURCES = "Disponibla resurser"
F_PLANNING = "Planering och beredning"

FACTORS: tuple[Factor, ...] = (
    Factor("arbetslaget", F_RESOURCES, "Arbetslaget",
           "Lämpligt antal montörer för varje installationsskede enligt uppgjord bemanningsplan",
           "Lämpligt antal montörer", "Bemanningsplan saknas", source="Avvikelseanalys, s. 46"),
    Factor("arbetsledning", F_RESOURCES, "Arbetsledarinsats",
           "Extra insats i arbetsledning", "Erforderlig arbetsledning", "Otillräcklig arbetsledning",
           source="Avvikelseanalys, s. 46"),
    Factor("hjalpmedel", F_RESOURCES, "Tekniska hjälpmedel",
           "Disponibla fordon på arbetsplatsen", "Lämpliga tekniska hjälpmedel",
           "Dåligt eller otillräckligt med tekniska hjälpmedel", source="Avvikelseanalys, s. 46"),

    Factor("underlag", F_PLANNING, "Ritningar och tekniska beskrivningar",
           "Ritningsunderlaget är berett för förtillverkning", "Erforderliga ritningar och tekniska beskrivningar",
           "Ofullständigt underlag", source="Analys av avvikelser, s. 47"),
    Factor("materialplanering", F_PLANNING, "Materialplanering",
           "Materialet levereras till arbetsstället", "Erforderligt material finns tillgängligt i förråd",
           "Ofullständig avropsplan, dålig framkomlighet för materialtransporter",
           source="Analys av avvikelser, s. 47"),
    Factor("samordning", F_PLANNING, "Samordning",
           "Aktuella detaljplaner och särskilda insatser för samordning med andra yrkesgrupper",
           "Huvudplan tillgänglig, planerade byggmöten", "Ofullständiga planer, dålig samordning",
           source="Analys av avvikelser, s. 47"),
)
FACTOR_BY_ID = {f.id: f for f in FACTORS}


def base_time(table_id: str, key: float, column: int = 1) -> float | None:
    """Grundtiden för en dimension eller vikt: första raden vars gräns räcker till.

    Tabellerna anger `-35,0` för "till och med 35". En dimension över den största raden har ingen normtid i
    listan, och då returneras ingenting - listan säger inget om den, och att förlänga den sista raden uppåt vore
    att hitta på en tid.
    """
    t = BY_ID.get(table_id)
    if t is None:
        return None
    for row in t.rows:
        try:
            if float(row[0]) >= float(key):
                v = row[column]
                return float(v) if isinstance(v, (int, float)) else None
        except (TypeError, ValueError):
            continue
    return None


def hours(base: float, quantity: float, supplements: list[str] | None = None,
          deviation_pct: float = 0.0) -> dict[str, float]:
    """Timmar för en post, och varje steg dit.

    Redovisas som delar och inte bara som en summa: den som ska försvara ett anbud behöver kunna peka på vilket
    tillägg och vilken bedömning som gjorde tiden vad den blev.
    """
    add = sum(SUPPLEMENT_BY_ID[s].pct for s in (supplements or []) if s in SUPPLEMENT_BY_ID)
    grund = base * quantity
    med_tillagg = grund * (1 + add)
    total = med_tillagg * (1 + deviation_pct / 100.0)
    return {"grundtid": round(grund, 3), "tillagg_pct": round(add * 100, 1),
            "efter_tillagg": round(med_tillagg, 3), "avvikelse_pct": round(deviation_pct, 1),
            "timmar": round(total, 3)}


def catalogue() -> dict[str, Any]:
    """Hela normtidsunderlaget, som gränssnittet behöver det."""
    return {"tables": [t.as_dict() for t in TABLES],
            "supplements": [s.as_dict() for s in SUPPLEMENTS],
            "factors": [f.as_dict() for f in FACTORS],
            "source": "Normtid VVS (Införlag)",
            "warning": "Tabellerna är avlästa ur bilder av boken. Kontrollera mot utgåvan innan anbud lämnas."}
