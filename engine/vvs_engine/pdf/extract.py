"""Raw PDF forensics: one extraction pass per page.

Everything derived later stays traceable to RawPath.pid / TextSpan.tid (content hashes)
and to the PDF drawing sequence number (`seqno`) which is stored for provenance ONLY —
it never participates in any semantic decision.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from ..geometry.core import Seg, bbox_union, flatten_bezier, stable_id

from .. import rules as _rules
from .glyphtext import repairs_for_page


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


ANNOTATION_INK_IS_REVIEW = True   # en annotation är någons påskrift, inte det ritaren ritade


@dataclass
class RawPath:
    pid: str
    seqno: int
    page: int
    layer: str
    layer_id: int
    kind: str  # 's' stroke, 'f' fill, 'fs' fill+stroke
    width: float
    color: tuple | None
    fill: tuple | None
    closed: bool
    segs: list[Seg]
    bbox: tuple[float, float, float, float]
    n_items: int
    n_curves: int
    n_subpaths: int
    xobject: str | None = None
    dashes: str = ""
    stroke_opacity: float = 1.0
    fill_opacity: float = 1.0
    source_length_pt: float | None = None
    visible_intervals: list = field(default_factory=list)

    @property
    def length(self) -> float:
        return sum(s.length for s in self.segs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid, "seqno": self.seqno, "page": self.page, "layer": self.layer,
            "kind": self.kind, "width": round(self.width, 3), "color": self.color, "fill": self.fill,
            "closed": self.closed, "n_segments": len(self.segs), "n_items": self.n_items,
            "n_curves": self.n_curves, "n_subpaths": self.n_subpaths,
            "bbox": [round(v, 2) for v in self.bbox], "length": round(self.length, 2),
            "dashes": self.dashes, "stroke_opacity": self.stroke_opacity,
            "fill_opacity": self.fill_opacity, "source_length_pt": self.source_length_pt,
            "visible_intervals": self.visible_intervals,
        }


@dataclass
class TextChar:
    c: str
    bbox: tuple[float, float, float, float]
    origin: tuple[float, float]


@dataclass
class TextSpan:
    tid: str
    seqno: int
    page: int
    text: str
    bbox: tuple[float, float, float, float]
    dir: tuple[float, float]
    font: str
    size: float
    chars: list[TextChar]
    layer: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"tid": self.tid, "page": self.page, "text": self.text, "bbox": [round(v, 2) for v in self.bbox],
                "dir": [round(self.dir[0], 3), round(self.dir[1], 3)], "font": self.font, "size": round(self.size, 2),
                "n_chars": len(self.chars)}


@dataclass
class PageInfo:
    index: int
    width: float
    height: float
    rotation: int
    mediabox: list[float]
    cropbox: list[float]
    n_images: int
    n_annots: int
    n_xobjects: int
    xobjects: list[dict]
    fonts: list[dict]
    annots: list[dict]
    markup_set_aside: dict | None = None   # påskrift som lades åt sidan: hur mycket och av vilket slag


@dataclass
class RawPage:
    info: PageInfo
    paths: list[RawPath]
    spans: list[TextSpan]
    input_class: dict | None = None            # how the page was classified before it was accepted
    source_path: str | None = None             # the PDF this page came from (the review layer re-renders it)
    embedded_fonts: tuple = ()                 # (name, buffer) of the typefaces the page embeds
    visibility_report: dict = field(default_factory=dict)


class LazyPages(Sequence):
    """The document's readable pages, each built the first time it is asked for.

    It is a list to everything that uses it - length, indexing, iteration - and the one thing it adds is
    `release`, which hands a page back once the reading is finished with it. A reading that walks a set from
    front to back then holds one page at a time instead of all of them.

    The marks a page carried were inventoried and set aside when the document was classified, before any page
    was read; they are remembered here so that a page read twice - or read after being released - reports the
    same marks as the first time, although the ink is already off the shared document.
    """

    def __init__(self, doc, indexes: list[int], pdf_path: str, known: dict[int, tuple] | None = None):
        self._doc, self._idx, self._path = doc, list(indexes), pdf_path
        self._known = known or {}
        self._held: dict[int, RawPage] = {}

    def __len__(self) -> int:
        return len(self._idx)

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[k] for k in range(*i.indices(len(self)))]
        if i < 0:
            i += len(self._idx)
        if i not in self._held:
            pno = self._idx[i]
            annots, markup, only_markup = self._known.get(pno, (None, None, False))
            if only_markup:
                # bladet har ingen egen ritning under märkena: läs det igen ur filen med märkena kvar
                with pymupdf.open(self._path) as again:
                    got = _read_page(again, pno, self._path, keep_markup=True)
            else:
                got = _read_page(self._doc, pno, self._path, known=(annots, markup) if annots is not None else None)
            if isinstance(got, dict):                       # classified readable, and then was not: not ours to hide
                raise UnsupportedInputError(f"page {pno + 1} carries no vector drawing", [got])
            self._held[i] = got
        return self._held[i]

    def release(self, i: int) -> None:
        """Done with this page. The next ask reads it again."""
        self._held.pop(i, None)


class UnsupportedInputError(Exception):
    """The PDF carries no page the engine can read: every page is a scan, an image or empty."""

    def __init__(self, message: str, classifications: list[dict]):
        super().__init__(message)
        self.classifications = classifications


@dataclass
class RawDocument:
    path: str
    n_pages: int
    metadata: dict
    ocgs: dict[int, dict]
    pages: list[RawPage] = field(default_factory=list)
    skipped_pages: list[dict] = field(default_factory=list)   # scanned / image-only pages, with the reason

    def inventory(self) -> dict[str, Any]:
        out = {"source": self.path, "n_pages": self.n_pages, "metadata": self.metadata,
               "ocgs": [{"xref": k, **v} for k, v in sorted(self.ocgs.items())], "pages": [],
               "skipped_pages": self.skipped_pages}
        for pg in self.pages:
            kinds: dict[str, int] = {}
            layers: dict[str, int] = {}
            widths: dict[str, int] = {}
            n_segs = 0
            n_curves = 0
            for p in pg.paths:
                kinds[p.kind] = kinds.get(p.kind, 0) + 1
                layers[p.layer] = layers.get(p.layer, 0) + 1
                w = f"{p.width:.2f}"
                widths[w] = widths.get(w, 0) + 1
                n_segs += len(p.segs)
                n_curves += p.n_curves
            out["pages"].append({
                "page": pg.info.index, "width": pg.info.width, "height": pg.info.height, "rotation": pg.info.rotation,
                "mediabox": pg.info.mediabox, "cropbox": pg.info.cropbox,
                "n_paths": len(pg.paths), "n_segments": n_segs, "n_curve_items": n_curves,
                "n_text_spans": len(pg.spans), "n_text_chars": sum(len(s.chars) for s in pg.spans),
                "n_images": pg.info.n_images, "n_annotations": pg.info.n_annots, "n_xobjects": pg.info.n_xobjects,
                "xobjects": pg.info.xobjects, "fonts": pg.info.fonts, "annotations": pg.info.annots,
                "markup_set_aside": pg.info.markup_set_aside, "input_class": pg.input_class,
                "path_kinds": kinds, "layers": dict(sorted(layers.items())), "stroke_widths": dict(sorted(widths.items())),
            })
        return out


def _pt(p) -> tuple[float, float]:
    return (float(p.x), float(p.y))


def _items_to_segs(items, closed: bool) -> tuple[list[Seg], int, int]:
    """Convert PyMuPDF path items into straight segments (curves flattened). Returns (segs, n_curves, n_subpaths)."""
    segs: list[Seg] = []
    n_curves = 0
    n_sub = 0
    first: tuple[float, float] | None = None
    last: tuple[float, float] | None = None
    for it in items:
        op = it[0]
        if op == "l":
            a, b = _pt(it[1]), _pt(it[2])
            if last is None or (abs(last[0] - a[0]) > 1e-6 or abs(last[1] - a[1]) > 1e-6):
                # new subpath
                if closed and first is not None and last is not None and (abs(first[0]-last[0]) > 1e-6 or abs(first[1]-last[1]) > 1e-6):
                    segs.append(Seg(last[0], last[1], first[0], first[1]))
                first = a
                n_sub += 1
            segs.append(Seg(a[0], a[1], b[0], b[1]))
            last = b
        elif op == "c":
            p0, p1, p2, p3 = _pt(it[1]), _pt(it[2]), _pt(it[3]), _pt(it[4])
            if last is None or (abs(last[0] - p0[0]) > 1e-6 or abs(last[1] - p0[1]) > 1e-6):
                if closed and first is not None and last is not None and (abs(first[0]-last[0]) > 1e-6 or abs(first[1]-last[1]) > 1e-6):
                    segs.append(Seg(last[0], last[1], first[0], first[1]))
                first = p0
                n_sub += 1
            chord = math.hypot(p3[0] - p0[0], p3[1] - p0[1])
            n = 4 if chord < 3 else (8 if chord < 30 else 16)
            pts = flatten_bezier(p0, p1, p2, p3, n)
            for i in range(len(pts) - 1):
                segs.append(Seg(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]))
            n_curves += 1
            last = p3
        elif op == "re":
            r = it[1]
            x0, y0, x1, y1 = float(r.x0), float(r.y0), float(r.x1), float(r.y1)
            segs += [Seg(x0, y0, x1, y0), Seg(x1, y0, x1, y1), Seg(x1, y1, x0, y1), Seg(x0, y1, x0, y0)]
            first = last = None
            n_sub += 1
        elif op == "qu":
            q = it[1]
            pts = [_pt(q.ul), _pt(q.ur), _pt(q.lr), _pt(q.ll)]
            for i in range(4):
                a, b = pts[i], pts[(i + 1) % 4]
                segs.append(Seg(a[0], a[1], b[0], b[1]))
            first = last = None
            n_sub += 1
    if closed and first is not None and last is not None and (abs(first[0]-last[0]) > 1e-6 or abs(first[1]-last[1]) > 1e-6):
        segs.append(Seg(last[0], last[1], first[0], first[1]))
    return segs, n_curves, max(n_sub, 1)


def _embedded_fonts(doc, page) -> tuple:
    """The typefaces embedded in the page, as (name, buffer).

    A CAD export explodes its labels into line geometry but still embeds the font it drew them with, usually
    subset to the characters its remaining real text uses. Those glyph shapes are the drawing's own evidence of
    what its letters look like, so the recogniser is given them alongside the generic alphabets."""
    out = []
    seen = set()
    try:
        for xref, ext, ftype, base, name, enc in page.get_fonts():
            if xref in seen:
                continue
            seen.add(xref)
            try:
                buf = doc.extract_font(xref)[3]
            except Exception:
                continue
            if buf and len(buf) > 200:
                # the name becomes a PDF resource name when the glyphs are re-rendered: keep it simple
                safe = "".join(c for c in (base or name or "F") if c.isalnum()) or "F"
                out.append((f"{safe}{xref}", bytes(buf)))
    except Exception:
        return ()
    return tuple(sorted(out))


def _color(c) -> tuple | None:
    if c is None:
        return None
    return tuple(round(float(v), 4) for v in c)


def _annot_length(a) -> float:
    """How far a markup runs, in points, when its shape says so."""
    try:
        pts = a.vertices or []
    except Exception:
        return 0.0
    if not pts or not isinstance(pts[0], (tuple, list)) or len(pts) < 2:
        return 0.0
    tot = 0.0
    for i in range(1, len(pts)):
        (x0, y0), (x1, y1) = pts[i - 1][:2], pts[i][:2]
        tot += math.hypot(x1 - x0, y1 - y0)
    return tot


def _annot_fingerprint(kind: str, rect: list, vertices, content: str, subject: str) -> str:
    """Ett märke känns igen på vad det är och var det sitter - inte på sitt xref, som byter värde när filen
    sparas om. Samma märke inventerat två gånger får samma avtryck."""
    h = hashlib.sha1()
    h.update(kind.encode()); h.update(repr(rect).encode())
    try:
        flat = []
        for v in (vertices or []):
            if isinstance(v, (tuple, list)) and v and isinstance(v[0], (tuple, list)):
                flat.extend((round(float(p[0]), 1), round(float(p[1]), 1)) for p in v)
            elif isinstance(v, (tuple, list)):
                flat.append((round(float(v[0]), 1), round(float(v[1]), 1)))
        h.update(repr(flat).encode())
    except Exception:
        pass
    h.update((content or "").encode("utf-8", "replace")); h.update((subject or "").encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def _inventory_annotations(page) -> list[dict]:
    """Every mark on the page, recorded before the page is classified or read.

    Kind, position, xref, appearance stream, author, text, how far it runs, and a fingerprint of its geometry:
    enough to point at the mark afterwards, and enough for a page inventoried twice to say the same thing.
    A mark that cannot be read is still counted - as a mark of unknown kind - because an inventory that drops
    what it could not parse is not an inventory.
    """
    out: list[dict] = []
    try:
        a = page.first_annot
    except Exception:
        return out
    doc = page.parent
    while a:
        xref = 0
        try:
            xref = int(a.xref or 0)
        except Exception:
            pass
        try:
            kind = a.type[1]
            info = a.info or {}
            try:
                verts = a.vertices or []
            except Exception:
                verts = []
            ap = ""
            try:
                if xref:
                    k, v = doc.xref_get_key(xref, "AP/N")
                    ap = v if k == "xref" else (k if k != "null" else "")
            except Exception:
                ap = ""
            rect = [round(float(v), 2) for v in a.rect]
            content = (info.get("content") or "")[:80]
            subject = (info.get("subject") or "")[:80]
            n_pts = 0
            if verts and isinstance(verts[0], (tuple, list)):
                n_pts = sum(len(v) for v in verts) if isinstance(verts[0][0], (tuple, list)) else len(verts)
            out.append({"type": kind, "rect": rect, "content": content, "subject": subject,
                        "author": (info.get("title") or "")[:60], "xref": xref, "appearance": ap,
                        "n_vertices": n_pts, "ink_pt": round(_annot_length(a), 1),
                        "fingerprint": _annot_fingerprint(kind, rect, verts, content, subject)})
        except Exception as e:
            out.append({"type": "?", "rect": [], "content": "", "subject": "", "author": "", "xref": xref,
                        "appearance": "", "n_vertices": 0, "ink_pt": 0.0, "fingerprint": "",
                        "error": f"{type(e).__name__}: {e}"[:120]})
        try:
            a = a.next
        except Exception:
            break
    return out


def _set_markup_aside(page, annots: list[dict], keep: bool = False) -> dict | None:
    """Take the marks' ink off the page before the drawing is read, and prove that it went.

    An annotation is not what the engineer drew. It is what somebody wrote afterwards on top of it: a cloud
    round a change, a note to the contractor, or - the one that matters here - a takeoff someone has already
    measured, drawn as coloured polylines with the length in the comment. PyMuPDF renders those appearance
    streams into `get_drawings()` alongside the drawing's own strokes, and nothing downstream can tell them
    apart: they carry a stroke width and a colour like any other line. A reading that keeps them measures one
    person's opinion of the drawing and reports it as the drawing.

    So the ink goes, and the record of it stays: how many marks, of what kind, whose, how far they ran - and the
    evidence: how many drawings the page had before and after, and how many marks were left. A removal that
    stopped halfway is reported as such, not as done; the page is then not safe to read, because the ink still
    on it has no known origin. A page whose only content is annotations is a different case - there the marks
    are the page - and it is asked for with `keep`.
    """
    if not annots:
        return None
    kinds: dict[str, int] = {}
    who: dict[str, int] = {}
    ink = 0.0
    for rec in annots:
        kinds[rec["type"]] = kinds.get(rec["type"], 0) + 1
        if rec.get("author"):
            who[rec["author"]] = who.get(rec["author"], 0) + 1
        ink += rec.get("ink_pt") or 0.0
    base = {"n": len(annots), "kinds": kinds, "authors": who, "ink_pt": round(ink, 1),
            "fingerprints": [r["fingerprint"] for r in annots]}
    if not _R("pdf.extract.ANNOTATION_INK_IS_REVIEW", ANNOTATION_INK_IS_REVIEW):
        return {**base, "removed": False, "why": "regeln som lägger påskrift åt sidan är avstängd"}
    if keep:                              # asked for again by a page that had nothing else on it
        return {**base, "removed": False, "why": "bladet har ingen egen ritning under påskriften"}
    try:
        before = len(page.get_drawings())
    except Exception:
        before = -1
    error = ""
    try:
        a = page.first_annot
        while a:
            a = page.delete_annot(a)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"[:120]
    try:
        left = sum(1 for _ in page.annots())
    except Exception:
        left = -1
    try:
        after = len(page.get_drawings())
    except Exception:
        after = -1
    evidence = {"drawings_before": before, "drawings_after": after, "annotations_left": left, "error": error}
    if left != 0:
        return {**base, "removed": False, "partial": True, "evidence": evidence,
                "why": f"påskriften gick bara delvis att lyfta av bladet ({left} av {len(annots)} märken kvar): "
                       "bläcket som är kvar har okänt ursprung och bladet läses inte"}
    return {**base, "removed": True, "evidence": evidence,
            "why": "en annotation är någons påskrift på ritningen, inte det ritaren ritade"}


def _read_page(doc, pno: int, pdf_path: str, keep_markup: bool = False, known: tuple | None = None) -> RawPage | dict:
    """One page's vector content, or the reason it was not read.

    The order is the contract: the marks are inventoried first, then taken off, and only then is the page
    classified. Classifying first would count a takeoff's polylines as vector content and call a scanned sheet
    with somebody's markup on it a vector drawing - and then read the markup as the drawing.

    Layer ids are numbered within the page, from its own layer names sorted. They used to be handed out in the
    order the document happened to introduce them, which made a page's own artifact depend on which pages had
    been read before it - and once pages are read on demand, that is not even a fixed order.
    """
    page = doc[pno]
    if known is not None:
        annots, markup = known
        if annots and not keep_markup and any(True for _ in page.annots()):
            markup = _set_markup_aside(page, annots, keep=False)      # a fresh opening still carries the marks
    else:
        annots = _inventory_annotations(page)
        markup = _set_markup_aside(page, annots, keep=keep_markup)
    if markup and markup.get("partial"):
        return {"page": pno, "mode": "unsafe_markup", "n_paths": 0, "n_chars": 0, "n_images": 0,
                "image_coverage": 0.0, "reasons": [markup["why"]], "markup_set_aside": markup, "annotations": annots}
    from .classify import classify_page
    drawings = page.get_drawings(extended=True)
    klass = classify_page(page, drawings=drawings)
    if klass.mode in ("raster", "empty"):
        if klass.mode == "empty" and markup and markup.get("removed"):
            # Nothing was drawn under the marks: on this page they are not somebody's comment on a drawing, they
            # are the drawing. The file itself was never touched, so the page is simply read again from it.
            with pymupdf.open(pdf_path) as again:
                return _read_page(again, pno, pdf_path, keep_markup=True)
        return {"page": pno, **klass.as_dict(), "markup_set_aside": markup, "annotations": annots}
    rot = page.rotation
    # Work in the displayed (rotated) page space: PyMuPDF get_drawings/get_text return unrotated
    # coordinates; map them with rotation_matrix so all downstream geometry matches the rendered page.
    M = page.rotation_matrix if rot else None
    rect = page.rect
    from .visibility import Visibility
    visibility = Visibility(rect, M)
    layer_ids = {name: i for i, name in enumerate(sorted({d.get("layer") or "" for d in drawings}))}
    paths: list[RawPath] = []
    for seq, d in enumerate(drawings):
        visible_state = visibility.consume(d)
        if visible_state is None:
            continue
        items = d.get("items") or []
        if M is not None:
            items = _transform_items(items, M)
        closed = bool(d.get("closePath"))
        segs, n_curves, n_sub = _items_to_segs(items, closed)
        if not segs:
            continue
        layer = d.get("layer") or ""
        kind = d.get("type") or "s"
        width = float(d.get("width") or 0.0)
        key = (layer, kind, f"{width:.3f}", _color(d.get('color')), _color(d.get('fill')),
               d.get('dashes'), d.get('stroke_opacity'), d.get('fill_opacity'),
               ",".join(f"{s.x0:.4f},{s.y0:.4f},{s.x1:.4f},{s.y1:.4f}" for s in segs))
        pid = stable_id("path", pno, *key)
        source_length=sum(s.length for s in segs)
        segs, intervals=visibility.apply(segs,d,visible_state,pid)
        if not segs:
            continue
        bbox = bbox_union([s.bbox() for s in segs])
        paths.append(RawPath(pid=pid, seqno=d.get('seqno',seq), page=pno, layer=layer, layer_id=layer_ids[layer], kind=kind,
                             width=width, color=_color(d.get("color")), fill=_color(d.get("fill")), closed=closed,
                             segs=segs, bbox=bbox, n_items=len(items), n_curves=n_curves, n_subpaths=n_sub,
                             dashes=d.get('dashes') or '', stroke_opacity=float(d.get('stroke_opacity',1.) or 0),
                             fill_opacity=float(d.get('fill_opacity',1.) or 0),
                             source_length_pt=source_length,visible_intervals=intervals))
    # duplicate pid disambiguation (identical geometry drawn twice): keep both, suffix by occurrence rank in
    # a content-sorted order so that the result does not depend on enumeration order.
    _dedupe_ids(paths)
    spans = _extract_text(page, pno, M)
    if visibility.report['clip_count'] and spans:
        # An extracted native span may be entirely outside a CAD viewport. Only
        # discard spans whose whole displayed box is blank in the actual renderer.
        # This is conservative: partially clipped text and later occlusion remain
        # a reported limitation, rather than inferring visibility from nearby paths.
        import numpy as np
        scale=min(2.,math.sqrt(20_000_000/(rect.width*rect.height)))
        pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False,annots=False)
        pixels=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
        kept=[]
        for span in spans:
            x0,y0,x1,y1=span.bbox
            crop=pixels[max(0,int(y0*scale)-1):min(pix.height,math.ceil(y1*scale)+1),
                        max(0,int(x0*scale)-1):min(pix.width,math.ceil(x1*scale)+1)]
            if crop.size and int(crop.min()) < 255:
                kept.append(span)
            else:
                visibility.report.setdefault('blank_text_spans',[]).append(span.as_dict())
        spans=kept
    xobjs = []
    try:
        for xo in page.get_xobjects():
            xobjs.append({"xref": xo[0], "name": xo[1], "invoker": xo[2], "bbox": [round(v, 2) for v in xo[3]]})
    except Exception:
        pass
    fonts = []
    try:
        for f in page.get_fonts():
            fonts.append({"xref": f[0], "ext": f[1], "type": f[2], "basefont": f[3], "name": f[4], "encoding": f[5]})
    except Exception:
        pass
    info = PageInfo(index=pno, width=float(rect.width), height=float(rect.height), rotation=rot,
                    mediabox=[round(v, 2) for v in page.mediabox], cropbox=[round(v, 2) for v in page.cropbox],
                    n_images=len(page.get_images()), n_annots=len(annots), n_xobjects=len(xobjs), xobjects=xobjs,
                    fonts=fonts, annots=annots, markup_set_aside=markup)
    rp = RawPage(info=info, paths=paths, spans=spans,visibility_report=visibility.report)
    klass_d = klass.as_dict()
    if keep_markup and annots:
        klass_d["markup_only"] = True
        klass_d["reasons"] = list(klass_d["reasons"]) + [
            f"MARKUP_ONLY: bladet har ingen egen ritning; det som läses är {len(annots)} märken av "
            + ", ".join(f"{k} ({n})" for k, n in sorted(markup["kinds"].items()))]
    else:
        klass_d["markup_only"] = False
    rp.input_class = klass_d
    rp.source_path = pdf_path
    rp.embedded_fonts = _embedded_fonts(doc, page)
    return rp


def extract_document(pdf_path: str, pages: list[int] | None = None, progress=None, eager: bool = True) -> RawDocument:
    """Read the vector content of every page: paths with their segments, layers, stroke widths and text spans.

    Only vector pages are analysed. A page whose content is a scan or an image is classified as such and skipped,
    because reading it would mean guessing at pixels instead of the drawing's own geometry; a PDF with no vector
    page at all raises UnsupportedInputError.

    eager=False reads a page's geometry the first time somebody asks for it, and lets the reading hand it back
    when it is done with the page. It matters at the size real sets arrive in: a fifty-sheet set holds 1.1
    million paths, and building all of them before reading any of them took two gigabytes of memory before the
    first metre was measured. That is not a page being expensive; it is forty-nine pages being kept for later.
    The classification pass still visits every page up front, because which pages there are to read is part of
    what the document is.
    """
    doc = pymupdf.open(pdf_path)
    try:
        ocgs_raw = doc.get_ocgs() or {}
    except Exception:
        ocgs_raw = {}
    ocgs = {int(k): {"name": v.get("name", ""), "on": bool(v.get("on", True))} for k, v in ocgs_raw.items()}
    rd = RawDocument(path=pdf_path, n_pages=len(doc), metadata={k: v for k, v in (doc.metadata or {}).items() if v}, ocgs=ocgs)
    wanted = [pno for pno in range(len(doc)) if pages is None or pno in pages]
    if eager:
        for pno in wanted:
            got = _read_page(doc, pno, pdf_path)
            (rd.skipped_pages if isinstance(got, dict) else rd.pages).append(got)
        doc.close()
    else:
        from .classify import classify_page
        keep = []
        known: dict[int, tuple] = {}
        for pno in wanted:
            page = doc[pno]
            annots = _inventory_annotations(page)
            markup = _set_markup_aside(page, annots, keep=False)
            if markup and markup.get("partial"):
                rd.skipped_pages.append({"page": pno, "mode": "unsafe_markup", "n_paths": 0, "n_chars": 0,
                                         "n_images": 0, "image_coverage": 0.0, "reasons": [markup["why"]],
                                         "markup_set_aside": markup, "annotations": annots})
                continue
            klass = classify_page(page)
            if klass.mode == "empty" and markup and markup.get("removed"):
                known[pno] = (annots, markup, True)          # bara märken: läses igen med märkena kvar
                keep.append(pno)
            elif klass.mode in ("raster", "empty"):
                rd.skipped_pages.append({"page": pno, **klass.as_dict(), "markup_set_aside": markup, "annotations": annots})
            else:
                known[pno] = (annots, markup, False)
                keep.append(pno)
        rd.pages = LazyPages(doc, keep, pdf_path, known)
    if not len(rd.pages):
        which = ", ".join(f"page {c['page'] + 1}: {'; '.join(c['reasons'])}" for c in rd.skipped_pages) or "no pages"
        raise UnsupportedInputError(
            "The PDF carries no vector drawing. This engine reads the drawing's own vector geometry and never "
            f"guesses at pixels, so a scanned or image-only PDF cannot be measured ({which}).", rd.skipped_pages)
    return rd


def _transform_items(items, M):
    out = []
    for it in items:
        op = it[0]
        if op == "l":
            out.append(("l", it[1] * M, it[2] * M))
        elif op == "c":
            out.append(("c", it[1] * M, it[2] * M, it[3] * M, it[4] * M))
        elif op == "re":
            q = it[1].quad * M
            out.append(("qu", q))
        elif op == "qu":
            out.append(("qu", it[1] * M))
    return out


def _dedupe_ids(paths: list[RawPath]) -> None:
    groups: dict[str, list[RawPath]] = {}
    for p in paths:
        groups.setdefault(p.pid, []).append(p)
    for pid, lst in groups.items():
        if len(lst) > 1:
            # rank by full geometry string (identical) then by nothing else -> identical objects are interchangeable;
            # give them distinct suffixes in a content-sorted order (all equal -> order irrelevant for semantics).
            lst_sorted = sorted(lst, key=lambda p: (len(p.segs), p.length))
            for i, p in enumerate(lst_sorted):
                p.pid = f"{pid}_{i}"


def _extract_text(page, pno: int, M) -> list[TextSpan]:
    spans: list[TextSpan] = []
    try:
        raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES)
    except Exception:
        return spans
    # Tecken läsaren inte kunde tyda, ifyllda ur typsnittets egen glyftabell. Tom på nästan varje blad; på ett
    # som plottats med Identity-H och ofullständig teckentabell är det skillnaden mellan "Längd(m)" och åtta
    # ersättningstecken.
    fixes = repairs_for_page(page, page.parent)
    seq = 0
    for b in raw.get("blocks", []):
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            d = line.get("dir", (1.0, 0.0))
            for sp in line.get("spans", []):
                chars = []
                for ch in sp.get("chars", []):
                    bb = ch["bbox"]
                    org = ch.get("origin", (bb[0], bb[3]))
                    glyph = fixes.get((round(float(org[0]), 1), round(float(org[1]), 1)))
                    if M is not None:
                        r = pymupdf.Rect(bb) * M
                        bb = (r.x0, r.y0, r.x1, r.y1)
                        o = pymupdf.Point(org) * M
                        org = (o.x, o.y)
                    chars.append(TextChar(c=glyph or ch["c"], bbox=tuple(float(v) for v in bb),
                                          origin=(float(org[0]), float(org[1]))))
                text = "".join(c.c for c in chars)
                if not text.strip():
                    continue
                bbox = bbox_union([c.bbox for c in chars])
                dd = (float(d[0]), float(d[1]))
                if M is not None:
                    p = pymupdf.Point(dd) * pymupdf.Matrix(M.a, M.b, M.c, M.d, 0, 0)
                    dd = (p.x, p.y)
                tid = stable_id("text", pno, text, f"{bbox[0]:.1f}", f"{bbox[1]:.1f}", sp.get("font", ""))
                spans.append(TextSpan(tid=tid, seqno=seq, page=pno, text=text, bbox=bbox, dir=dd,
                                      font=sp.get("font", ""), size=float(sp.get("size", 0.0)), chars=chars))
                seq += 1
    # dedupe tids
    seen: dict[str, int] = {}
    for s in spans:
        if s.tid in seen:
            seen[s.tid] += 1
            s.tid = f"{s.tid}_{seen[s.tid]}"
        else:
            seen[s.tid] = 0
    return spans
