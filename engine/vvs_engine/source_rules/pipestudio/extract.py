"""Stage 1 - extract: every vector path and text object with full attributes.

Zero interpretation. The only processing is (a) mapping raw coordinates into
the displayed (de-rotated) page frame so geometry, text and the rendered
background agree, and (b) flagging exact duplicate paths (CAD exports draw
many strokes there-and-back) - flagged, not dropped, so the profile can count
them.
"""
import json
import sys
from dataclasses import dataclass, field, fields, asdict

import pymupdf

from .geom import flatten


@dataclass
class Path:
    id: int
    kind: str                 # "s" stroke, "f" fill, "fs" both
    width: float
    color: list | None        # stroke rgb 0..1
    fill: list | None
    dashes: str
    layer: str
    closed: bool
    rect: list                # x0,y0,x1,y1
    items: list               # ["l",x0,y0,x1,y1] | ["c",8 floats] | ["re"|"qu",8 floats]
    duplicate_of: int | None = None


@dataclass
class Text:
    id: int
    text: str
    bbox: list
    font: str
    size: float
    dir: list                 # writing direction (cos, sin)


@dataclass
class Extraction:
    sheet: str
    page: list                # width, height (displayed)
    rotation: int
    paths: list = field(default_factory=list)
    texts: list = field(default_factory=list)
    page_no: int = 0          # which page of the PDF (booklets carry covers before the plans)


def _pt(p, mat):
    q = p * mat
    return (round(q.x, 3), round(q.y, 3))


def _items(raw_items, mat):
    out = []
    for it in raw_items:
        k = it[0]
        if k == "l":
            a, b = _pt(it[1], mat), _pt(it[2], mat)
            out.append(["l", *a, *b])
        elif k == "c":
            pts = [_pt(p, mat) for p in it[1:5]]
            out.append(["c", *[v for p in pts for v in p]])
        elif k == "re":
            r = it[1]
            pts = [_pt(p, mat) for p in (r.tl, r.tr, r.br, r.bl)]
            out.append(["re", *[v for p in pts for v in p]])
        elif k == "qu":
            q = it[1]
            pts = [_pt(p, mat) for p in (q.ul, q.ur, q.lr, q.ll)]
            out.append(["qu", *[v for p in pts for v in p]])
    return out


def _dup_key(items):
    """Orientation-insensitive identity of a path's flattened geometry."""
    segs = []
    for a, b in flatten(items):
        a = (round(a[0], 2), round(a[1], 2))
        b = (round(b[0], 2), round(b[1], 2))
        segs.append((a, b) if a <= b else (b, a))
    return tuple(sorted(segs))


def extract(pdf_path, page_no=0):
    doc = pymupdf.open(pdf_path)
    page = doc[page_no]
    mat = page.rotation_matrix if page.rotation else pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    ex = Extraction(sheet=page.parent.name.rsplit("/", 1)[-1].rsplit(".", 1)[0],
                    page=[round(page.rect.width, 3), round(page.rect.height, 3)],
                    rotation=page.rotation, page_no=page_no)

    seen = {}
    for i, d in enumerate(page.get_drawings()):
        items = _items(d["items"], mat)
        r = d["rect"] * mat
        p = Path(id=i, kind=d["type"], width=round(d.get("width") or 0.0, 3),
                 color=list(d["color"]) if d.get("color") else None,
                 fill=list(d["fill"]) if d.get("fill") else None,
                 dashes=d.get("dashes") or "", layer=d.get("layer") or "",
                 closed=bool(d.get("closePath")),
                 rect=[round(v, 3) for v in (r.x0, r.y0, r.x1, r.y1)], items=items)
        key = (p.kind, p.width, p.dashes, _dup_key(items))
        if key in seen:
            p.duplicate_of = seen[key]
        else:
            seen[key] = i
        ex.paths.append(p)

    raw = page.get_text("rawdict")
    tid = 0
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                s = "".join(ch["c"] for ch in span.get("chars", []))
                if not s.strip():
                    continue
                bb = pymupdf.Rect(span["bbox"]) * mat
                ex.texts.append(Text(id=tid, text=s, bbox=[round(v, 3) for v in bb],
                                     font=span.get("font", ""), size=round(span.get("size", 0), 2),
                                     dir=list(line.get("dir", (1, 0)))))
                tid += 1
    return ex


def save(ex, out_path):
    with open(out_path, "w") as f:
        json.dump(asdict(ex), f)


def load(path):
    with open(path) as f:
        d = json.load(f)
    d["paths"] = [Path(**p) for p in d["paths"]]
    d["texts"] = [Text(**t) for t in d["texts"]]
    # a file written by a newer version may carry fields this one does not know
    known = {f.name for f in fields(Extraction)}
    return Extraction(**{k: v for k, v in d.items() if k in known})


if __name__ == "__main__":
    import os
    for pdf in sys.argv[1:]:
        ex = extract(pdf)
        out_dir = os.path.join("debug", ex.sheet)
        os.makedirs(out_dir, exist_ok=True)
        save(ex, os.path.join(out_dir, "01_extract.json"))
        dups = sum(1 for p in ex.paths if p.duplicate_of is not None)
        print(f"{ex.sheet}: page {ex.page[0]:.0f}x{ex.page[1]:.0f} rot={ex.rotation} "
              f"paths={len(ex.paths)} (dup {dups}) texts={len(ex.texts)}")
