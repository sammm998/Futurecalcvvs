from __future__ import annotations

import math

"""Övningsritningarna.

Ett övningsblad är inte en bild. Det är geometri: väggar, rörstråk med system och dimension, symboler med
plats och sort. Gränssnittet ritar det, den som övar mäter på det, och facit räknas **ur samma geometri** -
aldrig ur ett tal någon skrivit in för hand. Skriver någon om ett stråk följer facit med.

Skalan anges som meter per ritningsenhet. Bladen är ritade i en ruta på 1200 x 760 enheter, och 0,05 m per
enhet ger ett hus på 60 x 38 meter — det är för stort för ett badrum, så varje blad sätter sin egen.
"""

Pt = tuple[float, float]


def length(points: list[Pt]) -> float:
    return sum(math.dist(points[i - 1], points[i]) for i in range(1, len(points)))


def metres(points: list[Pt], m_per_unit: float) -> float:
    return round(length(points) * m_per_unit, 2)


def path_d(points: list[Pt]) -> str:
    return "M" + " L".join(f"{x} {y}" for x, y in points)


class Plan:
    """Ett blad. `runs` är rörstråk, `symbols` är komponenter, `rooms` är rum med namn."""

    def __init__(self, slug: str, title: str, m_per_unit: float, view=(0, 0, 1200, 760)):
        self.slug, self.title, self.m_per_unit, self.view = slug, title, m_per_unit, view
        self.walls: list[list[Pt]] = []
        self.runs: list[dict] = []
        self.symbols: list[dict] = []
        self.rooms: list[dict] = []

    def wall(self, *pts: Pt) -> "Plan":
        self.walls.append(list(pts))
        return self

    def run(self, rid: str, sys: str, dn: int, *pts: Pt, label: str = "") -> "Plan":
        self.runs.append({
            "id": rid, "sys": sys, "dn": dn, "label": label or f"{sys}-{dn}",
            "points": [list(p) for p in pts], "d": path_d(list(pts)),
            "m": metres(list(pts), self.m_per_unit),
        })
        return self

    def symbol(self, sid: str, kind: str, x: float, y: float, name: str = "", rot: float = 0) -> "Plan":
        self.symbols.append({"id": sid, "kind": kind, "x": x, "y": y, "name": name or kind, "rot": rot})
        return self

    def room(self, name: str, x: float, y: float, w: float, h: float) -> "Plan":
        self.rooms.append({"name": name, "x": x, "y": y, "w": w, "h": h})
        return self

    # ---- frågor facit ställs mot -------------------------------------------------------------------

    def metres_of(self, *ids: str) -> float:
        return round(sum(r["m"] for r in self.runs if r["id"] in ids), 2)

    def metres_where(self, sys: str | None = None, dn: int | None = None) -> float:
        return round(sum(r["m"] for r in self.runs
                         if (sys is None or r["sys"] == sys) and (dn is None or r["dn"] == dn)), 2)

    def ids_of_kind(self, *kinds: str) -> list[str]:
        return sorted(s["id"] for s in self.symbols if s["kind"] in kinds)

    def count_of(self, *kinds: str) -> int:
        return len(self.ids_of_kind(*kinds))

    def names(self) -> dict[str, str]:
        return {s["id"]: s["name"] for s in self.symbols}

    def data(self) -> dict:
        return {
            "plan": self.slug, "title": self.title, "m_per_unit": self.m_per_unit, "view": list(self.view),
            "walls": [[list(p) for p in w] for w in self.walls],
            "runs": [{k: v for k, v in r.items() if k != "points"} for r in self.runs],
            "symbols": self.symbols, "rooms": self.rooms,
            "names": self.names(),
        }


# ---------------------------------------------------------------- blad 1: ett badrum

BAD = Plan("badrum-1", "Badrum med WC, tvättställ, dusch och golvbrunn", 0.012, (0, 0, 900, 620))
(BAD
 .wall((60, 60), (840, 60), (840, 560), (60, 560), (60, 60))
 .wall((460, 60), (460, 300))
 .room("Badrum", 60, 60, 400, 500)
 .room("WC", 460, 60, 380, 240)
 # tappkallvatten: från stam till tvättställ, WC och dusch
 .run("kv-stam", "KV", 20, (110, 540), (110, 200), label="KV1-B2-20")
 .run("kv-tvatt", "KV", 15, (110, 200), (300, 200), label="KV1-B2-15")
 .run("kv-dusch", "KV", 15, (110, 330), (250, 330), (250, 430), label="KV1-B3-15")
 .run("kv-wc", "KV", 15, (110, 130), (620, 130), label="KV1-B4-15")
 # tappvarmvatten följer kallvattnet fram till tvättställ och dusch
 .run("vv-stam", "VV", 20, (140, 540), (140, 230), label="VV1-B2-20")
 .run("vv-tvatt", "VV", 15, (140, 230), (300, 230), label="VV1-B2-15")
 .run("vv-dusch", "VV", 15, (140, 350), (250, 350), (250, 430), label="VV1-B3-15")
 # spillvatten med självfall mot stammen
 .run("s-golvbrunn", "S", 75, (250, 470), (360, 470), (360, 540), label="S1-B1-75")
 .run("s-wc", "S", 110, (620, 190), (620, 470), (360, 470), label="S1-B1-110")
 .run("s-tvatt", "S", 50, (300, 260), (360, 260), (360, 470), label="S1-B2-50")
 .symbol("v-kv-stam", "kulventil", 110, 500, "Avstängning KV vid stam")
 .symbol("v-vv-stam", "kulventil", 140, 500, "Avstängning VV vid stam")
 .symbol("v-tvatt", "kulventil", 285, 215, "Avstängning tvättställ")
 .symbol("v-wc", "kulventil", 600, 130, "Avstängning WC")
 .symbol("gb1", "golvbrunn", 250, 470, "Golvbrunn")
 .symbol("wc1", "wc", 620, 165, "WC-stol")
 .symbol("tv1", "tvattstall", 315, 245, "Tvättställ")
 .symbol("du1", "dusch", 250, 430, "Duschplats")
 .symbol("bl1", "blandare", 315, 215, "Tvättställsblandare")
 .symbol("bl2", "blandare", 250, 390, "Duschblandare")
 )

# ---------------------------------------------------------------- blad 2: en värmekrets

VARME = Plan("varme-1", "Radiatorkrets med fram- och returledning", 0.03, (0, 0, 1100, 700))
(VARME
 .wall((60, 60), (1040, 60), (1040, 640), (60, 640), (60, 60))
 .wall((400, 60), (400, 380)).wall((740, 260), (740, 640))
 .room("Kontor 1", 60, 60, 340, 580).room("Kontor 2", 400, 60, 340, 320).room("Korridor", 740, 260, 300, 380)
 .run("vs-fram", "VS", 32, (120, 600), (120, 140), (900, 140), label="VS1-F-32")
 .run("vs-retur", "VS", 32, (150, 600), (150, 170), (900, 170), label="VS1-R-32")
 .run("vs-gren1", "VS", 20, (300, 140), (300, 250), label="VS1-F-20")
 .run("vs-gren2", "VS", 20, (600, 140), (600, 250), label="VS1-F-20")
 .run("vs-gren3", "VS", 20, (860, 140), (860, 320), label="VS1-F-20")
 .run("vs-ret1", "VS", 20, (330, 170), (330, 250), label="VS1-R-20")
 .run("vs-ret2", "VS", 20, (630, 170), (630, 250), label="VS1-R-20")
 .symbol("rad1", "radiator", 300, 270, "Radiator kontor 1", 0)
 .symbol("rad2", "radiator", 600, 270, "Radiator kontor 2", 0)
 .symbol("rad3", "radiator", 860, 340, "Radiator korridor", 0)
 .symbol("p1", "pump", 120, 560, "Cirkulationspump")
 .symbol("v1", "kulventil", 120, 480, "Avstängning framledning")
 .symbol("v2", "kulventil", 150, 480, "Avstängning returledning")
 .symbol("inj1", "injustering", 330, 210, "Injusteringsventil radiator 1")
 .symbol("inj2", "injustering", 630, 210, "Injusteringsventil radiator 2")
 .symbol("bv1", "backventil", 120, 420, "Backventil")
 .symbol("exp1", "expansionskarl", 190, 560, "Expansionskärl")
 )

# ---------------------------------------------------------------- blad 3: en tappvattenstam

STAM = Plan("stam-1", "Tappvattenstam med KV, VV och VVC genom tre plan", 0.02, (0, 0, 1000, 760))
(STAM
 .wall((80, 60), (920, 60), (920, 700), (80, 700), (80, 60))
 .wall((80, 280), (920, 280)).wall((80, 490), (920, 490))
 .room("Plan 3", 80, 60, 840, 220).room("Plan 2", 80, 280, 840, 210).room("Plan 1", 80, 490, 840, 210)
 .run("kv-stig", "KV", 32, (200, 660), (200, 120), label="KV1-S1-32")
 .run("vv-stig", "VV", 25, (240, 660), (240, 120), label="VV1-S1-25")
 .run("vvc-stig", "VVC", 15, (280, 660), (280, 120), label="VVC1-S1-15")
 .run("kv-p3", "KV", 20, (200, 160), (700, 160), label="KV1-S1-20")
 .run("kv-p2", "KV", 20, (200, 380), (700, 380), label="KV1-S1-20")
 .run("kv-p1", "KV", 20, (200, 590), (700, 590), label="KV1-S1-20")
 .run("vv-p3", "VV", 20, (240, 190), (700, 190), label="VV1-S1-20")
 .run("vv-p2", "VV", 20, (240, 410), (700, 410), label="VV1-S1-20")
 .run("vv-p1", "VV", 20, (240, 620), (700, 620), label="VV1-S1-20")
 .symbol("v3", "kulventil", 200, 200, "Avstängning plan 3")
 .symbol("v2", "kulventil", 200, 420, "Avstängning plan 2")
 .symbol("v1", "kulventil", 200, 630, "Avstängning plan 1")
 .symbol("bv", "backventil", 200, 690, "Backventil inkommande")
 .symbol("i1", "injustering", 280, 300, "Injustering VVC")
 )

# ---------------------------------------------------------------- blad 4: ett ventilationsblad

VENT = Plan("vent-1", "Till- och frånluft med don, spjäll och aggregat", 0.035, (0, 0, 1180, 720))
(VENT
 .wall((60, 60), (1120, 60), (1120, 660), (60, 660), (60, 60))
 .wall((420, 60), (420, 400)).wall((760, 300), (760, 660))
 .room("Kontorslandskap", 60, 60, 360, 600).room("Mötesrum", 420, 60, 340, 340)
 .room("Pentry", 760, 300, 360, 360)
 # tilluft: huvudkanal och avstick till varje don
 .run("tl-huvud", "TL", 400, (140, 620), (140, 140), (980, 140), label="TL1-400")
 .run("tl-gren1", "TL", 160, (300, 140), (300, 300), label="TL1-160")
 .run("tl-gren2", "TL", 160, (560, 140), (560, 280), label="TL1-160")
 .run("tl-gren3", "TL", 125, (900, 140), (900, 420), label="TL1-125")
 # frånluft går tillbaka i egen kanal
 .run("fl-huvud", "FL", 400, (200, 620), (200, 200), (980, 200), label="FL1-400")
 .run("fl-gren1", "FL", 160, (360, 200), (360, 300), label="FL1-160")
 .run("fl-gren2", "FL", 125, (660, 200), (660, 280), label="FL1-125")
 .run("fl-pentry", "FL", 100, (940, 200), (940, 480), label="FL1-100")
 .symbol("agg1", "aggregat", 170, 620, "Luftbehandlingsaggregat LA01")
 .symbol("don1", "tilluftsdon", 300, 320, "Tilluftsdon kontor")
 .symbol("don2", "tilluftsdon", 560, 300, "Tilluftsdon mötesrum")
 .symbol("don3", "tilluftsdon", 900, 440, "Tilluftsdon pentry")
 .symbol("don4", "franluftsdon", 360, 320, "Frånluftsdon kontor")
 .symbol("don5", "franluftsdon", 660, 300, "Frånluftsdon mötesrum")
 .symbol("don6", "franluftsdon", 940, 500, "Frånluftsdon pentry")
 .symbol("sp1", "spjall", 300, 220, "Injusteringsspjäll TL gren 1")
 .symbol("sp2", "spjall", 560, 220, "Injusteringsspjäll TL gren 2")
 .symbol("bsp1", "brandspjall", 420, 140, "Brandspjäll i vägg mot mötesrum")
 .symbol("bsp2", "brandspjall", 760, 200, "Brandspjäll i vägg mot pentry")
 )

# ---------------------------------------------------------------- blad 5: spill och dag under mark

MARK = Plan("mark-1", "Spill- och dagvatten med brunnar och självfall", 0.05, (0, 0, 1200, 700))
(MARK
 .wall((80, 80), (1120, 80), (1120, 620), (80, 620), (80, 80))
 .room("Byggnad", 80, 80, 640, 540).room("Gård", 720, 80, 400, 540)
 .run("s-samling", "S", 160, (200, 540), (200, 200), (980, 200), label="S1-M-160")
 .run("s-gren-a", "S", 110, (340, 200), (340, 380), label="S1-M-110")
 .run("s-gren-b", "S", 110, (520, 200), (520, 420), label="S1-M-110")
 .run("s-gren-c", "S", 75, (660, 200), (660, 340), label="S1-M-75")
 .run("d-samling", "D", 200, (860, 540), (860, 300), (1060, 300), label="D1-M-200")
 .run("d-gren-a", "D", 110, (860, 420), (740, 420), label="D1-M-110")
 .run("d-gren-b", "D", 110, (960, 300), (960, 480), label="D1-M-110")
 .symbol("sb1", "spolbrunn", 200, 200, "Spolbrunn SB1")
 .symbol("sb2", "spolbrunn", 980, 200, "Spolbrunn SB2")
 .symbol("rb1", "rensbrunn", 340, 380, "Rensbrunn RB1")
 .symbol("db1", "dagvattenbrunn", 740, 420, "Dagvattenbrunn DB1")
 .symbol("db2", "dagvattenbrunn", 960, 480, "Dagvattenbrunn DB2")
 .symbol("fb1", "fettavskiljare", 520, 440, "Fettavskiljare")
 .symbol("lv1", "luftare", 660, 320, "Vakuumventil")
 )

# ---------------------------------------------------------------- blad 6: en undercentral

UC = Plan("uc-1", "Undercentral: fjärrvärme, växlare, VVC och shuntgrupp", 0.02, (0, 0, 1040, 680))
(UC
 .wall((60, 60), (980, 60), (980, 620), (60, 620), (60, 60))
 .room("Undercentral", 60, 60, 920, 560)
 .run("fv-fram", "FV", 65, (120, 560), (120, 180), (420, 180), label="FV-F-65")
 .run("fv-retur", "FV", 65, (160, 560), (160, 220), (420, 220), label="FV-R-65")
 .run("vs-fram", "VS", 50, (500, 180), (860, 180), (860, 380), label="VS1-F-50")
 .run("vs-retur", "VS", 50, (500, 220), (800, 220), (800, 380), label="VS1-R-50")
 .run("vv-ut", "VV", 40, (500, 300), (900, 300), label="VV1-40")
 .run("vvc-in", "VVC", 20, (900, 340), (520, 340), label="VVC1-20")
 .run("kv-in", "KV", 50, (120, 460), (460, 460), (460, 320), label="KV1-50")
 .symbol("vx1", "varmevaxlare", 460, 200, "Värmeväxlare värme")
 .symbol("vx2", "varmevaxlare", 460, 320, "Värmeväxlare tappvarmvatten")
 .symbol("p1", "pump", 700, 180, "Värmekretspump")
 .symbol("p2", "pump", 700, 340, "VVC-pump")
 .symbol("exp1", "expansionskarl", 900, 420, "Expansionskärl")
 .symbol("sv1", "styrventil", 380, 180, "Styrventil primär värme")
 .symbol("sv2", "styrventil", 380, 300, "Styrventil primär tappvarmvatten")
 .symbol("v1", "kulventil", 120, 520, "Avstängning fjärrvärme fram")
 .symbol("v2", "kulventil", 160, 520, "Avstängning fjärrvärme retur")
 .symbol("v3", "kulventil", 200, 460, "Avstängning inkommande kallvatten")
 .symbol("smf1", "smutsfilter", 260, 180, "Smutsfilter primär")
 .symbol("mv1", "matare", 300, 220, "Energimätare fjärrvärme")
 )

PLANS = {p.slug: p for p in (BAD, VARME, STAM, VENT, MARK, UC)}
