"""Vad en handling är, läst ur bladet självt.

En mängdning läser en ritning. En projektanalys läser en HANDLING: hundratals blad som tillsammans är ett
byggprojekt, och frågan är vad var och ett av dem är. Vilket hus, vilken disciplin, vilket plan, vilken
version, och vilket blad det hör ihop med.

Det här är den läsningen, och den är med flit billig. Att köra hela mängdningen på trehundra blad för att få
veta vad de heter tar timmar; att läsa deras text tar sekunder. Så här läses bara text - ingen geometri, inga
hänvisningslinjer, inga rör - och resultatet är vad bladet SÄGER om sig självt.

VAD SOM ALDRIG HITTAS PÅ

Ett filnamn är inte en revision. `Hus A (1).pdf` och `Hus A (2).pdf` säger ingenting om vad som kom först;
det är vad en webbläsare gör när man laddar ned samma fil två gånger. Ett före/efter-förhållande får bara
påstås när handlingarna själva bär det: samma ritningsnummer, samma hus, samma disciplin, och en
revisionsbeteckning eller ett datum som skiljer dem åt.

Två handlingar från samma dag med samma status är inte ett revisionspar. En arkitektritning och en
VVS-ritning, båda relationshandling 2025-05-14, är två discipliner i samma projektskede - och att kalla dem
före och efter vore att uppfinna en historia projektet inte har.

Där det inte går att avgöra säkert står det att det inte går att avgöra säkert.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass, field
from typing import Any

import pymupdf

# ---------------------------------------------------------------------------------------------------------
# Ordförrådet: svensk byggpraxis, inte något visst projekts
# ---------------------------------------------------------------------------------------------------------

# Disciplinbokstaven först i ritningsnumret. Projektets egen förteckning gäller alltid före den här listan;
# den finns för de blad som inte har någon förteckning att gå efter.
DISCIPLINES = {
    "A": "Arkitekt", "K": "Konstruktion", "V": "VVS", "W": "VVS", "R": "Rör", "L": "Luftbehandling",
    "E": "El", "T": "Tele", "S": "Styr", "M": "Mark", "G": "Geoteknik", "B": "Brand", "H": "Hiss",
    "P": "Process", "I": "Inredning", "N": "Landskap",
}

# Handlingens skede. Ordningen i listan är projektets ordning i tiden, och det är den enda ordning som
# används där datum saknas - aldrig filnamn, aldrig uppladdningsordning.
STAGES = [
    ("FÖRSTUDIE", 0), ("PROGRAMHANDLING", 1), ("SYSTEMHANDLING", 2), ("FÖRFRÅGNINGSUNDERLAG", 3),
    ("FU", 3), ("BYGGLOVSHANDLING", 4), ("GRANSKNINGSHANDLING", 5), ("BYGGHANDLING", 6),
    ("PRODUKTIONSHANDLING", 6), ("RELATIONSHANDLING", 9), ("RELATIONSRITNING", 9),
]

# Vad ett blad kan vara för sorts ritning, läst ur ritningsnamnet.
KINDS = [
    ("PLAN", "Plan"), ("SEKTION", "Sektion"), ("FASAD", "Fasad"), ("TAKPLAN", "Takplan"),
    ("SITUATIONSPLAN", "Situationsplan"), ("UPPSTÄLLNING", "Uppställning"), ("SCHEMA", "Schema"),
    ("FLÖDESSCHEMA", "Flödesschema"), ("PRINCIP", "Principritning"), ("DETALJ", "Detalj"),
    ("RIVNING", "Rivning"), ("STAMSCHEMA", "Stamschema"), ("ÖVERSIKT", "Översikt"),
]

_DATE = re.compile(r"\b(20\d{2})[-–./](\d{1,2})[-–./](\d{1,2})\b")
_REV_WORD = re.compile(r"\bREV(?:ISION)?\.?\s*([A-ZÅÄÖ]{1,2}|\d{1,2})\b", re.I)
_HUS = re.compile(r"\bHUS\s+([A-ZÅÄÖ0-9]{1,3})\b", re.I)
_PLAN = re.compile(r"\bPLAN\s+([A-ZÅÄÖ]?\d{1,2})\b", re.I)
_DEL = re.compile(r"\bDEL\s+(\d{1,3})\b", re.I)
_SCALE = re.compile(r"\b1\s*[:：]\s*(\d{1,4})\b")

# Ett svenskt ritningsnummer: disciplinbokstav, innehållsgrupp, vy, och en del som pekar ut hus, plan och
# delruta. Skrivsätten varierar mellan kontor, så numret plockas isär så långt det går och inte längre.
# Ett svenskt ritningsnummer skrivs i minst tre led: disciplinbokstav, innehållsgrupp, och därefter vy, hus
# och delruta i de kombinationer kontoret använder. Tre led krävs med flit - `S13-12` är en rörbeteckning på
# ritningen och inte ett ritningsnummer, och två led skiljer dem inte åt.
_NUMBER = re.compile(
    r"\b([A-ZÅÄÖ])[-\s]"                       # disciplin
    r"(\d{2}(?:\.\d)?)[-\s]"                   # innehållsgrupp, ibland med decimal
    r"(?:(\d)[-\s])?"                          # vy: plan, sektion, uppställning
    r"(?:([A-ZÅÄÖ])[-\s]?)?"                   # hus
    r"(\d{2,4})\b", re.I)                      # plan och del


@dataclass
class Field:
    """Ett värde och var det kom ifrån. Utan källan är värdet ett påstående ingen kan pröva."""
    value: Any = None
    source: str = ""          # den textrad värdet lästes ur
    where: str = ""           # namnruta | ritningsnummer | filnamn
    confidence: float = 0.0

    def as_dict(self):
        return {"value": self.value, "source": self.source[:120], "where": self.where,
                "confidence": round(self.confidence, 2)}


@dataclass
class Handling:
    """Ett blad, så som det beskriver sig självt."""
    path: str
    filename: str
    page: int = 0
    n_pages: int = 1
    number: Field = field(default_factory=Field)
    discipline: Field = field(default_factory=Field)
    building: Field = field(default_factory=Field)
    floor: Field = field(default_factory=Field)
    part: Field = field(default_factory=Field)
    title: Field = field(default_factory=Field)
    kind: Field = field(default_factory=Field)
    status: Field = field(default_factory=Field)
    stage_order: int | None = None
    revision: Field = field(default_factory=Field)
    revision_date: Field = field(default_factory=Field)
    document_date: Field = field(default_factory=Field)
    project: Field = field(default_factory=Field)
    scale: Field = field(default_factory=Field)
    read_error: str = ""

    @property
    def key(self) -> str:
        """Det som gör två blad till samma ritning i olika versioner.

        Numret om det finns, annars hus + disciplin + plan + del. Filnamnet ingår aldrig: två filer med samma
        innehåll och olika namn är samma ritning, och två filer med samma namn i olika mappar behöver inte vara
        det.
        """
        if self.number.value:
            return str(self.number.value).upper()
        bits = [str(self.discipline.value or "?"), str(self.building.value or "?"),
                str(self.floor.value or "?"), str(self.part.value or "?")]
        return "/".join(bits)

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "filename": self.filename, "page": self.page, "n_pages": self.n_pages,
                "key": self.key, "stage_order": self.stage_order, "read_error": self.read_error,
                **{k: getattr(self, k).as_dict() for k in
                   ("number", "discipline", "building", "floor", "part", "title", "kind", "status",
                    "revision", "revision_date", "document_date", "project", "scale")}}


def _rows(page) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Bladets textrader med sina rutor, i läsordning."""
    out = []
    for blk in page.get_text("dict").get("blocks", []):
        for ln in blk.get("lines", []):
            txt = "".join(sp.get("text", "") for sp in ln.get("spans", [])).strip()
            if txt:
                bb = ln.get("bbox") or blk.get("bbox")
                out.append((txt, tuple(bb)))
    return out


def _title_block(rows, w: float, h: float) -> list[tuple[str, tuple]]:
    """Namnrutan: den nedre högra fjärdedelen, där svenska ritningar bär sin beskrivning.

    Rutan är inte alltid där - liggande A1 har den i högerkanten, ett stående blad längst ned - så det som
    returneras är ett urval att leta i först, inte ett påstående om var rutan sitter. Hittas inget där läses
    hela bladet.
    """
    near = [(t, b) for t, b in rows if b[0] > 0.55 * w and b[1] > 0.55 * h]
    return near or rows


def _find_date(texts: list[str]) -> tuple[str | None, str]:
    for t in texts:
        m = _DATE.search(t)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return dt.date(y, mo, d).isoformat(), t
            except ValueError:
                continue
    return None, ""


def _find_stage(texts: list[str]) -> tuple[str | None, int | None, str]:
    """Skedet, och var i projektets ordning det ligger.

    Längsta träffen vinner: "RELATIONSHANDLING" innehåller inte "BYGGHANDLING", men ett blad kan bära båda -
    "bygghandling" i en stämpel och "relationshandling" i statusfältet - och då är det den senare som gäller.
    """
    best = None
    for t in texts:
        up = t.upper()
        for word, order in STAGES:
            if word in up and (best is None or order > best[1] or (order == best[1] and len(word) > len(best[0]))):
                best = (word, order, t)
    return (best[0], best[1], best[2]) if best else (None, None, "")


def _find_number(block: list[str], sheet: list[str], filename: str) -> tuple[str | None, dict, str, str]:
    """Ritningsnumret: bladets eget, inte det första nummerliknande som råkar stå någonstans på det.

    Ett blad bär andra ritningars nummer också - hänvisningar till sektioner, till angränsande delritningar,
    till en konstruktionsritning i en not. Läst rakt av blev en VVS-ritning en konstruktionsritning för att den
    hänvisade till en. Och en rörbeteckning som `S13-12` ser ut som ett nummer om man bara kräver två led.

    Det starkaste beviset är att bladet och filen säger samma sak: ett kontor döper filen efter ritningen, så
    ett nummer som står både i namnrutan och i filnamnet är bladets eget. Därnäst namnrutan ensam, och sist
    filnamnet ensam - för ett filnamn är vad någon döpte nedladdningen till.
    """
    def cands(pool, where):
        out = []
        for t in pool:
            for m in _NUMBER.finditer(t):
                disc, grp, view, house, tail = m.groups()
                parts = {"discipline": disc.upper(), "group": grp, "view": view,
                         "building": house.upper() if house else None}
                if tail and len(tail) == 4:
                    parts["floor"], parts["part"] = tail[:2], tail[2:]
                elif tail:
                    parts["floor"] = tail
                n_parts = sum(1 for x in (view, house) if x) + 2
                out.append((m.group(0).upper().replace(" ", "-"), parts, where, t, n_parts))
        return out

    from_name = cands([os.path.splitext(filename)[0]], "filnamn")
    from_block = cands(block, "ritningsnummer")
    from_sheet = cands(sheet, "ritningsnummer")
    name_set = {c[0] for c in from_name}

    both = [c for c in from_block + from_sheet if c[0] in name_set]
    if both:
        best = max(both, key=lambda c: c[4])
        return best[0], best[1], "namnruta och filnamn", best[3]
    if from_block:
        best = max(from_block, key=lambda c: c[4])
        return best[0], best[1], best[2], best[3]
    if from_name:
        best = max(from_name, key=lambda c: c[4])
        return best[0], best[1], best[2], best[3]
    return None, {}, "", ""


def read_handling(path: str, page: int = 0) -> Handling:
    """Vad ett blad säger om sig självt. Bara text - snabbt nog för hundratals blad."""
    h = Handling(path=path, filename=os.path.basename(path), page=page)
    try:
        doc = pymupdf.open(path)
        h.n_pages = len(doc)
        pg = doc[min(page, len(doc) - 1)]
        rows = _rows(pg)
        w, hh = pg.rect.width, pg.rect.height
        doc.close()
    except Exception as e:                                  # noqa: BLE001
        h.read_error = f"{type(e).__name__}: {e}"[:120]
        return h

    block = _title_block(rows, w, hh)
    btexts = [t for t, _ in block]
    atexts = [t for t, _ in rows]

    num, parts, where, src = _find_number(btexts, atexts, h.filename)
    if num:
        h.number = Field(num, src, where,
                         0.95 if where == "namnruta och filnamn" else 0.7 if where == "ritningsnummer" else 0.5)
        if parts.get("discipline"):
            d = parts["discipline"]
            h.discipline = Field(DISCIPLINES.get(d, d), src, where, 0.8 if d in DISCIPLINES else 0.4)
        for k in ("building", "floor", "part"):
            if parts.get(k):
                setattr(h, k, Field(parts[k], src, where, 0.6))

    for rx, fld in ((_PLAN, "floor"), (_DEL, "part")):
        for t in btexts:
            m = rx.search(t)
            if m:
                setattr(h, fld, Field(m.group(1).upper(), t, "namnruta", 0.85))
                break

    stage, order, ssrc = _find_stage(btexts + atexts)
    if stage:
        h.status = Field(stage, ssrc, "namnruta", 0.9)
        h.stage_order = order

    for t in btexts + atexts:
        m = _REV_WORD.search(t)
        if m:
            h.revision = Field(m.group(1).upper(), t, "namnruta", 0.8)
            break

    d, src = _find_date(btexts)
    if d:
        h.document_date = Field(d, src, "namnruta", 0.8)
    rd, rsrc = _find_date([t for t in btexts if _REV_WORD.search(t)])
    if rd:
        h.revision_date = Field(rd, rsrc, "namnruta", 0.8)

    for t in btexts:
        m = _SCALE.search(t)
        if m:
            h.scale = Field(f"1:{m.group(1)}", t, "namnruta", 0.9)
            break

    # Ritningsnamnet. Den längsta raden i namnrutan är sällan det: namnrutan bär också konsultens namn,
    # adress och telefonnummer, och de raderna är långa. Så en rad med ett långt siffertåg i är ett
    # telefonnummer eller ett organisationsnummer och inte ett ritningsnamn, och en rad som säger vad bladet
    # visar - plan, sektion, rivning - går före en som bara är lång.
    cand = [t for t in btexts if 6 < len(t) < 90 and not _DATE.search(t) and not _SCALE.search(t)
            and not re.search(r"\d{5,}", t)
            and not (h.number.value and h.number.value in t.upper().replace(" ", "-"))]
    named = [t for t in cand if any(w in t.upper() for w in (k[0] for k in KINDS))]
    if named or cand:
        best = max(named or cand, key=len)
        h.title = Field(best[:120], best, "namnruta", 0.7 if named else 0.4)
        for word, name in KINDS:
            if word in best.upper():
                h.kind = Field(name, best, "namnruta", 0.75)
                break
    if not h.kind.value:
        for word, name in KINDS:
            if word in h.filename.upper():
                h.kind = Field(name, h.filename, "filnamn", 0.5)
                break

    # Huset skrivet i klartext går före huset läst ur numret: "HUS B" är projektets eget ord för det.
    # Ritningsnamnet först av allt, för det är den rad som beskriver DET HÄR bladet - en översiktsritning bär
    # gärna grannhusets bokstav också, i en hänvisning, och den raden handlar inte om bladet.
    for pool, conf in ((([h.title.value] if h.title.value else []), 0.95), (btexts, 0.8)):
        hit = next((m for t in pool for m in [_HUS.search(t or "")] if m), None)
        if hit:
            h.building = Field(hit.group(1).upper(), hit.group(0), "ritningsnamn" if conf > 0.9 else "namnruta", conf)
            break
    return h


# ---------------------------------------------------------------------------------------------------------
# Att para ihop versioner utan att hitta på dem
# ---------------------------------------------------------------------------------------------------------

def _rev_rank(rev: str | None) -> int | None:
    """Var en revisionsbeteckning ligger i ordningen. A före B, 1 före 2, och inget före A."""
    if not rev:
        return None
    r = rev.strip().upper()
    if r.isdigit():
        return int(r)
    if len(r) == 1 and r.isalpha():
        return ord(r) - ord("A") + 1
    if len(r) == 2 and r.isalpha():
        return (ord(r[0]) - ord("A") + 1) * 26 + (ord(r[1]) - ord("A") + 1)
    return None


def _newer(a: Handling, b: Handling) -> int:
    """Vilken av två handlingar som är senare: -1 om a, 1 om b, 0 om det inte går att säga.

    Prövas i den ordning bevisen är starka: revisionsbeteckningen är projektets eget ord för ordningen,
    därefter revisionsdatumet, därefter handlingens datum, och sist skedet. Säger inget av dem något säger
    funktionen ingenting - och då finns inget par.
    """
    ra, rb = _rev_rank(a.revision.value), _rev_rank(b.revision.value)
    if ra is not None and rb is not None and ra != rb:
        return -1 if ra > rb else 1
    for fld in ("revision_date", "document_date"):
        da, db = getattr(a, fld).value, getattr(b, fld).value
        if da and db and da != db:
            return -1 if da > db else 1
    if a.stage_order is not None and b.stage_order is not None and a.stage_order != b.stage_order:
        return -1 if a.stage_order > b.stage_order else 1
    return 0


@dataclass
class Pair:
    """Två blad av samma ritning i olika version, och varför de anses vara det."""
    key: str
    before: Handling
    after: Handling
    why: list[str]
    confidence: float

    def as_dict(self):
        return {"key": self.key, "before": self.before.as_dict(), "after": self.after.as_dict(),
                "why": self.why, "confidence": round(self.confidence, 2)}


@dataclass
class NotAPair:
    """Två blad som liknar ett par men inte är det, och vad de är i stället."""
    key: str
    docs: list[Handling]
    reading: str
    why: str

    def as_dict(self):
        return {"key": self.key, "docs": [d.as_dict() for d in self.docs], "reading": self.reading, "why": self.why}


def pair_versions(docs: list[Handling]) -> tuple[list[Pair], list[NotAPair]]:
    """Vilka blad som är samma ritning i två versioner, och vilka som bara ser ut så.

    Kravet är hårt med flit. Samma ritningsnummer räcker inte: numret måste finnas, disciplinen och huset måste
    stämma, och något av handlingarna själva måste säga vilken som kom först. Två relationshandlingar från
    samma dag på var sin disciplin är inte ett par - de är två discipliner i samma skede, och det är vad som
    står i svaret i stället för ett påhittat före och efter.
    """
    by_key: dict[str, list[Handling]] = {}
    for d in docs:
        if d.read_error:
            continue
        by_key.setdefault(d.key, []).append(d)

    pairs: list[Pair] = []
    unclear: list[NotAPair] = []
    for key, group in sorted(by_key.items()):
        if len(group) < 2:
            continue
        discs = {str(d.discipline.value or "?") for d in group}
        if len(discs) > 1:
            unclear.append(NotAPair(key, group, "parallella discipliner",
                                    "Bladen har samma beteckning men olika disciplin. Det är inte två versioner "
                                    "av en ritning utan flera discipliner som redovisar samma område."))
            continue
        group = sorted(group, key=lambda d: (d.filename, d.page))
        settled, undecided = [], []
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                cmpv = _newer(a, b)
                if cmpv == 0:
                    undecided.append((a, b))
                    continue
                before, after = (b, a) if cmpv < 0 else (a, b)
                why, conf = [], 0.0
                if _rev_rank(before.revision.value) is not None and _rev_rank(after.revision.value) is not None:
                    why.append(f"revision {before.revision.value} före {after.revision.value}")
                    conf = max(conf, 0.9)
                for fld, name in (("revision_date", "revisionsdatum"), ("document_date", "datum")):
                    x, y = getattr(before, fld).value, getattr(after, fld).value
                    if x and y and x != y:
                        why.append(f"{name} {x} före {y}")
                        conf = max(conf, 0.8)
                if before.stage_order is not None and after.stage_order is not None \
                        and before.stage_order != after.stage_order:
                    why.append(f"{before.status.value} före {after.status.value}")
                    conf = max(conf, 0.7)
                if before.number.value and after.number.value:
                    conf = min(1.0, conf + 0.05)
                settled.append(Pair(key, before, after, why, conf))
        pairs.extend(settled)
        if undecided and not settled:
            a, b = undecided[0]
            same_day = a.document_date.value and a.document_date.value == b.document_date.value
            unclear.append(NotAPair(
                key, group,
                "samma projektskede" if same_day else "går inte att ordna",
                "Bladen bär samma beteckning men ingenting i dem säger vilket som kom först: ingen revision, "
                + ("samma datum och samma status. De verkar vara samma skede, inte före och efter."
                   if same_day else "inget skiljande datum och inget skiljande skede.")))
    return pairs, unclear


def as_report(docs: list[Handling]) -> dict[str, Any]:
    """Handlingsförteckningen, versionsparen, och det som inte gick att avgöra."""
    pairs, unclear = pair_versions(docs)
    tree: dict[str, dict[str, list[dict]]] = {}
    for d in docs:
        b = str(d.building.value or "Okänt hus")
        disc = str(d.discipline.value or "Okänd disciplin")
        tree.setdefault(b, {}).setdefault(disc, []).append(d.as_dict())
    for b in tree:
        for disc in tree[b]:
            tree[b][disc].sort(key=lambda r: (r["key"], r["filename"]))
    dupes = {}
    for d in docs:
        dupes.setdefault(d.key, []).append(d.filename)
    return {
        "documents": [d.as_dict() for d in docs],
        "tree": tree,
        "buildings": sorted(tree),
        "disciplines": sorted({disc for b in tree.values() for disc in b}),
        "pairs": [p.as_dict() for p in pairs],
        "unclear": [u.as_dict() for u in unclear],
        "duplicates": {k: v for k, v in dupes.items() if len(v) > 1},
        "unreadable": [d.filename for d in docs if d.read_error],
        "totals": {"documents": len(docs), "buildings": len(tree),
                   "disciplines": len({disc for b in tree.values() for disc in b}),
                   "pairs": len(pairs), "unclear": len(unclear)},
    }
