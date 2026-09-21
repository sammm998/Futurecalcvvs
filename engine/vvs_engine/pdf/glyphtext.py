"""Tecken som läsaren inte kunde tyda.

Ett PDF-typsnitt som bäddats in med `Identity-H` adresserar sina tecken med glyfnummer, och vilket tecken ett
glyfnummer betyder står i typsnittets ToUnicode-tabell. Är den inte utskriven, eller utskriven men ofullständig
- vilket den ofta är i utskrifter från CAD-plottar - kan läsaren inte säga vad som står. På skärmen står det
rätt, för glyferna ritas ändå, men den som läser texten ur filen får ersättningstecken: "Längd(m)" kommer ut
som åtta stycken U+FFFD, och "OBS: Nytt fönster" blir "0BS" och ett styrtecken.

Det finns inget att gissa, och ingen vakt som behöver väga läsbarhet mot läsbarhet:

  * **Vilka tecken som är otydda** säger läsaren själv. U+FFFD betyder "jag vet inte vad det här är". Ett
    tecken som kom ut som en bokstav rörs aldrig, oavsett vilket typsnitt det står i.
  * **Vad glyfen ritar** står i det inbäddade typsnittet. Tabellen byggs baklänges ur det - för varje tecken,
    vilken glyf typsnittet ritar det med - och då går även å, ä och ö tillbaka.

Ett tidigare försök jämförde avkodad text mot rå och behöll den som såg mest läsbar ut. Det gick inte att få
rätt: två typsnitt på samma sida kan heta samma sak, ett trasigt och ett helt, och då blev "Krets" till
"Ircrs" av en tabell det inte hörde till. Ersättningstecknet avgör saken utan att någon behöver väga.

Ett andra försök frågade först om ToUnicode saknades helt, och byggde tabell bara då. Det räckte inte: på åtta
blad fanns tabellen, men två glyfer stod inte i den, och just de två bar ordet "OBS". Villkoret är alltså inte
vad typsnittet lovar utan vad läsningen gav - och därför byggs tabellen först när ett otytt tecken faktiskt
dykt upp ur just det typsnittet. Blad utan otydda tecken - de allra flesta - packar aldrig upp ett typsnitt.

Namnet är den enda tråd som binder ihop textraden med typsnittet den ritades i, och den tråden håller dåligt.
De två vägarna in i filen stavar namnet olika - sidans typsnittslista säger "Nimbus Sans Regular" där
textraden säger "NimbusSans-Regular", och ett utsnitt bär ett slumpat förled som "ABCDEF+" - så namnen jämförs
skalade: förledet bort, bara bokstäver och siffror kvar. Och två olika typsnitt på samma sida kan heta precis
samma sak, så namnet pekar inte alltid ut ett. Då frågas alla som bär namnet, och svaret gäller bara om de är
överens: säger en tabell "L" och en annan "i" om samma glyf, går det inte att veta och tecknet står kvar
otytt. Passar inget namn alls men sidan bär bara ett enda inbäddat typsnitt, är det det tecknet kom ur.
"""

from __future__ import annotations

# Hur långt upp i teckentabellen den omvända glyftabellen byggs. 0x250 täcker latin med tillägg, vilket är allt
# en svensk ritning skriver.
_SCAN_TO = 0x250

# Läsarens eget "jag vet inte vad det här är": U+FFFD, ersättningstecknet.
UNREAD = 0xFFFD


def _norm(name: str) -> str:
    """Typsnittsnamnet skalat: utsnittets förled bort, bara bokstäver och siffror kvar.

    "ABCDEF+Nimbus Sans Regular" och "NimbusSans-Regular" är samma typsnitt och ska mötas.
    """
    n = name or ""
    if len(n) > 7 and n[6] == "+":
        n = n[7:]
    return "".join(c for c in n.lower() if c.isalnum())


def page_fonts(page) -> dict[str, list[int]]:
    """Sidans inbäddade typsnitt: skalat namn till de ställen i filen typsnitt med det namnet ligger på.

    Namnet är inte unikt. Ett blad kan bära två typsnitt som båda heter ArialMT, ett inbäddat och ett som
    bara namnges, och vilket en textrad ritades i säger raden inte.
    """
    out: dict[str, list[int]] = {}
    try:
        fonts = page.get_fonts(full=True)
    except Exception:
        return out
    for f in fonts:
        key = _norm(f[3])
        if key:
            out.setdefault(key, []).append(f[0])
    return out


def _table_from_font(doc, xref: int) -> dict[int, str]:
    """Glyfnummer till tecken, byggt baklänges ur det inbäddade typsnittet."""
    try:
        import pymupdf
        buf = doc.extract_font(xref)[3]
        if not buf:
            return {}
        font = pymupdf.Font(fontbuffer=buf)
    except Exception:
        return {}
    table: dict[int, str] = {}
    for u in range(32, _SCAN_TO):
        try:
            gid = font.has_glyph(u)
        except Exception:
            continue
        if gid and gid not in table:
            table[gid] = chr(u)
    return table


def repairs_for_page(page, doc) -> dict[tuple[float, float], str]:
    """Var på sidan ett otytt tecken står, och vad det ska vara.

    Nyckeln är tecknets ursprungspunkt avrundad till tiondels punkt. rawdict och get_texttrace kommer ur samma
    läsning och ger samma punkter, så uppslaget är exakt - men rawdict bär inga glyfnummer och texttrace bär
    inga rader, och därför behövs båda: den ena säger var tecknen står, den andra vad de föreställer.

    Ett typsnitt packas upp först när ett otytt tecken kommit ur det. Sidor utan sådana tecken - de allra
    flesta - betalar bara för en genomgång av textraderna.
    """
    try:
        trace = page.get_texttrace()
    except Exception:
        return {}
    if not any(c[0] == UNREAD for sp in trace for c in sp.get("chars", ())):
        return {}

    xrefs = page_fonts(page)
    # Finns bara ett inbäddat typsnitt på sidan är det det varje otytt tecken kom ur, vad raden än kallar det.
    lone = next(iter(xrefs.values())) if len(xrefs) == 1 else None
    tables: dict[int, dict[int, str]] = {}
    out: dict[tuple[float, float], str] = {}
    for sp in trace:
        chars = sp.get("chars", ())
        if not any(c[0] == UNREAD for c in chars):
            continue
        kandidater = xrefs.get(_norm(sp.get("font") or "")) or lone
        if not kandidater:
            continue
        for xref in kandidater:
            if xref not in tables:
                tables[xref] = _table_from_font(doc, xref)
        for ch in chars:
            code, gid, origin = ch[0], ch[1], ch[2]
            if code != UNREAD:
                continue
            svar = {tables[x][gid] for x in kandidater if gid in tables[x]}
            if len(svar) == 1:                     # ett enda svar: alla som kan glyfen ritar samma tecken
                out[(round(float(origin[0]), 1), round(float(origin[1]), 1))] = svar.pop()
    return out


def repaired_page_text(page, doc, clip=None, fixes=None) -> str:
    """Sidans text med de otydda tecknen ifyllda. För den som bara vill läsa, inte mäta.

    `fixes` går att skicka med när samma sida läses flera gånger - hela sidan och sedan namnrutan - så att
    typsnitten bara behöver packas upp en gång.
    """
    if fixes is None:
        fixes = repairs_for_page(page, doc)
    if not fixes:
        try:
            return page.get_text("text", clip=clip) if clip is not None else page.get_text("text")
        except Exception:
            return ""
    try:
        raw = page.get_text("rawdict", clip=clip) if clip is not None else page.get_text("rawdict")
    except Exception:
        return ""
    lines: list[str] = []
    for b in raw.get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            buf = []
            for sp in ln.get("spans", []):
                for ch in sp.get("chars", []):
                    org = ch.get("origin") or (0.0, 0.0)
                    key = (round(float(org[0]), 1), round(float(org[1]), 1))
                    buf.append(fixes.get(key, ch["c"]))
            if "".join(buf).strip():
                lines.append("".join(buf))
    return "\n".join(lines)
