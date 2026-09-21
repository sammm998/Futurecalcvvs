"""Generic character recognition for vector glyphs.

Evidence used: normalized stroke geometry (translation/scale normalized, aspect preserved), enclosed-region
count, and deterministic isolated-glyph rasterization compared against skeletons of generic reference fonts
(PDF base-14 Helvetica / Courier / Times rendered by PyMuPDF). No drawing-specific alphabet, no expected words.
Identical shapes are clustered into drawing-local families and classified once.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pymupdf
from scipy import ndimage

from ..geometry.core import Seg
from .hershey import hershey_fonts

from .. import rules as _rules


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


GRID = 32
INNER = 26
CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ0123456789abdefghijmnqrty-/+.,:()[]=%°Ø&*•"
ALIASES = {"•": "."}
_REF_FONTS = ("helv", "cour", "tiro")

# expected enclosed regions per character (generic typographic topology; not drawing-specific)
HOLES = {**{c: 0 for c in CHARSET}, **{"A": 1, "B": 2, "D": 1, "O": 1, "P": 1, "Q": 1, "R": 1, "0": 1, "4": 1, "6": 1, "8": 2, "9": 1,
          "a": 1, "b": 1, "d": 1, "e": 1, "g": 1, "q": 1, "Ø": 1, "%": 2, "&": 1, "Å": 2, "Ä": 1, "Ö": 1, "°": 1}}


def _line_pixels(x0, y0, x1, y1):
    n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 2
    t = np.linspace(0.0, 1.0, n)
    xs = np.rint(x0 + (x1 - x0) * t).astype(int)
    ys = np.rint(y0 + (y1 - y0) * t).astype(int)
    return xs, ys


MAX_ASPECT = 12.0


def _norm_scales(w: float, h: float) -> tuple[float, float]:
    """Box-fit normalization: stretch both axes to INNER unless the shape is a thin bar (then keep it thin)."""
    w = max(w, 1e-6); h = max(h, 1e-6)
    ar = w / h
    if ar > 2.5:
        return INNER / w, INNER / w
    if ar < 0.4:
        return INNER / h, INNER / h
    return INNER / w, INNER / h


NBINS = 4


def rasterize_segments(segs: list[Seg], angle_deg: float = 0.0) -> tuple[np.ndarray, float]:
    img, ar, _ = rasterize_segments_oriented(segs, angle_deg)
    return img, ar


def rasterize_segments_oriented(segs: list[Seg], angle_deg: float = 0.0) -> tuple[np.ndarray, float, np.ndarray]:
    """Rasterize stroke segments into a GRID x GRID binary image after rotating by -angle (so text reads left->right).
    Returns (bitmap, aspect_ratio = w/h in the rotated frame (clamped), orientation-bin map (-1 = no ink))."""
    a = -math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    arr = np.array([(s.x0, s.y0, s.x1, s.y1) for s in segs], dtype=float)
    x0 = arr[:, 0] * ca - arr[:, 1] * sa; y0 = arr[:, 0] * sa + arr[:, 1] * ca
    x1 = arr[:, 2] * ca - arr[:, 3] * sa; y1 = arr[:, 2] * sa + arr[:, 3] * ca
    xmin = min(x0.min(), x1.min()); xmax = max(x0.max(), x1.max())
    ymin = min(y0.min(), y1.min()); ymax = max(y0.max(), y1.max())
    w = max(xmax - xmin, 1e-6); h = max(ymax - ymin, 1e-6)
    sx, sy = _norm_scales(w, h)
    ox = (GRID - w * sx) / 2 - xmin * sx
    oy = (GRID - h * sy) / 2 - ymin * sy
    t = np.linspace(0.0, 1.0, 48)
    X = (x0 * sx + ox)[:, None] + ((x1 - x0) * sx)[:, None] * t[None, :]
    Y = (y0 * sy + oy)[:, None] + ((y1 - y0) * sy)[:, None] * t[None, :]
    xs = np.clip(np.rint(X).astype(int), 0, GRID - 1); ys = np.clip(np.rint(Y).astype(int), 0, GRID - 1)
    img = np.zeros((GRID, GRID), dtype=np.uint8)
    img[ys.ravel(), xs.ravel()] = 1
    ang = np.degrees(np.arctan2((y1 - y0) * sy, (x1 - x0) * sx)) % 180.0
    bins = (np.rint(ang / (180.0 / NBINS)).astype(int) % NBINS)
    omap = np.full((GRID, GRID), -1, dtype=np.int8)
    # deterministic: longer segments assigned last so they dominate at junctions
    order = np.argsort(np.hypot((x1 - x0) * sx, (y1 - y0) * sy), kind="stable")
    omap[ys[order].ravel(), xs[order].ravel()] = np.repeat(bins[order], xs.shape[1]).astype(np.int8)
    return img, float(min(max(w / h, 1.0 / _R("text.recognize.MAX_ASPECT", MAX_ASPECT)), _R("text.recognize.MAX_ASPECT", MAX_ASPECT))), omap


def rasterize_polygon_fill(segs: list[Seg], angle_deg: float = 0.0) -> tuple[np.ndarray, float]:
    """Rasterize closed outline contours (filled glyphs) with even-odd filling, then thin to a skeleton."""
    img, ar = rasterize_segments(segs, angle_deg)
    # even-odd fill via scanline parity on the outline pixels is unreliable at low res; use polygon filling
    a = -math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = np.array([(s.x0 * ca - s.y0 * sa, s.x0 * sa + s.y0 * ca, s.x1 * ca - s.y1 * sa, s.x1 * sa + s.y1 * ca) for s in segs])
    xmin = min(pts[:, 0].min(), pts[:, 2].min()); xmax = max(pts[:, 0].max(), pts[:, 2].max())
    ymin = min(pts[:, 1].min(), pts[:, 3].min()); ymax = max(pts[:, 1].max(), pts[:, 3].max())
    w = max(xmax - xmin, 1e-6); h = max(ymax - ymin, 1e-6)
    R = 4
    G = GRID * R
    sx, sy = _norm_scales(w, h)
    sx *= R; sy *= R
    ox = (G - w * sx) / 2 - xmin * sx
    oy = (G - h * sy) / 2 - ymin * sy
    # crossing-number fill at supersampled resolution
    yy = np.arange(G) + 0.5
    fill = np.zeros((G, G), dtype=bool)
    xs_cross: list[list[float]] = [[] for _ in range(G)]
    for x0, y0, x1, y1 in pts:
        X0, Y0, X1, Y1 = x0 * sx + ox, y0 * sy + oy, x1 * sx + ox, y1 * sy + oy
        if abs(Y1 - Y0) < 1e-9:
            continue
        lo, hi = (Y0, Y1) if Y0 < Y1 else (Y1, Y0)
        for row in range(max(0, int(math.ceil(lo - 0.5))), min(G - 1, int(math.floor(hi - 0.5))) + 1):
            y = row + 0.5
            if y < lo or y >= hi:
                continue
            xc = X0 + (y - Y0) * (X1 - X0) / (Y1 - Y0)
            xs_cross[row].append(xc)
    for row in range(G):
        xc = sorted(xs_cross[row])
        for i in range(0, len(xc) - 1, 2):
            a0, a1 = int(math.ceil(xc[i] - 0.5)), int(math.floor(xc[i + 1] - 0.5))
            if a1 >= a0:
                fill[row, max(0, a0):min(G, a1 + 1)] = True
    small = fill.reshape(GRID, R, GRID, R).mean(axis=(1, 3)) > 0.5
    sk = zhang_suen(small.astype(np.uint8))
    return sk, float(min(max(w / h, 1.0 / _R("text.recognize.MAX_ASPECT", MAX_ASPECT)), _R("text.recognize.MAX_ASPECT", MAX_ASPECT)))


def skeleton_orientation(img: np.ndarray) -> np.ndarray:
    """Orientation bins of a skeleton image from local 5x5 neighbourhood PCA (deterministic)."""
    omap = np.full(img.shape, -1, dtype=np.int8)
    pts = np.argwhere(img > 0)
    if len(pts) == 0:
        return omap
    P = np.pad(img, 2)
    for y, x in pts:
        win = P[y:y + 5, x:x + 5]
        wy, wx = np.nonzero(win)
        if len(wx) < 2:
            omap[y, x] = 0
            continue
        cx, cy = wx.mean(), wy.mean()
        sxx = ((wx - cx) ** 2).sum(); syy = ((wy - cy) ** 2).sum(); sxy = ((wx - cx) * (wy - cy)).sum()
        ang = 0.5 * math.degrees(math.atan2(2 * sxy, sxx - syy)) % 180.0
        omap[y, x] = int(round(ang / (180.0 / NBINS))) % NBINS
    return omap


def zhang_suen(img: np.ndarray) -> np.ndarray:
    """Deterministic Zhang-Suen thinning (vectorized)."""
    img = img.copy().astype(np.uint8)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            P = np.pad(img, 1)
            p2 = P[:-2, 1:-1]; p3 = P[:-2, 2:]; p4 = P[1:-1, 2:]; p5 = P[2:, 2:]
            p6 = P[2:, 1:-1]; p7 = P[2:, :-2]; p8 = P[1:-1, :-2]; p9 = P[:-2, :-2]
            B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            A = np.zeros_like(img, dtype=np.int32)
            for i in range(8):
                A += ((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int32)
            if step == 0:
                c1 = (p2 * p4 * p6) == 0
                c2 = (p4 * p6 * p8) == 0
            else:
                c1 = (p2 * p4 * p8) == 0
                c2 = (p2 * p6 * p8) == 0
            m = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & c1 & c2
            if m.any():
                img[m] = 0
                changed = True
    return img


def count_holes(img: np.ndarray) -> int:
    """Number of enclosed background regions in a (dilated) binary image (vectorized border flood)."""
    d = _dilate(img)
    H, W = d.shape
    bg = (d == 0)
    reach = np.zeros_like(bg)
    reach[0, :] = bg[0, :]; reach[-1, :] = bg[-1, :]; reach[:, 0] = bg[:, 0]; reach[:, -1] = bg[:, -1]
    while True:
        P = np.pad(reach, 1)
        grown = (P[1:-1, 1:-1] | P[:-2, 1:-1] | P[2:, 1:-1] | P[1:-1, :-2] | P[1:-1, 2:]) & bg
        if np.array_equal(grown, reach):
            break
        reach = grown
    left = bg & ~reach
    if not left.any():
        return 0
    _, n = ndimage.label(left)
    return int(n)


def _flood(bg, visited, y, x):
    H, W = bg.shape
    st = [(y, x)]
    visited[y, x] = True
    while st:
        cy, cx = st.pop()
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if 0 <= ny < H and 0 <= nx < W and bg[ny, nx] and not visited[ny, nx]:
                visited[ny, nx] = True
                st.append((ny, nx))


def _dilate(img: np.ndarray) -> np.ndarray:
    P = np.pad(img, 1)
    out = P[1:-1, 1:-1] | P[:-2, 1:-1] | P[2:, 1:-1] | P[1:-1, :-2] | P[1:-1, 2:]
    return out.astype(np.uint8)


@lru_cache(maxsize=1)
def _grid_coords() -> np.ndarray:
    ys, xs = np.mgrid[0:GRID, 0:GRID]
    return np.stack([ys.ravel(), xs.ravel()], axis=1).astype(float)


def distance_transform(img: np.ndarray) -> np.ndarray:
    if not (img > 0).any():
        return np.full((GRID, GRID), float(GRID), dtype=float)
    return ndimage.distance_transform_edt(img == 0).astype(float)


@dataclass
class RefGlyph:
    char: str
    font: str
    img: np.ndarray
    dt: np.ndarray
    aspect: float
    holes: int
    omap: np.ndarray | None = None
    dt_bins: np.ndarray | None = None   # (NBINS, GRID, GRID)


def oriented_dts(img: np.ndarray, omap: np.ndarray) -> np.ndarray:
    out = np.empty((NBINS, GRID, GRID), dtype=float)
    for b in range(NBINS):
        m = (img > 0) & (omap == b)
        if m.any():
            out[b] = ndimage.distance_transform_edt(~m)
        else:
            out[b] = float(GRID)
    return out


@lru_cache(maxsize=4)
def reference_alphabet(embedded: tuple[tuple[str, bytes], ...] = ()) -> list[RefGlyph]:
    """Reference shapes to recognise a drawn glyph against.

    Generic alphabets (Hershey strokes, three PDF base fonts) plus, when the drawing embeds its own typeface, the
    glyphs of that very font: a CAD export explodes its labels into line geometry but still embeds the font it
    drew them with, so those shapes are the drawing's own evidence rather than a generic stand-in."""
    refs: list[RefGlyph] = []
    for fname, buf in embedded:
        for ch in CHARSET:
            img, ar = _render_reference(ch, fname, buf)
            if img is None:
                continue
            omap = skeleton_orientation(img)
            refs.append(RefGlyph(char=ch, font=f"embedded:{fname}", img=img, dt=distance_transform(img), aspect=ar,
                                 holes=HOLES.get(ch, 0), omap=omap, dt_bins=oriented_dts(img, omap)))
    for fname, glyphs in hershey_fonts().items():
        for ch in CHARSET:
            segs = glyphs.get(ch)
            if not segs:
                continue
            img, ar, omap = rasterize_segments_oriented(segs)
            refs.append(RefGlyph(char=ch, font=f"hershey:{fname}", img=img, dt=distance_transform(img), aspect=ar,
                                 holes=HOLES.get(ch, 0), omap=omap, dt_bins=oriented_dts(img, omap)))
    for font in _REF_FONTS:
        for ch in CHARSET:
            img, ar = _render_reference(ch, font)
            if img is None:
                continue
            omap = skeleton_orientation(img)
            refs.append(RefGlyph(char=ch, font=font, img=img, dt=distance_transform(img), aspect=ar, holes=HOLES.get(ch, 0),
                                 omap=omap, dt_bins=oriented_dts(img, omap)))
    return refs


def _render_reference(ch: str, font: str, buffer: bytes | None = None):
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    try:
        if buffer is not None:
            page.insert_font(fontname=font, fontbuffer=buffer)
            f = pymupdf.Font(fontbuffer=buffer)
            if not f.has_glyph(ord(ch)):
                doc.close()
                return None, 1.0      # a subset font carries only the characters its text actually used
        page.insert_text((40, 150), ch, fontsize=110, fontname=font)
    except Exception:
        doc.close()
        return None, 1.0
    pix = page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    ink = arr < 128
    ys, xs = np.where(ink)
    if len(xs) == 0:
        return None, 1.0
    crop = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8)
    # Thin at render resolution and re-measure the skeleton's own extent. A drawn glyph reaches us as centre
    # lines, and is normalized by those; a reference rendered from a font arrives as filled outlines, whose box
    # is wider than its centre lines by one stroke width. Normalizing the reference by its outline would set the
    # two shapes side by side at different scales - visible as a crossbar or a stem sitting a step off - so the
    # reference is reduced to centre lines first and normalized by the same measure as the drawing.
    sk_full = zhang_suen(crop)
    sy_, sx_ = np.where(sk_full)
    if len(sx_) == 0:
        return None, 1.0
    crop = sk_full[sy_.min():sy_.max() + 1, sx_.min():sx_.max() + 1]
    h, w = crop.shape
    sx, sy = _norm_scales(w, h)
    th, tw = max(1, int(round(h * sy))), max(1, int(round(w * sx)))
    ys2 = (np.arange(th) * (h / th)).astype(int)
    xs2 = (np.arange(tw) * (w / tw)).astype(int)
    small = np.zeros((th, tw), dtype=np.uint8)
    for i, yy in enumerate(ys2):
        for j, xx in enumerate(xs2):
            y_end = int(min(h, (i + 1) * (h / th))); x_end = int(min(w, (j + 1) * (w / tw)))
            # a centre line is one pixel wide: a block keeps the line when any of it is inked, never by majority
            small[i, j] = 1 if crop[yy:max(yy + 1, y_end), xx:max(xx + 1, x_end)].any() else 0
    sk = zhang_suen(small)
    img = np.zeros((GRID, GRID), dtype=np.uint8)
    oy = (GRID - th) // 2; ox = (GRID - tw) // 2
    img[oy:oy + th, ox:ox + tw] = sk
    return img, float(min(max(w / h, 1.0 / _R("text.recognize.MAX_ASPECT", MAX_ASPECT)), _R("text.recognize.MAX_ASPECT", MAX_ASPECT)))


def chamfer(img_a: np.ndarray, dt_a: np.ndarray, img_b: np.ndarray, dt_b: np.ndarray) -> float:
    pa = img_a > 0; pb = img_b > 0
    if not pa.any() or not pb.any():
        return 99.0
    return 0.5 * (dt_b[pa].mean() + dt_a[pb].mean()) / INNER


@dataclass
class FamilyResult:
    family_id: str
    char: str
    score: float
    alternatives: list[tuple[str, float]]
    holes: int
    aspect: float
    n_members: int = 0


def family_fingerprint(img: np.ndarray, aspect: float, size_class: str = "", has_diacritic: bool = False) -> str:
    d = _dilate(img)
    coarse = d.reshape(16, 2, 16, 2).max(axis=(1, 3))
    return hashlib.sha1(coarse.tobytes() + f"|{round(aspect * 8) / 8:.3f}|{size_class}|{int(has_diacritic)}".encode()).hexdigest()[:12]


SMALL_MARKS = set("-.,:=°'~")


@lru_cache(maxsize=4)
def _ref_arrays(embedded: tuple[tuple[str, bytes], ...] = ()):
    refs = reference_alphabet(embedded)
    dts = np.stack([r.dt.ravel() for r in refs])
    raw_bins = np.stack([r.dt_bins.reshape(NBINS, -1) for r in refs])        # (n_ref, NBINS, 1024)
    bdm = _bin_dist_matrix()
    # relaxed[r, b, p] = min_b' ( dt_bins[r, b', p] + lambda * bindist(b, b') ): cost for a glyph pixel of bin b at p
    dt_bins = np.stack([(raw_bins[:, bp, :] + _R("text.recognize.ORIENT_LAMBDA", ORIENT_LAMBDA) * bdm[b, bp]) for b in range(NBINS) for bp in [slice(None)]], axis=1) if False else None
    dt_bins = np.empty_like(raw_bins)
    for b in range(NBINS):
        dt_bins[:, b, :] = (raw_bins + (_R("text.recognize.ORIENT_LAMBDA", ORIENT_LAMBDA) * bdm[b])[None, :, None]).min(axis=1)
    ref_bins = np.stack([np.where(r.omap.ravel() < 0, 0, r.omap.ravel()) for r in refs])   # (n_ref, 1024)
    # sparse ink representation of refs for term 2
    kmax = int(max(int((r.img > 0).sum()) for r in refs))
    ink_idx = np.zeros((len(refs), kmax), dtype=np.int64)
    ink_bin = np.zeros((len(refs), kmax), dtype=np.int64)
    ink_valid = np.zeros((len(refs), kmax), dtype=float)
    for i, r in enumerate(refs):
        idx = np.nonzero(r.img.ravel() > 0)[0]
        ink_idx[i, :len(idx)] = idx
        ink_bin[i, :len(idx)] = ref_bins[i, idx]
        ink_valid[i, :len(idx)] = 1.0
    masks = (ink_idx, ink_bin, ink_valid)
    counts = np.array([float((r.img > 0).sum()) for r in refs])
    aspects = np.array([r.aspect for r in refs])
    holes = np.array([r.holes for r in refs])
    chars = [r.char for r in refs]
    lower = np.array([c.islower() for c in chars])
    small = np.array([c in SMALL_MARKS for c in chars])
    diacritic = np.array([c in DIACRITIC_CHARS for c in chars])
    return refs, dts, masks, counts, aspects, holes, chars, lower, small, diacritic, dt_bins, ref_bins


DIACRITIC_CHARS = set("ÅÄÖij")


ORIENT_LAMBDA = 3.0  # pixels of extra distance per orientation-bin step


def _bin_dist_matrix() -> np.ndarray:
    m = np.zeros((NBINS, NBINS))
    for a in range(NBINS):
        for b in range(NBINS):
            d = abs(a - b)
            m[a, b] = min(d, NBINS - d)
    return m


def classify(img: np.ndarray, aspect: float, holes: int, allow_lower: bool = True, rel_height: float = 1.0,
             has_diacritic: bool = False, rel_size: float | None = None, omap: np.ndarray | None = None,
             embedded: tuple[tuple[str, bytes], ...] = ()) -> tuple[str, float, list[tuple[str, float]]]:
    """Score glyph against all reference glyphs (batched symmetric chamfer + capped aspect + hole penalties).

    rel_height: glyph height relative to its row height; punctuation marks are only admitted for short glyphs and
    excluded for full-height glyphs (structural typography, not drawing-specific knowledge)."""
    refs, dts, masks, counts, aspects, rholes, chars, lower, small, diacritic, dt_bins, ref_bins = _ref_arrays(embedded)
    if rel_size is not None and rel_size < 0.18 and rel_height < 0.18:
        return ".", 0.0, [(".", 0.0)]
    m = (img.ravel() > 0).astype(float)
    if m.sum() == 0:
        return "?", 99.0, []
    tau = 0.35 * INNER
    if omap is None:
        omap = skeleton_orientation(img)
    ob = omap.ravel()
    gpix = np.nonzero(m)[0]
    gb = ob[gpix]
    bdm = _bin_dist_matrix()
    # term 1: glyph pixels -> nearest ref pixel of compatible orientation (precomputed relaxed DTs)
    gb = np.where(gb < 0, 0, gb)
    c1 = np.minimum(dt_bins[:, gb, gpix], tau) ** 2                            # (n_ref, npix)
    t1 = c1.mean(axis=1)
    # term 2: ref pixels -> nearest glyph pixel of compatible orientation
    ink_idx, ink_bin, ink_valid = masks
    g_raw = np.empty((NBINS, GRID * GRID), dtype=float)
    for b in range(NBINS):
        mb = (img > 0) & (omap == b)
        g_raw[b] = ndimage.distance_transform_edt(~mb).ravel() if mb.any() else float(GRID)
    g_rel = np.empty_like(g_raw)
    for b in range(NBINS):
        g_rel[b] = (g_raw + (_R("text.recognize.ORIENT_LAMBDA", ORIENT_LAMBDA) * bdm[b])[:, None]).min(axis=0)
    c2 = np.minimum(g_rel[ink_bin, ink_idx], tau) ** 2                          # (n_ref, kmax)
    t2 = (c2 * ink_valid).sum(axis=1) / np.maximum(counts, 1)
    c = np.sqrt(0.5 * (t1 + t2)) / INNER
    pen = np.minimum(0.04 * np.abs(np.log(aspect / aspects)), 0.08)
    pen += 0.05 * np.abs(holes - rholes)
    # Every stroke of the reference has to be found in the glyph, and every stroke of the glyph in the reference.
    # The chamfer terms cap each pixel's distance so that a bent or shifted stroke costs little - and the cap
    # makes a stroke that is missing altogether cost little too: an E's middle bar lies far from every pixel of
    # a C, every one of its pixels pays the cap, and the cap is small enough that the E's straight stem and flat
    # top and bottom, which a condensed C shares, still win. That read a whole sheet's C as E. So the share of
    # ink on either side that has nothing of the other within a stroke's reach is paid for separately: a
    # deformation is not a missing stroke.
    reach = _R("text.recognize.COVER_REACH", COVER_REACH) * INNER
    gdt = ndimage.distance_transform_edt(~(img > 0)).ravel()
    uncovered_ref = ((gdt[ink_idx] > reach) * ink_valid).sum(axis=1) / np.maximum(counts, 1)
    uncovered_glyph = (dts[:, gpix] > reach).mean(axis=1)
    pen += _R("text.recognize.COVER_WEIGHT", COVER_WEIGHT) * (uncovered_ref + uncovered_glyph)
    score = c + pen
    if not allow_lower:
        score = np.where(lower & ~diacritic, 99.0, score)
    score = np.where(diacritic == has_diacritic, score, 99.0)
    if rel_height >= 0.55:
        score = np.where(small, 99.0, score)
    elif rel_height < 0.35:
        score = np.where(~small, score + 0.08, score)
    best: dict[str, float] = {}
    for i, ch in enumerate(chars):
        v = float(score[i])
        ch = ALIASES.get(ch, ch)
        if ch not in best or v < best[ch]:
            best[ch] = v
    ranked = sorted(best.items(), key=lambda kv: (kv[1], kv[0]))
    best_c, best_s = ranked[0]
    return best_c, best_s, [(a, round(b, 4)) for a, b in ranked[:4]]


UNKNOWN_THRESHOLD = 0.14
COVER_REACH = 0.22      # of the inner box: how far a stroke may lie from the other shape and still be the same stroke
COVER_WEIGHT = 0.10     # score per unit share of ink that has no counterpart within that reach


def decide(char: str, score: float, alternatives: list[tuple[str, float]]) -> tuple[str, bool]:
    """The character to use, and whether it was accepted on a relaxed rule.

    Only a match within the threshold is a reading. Accepting a decisively-best candidate further out was tried
    and rejected: on W-50-1-A-0014 it read every 'S' as '5', and because the misreading was systematic the
    drawing-local grammar then reinforced it. An unnamed character costs one label; a confidently wrong one
    silently splits an identity in two.
    """
    return (char, False) if score <= _R("text.recognize.UNKNOWN_THRESHOLD", UNKNOWN_THRESHOLD) else ("?", False)
