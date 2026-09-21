"""Vad läsningen gjorde med varje ritning i materialet, som en läsbar sida.

Svepet sparar en rad per ritning medan det går. Det här gör raderna till en genomgång som svarar på de frågor
man faktiskt ställer om ett mängdningssystem, ritning för ritning:

  hittades allt?      hur många beteckningar bladet skriver, och hur många av dem som fick fäste på ett rör
  blev det rätt?      för de blad som har en mängdförteckning: täckning och falskhet mot den
  mängdades det?      meter, rader, och hur stor del av det ritade röret som bär en identitet
  togs väggar med?    hittades bladets skraffering alls, och hur många meter som ligger i den

En korpus som bara redovisas som ett medelvärde döljer just det som är värt att veta, så tabellen är per
ritning och sammanställningarna kommer efteråt.

    python3 tools/corpus_report.py <sweep.json> <ut.md> [facit-metrics.json]
"""
from __future__ import annotations

import collections
import json
import sys


def pct(n: float, of: float) -> str:
    return f"{100.0 * n / of:.1f} %".replace(".", ",") if of else "–"


def num(x, d: int = 1) -> str:
    return "–" if x is None else f"{x:.{d}f}".replace(".", ",")


def facit_by_tag(path: str | None) -> dict:
    """Mängdförteckningens mått per blad, när de finns. Läses bara för rapporten - aldrig av läsningen."""
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    sheets = d["sheets"] if isinstance(d.get("sheets"), list) else list((d.get("sheets") or {}).values())
    return {s["tag"]: s for s in sheets}


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    facit = facit_by_tag(sys.argv[3] if len(sys.argv) > 3 else None)
    with open(src, encoding="utf-8") as fh:
        rows = list(json.load(fh).values())
    rows.sort(key=lambda r: r["name"].lower())

    ok = [r for r in rows if r["state"] == "OK"]
    bad = [r for r in rows if r["state"] != "OK"]
    with_m = [r for r in ok if (r.get("confirmed_horizontal_m") or 0) > 0]

    def cov(r) -> dict:
        return r.get("coverage") or {}

    def prof(r) -> dict:
        return r.get("profile") or {}

    def anchors(r) -> dict:
        return r.get("anchors") or {}

    def placed(r) -> tuple[int, int]:
        a = anchors(r)
        good = int(a.get("VERIFIED_PIPE_ATTACHMENT") or 0)
        return good, sum(int(v or 0) for v in a.values())

    L: list[str] = [
        "# Hela materialet, ritning för ritning",
        "",
        f"Varje unik ritnings-PDF som finns lokalt ur ritningsmappen, läst blint: **{len(rows)} filer**. Ingen",
        "mängdförteckning öppnades under läsningen och ingenting jämfördes med ett facit medan den gick. Där en",
        "mängdförteckning finns står jämförelsen i tabellen nedan - den är skriven efteråt, ur ett fruset",
        "resultat.",
        "",
        "En läsning som bara prövas där svaret är känt är prövad på fel ställe. Därför är hela materialet med,",
        "inte bara de blad som har ett facit.",
        "",
        "## Sammanfattning",
        "",
        "| | antal | andel |",
        "|---|---:|---:|",
        f"| filer | {len(rows)} | |",
        f"| lästa utan fel | {len(ok)} | {pct(len(ok), len(rows))} |",
        f"| varav gav meter | {len(with_m)} | {pct(len(with_m), len(rows))} |",
        f"| gick inte att läsa | {len(bad)} | {pct(len(bad), len(rows))} |",
        "",
    ]

    # ---- hittades allt? -------------------------------------------------------------------------------
    des_tot = sum(int(r.get("designations") or 0) for r in ok)
    good_tot = sum(placed(r)[0] for r in ok)
    anch_tot = sum(placed(r)[1] for r in ok)
    amb_tot = sum(int(anchors(r).get("AMBIGUOUS_PIPE_ATTACHMENT") or 0) for r in ok)
    none_tot = sum(int(anchors(r).get("NO_PIPE_ATTACHMENT") or 0) for r in ok)
    L += [
        "## Hittades allt, och kopplades beteckningarna till rör?",
        "",
        f"Över de lästa bladen: **{des_tot} beteckningar** lästes och **{anch_tot} hänvisningslinjer** följdes",
        f"från dem till ett fäste. Av fästena är **{good_tot} verifierade** ({pct(good_tot, anch_tot)}),",
        f"{amb_tot} tvetydiga ({pct(amb_tot, anch_tot)}) och {none_tot} landade inte på någon rörgeometri",
        f"({pct(none_tot, anch_tot)}).",
        "",
        "Ett fäste som inte landar är inte alltid ett fel - en beteckning kan peka på en komponent, en",
        "hänvisning till ett annat blad eller en not - men det är den posten man går igenom först när ett blad",
        "ger för lite.",
        "",
    ]

    # ---- togs väggar med? -----------------------------------------------------------------------------
    hatch_found = [r for r in ok if (prof(r).get("hatch_families") or 0) > 0]
    hatch_m = sum(r.get("in_hatched_area_m") or 0 for r in ok)
    L += [
        "## Väggar: hittades skrafferingen, och hur mycket rör ligger i den?",
        "",
        f"Skraffering hittades på **{len(hatch_found)} av {len(ok)} lästa blad** ({pct(len(hatch_found), len(ok))}),",
        f"och **{num(hatch_m)} m** ritat rör ligger inne i den. De metrarna redovisas för sig och ingår inte i",
        "den vågräta mängden som förval: skrafferingen markerar oftast vägg, befintlig del eller yta utanför",
        "entreprenaden, och en mängdare drar av dem. Kryssrutan i mängdtabellen räknar in dem igen för den som",
        "vill.",
        "",
        "Ett blad utan skraffering är inte med nödvändighet ett fel - alla ritningar skrafferar inte - men ett",
        "blad som ritar väggar utan att de hittas räknar rör i vägg utan att någon ser det. Kolumnen *skraff*",
        "nedan säger vilket som är vilket.",
        "",
    ]

    # ---- tabellen ------------------------------------------------------------------------------------
    L += [
        "## Varje ritning",
        "",
        "*bet* = beteckningar lästa · *fäste* = verifierade av alla följda hänvisningslinjer · *rader* = rader i",
        "mängden · *m* = bekräftad vågrät längd · *täck* = andel ritat rör som bär en identitet · *skraff* =",
        "skrafferingar hittade / meter rör i dem · *facit* = täckning och falskhet mot mängdförteckningen",
        "",
        "| ritning | bet | fäste | rader | m | täck | skala | skraff | facit |",
        "|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for r in rows:
        if r["state"] != "OK":
            L.append(f"| `{r['name']}` | | | | | | **{r['state']}** | | {(r.get('error') or '')[:60]} |")
            continue
        c, p = cov(r), prof(r)
        good, tot = placed(r)
        f = facit.get(r.get("drawing") or "") or facit.get(r["name"].removesuffix(".pdf")) or {}
        fm = f.get("metres") or {}
        fac = (f"{pct(fm['coverage'], 1)} / {pct(fm['false_ownership'], 1)}"
               if fm.get("coverage") is not None else "–")
        nh = p.get("hatch_families") or 0
        hm = r.get("in_hatched_area_m") or 0
        L.append(
            f"| `{r['name']}` | {r.get('designations') or 0} | {good}/{tot} | {r.get('rows') or 0} | "
            f"{num(r.get('confirmed_horizontal_m') or 0)} | {pct(c.get('share') or 0, 1)} | "
            f"{c.get('scale_state') or '–'} | {nh}{f' · {num(hm)} m' if hm else ''} | {fac} |")

    # ---- det som inte gick ----------------------------------------------------------------------------
    if bad:
        errs = collections.Counter((r.get("error") or "").split(":")[0] for r in bad)
        L += ["", f"## {len(bad)} filer som inte gick att läsa", "", "| fel | filer |", "|---|---:|"]
        for k, n in errs.most_common():
            L.append(f"| {k or '–'} | {n} |")
        L += [""]
        for r in bad:
            L.append(f"- `{r['name']}` ({r['classification']}): {(r.get('error') or '')[:160]}")

    # ---- blad utan meter ------------------------------------------------------------------------------
    zero = [r for r in ok if (r.get("confirmed_horizontal_m") or 0) == 0]
    if zero:
        L += ["", f"## {len(zero)} blad som lästes utan att ge en meter", "",
              "Ett blad utan meter är inte med nödvändighet ett fel: en sektionsritning, ett blad i en annan",
              "disciplin eller en handling utan rör ska ge noll. Skälet står i skalan och i hur många",
              "beteckningar bladet skriver - ett blad med hundra beteckningar och noll meter är alltid ett fel.",
              "", "| ritning | bet | fäste | skala | skäl |", "|---|---:|---:|---|---|"]
        for r in sorted(zero, key=lambda r: -(int(r.get("designations") or 0))):
            good, tot = placed(r)
            c = cov(r)
            L.append(f"| `{r['name']}` | {r.get('designations') or 0} | {good}/{tot} | "
                     f"{c.get('scale_state') or '–'} | {c.get('scale_reason') or '–'} |")

    # ---- där mest står oägt --------------------------------------------------------------------------
    unowned = sorted((r for r in ok if (cov(r).get("unowned_m") or 0) > 0),
                     key=lambda r: -(cov(r).get("unowned_m") or 0))[:20]
    if unowned:
        L += ["", "## Tjugo blad med mest ritat rör som ingen beteckning når", "",
              "Oägda meter är läsningens egen redovisning av var den inte räcker till: geometrin är läst, men",
              "ingen etikett pekar på den. Det är den lista man arbetar sig nedför.",
              "", "| ritning | oägt m | ritat m | täck | bet | fäste |", "|---|---:|---:|---:|---:|---:|"]
        for r in unowned:
            c = cov(r)
            good, tot = placed(r)
            L.append(f"| `{r['name']}` | {num(c.get('unowned_m'))} | {num(c.get('drawn_m'))} | "
                     f"{pct(c.get('share') or 0, 1)} | {r.get('designations') or 0} | {good}/{tot} |")

    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(x for x in L if x is not None) + "\n")
    print(out, len(rows), "rader")


if __name__ == "__main__":
    main()
