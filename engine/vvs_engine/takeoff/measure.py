"""Mätmotorn: en form, en skala, ett mått.

En central motor för allt som mäts på ett blad, oavsett om formen ritades för hand i mängdningen eller kommer
ur CAD-modellen. Tre regler bär den:

* **Måttet räknas ur koordinater, aldrig ur skärmen.** Samma form ger samma mängd vid varje zoomnivå, i varje
  webbläsare, på varje skärm. Zoomen finns inte i den här filen och kan därför inte påverka något.
* **Utan skala finns ingen meter.** Ett blad vars skala varken går att läsa eller är uppmätt ger måttet i
  ritningens egna punkter, med skälet utskrivet. En påhittad meter är värre än ingen.
* **Varje steg redovisas.** Rått mått, vald skala, påslag, resultat. Ett tal ingen kan följa bakåt är inget
  belägg, och det är belägg mängdning handlar om.

Ett blad kan ha flera skalor: en planritning i 1:50 med en detalj i 1:20 i hörnet. Därför mäts en form i den
*viewport* den ligger i, och viewportarna prövas i en bestämd ordning så att överlapp alltid avgörs likadant.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .geometry import (Point, angle_between, area_with_holes, centroid, length_of, perimeter_of,
                       point_in_ring, ring_area)

LENGTH_KINDS = ("langd", "polylinje", "frihand", "linje", "avstand")
AREA_KINDS = ("area", "rektangel", "polygon", "moln", "volym", "yta")
COUNT_KINDS = ("antal", "count")
ANGLE_KINDS = ("vinkel",)

# Enheter mätmotorn kan svara i. Basen är meter, för det är vad ett bygge handlas i.
UNITS: dict[str, float] = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0, "km": 1000.0,
                           "tum": 0.0254, "fot": 0.3048, "yard": 0.9144}


class ScaleError(ValueError):
    """Skalan går inte att använda, och måttet ska inte låtsas om det."""


def convert(value: float, frm: str, to: str, power: int = 1) -> float:
    """Räkna om ett mått mellan enheter. power=2 för ytor, 3 för volymer."""
    if frm not in UNITS or to not in UNITS:
        raise ScaleError(f"okänd enhet: {frm if frm not in UNITS else to}")
    return value * (UNITS[frm] / UNITS[to]) ** power


@dataclass(frozen=True)
class Scale:
    """Hur många meter en punkt på pappret är, och varifrån det beskedet kommer.

    `source` är inte pynt: en uppmätt skala och en läst skala är olika slags påståenden, och den som läser
    mängden ska kunna se vilket hon har framför sig.
    """
    meters_per_point: float
    source: str = "OKÄND"          # UPPMÄTT | LÄSNINGEN | ANGIVEN | OKÄND
    label: str = ""                # "1:50" när den är känd

    def __post_init__(self) -> None:
        if not (0 < self.meters_per_point < 1.0):
            raise ScaleError("skalan ligger utanför vad en ritning kan betyda")

    @property
    def ratio(self) -> float:
        """Skalans nämnare: 1:50 ger 50. En punkt är 1/72 tum = 0,0003528 m på pappret."""
        return self.meters_per_point / 0.0003527777777777778

    @classmethod
    def from_ratio(cls, denominator: float, source: str = "ANGIVEN") -> "Scale":
        """1:50 som skala: en meter på pappret är femtio i verkligheten."""
        if denominator <= 0:
            raise ScaleError("skalans nämnare måste vara större än noll")
        return cls(meters_per_point=0.0003527777777777778 * denominator, source=source,
                   label=f"1:{denominator:g}")


def scale_from_two_points(a: Sequence[float], b: Sequence[float], real_length: float,
                          unit: str = "m", source: str = "UPPMÄTT") -> Scale:
    """Skalan ur en sträcka någon dragit över något vars mått hon vet."""
    d = math.dist((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))
    if d < 5.0:
        raise ScaleError("sträckan är för kort för att mäta skalan på")
    metres = convert(float(real_length), unit, "m")
    if metres <= 0:
        raise ScaleError("längden måste vara större än noll")
    return Scale(meters_per_point=metres / d, source=source)


@dataclass(frozen=True)
class Viewport:
    """Ett område på sidan med en egen skala: detaljen i hörnet är inte i planens skala.

    `order` avgör överlapp: den lägsta ordningen vinner, och vid lika ordning den som kom först. Det gör svaret
    detsamma varje gång, vilket är hela poängen - två viewportar som överlappar får aldrig ge två olika mängder
    beroende på i vilken ordning de råkade sparas.
    """
    name: str
    ring: list[Point]
    scale: Scale
    order: int = 0
    unit: str = "m"

    def holds(self, pt: Sequence[float]) -> bool:
        return point_in_ring(pt, self.ring)


def scale_at(pt: Sequence[float], scale: Scale | None, viewports: Iterable[Viewport] = ()) -> tuple[Scale | None, str]:
    """Skalan som gäller där formen ligger, och namnet på den viewport som avgjorde det."""
    best: Viewport | None = None
    best_i = 0
    for i, v in enumerate(viewports or ()):
        if v.holds(pt) and (best is None or (v.order, i) < (best.order, best_i)):
            best, best_i = v, i
    if best is not None:
        return best.scale, best.name
    return scale, ""


@dataclass
class Measurement:
    """Vad formen mätte, och hur talet kom fram."""
    kind: str
    unit: str
    value: float | None                      # i `unit`
    raw: float | None = None                 # innan påslag, i samma enhet
    points: int = 0
    scale_source: str = "INGEN"
    viewport: str = ""
    steps: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        out = {"kind": self.kind, "unit": self.unit, "value": self.value, "raw": self.raw,
               "points": self.points, "scale_source": self.scale_source, "steps": dict(self.steps)}
        if self.viewport:
            out["viewport"] = self.viewport
        if self.extra:
            out.update(self.extra)
        if self.warnings:
            out["warnings"] = list(self.warnings)
        return out


def _round(v: float | None, d: int = 4) -> float | None:
    return None if v is None else round(v + 0.0, d)


def measure(kind: str, points: Iterable[Sequence[float]], scale: Scale | None = None, *,
            viewports: Iterable[Viewport] = (), holes: Iterable[Iterable[Sequence[float]]] = (),
            unit: str = "m", multiplier: float = 1.0, addition: float = 0.0,
            depth: float | None = None, waste: float = 0.0) -> Measurement:
    """Mät en form.

    kind          vad som mäts: längd, yta, volym, antal, vinkel
    points        formens punkter i ritningens koordinater
    scale         bladets skala; None betyder att måttet stannar i punkter
    viewports     områden med egen skala; formens tyngdpunkt avgör vilken som gäller
    holes         hål som dras av ur ytan
    multiplier    påslag i antal: två rör längs samma sträcka, tre våningar likadana
    addition      påslag i enheten: anslutningen som inte är ritad
    depth         ytans djup, som gör kvadratmeter till kubikmeter
    waste         spill i procent, redovisat för sig
    """
    pts = [(float(p[0]), float(p[1])) for p in points]
    m = Measurement(kind=kind, unit=unit, value=None, points=len(pts))
    if kind in COUNT_KINDS:
        m.unit = "st"
        m.raw = float(len(pts))
        m.value = _round(len(pts) * multiplier + addition)
        m.scale_source = "EJ_TILLÄMPLIG"
        m.steps = {"antal": len(pts), "multiplikator": multiplier, "tillagg": addition}
        return m
    if len(pts) < 2:
        m.warnings.append("för få punkter för att mäta")
        return m

    here = centroid(pts)
    sc, vp = scale_at(here, scale, viewports)
    m.viewport = vp
    m.scale_source = sc.source if sc else "INGEN"

    if kind in ANGLE_KINDS:
        m.unit = "grader"
        if len(pts) < 3:
            m.warnings.append("en vinkel behöver tre punkter")
            return m
        m.raw = angle_between(pts[0], pts[1], pts[2])
        m.value = _round(m.raw)
        m.scale_source = "EJ_TILLÄMPLIG"
        return m

    if sc is None:
        # ingen skala: måttet stannar i ritningens egna punkter, och säger det
        m.unit = "pt"
        m.raw = perimeter_of(pts) if kind in AREA_KINDS else length_of(pts)
        m.value = _round(m.raw)
        m.warnings.append("bladet har ingen skala - måttet är i ritningens punkter")
        if kind in AREA_KINDS and len(pts) >= 3:
            m.extra["area_pt2"] = _round(area_with_holes(pts, holes))
        return m

    mpp = sc.meters_per_point
    if kind in AREA_KINDS:
        area_pt = area_with_holes(pts, holes)
        gross_pt = ring_area(pts)
        area_m2 = area_pt * mpp * mpp
        per_m = perimeter_of(pts) * mpp
        value = area_m2 * multiplier + addition
        m.unit = "m²" if unit == "m" else f"{unit}²"
        m.raw = _round(convert(area_m2, "m", unit, power=2) if unit != "m" else area_m2)
        m.value = _round(convert(value, "m", unit, power=2) if unit != "m" else value)
        m.steps = {"area_m2": _round(area_m2), "multiplikator": multiplier, "tillagg": addition,
                   "omkrets_m": _round(per_m)}
        m.extra["perimeter"] = _round(per_m)
        m.extra["area_pt2"] = _round(area_pt, 2)      # formen i ritningens egna punkter, före skalan
        if gross_pt > area_pt:
            m.extra["holes"] = _round((gross_pt - area_pt) * mpp * mpp)
            m.steps["avdrag_m2"] = m.extra["holes"]
        if depth:
            vol = value * float(depth)
            m.extra["volume"] = _round(vol)
            m.steps["djup_m"] = float(depth)
            m.steps["volym_m3"] = _round(vol)
        if waste:
            m.extra["with_waste"] = _round((m.value or 0.0) * (1 + waste / 100.0))
            m.steps["spill_pct"] = waste
        return m

    # längd
    raw_m = length_of(pts) * mpp
    value = raw_m * multiplier + addition
    m.unit = unit
    m.raw = _round(convert(raw_m, "m", unit) if unit != "m" else raw_m)
    m.value = _round(convert(value, "m", unit) if unit != "m" else value)
    m.steps = {"ratt_m": _round(raw_m), "multiplikator": multiplier, "tillagg": addition}
    if waste:
        m.extra["with_waste"] = _round((m.value or 0.0) * (1 + waste / 100.0))
        m.steps["spill_pct"] = waste
    return m
