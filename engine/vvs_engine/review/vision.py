"""Looking at the drawing, after having read it - to find what the reading missed, never to measure.

The vector reading is the geometry. It knows where every line is, to the point, because it took them out of the
PDF. What it cannot do is notice that a whole family of pipe was never accepted, or that the overlay it drew
runs along a wall instead of a pipe. A person spots that in a second by looking.

So this renders the page and the reading's own overlay, and asks a model what it sees. The discipline is one
sentence, and it is enforced by what this module returns: **findings, never measurements**. Nothing here
produces a coordinate, a length, a designation or a pipe. Everything it returns is a question for the vector
code to answer - "there seems to be pipe here that nothing measured" is a place to go and look for a real vector
family, not a licence to draw one from pixels.

That is why the return type is a list of Finding and there is no apply(). A vision finding cannot move a metre
because there is no path from here to a metre. It reaches the reader, as an unresolved case, and the fix is
always made in the vector code afterwards.

And it does not stop at the observation. The page is shown in named tiles, and a finding must name one of them -
a tile the caller drew, never a coordinate the model invented, which is the same fence the second reader works
behind. Every named tile is then handed to `region.explain_region`, which accounts for the ink there out of the
vectors alone: which stroke family it belongs to, what the reading made of it, which labels sit there and
whether their leaders reached anything, and the reason there are no metres. The eye says where to look. The
vectors say why. Only the second of those two is ever an answer.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Any, Callable

# what the eye is asked, in the order a reader would ask it
QUESTIONS = [
    ("missed_labels", "Syns det VVS-beteckningar på ritningen som INTE finns i listan över lästa beteckningar?"),
    ("missed_pipes", "Syns det ritade rörledningar som ingen färgad överläggning följer?"),
    ("overlay_wrong", "Följer någon färgad överläggning något annat än ett rör - en vägg, en möbel, en måttlinje?"),
    ("paired_wall", "Finns det ställen där två parallella linjer är ett ritat föremål snarare än två rör?"),
]


@dataclass
class Finding:
    kind: str
    detail: str
    where: str = ""                 # in the model's own words; never turned into a coordinate
    tile: str = ""                  # one of the tiles the caller drew on the page, or empty
    bbox: list[float] | None = None  # that tile's rectangle - the caller's, never the model's
    account: dict[str, Any] | None = None   # what the vectors say about that tile
    source: str = "vision_second_opinion"

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail[:400], "where": self.where[:120],
                "tile": self.tile, "bbox": self.bbox, "vector_account": self.account,
                "source": self.source,
                "note": "observation located to a tile the caller drew; the reason beside it is read from the "
                        "vectors, never from the picture"}


@dataclass
class VisionReview:
    asked: bool = False
    findings: list[Finding] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"asked": self.asked, "n_findings": len(self.findings), "note": self.note,
                "findings": [f.as_dict() for f in self.findings],
                "contract": "vision reports what the vector reading may have missed; it never creates geometry"}


TILE_COLS, TILE_ROWS = 6, 4


def tiles(width: float, height: float, cols: int = TILE_COLS, rows: int = TILE_ROWS) -> list[tuple[str, list[float]]]:
    """The page cut into named rectangles. The names are the only places a finding may be put.

    A model asked for a coordinate will produce one, and it will be plausible and sometimes wrong. Asked to name
    one of twenty-four rectangles that were drawn on the picture it was shown, it can only be right or refuse -
    and a rectangle is enough to go and read the vectors there, which is all the location is for.
    """
    out: list[tuple[str, list[float]]] = []
    for r in range(rows):
        for c in range(cols):
            out.append((f"{chr(ord('A') + r)}{c + 1}",
                        [width * c / cols, height * r / rows, width * (c + 1) / cols, height * (r + 1) / rows]))
    return out


def grid_png(png: bytes, tl: list[tuple[str, list[float]]], dpi: int = 110) -> bytes:
    """The same view with the tiles drawn and named, so the eye and the vectors mean the same place."""
    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(png)).convert("RGB")
    d = ImageDraw.Draw(im)
    k = dpi / 72.0
    for name, b in tl:
        x0, y0, x1, y1 = (v * k for v in b)
        d.rectangle([x0, y0, x1, y1], outline=(0, 140, 220), width=2)
        d.text((x0 + 6, y0 + 4), name, fill=(0, 140, 220))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def render_page_png(page_doc, page_index: int, dpi: int = 110, clip=None) -> bytes:
    """The page as the eye would see it. Used for looking, never for measuring."""
    import pymupdf
    pg = page_doc[page_index]
    m = pymupdf.Matrix(dpi / 72.0, dpi / 72.0)
    pix = pg.get_pixmap(matrix=m, clip=clip)
    return pix.tobytes("png")


def overlay_png(png: bytes, runs: list[list[list[float]]], dpi: int = 110, colour=(220, 30, 30)) -> bytes:
    """The same view with the reading's own confirmed runs drawn over it, so the two can be compared."""
    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(png)).convert("RGB")
    d = ImageDraw.Draw(im)
    k = dpi / 72.0
    for poly in runs:
        pts = [(p[0] * k, p[1] * k) for p in poly]
        if len(pts) >= 2:
            d.line(pts, fill=colour, width=3)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def compose(pa, max_labels: int = 120) -> str:
    """What the reading claims, in words, so the eye is checking a stated answer rather than free-associating."""
    lg = pa.legend
    des = sorted({(d.display_text or d.text or "").strip() for d in pa.designations if (d.text or "").strip()})
    measured = sorted({q["designation"] for q in pa.quantities if q.get("confirmed_total_m", 0) > 0})
    return "\n".join([
        f"Läsningen hittade {len(des)} textbeteckningar och mätte {len(measured)} av dem.",
        f"Ritningens egen beteckningslista: {'hittad, ' + str(len(lg.entries)) + ' poster' if lg.entries else 'hittades inte'}.",
        f"Rörfamiljer som accepterades: {len(pa.pipe_families)}.",
        "",
        "Beteckningar som mättes:",
        ", ".join(measured[:max_labels]) or "(inga)",
        "",
        "Beteckningar som lästes men inte mättes:",
        ", ".join([d for d in des if d not in measured][:max_labels]) or "(inga)",
    ])


def look(pa, page_doc, ask: Callable[[str, list[bytes]], str] | None = None, dpi: int = 110) -> VisionReview:
    """Ask the eye about a page that has already been read. Without a transport, nothing is asked."""
    if ask is None:
        return VisionReview(asked=False, note="ingen vision-transport angiven; läsningen står på sin egen geometri")
    try:
        base = render_page_png(page_doc, pa.page.info.index, dpi=dpi)
        runs = [poly for p in (pa.ownership.pipes if pa.ownership else []) for poly in p.points]
        tl = tiles(pa.page.info.width, pa.page.info.height)
        shots = [grid_png(base, tl, dpi=dpi), grid_png(overlay_png(base, runs, dpi=dpi), tl, dpi=dpi)]
    except Exception as e:
        return VisionReview(asked=False, note=f"kunde inte rendera sidan: {type(e).__name__}")

    names = [n for n, _ in tl]
    prompt = "\n".join([
        "Du ser samma VVS-ritning två gånger: först som den är, sedan med den automatiska läsningens rör",
        "utritade i rött ovanpå. Båda bilderna har ett blått rutnät med rutnamn i varje rutas övre vänstra hörn.",
        "Läsningen påstår följande:",
        "",
        compose(pa),
        "",
        "Svara på var och en av frågorna nedan. Svara med en rad per iakttagelse, i formen",
        "  NYCKEL | vad du ser | RUTA",
        "där RUTA är exakt ett av rutnamnen nedan. Skriv INGET för en fråga där du inte ser något.",
        "Hitta inte på koordinater, längder eller beteckningar, och hitta inte på ett rutnamn som inte står i",
        "listan - det svaret kastas.",
        "",
        "rutnamn: " + " ".join(names),
        "",
    ] + [f"{k}: {q}" for k, q in QUESTIONS])

    try:
        raw = ask(prompt, shots)
    except Exception as e:
        return VisionReview(asked=False, note=f"vision kunde inte nås: {type(e).__name__}")

    found = parse(raw, tl)
    # The eye said where to look. From here on nothing it wrote is consulted again: every tile it named is read
    # out of the vectors, and that reading is what the finding carries beside it.
    from .region import explain_region
    seen: dict[str, dict] = {}
    for f in found:
        if not f.tile:
            continue
        if f.tile not in seen:
            try:
                seen[f.tile] = explain_region(pa, f.bbox, pa.page.info.index)
            except Exception as e:                              # noqa: BLE001
                seen[f.tile] = {"error": f"kunde inte läsa vektorerna i rutan: {type(e).__name__}"}
        f.account = seen[f.tile]
    return VisionReview(asked=True, findings=found,
                        note="andra åsikt; platsen är en ruta som läsningen ritade, och skälet läses ur vektorerna")


def parse(raw: str, tl: list[tuple[str, list[float]]] | None = None) -> list[Finding]:
    """Lines the eye wrote, kept only where they name one of the questions - and one of the tiles.

    A tile that is not on the list is dropped rather than guessed at, exactly as a candidate that is not on the
    second reader's list is refused. The observation survives without a place; it simply cannot be looked up.
    """
    keys = {k for k, _ in QUESTIONS}
    boxes = {n.upper(): b for n, b in (tl or [])}
    out: list[Finding] = []
    for line in (raw or "").splitlines():
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        kind = parts[0].strip().lower().strip("-* ").split()[0] if parts[0].strip() else ""
        if kind not in keys or len(parts) < 2 or not parts[1]:
            continue
        where = parts[2] if len(parts) > 2 else ""
        tile = ""
        for tok in where.replace(",", " ").split():
            t = tok.strip(".;:()[]").upper()
            if t in boxes:
                tile = t
                break
        out.append(Finding(kind=kind, detail=parts[1], where=where, tile=tile,
                           bbox=boxes.get(tile) if tile else None))
    return out
