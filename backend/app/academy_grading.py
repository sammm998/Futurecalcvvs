from __future__ import annotations

import math
from typing import Any

"""Rättningen.

Allt rättas här, på servern, mot facit som aldrig lämnat den. Klienten skickar vad någon gjorde och får
tillbaka poäng, godkänt eller inte, och en förklaring som säger något - inte "Fel".

Poängen är alltid 0..1 och multipliceras med övningens `points` först när den bokförs. Det gör att en övning
kan väga tyngre utan att rättningen behöver veta om det.

Två saker är gemensamma för alla sorter:

  * **Tolerans i andel, inte i enhet.** ±2 % betyder samma sak på ett tolvmetersrör som på ett trehundra.
    En absolut tolerans i meter är antingen löjligt snäll eller omöjlig, beroende på uppgiftens storlek.
  * **Delpoäng där det finns delar.** Den som hittar fem ventiler av sex har inte gjort fel; hen har gjort
    det mesta rätt, och får veta vilken som saknas.
"""

Feedback = dict[str, Any]
Result = tuple[float, bool, Feedback]


def _num(v: Any) -> float | None:
    """Ett tal ur något en människa skrivit. Svenskt decimalkomma, mellanslag som tusenavskiljare."""
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    t = v.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _within(given: float, want: float, tol: float) -> bool:
    if want == 0:
        return abs(given) <= max(tol, 0.0001)
    return abs(given - want) / abs(want) <= tol


def _pct_off(given: float, want: float) -> float:
    return 0.0 if want == 0 else (given - want) / abs(want) * 100.0


def _sv(x: float, decimals: int = 2) -> str:
    return f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")


def _sets(given: Any, want: Any) -> tuple[set, set]:
    g = set(given or []) if isinstance(given, (list, set, tuple)) else set()
    w = set(want or []) if isinstance(want, (list, set, tuple)) else set()
    return g, w


def _set_score(g: set, w: set) -> tuple[float, set, set]:
    """Jaccard mot facit: rätt delat med allt som är antingen valt eller rätt. Ett felval kostar lika mycket
    som ett missat, vilket är rimligt - att peka på fel ventil är inte bättre än att inte peka alls."""
    hit = g & w
    miss = w - g
    wrong = g - w
    union = len(g | w)
    return (len(hit) / union if union else 1.0), miss, wrong


# ---------------------------------------------------------------- längd ur en polyline

def polyline_metres(points: list[list[float]], m_per_unit: float) -> float:
    """Längden på det någon ritade, i meter. Samma räkning som mängdaren gör i verktyget."""
    total = 0.0
    for i in range(1, len(points or [])):
        (x0, y0), (x1, y1) = points[i - 1][:2], points[i][:2]
        total += math.hypot(x1 - x0, y1 - y0)
    return total * m_per_unit


# ---------------------------------------------------------------- sorterna

def _grade_measure(ex: dict, given: dict) -> Result:
    """Mängda: någon har ritat en eller flera polylinjer på bladet, och vi jämför metrarna."""
    scale = float((ex.get("data") or {}).get("m_per_unit") or 0.01)
    runs = given.get("runs") or []
    got = sum(polyline_metres(r, scale) for r in runs)
    if given.get("metres") is not None:                 # klienten får skicka sin egen summa; vi räknar om ändå
        pass
    want = float((ex.get("answer") or {}).get("metres") or 0.0)
    tol = float(ex.get("tolerance") or 0.02)
    ok = _within(got, want, tol)
    off = _pct_off(got, want)
    fb: Feedback = {
        "din_mangd": round(got, 2), "ratt_mangd": round(want, 2),
        "avvikelse_pct": round(off, 1), "tolerans_pct": round(tol * 100, 1),
        "text": (
            f"Rätt. Du fick {_sv(got)} m mot facit {_sv(want)} m, en avvikelse på {_sv(off, 1)} %."
            if ok else
            f"Din mängd blev {_sv(got)} m. Rätt mängd är {_sv(want)} m — du ligger {_sv(off, 1)} % "
            f"{'över' if off > 0 else 'under'}, och toleransen är ±{_sv(tol * 100, 1)} %."
        ),
    }
    hint = (ex.get("answer") or {}).get("miss_hint")
    if not ok and hint:
        fb["text"] += " " + hint
    # Delpoäng: full poäng inom tolerans, sedan avtagande till noll vid fem gånger toleransen.
    score = 1.0 if ok else max(0.0, 1.0 - (abs(off) / 100.0) / (tol * 5 or 0.1))
    return score, ok, fb


def _grade_select(ex: dict, given: dict) -> Result:
    """Markera komponenter, hitta fel, ritningsurval: en mängd id mot en mängd id."""
    g, w = _sets(given.get("picked"), (ex.get("answer") or {}).get("picked"))
    score, miss, wrong = _set_score(g, w)
    ok = score >= float((ex.get("answer") or {}).get("pass") or 1.0)
    names = (ex.get("data") or {}).get("names") or {}
    label = lambda i: names.get(i, i)                                            # noqa: E731
    if ok and not miss and not wrong:
        text = f"Rätt. Du identifierade samtliga {len(w)}."
    else:
        bits = [f"Du hittade {len(g & w)} av {len(w)}."]
        if miss:
            bits.append("Du missade: " + ", ".join(sorted(label(i) for i in miss)) + ".")
        if wrong:
            bits.append("Fel markering: " + ", ".join(sorted(label(i) for i in wrong)) + ".")
        text = " ".join(bits)
    return score, ok, {"ratt": len(g & w), "av": len(w), "missade": sorted(miss), "felaktiga": sorted(wrong), "text": text}


def _grade_choice(ex: dict, given: dict) -> Result:
    """Ett val bland flera. Dimension, symbol, sant/falskt."""
    want = (ex.get("answer") or {}).get("index")
    got = given.get("index")
    ok = got is not None and int(got) == int(want)
    opts = (ex.get("data") or {}).get("options") or []
    right = opts[int(want)] if isinstance(want, int) and 0 <= int(want) < len(opts) else str(want)
    text = "Rätt." if ok else f"Rätt svar är {right}."
    why = (ex.get("answer") or {}).get("why") or ""
    return (1.0 if ok else 0.0), ok, {"text": (text + " " + why).strip(), "ratt_index": want}


def _grade_pairs(ex: dict, given: dict) -> Result:
    """Matchning: vänster id -> höger id."""
    want = dict((ex.get("answer") or {}).get("pairs") or {})
    got = dict(given.get("pairs") or {})
    hit = [k for k, v in want.items() if got.get(k) == v]
    score = len(hit) / len(want) if want else 1.0
    ok = score >= 1.0
    missade = sorted(k for k in want if k not in hit)
    names = (ex.get("data") or {}).get("names") or {}
    text = ("Rätt. Alla par stämmer." if ok else
            f"{len(hit)} av {len(want)} par rätt. Se över: "
            + ", ".join(names.get(k, k) for k in missade) + ".")
    return score, ok, {"ratt": len(hit), "av": len(want), "felaktiga": missade, "text": text}


def _grade_order(ex: dict, given: dict) -> Result:
    """Bygg rörsystem: rätt ordning på komponenterna."""
    want = list((ex.get("answer") or {}).get("order") or [])
    got = list(given.get("order") or [])
    if not want:
        return 1.0, True, {"text": "Rätt."}
    # Poäng på hur många som står på rätt plats relativt sin granne, inte på exakt index: den som sätter ett
    # enda fel först har inte gjort allt fel efter det.
    pairs_want = set(zip(want, want[1:]))
    pairs_got = set(zip(got, got[1:]))
    score = len(pairs_want & pairs_got) / len(pairs_want) if pairs_want else 1.0
    ok = got == want
    names = (ex.get("data") or {}).get("names") or {}
    text = ("Rätt ordning." if ok else
            "Rätt ordning är: " + " → ".join(names.get(k, k) for k in want) + ".")
    return score, ok, {"text": text, "ratt_ordning": want if not ok else None}


def _grade_numeric(ex: dict, given: dict) -> Result:
    """Ett tal med tolerans."""
    want = _num((ex.get("answer") or {}).get("value"))
    got = _num(given.get("value"))
    tol = float(ex.get("tolerance") or 0.01)
    unit = (ex.get("data") or {}).get("unit") or ""
    if got is None or want is None:
        return 0.0, False, {"text": "Inget tal att rätta."}
    ok = _within(got, want, tol)
    text = ("Rätt." if ok else
            f"Du svarade {_sv(got)} {unit}. Rätt svar är {_sv(want)} {unit}.")
    why = (ex.get("answer") or {}).get("why") or ""
    return (1.0 if ok else 0.0), ok, {"text": (text + " " + why).strip(), "ratt_varde": want}


def _grade_steps(ex: dict, given: dict) -> Result:
    """Kalkylövning: flera tal, ett per steg, och varje steg rättas för sig.

    Den som räknat rätt material men fel timkostnad ska se exakt det, inte ett underkänt på hela uppgiften.
    """
    steps = list((ex.get("data") or {}).get("steps") or [])
    want = dict((ex.get("answer") or {}).get("steps") or {})
    got = dict(given.get("steps") or {})
    tol = float(ex.get("tolerance") or 0.01)
    rows, hits = [], 0
    for st in steps:
        key = st.get("key")
        w = _num(want.get(key))
        g = _num(got.get(key))
        ok = w is not None and g is not None and _within(g, w, tol)
        hits += 1 if ok else 0
        rows.append({
            "key": key, "label": st.get("label", key), "unit": st.get("unit", ""),
            "ditt": g, "ratt": w, "ok": ok,
        })
    score = hits / len(steps) if steps else 1.0
    ok = hits == len(steps)
    first_bad = next((r for r in rows if not r["ok"]), None)
    text = ("Rätt hela vägen." if ok else
            f"{hits} av {len(steps)} steg rätt."
            + (f" Första felet är {first_bad['label'].lower()}: du skrev {_sv(first_bad['ditt'] or 0)}, "
               f"rätt är {_sv(first_bad['ratt'] or 0)} {first_bad['unit']}." if first_bad else ""))
    return score, ok, {"steg": rows, "ratt": hits, "av": len(steps), "text": text}


def _grade_buckets(ex: dict, given: dict) -> Result:
    """Kategorisering: objekt -> kategori."""
    want = dict((ex.get("answer") or {}).get("buckets") or {})
    got = dict(given.get("buckets") or {})
    hit = [k for k, v in want.items() if got.get(k) == v]
    score = len(hit) / len(want) if want else 1.0
    ok = score >= 1.0
    names = (ex.get("data") or {}).get("names") or {}
    fel = sorted(k for k in want if k not in hit)
    text = ("Rätt. Alla hamnade i sin kategori." if ok else
            f"{len(hit)} av {len(want)} rätt. Fel kategori: " + ", ".join(names.get(k, k) for k in fel) + ".")
    return score, ok, {"ratt": len(hit), "av": len(want), "felaktiga": fel, "text": text}


def _grade_room(ex: dict, given: dict) -> Result:
    """Mängda ett helt rum: flera namngivna poster, var och en med sin tolerans."""
    want = dict((ex.get("answer") or {}).get("items") or {})
    got = dict(given.get("items") or {})
    tol = float(ex.get("tolerance") or 0.05)
    rows, hits = [], 0
    for key, w in want.items():
        wv = _num(w)
        gv = _num(got.get(key))
        ok = wv is not None and gv is not None and _within(gv, wv, tol)
        hits += 1 if ok else 0
        rows.append({"key": key, "ditt": gv, "ratt": wv, "ok": ok})
    score = hits / len(want) if want else 1.0
    ok = hits == len(want)
    text = ("Hela rummet rätt mängdat." if ok else
            f"{hits} av {len(want)} poster inom toleransen.")
    return score, ok, {"poster": rows, "ratt": hits, "av": len(want), "text": text}


KINDS = {
    "mangda": _grade_measure,
    "rum": _grade_room,
    "markera": _grade_select,
    "hitta-fel": _grade_select,
    "ritningsquiz": _grade_select,
    "dimension": _grade_choice,
    "symbol": _grade_choice,
    "matcha": _grade_pairs,
    "bygg": _grade_order,
    "kalkyl": _grade_steps,
    "numerisk": _grade_numeric,
    "kategorisera": _grade_buckets,
}


def grade(ex: dict, given: dict) -> Result:
    """Rätta en övning. Okänd sort är ingen krasch - den är en övning som inte går att rätta, och det sägs."""
    fn = KINDS.get(ex.get("kind") or "")
    if not fn:
        return 0.0, False, {"text": f"Övningstypen {ex.get('kind')!r} går inte att rätta."}
    try:
        return fn(ex, given or {})
    except (TypeError, ValueError, KeyError, IndexError) as e:
        return 0.0, False, {"text": f"Svaret gick inte att läsa: {e}"}


# ---------------------------------------------------------------- frågor

def grade_question(q: dict, given: Any) -> tuple[float, bool]:
    """En fråga i quiz eller tenta. Samma regler, men utan text tillbaka i tentaläge."""
    kind = q.get("kind") or "single"
    ans = q.get("answer") or {}
    if kind == "single":
        ok = given is not None and int(given) == int(ans.get("index", -1))
        return (1.0 if ok else 0.0), ok
    if kind == "bool":
        ok = bool(given) is bool(ans.get("value"))
        return (1.0 if ok else 0.0), ok
    if kind == "multi":
        g, w = _sets(given, ans.get("indexes"))
        score, _, _ = _set_score(g, w)
        return score, score >= 1.0
    if kind == "numeric":
        want, got = _num(ans.get("value")), _num(given)
        if want is None or got is None:
            return 0.0, False
        ok = _within(got, want, float(q.get("tolerance") or 0.01))
        return (1.0 if ok else 0.0), ok
    if kind == "match":
        want = dict(ans.get("pairs") or {})
        got = dict(given or {})
        hit = [k for k, v in want.items() if got.get(k) == v]
        score = len(hit) / len(want) if want else 1.0
        return score, score >= 1.0
    return 0.0, False
