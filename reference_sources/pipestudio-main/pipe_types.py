#!/usr/bin/env python3
import collections
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import re

import cv2
import fitz
import numpy as np
import pytesseract
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

import pipe_rules
import pipe_seg as ps
from pipe_seg import (CONFIG, angle_diff, export_ring, flatten_items, log,
                      seg_angle, seg_len, split_holes)

TYPE_CONFIG = {
    # T1 glyph collection
    "glyph_stroke_width": 0.72,    # pt, label text line weight
    "glyph_max_dim": 9.0,          # pt, max bbox side of a glyph piece
    "text_scale": 4.0,             # px/pt for the text-only OCR raster

    # T2 OCR + grammar
    # The CODE whitelist: what a SYS-MAT-DIM code can be spelled with.  Kept
    # tight on purpose — the grammar pass reads codes with this, and a narrow
    # alphabet is what stops tesseract inventing punctuation inside them.
    "ocr_config": '--psm 11 -c tessedit_char_whitelist='
                  '"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/().ÖÄÅ "',
    # The FREE-TEXT alphabet: label boxes carry more than the code.  The
    # sheets seen so far add an installation elevation ("CL 3250 OFG",
    # "VG+18.92"), a floor or room reference, a fall ("1:100"), a count
    # ("2 ST"), a diameter written with the ring ("ø110").  None of that is
    # a fixed format, so the extra-row pass runs with a wide alphabet and no
    # grammar at all and keeps whatever is in the box verbatim.  Lowercase is
    # included because these notes are not always set in capitals.
    # Quote characters are deliberately absent: they would have to be
    # escaped through the tesseract config argument and no label note needs
    # them.
    "ocr_text_chars": ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                       "abcdefghijklmnopqrstuvwxyz"
                       "0123456789"
                       "-/()., :;+*=%<>#&ÖÄÅöäåØøÆæ "),
    # pt, how far outside a detected label box its own glyphs may reach:
    # ink beyond this is another label's and is painted white before OCR
    "label_edge_margin": 0.75,
    # lettering-only rendering (see `lettering_strokes`): a box is rendered
    # from its own glyph strokes when it holds at least this many glyph-sized
    # black paths; fewer and the pixmap is read as before
    "lettering_min_paths": 4,
    # the stroke notation: a bar is a single straight black stroke at least
    # this heavy (the lettering is 0.72 pt on the 0134 family, the bars
    # 1.44 pt) and at least this long; maximum length comes from the label box
    "bar_min_width": 1.2,          # pt
    "bar_min_len": 3.0,            # pt
    # umlaut dots / rings over a letter: tiny paths of at most this extent,
    # the two dots this far apart (pt)
    "diacritic_max_size": 1.3,     # pt, a ring (Å)
    "diacritic_dot_max": 0.9,      # pt, one dot of Ö / Ä
    "diacritic_dot_gap": (1.0, 3.5),  # pt
    # a competing read of a bare dimension row may win on plausibility when
    # its confidence is within this many points of the chosen one
    "dim_tie_conf": 25.0,
    # Codes are SYSTEM-MATERIAL-DIM with an optional insulation suffix.  The
    # system/material vocabularies are FAMILIES with a numeric variant: the
    # 0134-style sheets write one digit (VS1, KV1, S2), the 0122-style sheets
    # two (VS31, KV01, S01), and the material digits vary the same way
    # (P2 vs P31).  Matching the family plus 1-2 (materials: 1-3) digits
    # accepts both without loosening what counts as a code.
    "systems": ["FJV1", "FJK1", "VP1", "VS1", "VS2", "KV1", "KV2", "VV1",
                "VVC1", "KB1", "D1", "S1", "S2", "S3", "S4"],
    "materials": ["E13", "S6", "S13", "X7", "K5", "X31", "R1",
                  "E4", "P2", "P3", "P5", "R8"],
    "type_granularity": "full",    # "full" keeps /W suffix, "dim" strips it

    # word -> block clustering (in units of word height)
    "word_link_dx": 0.9,           # horizontal reach when linking words
    "word_link_dy": 0.75,          # vertical reach when linking words

    # plain text labels carry no frame: their leader runs just under the text,
    # a couple of points below the OCR box, so the box is grown downwards to
    # reach it.  Labels drawn inside a frame already touch theirs and are left
    # exactly as detected.
    #
    # Only a properly OBLONG box is grown.  Measured over 241 label rows on
    # three sheets, they fall into two populations with nothing in between:
    # single-line codes at aspect >= 5 (~40 x 7 pt, 122 of which need the
    # growth to reach their line) and near-square two-line codes at aspect
    # 1.2-2.5 (~34 x 19 pt, SYS-MAT over DIM), every one of which already
    # touches its line and gains nothing.  The threshold sits in the empty gap.
    "plain_label_grow_down": 3.0,  # pt, added to the bottom of a plain label
    "plain_label_min_aspect": 3.0,  # width/height below this stays untouched
    "label_frame_margin": 8.0,     # pt, how far a frame may sit off the text
    "label_frame_slack": (30.0, 24.0),  # pt, max frame size over the text box

    # T3 leaders — the thin connection-line weights seen across sheets: the
    # 0134 family draws them at 0.48 pt, the 0122 family at 0.36 pt.  Neither
    # sheet family carries the other's width, so accepting both is safe.
    "leader_widths": [0.48, 0.36],  # pt
    "leader_snap": 0.7,            # pt, endpoint chaining tolerance
    "leader_label_tol": 3.0,       # pt, chain end to label block bbox
    "leader_pipe_tol": 3.0,        # pt, chain end to pipe geometry (arrowheads
                                   #     and join circles sit slightly short)

    # T4 bundles
    "bundle_window": 30.0,         # pt, how far from the endpoint bundle
                                   #     members may lie along the leader line
    "bundle_angle": 12.0,          # deg, orientation spread within a bundle
    "bundle_gap_single": 10.0,     # pt, max consecutive spacing when ONE code
                                   #     types a whole parallel bundle
    "bundle_gap_stacked": 10.0,    # pt, max consecutive spacing for stacked
                                   #     N-codes -> N-pipes mapping
    "near_slack": 1.0,             # pt, endpoint contacts within closest+slack
    "circle_tol": 3.0,             # pt, joining-circle centre to chain end

    # T4 proximity attachment (labels placed next to their pipe, no leader)
    "prox_tol": 10.0,              # pt, label bbox to pipe distance
    "prox_max_ratio": 2.0,         # 2nd-nearest run must be this factor farther

    # T4 type diffusion across near-continuous runs (valve batteries etc. chop
    # a line into several components; the label sits on one of them)
    "diffuse_gap": 14.0,           # pt, max endpoint gap to inherit across
    "diffuse_angle": 15.0,         # deg, collinearity of the two runs
    "diffuse_offaxis": 20.0,       # deg, gap vector vs run direction
    "diffuse_rounds": 8,

    # dimensions that exist in these drawings; OCR results snap to them
    # (union of the steel/PEX sizes on the 0134-family sheets and the copper
    # sizes 18/22/42/54/64/76/88/108 the 0122-family sheets use)
    "dims": [8, 10, 12, 15, 16, 18, 20, 22, 25, 28, 32, 35, 40, 42, 50, 54,
             63, 64, 75, 76, 88, 90, 108, 110, 125, 160],

    # T4 run splitting
    "split_resolution": 2.0,       # pt, centreline sampling for type regions
    "direction_tol": 0.75,         # pt, slack on the side test at a join
    # page-reading fallback for which stretch a joining point owns, used only
    # when no explicit signal (tee, elevation, diameter, position) decides —
    # see pipe_rules.choose_downstream:
    #   "forward"  read left->right (top->bottom when the pipe is vertical):
    #              a joining point starts a class that runs on to the next one
    #   "backward" a joining point claims the stretch behind it
    "claim_direction": "backward",
}


# --------------------------------------------------------------------------- #
# T1 + T2 - label blocks via text-only raster and one OCR pass
# --------------------------------------------------------------------------- #
# one entry per code: rect = the code's own text lines, block = whole stack,
# conf = OCR confidence 0-100 (-1 unknown), src = "ocr" (glyph strokes) or
# "text" (real PDF text objects); defaulted so 3-arg construction works
Label = collections.namedtuple("Label",
                               "code rect block conf src text score row "
                               "inherited",
                               defaults=(-1.0, "ocr", "", -1.0, 0, ""))
# code:  the label NAME.  For an ML box this is everything read inside the
#        box on one line — label boxes are not a fixed format, so the name
#        is what the box says (code, elevation, note ...), not a parsed
#        code.  `pipe_rules.parse_code` reads system and dimension off the
#        front of it when a rule needs them
# text:  the same content with one row per line, for display
# score: the ML detector's box score 0-1 when the box came from the model,
#        -1 when the label came from the vector/glyph rules
# row:   position of this code in a stacked box (0 = top).  ML labels keep
#        the model's box as their rect, so a stack's rows share one rect and
#        this is what still orders them top to bottom
# inherited: the note this label received from the LAST label of the ladder
#        line it shares ("CL 3200"), "" when everything in its name is its
#        own.  See `share_ladder_notes`


def _glyph_pieces(drawings, clip):
    tc = TYPE_CONFIG
    for d in drawings:
        if d["type"] != "s" or d.get("color") != (0.0, 0.0, 0.0):
            continue
        w = d.get("width") or 0.0
        if abs(w - tc["glyph_stroke_width"]) > 0.05:
            continue
        r = d["rect"]
        if max(r.width, r.height) > tc["glyph_max_dim"] or \
                max(r.width, r.height) < 0.2:
            continue
        if not (clip.x0 < (r.x0 + r.x1) / 2 < clip.x1 and
                clip.y0 < (r.y0 + r.y1) / 2 < clip.y1):
            continue
        yield d


def _ocr_words(page, drawings, clip):
    """Render only the glyph strokes on white and OCR the whole page once.
    Returns words as (text, fitz.Rect in page pt, confidence 0-100)."""
    tc = TYPE_CONFIG
    S = tc["text_scale"]
    W, H = int(page.rect.width * S), int(page.rect.height * S)
    canvas = np.full((H, W), 255, np.uint8)
    for d in _glyph_pieces(drawings, clip):
        for a, b in flatten_items(d["items"]):
            cv2.line(canvas, (int(a[0] * S), int(a[1] * S)),
                     (int(b[0] * S), int(b[1] * S)), 0, 2, cv2.LINE_AA)
    data = pytesseract.image_to_data(canvas, config=tc["ocr_config"],
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if not t:
            continue
        r = fitz.Rect(data["left"][i] / S, data["top"][i] / S,
                      (data["left"][i] + data["width"][i]) / S,
                      (data["top"][i] + data["height"][i]) / S)
        if r.height < 1.0 or r.height > 20.0:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        words.append((t, r, conf))
    return words


def _text_words(page, clip):
    """Words the PDF carries as real TEXT objects, as (text, rect, conf).

    Two label styles exist in the wild: the 0134-family sheets draw label
    text as 0.72 pt glyph strokes (readable only through `_ocr_words`), while
    the 0122-family sheets carry the very same codes as ordinary PDF text —
    invisible to the glyph path, but extractable losslessly here (conf 100,
    no OCR involved).  Word rectangles are reported in raw, unrotated
    coordinates just like `get_drawings`, so they go through the same
    rotation fix.
    """
    words = []
    mat = page.rotation_matrix if page.rotation else None
    for w in page.get_text("words"):
        t = str(w[4]).strip().upper()
        if not t:
            continue
        r = fitz.Rect(w[0], w[1], w[2], w[3])
        if mat is not None:
            r = (r * mat).normalize()
        if r.height < 1.0 or r.height > 20.0:
            continue
        if not (clip.x0 < (r.x0 + r.x1) / 2 < clip.x1 and
                clip.y0 < (r.y0 + r.y1) / 2 < clip.y1):
            continue
        words.append((t, r, 100.0))
    return words


def _cluster_words(words):
    """Group words into blocks by proximity (expanded-bbox overlap)."""
    tc = TYPE_CONFIG
    n = len(words)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    boxes = []
    for t, r, _conf in words:
        h = r.height
        boxes.append(fitz.Rect(r.x0 - h * tc["word_link_dx"],
                               r.y0 - h * tc["word_link_dy"],
                               r.x1 + h * tc["word_link_dx"],
                               r.y1 + h * tc["word_link_dy"]))
    order = sorted(range(n), key=lambda i: boxes[i].y0)
    for ii, i in enumerate(order):
        for j in order[ii + 1:]:
            if boxes[j].y0 > boxes[i].y1:
                break
            if boxes[i].intersects(boxes[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    blocks = collections.defaultdict(list)
    for i in range(n):
        blocks[find(i)].append(i)
    return list(blocks.values())


_DIM_FIX = str.maketrans({"O": "0", "I": "1", "L": "1", "B": "8", "S": "5"})


def _code_patterns():
    """Build the code grammar from the configured vocabularies.

    Systems and materials are FAMILY + digits: the configured entries are
    reduced to their letter families (VS1 -> VS) and matched with 1-2 digits
    for systems / 1-3 for materials, so VS1 and VS31, P2 and P31 all parse.
    The insulation suffix comes in two drawn spellings: `/W`-style on the
    0134 sheets and `-W40` / `-F60`-style on the 0122 sheets.
    """
    tc = TYPE_CONFIG
    sysfam = sorted({re.sub(r"\d+$", "", s) for s in tc["systems"]},
                    key=len, reverse=True)
    matfam = sorted({re.sub(r"\d+$", "", m) for m in tc["materials"]},
                    key=len, reverse=True)
    sysalt = rf"(?:{'|'.join(sysfam)})\d{{1,2}}"
    # materials read FAMILY + digits, optionally with one trailing letter:
    # the Hyllie sheets write kulvert PEX as X8D / X9D (legend: "PEX, KULVERT
    # 2-RÖRS"), the same X family the config already knows as X7 / X31
    matalt = rf"(?:{'|'.join(matfam)})\d{{1,3}}[A-Z]?"
    ins = r"(?:/[A-Z]{1,3}|-[A-Z]{1,2}\d{1,3})"
    full = re.compile(rf"^({sysalt})-({matalt})(-\d{{2,3}})({ins})?$")
    head = re.compile(rf"^({sysalt})-({matalt})$")
    dim = re.compile(rf"^(\d{{2,3}})(\([A-Z]\))?({ins})?$")
    return full, head, dim


def _parse_codes(lines):
    """Given a block's text lines (top->bottom) as (text, rect, conf), return
    valid pipe-type codes with their own sub-rects and OCR confidence.  A code
    is SYS-MAT[-DIM][/INS] on one line, or SYS-MAT on one line with the
    DIM[/INS] on the next."""
    tc = TYPE_CONFIG
    full, head, dim = _code_patterns()

    def snap_dim(ds):
        """OCR dims snap to the known dimension list (stray glyphs dropped)."""
        if int(ds) in tc["dims"]:
            return ds
        for k in range(len(ds)):
            cand = ds[:k] + ds[k + 1:]
            if cand and int(cand) in tc["dims"]:
                return cand
        return None

    codes = []  # (code, rect, conf)
    i = 0
    while i < len(lines):
        s, r, cf = lines[i][0].replace(" ", ""), lines[i][1], lines[i][2]
        m = full.match(s)
        if m:
            d = snap_dim(m.group(3)[1:])
            if d:
                codes.append((f"{m.group(1)}-{m.group(2)}-{d}{m.group(4) or ''}",
                              fitz.Rect(r), cf))
        elif head.match(s) and i + 1 < len(lines):
            nxt, r2, cf2 = (lines[i + 1][0].replace(" ", ""), lines[i + 1][1],
                            lines[i + 1][2])
            nxt = nxt.translate(_DIM_FIX) if not dim.match(nxt) else nxt
            m = dim.match(nxt)
            if m:
                d = snap_dim(m.group(1))
                if d:
                    both = [c for c in (cf, cf2) if c >= 0]
                    codes.append((f"{s}-{d}{m.group(3) or ''}",
                                  fitz.Rect(r) | r2,
                                  min(both) if both else -1.0))
                i += 1
        i += 1
    if TYPE_CONFIG["type_granularity"] == "dim":
        codes = [(c.split("/")[0], r, cf) for c, r, cf in codes]
    return codes


def _label_frames(drawings, clip):
    """Rectangular outlines a label may be drawn inside.

    A frame is a small closed path of axis-aligned strokes.  Labels that sit in
    one are already bounded by it, so their box is never grown downwards.
    """
    out = []
    for d in drawings:
        if d["type"] not in ("s", "f", "fs") or d.get("color") != (0.0, 0.0, 0.0):
            continue
        r = d["rect"]
        if not (4.0 < r.width < 160.0 and 4.0 < r.height < 120.0):
            continue
        items = list(flatten_items(d["items"]))
        if not (3 <= len(items) <= 6):
            continue
        if any(abs(a[0] - b[0]) > 0.3 and abs(a[1] - b[1]) > 0.3 for a, b in items):
            continue                                # not axis-aligned
        if not (clip.x0 < (r.x0 + r.x1) / 2 < clip.x1 and
                clip.y0 < (r.y0 + r.y1) / 2 < clip.y1):
            continue
        out.append(r)
    return out


def _is_framed(rect, frames):
    tc = TYPE_CONFIG
    m = tc["label_frame_margin"]
    sw, sh = tc["label_frame_slack"]
    return any(f.x0 - m <= rect.x0 and f.y0 - m <= rect.y0 and
               f.x1 + m >= rect.x1 and f.y1 + m >= rect.y1 and
               f.width < rect.width + sw and f.height < rect.height + sh
               for f in frames)


def _is_oblong(rect):
    """Is this box a proper wide rectangle, rather than square-ish?

    Only an oblong box is grown downwards: a square or near-square box is a
    two-line stack whose own bottom row already sits on the leader line.
    """
    return rect.height > 1e-6 and \
        rect.width / rect.height >= TYPE_CONFIG["plain_label_min_aspect"]


def _grow_down(rect, dy):
    return fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1 + dy)


def ocr_workers():
    """Bound concurrent OCR subprocesses. Local runs default to serial."""
    return max(1, min(8, int(os.environ.get("PIPE_OCR_WORKERS", "1"))))


def _ocr_variants(images, scale, origin, whitelist, box):
    return _ocr_render_variants([(images, scale, origin)], whitelist, box)


def _ocr_render_variants(renders, whitelist, box):
    """Parallelize only external Tesseract calls; PDF/geometry stays on caller.

    map preserves variant order, including tie-breaking and failed passes.
    All scales share a pool, so eight CPUs can work even though each scale
    has only four variants. Each subprocess uses OMP_THREAD_LIMIT=1.
    """
    jobs = [(img, f"--psm {psm} -c {whitelist}", scale, origin)
            for images, scale, origin in renders for img in images for psm in (6, 11)]

    def recognize(job):
        img, config, _, _ = job
        try:
            return pytesseract.image_to_data(img, config=config,
                                             output_type=pytesseract.Output.DICT)
        except Exception:
            return None  # Same per-pass failure handling as the serial reader.

    workers = ocr_workers()
    if workers == 1:
        results = list(map(recognize, jobs))
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(jobs)), thread_name_prefix="ocr") as pool:
            results = list(pool.map(recognize, jobs))
    for (img, config, scale, origin), data in zip(jobs, results):
        if data is None:
            continue
        try:
            yield _ocr_word_rows(img, scale, origin, config, inside=box, upper=False, data=data)
        except Exception:
            continue


def _ocr_word_rows(img, S, origin, config, inside=None, upper=True, data=None):
    """One tesseract pass over a rendered box -> text rows (text, Rect, conf),
    top to bottom, in page points.

    `inside`  keep only words whose centre lies in this Rect — the render is
              padded for tesseract's sake, and the padding is where the
              neighbouring label's row shows up
    `upper`   fold to upper case (the code grammar wants that; the free-text
              read keeps the case the drawing uses)
    """
    if data is None:
        data = pytesseract.image_to_data(img, config=config,
                                         output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if not t:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        r = fitz.Rect(origin[0] + data["left"][i] / S,
                      origin[1] + data["top"][i] / S,
                      origin[0] + (data["left"][i] + data["width"][i]) / S,
                      origin[1] + (data["top"][i] + data["height"][i]) / S)
        if inside is not None and not _inside(r, inside):
            continue
        words.append((t.upper() if upper else t, r, conf))
    if not words:
        return []
    words.sort(key=lambda w: (w[1].y0, w[1].x0))
    lines, cur = [], [words[0]]
    for w in words[1:]:
        if abs(w[1].y0 - cur[-1][1].y0) < max(3.0, cur[-1][1].height * 0.6):
            cur.append(w)
        else:
            lines.append(cur)
            cur = [w]
    lines.append(cur)
    rows = []
    for ln in lines:
        ln.sort(key=lambda w: w[1].x0)
        lr = fitz.Rect(ln[0][1])
        for _, r, _c in ln[1:]:
            lr |= r
        confs = [c for _, _, c in ln if c >= 0]
        rows.append((" ".join(t for t, _, _ in ln), lr,
                     min(confs) if confs else -1.0))
    return rows


def find_code(text):
    """The first complete SYS-MAT-DIM[/INS] code anywhere inside `text`, or
    "" — rescues a code the OCR wrapped in stray glyphs.

    A second, tolerant pass accepts a missing dash before the dimension
    ("VS1-S13 22/W" read as one line), but only with a material spelled
    exactly as configured: without the dash the digits are ambiguous
    ("S1322" is S13-22, not S1-32), and the configured list is what settles
    it.
    """
    if not text:
        return ""
    tc = TYPE_CONFIG
    full, _head, _dim = _code_patterns()
    flat = str(text).replace(" ", "").upper()
    m = re.search(full.pattern[1:-1], flat)
    if m:
        try:
            if int(m.group(3)[1:]) not in tc["dims"]:
                return ""
        except (TypeError, ValueError):
            return ""
        code = f"{m.group(1)}-{m.group(2)}{m.group(3)}{m.group(4) or ''}"
    else:
        sysfam = sorted({re.sub(r"\d+$", "", x) for x in tc["systems"]},
                        key=len, reverse=True)
        sysalt = rf"(?:{'|'.join(sysfam)})\d{{1,2}}"
        ins = r"(?:/[A-Z]{1,3}|-[A-Z]{1,2}\d{1,3})"
        code = ""
        for mat in sorted(tc["materials"], key=len, reverse=True):
            m = re.search(rf"({sysalt})-({mat})-?(\d{{2,3}})({ins})?(?![0-9])",
                          flat)
            if m and int(m.group(3)) in tc["dims"]:
                code = f"{m.group(1)}-{m.group(2)}-{m.group(3)}{m.group(4) or ''}"
                break
        if not code:
            # the material families as a pattern (X9D, S13, ...), greedy —
            # the digits split between material and dimension is settled by
            # the known dimension list
            matfam = sorted({re.sub(r"\d+$", "", x) for x in tc["materials"]},
                            key=len, reverse=True)
            m = re.search(rf"({sysalt})-((?:{'|'.join(matfam)})\d{{1,3}}[A-Z]?)"
                          rf"-?(\d{{2,3}})({ins})?(?![0-9])", flat)
            if m and int(m.group(3)) in tc["dims"]:
                code = f"{m.group(1)}-{m.group(2)}-{m.group(3)}{m.group(4) or ''}"
        if not code:
            return ""
    if tc["type_granularity"] == "dim":
        code = code.split("/")[0]
    return code


def _inside(wr, box):
    """A word belongs to a box when its CENTRE lies in the box.

    Labels sit stacked a few points apart (the model draws one box per
    label), so any overlap test on a padded box pulls the neighbour's row in
    and one box reads as two labels.  The centre test keeps a word that
    straddles the edge only when most of it is in.
    """
    return box.contains(fitz.Point((wr.x0 + wr.x1) / 2.0,
                                   (wr.y0 + wr.y1) / 2.0))


def _text_rows_in(page, box):
    """Real PDF text inside `box` as rows (text, Rect, conf=100), top to
    bottom.

    Used when the drawing carries the label as text objects: there is
    nothing to OCR and nothing to lose.  Word rectangles are mapped through
    the page rotation so they land where the detector's boxes are; a word
    counts only when its centre is inside the box (`_inside`).
    """
    mat = page.rotation_matrix if page.rotation else None
    tws = []
    for w in page.get_text("words"):
        wr = fitz.Rect(w[0], w[1], w[2], w[3])
        if mat is not None:
            wr = (wr * mat).normalize()
        if _inside(wr, box):
            tws.append((str(w[4]).strip(), wr))
    if not tws:
        return []
    tws.sort(key=lambda w: (round(w[1].y0, 1), w[1].x0))
    lines, cur = [], [tws[0]]
    for w in tws[1:]:
        if abs(w[1].y0 - cur[-1][1].y0) < 4.0:
            cur.append(w)
        else:
            lines.append(cur)
            cur = [w]
    lines.append(cur)
    rows = []
    for ln in lines:
        lr = fitz.Rect(ln[0][1])
        for _, wr in ln[1:]:
            lr |= wr
        rows.append((" ".join(t for t, _ in ln), lr, 100.0))
    return rows



# --------------------------------------------------------------------------- #
# Lettering-only rendering for the box readers
# --------------------------------------------------------------------------- #
# On the sheets that draw their labels as strokes, everything that shares the
# box with the lettering is drawn in ANOTHER weight or colour: the leader and
# its shelf line (0.48 pt), the heavy stroke bars of the vertical-pipe notation
# over/under a dimension (1.44 pt), the architecture and grid (grey), the
# background stamps ("AA1:1", grey).  Rendered together they are what tesseract
# trips over — a grey grid line through "-X7" reads as "4X7", a bar under "12"
# swallows the 1, a leader through "15" makes "= I Be -" (0111 OCR feedback,
# 2026-09-05).  So the box is rendered from the vectors, lettering strokes
# only, and the pixmap is used only when a page has no such strokes (scanned
# or rasterised input, the synthetic test sheets).
#
# The lettering weight is not a constant: it is the dominant stroke width
# among the glyph-sized black paths inside the box itself, derived per box.

_LETTERING_INDEX = {}   # (doc name, page number) -> _LetteringIndex


class _LetteringIndex:
    """All glyph-sized black stroke paths of a page, indexed for fast per-box
    lookup.  Built once per page (get_drawings is the slow part)."""

    def __init__(self, page):
        tc = TYPE_CONFIG
        mat = page.rotation_matrix if page.rotation else None
        segs, cxs, cys, widths, owner = [], [], [], [], []
        # heavy horizontal bars (stroke notation) are kept apart: they are
        # not lettering, but `stroke_bars` wants them
        bars = []
        for d in page.get_drawings():
            if d["type"] != "s" or d.get("color") != (0.0, 0.0, 0.0):
                continue
            r = fitz.Rect(d["rect"])
            if mat is not None:
                r = (r * mat).normalize()
            w = float(d.get("width") or 0.0)
            long_side = max(r.width, r.height)
            pts = list(flatten_items(d["items"]))
            # Bar length is bounded by the owning label box in stroke_bars,
            # not by a glyph-sized maximum: 50/WB can have a 28 pt bar.
            if (r.height < 0.6 and w >= tc["bar_min_width"] and len(pts) == 1
                    and long_side >= tc["bar_min_len"]):
                bars.append((r, w))
                continue
            if long_side > tc["glyph_max_dim"] or not pts:
                continue
            k = len(cxs)
            for a, b in pts:
                if mat is not None:
                    a = fitz.Point(a) * mat
                    b = fitz.Point(b) * mat
                segs.append((a[0], a[1], b[0], b[1]))
                owner.append(k)
            cxs.append((r.x0 + r.x1) / 2.0)
            cys.append((r.y0 + r.y1) / 2.0)
            widths.append(round(w, 2))
        self.cx = np.array(cxs, dtype=float)
        self.cy = np.array(cys, dtype=float)
        self.width = np.array(widths, dtype=float)
        self.segs = np.array(segs, dtype=float).reshape(-1, 4)
        self.owner = np.array(owner, dtype=int)
        self.bars = bars

    def in_box(self, box, margin):
        """Indices of the paths whose centre lies within `margin` of `box`."""
        if not len(self.cx):
            return np.zeros(0, dtype=int)
        m = ((self.cx > box.x0 - margin) & (self.cx < box.x1 + margin) &
             (self.cy > box.y0 - margin) & (self.cy < box.y1 + margin))
        return np.nonzero(m)[0]


def _lettering_index(page):
    key = (getattr(page.parent, "name", "") or id(page.parent), page.number)
    idx = _LETTERING_INDEX.get(key)
    if idx is None:
        if len(_LETTERING_INDEX) > 8:
            _LETTERING_INDEX.clear()
        idx = _LETTERING_INDEX[key] = _LetteringIndex(page)
    return idx


def lettering_strokes(page, box, margin=None):
    """The lettering strokes of one label box: (segments, width).

    `segments` is an (n, 4) array of x0, y0, x1, y1 in page points, `width`
    the lettering weight derived for this box — the most common stroke width
    among the glyph-sized black paths whose centre lies in the box.  Paths of
    any other width (leader ticks, bars) are left out.  Empty when the page
    draws no such strokes (real text, or a raster)."""
    tc = TYPE_CONFIG
    if margin is None:
        margin = tc["label_edge_margin"]
    idx = _lettering_index(page)
    ids = idx.in_box(box, margin)
    if len(ids) < tc["lettering_min_paths"]:
        return np.zeros((0, 4)), None
    ws, counts = np.unique(idx.width[ids], return_counts=True)
    w = float(ws[np.argmax(counts)])
    keep = ids[np.abs(idx.width[ids] - w) <= 0.05]
    mask = np.isin(idx.owner, keep)
    return idx.segs[mask], w


def render_lettering(segs, width, clip, scale):
    """Draw lettering segments on white: a greyscale image of `clip` at
    `scale` px/pt with the strokes at their true weight."""
    W = max(1, int(round(clip.width * scale)))
    H = max(1, int(round(clip.height * scale)))
    canvas = np.full((H, W), 255, np.uint8)
    t = max(1, int(round(width * scale)))
    for x0, y0, x1, y1 in segs:
        cv2.line(canvas,
                 (int(round((x0 - clip.x0) * scale)),
                  int(round((y0 - clip.y0) * scale))),
                 (int(round((x1 - clip.x0) * scale)),
                  int(round((y1 - clip.y0) * scale))),
                 0, t, cv2.LINE_AA)
    return canvas


def stroke_bars(page, rect, rows=None):
    """The heavy stroke bars of the vertical-pipe notation inside a label box.

    A bar is a short straight black stroke, heavier than the lettering,
    hugging a dimension figure: OVER means up, UNDER means down (drawing
    convention confirmed by the user). Returns
    [{"y", "x0", "x1", "width", "side"}] top to bottom;
    `side` is "over" / "under" relative to the nearest text row when `rows`
    [(text, Rect, conf)] are given, else None.  The reader never folds these
    into the text — they are geometry, and this is where they are kept."""
    box = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    out = []
    dimension_rows = [rw for rw in (rows or [])
                      if re.fullmatch(r"\s*(?:DN\s*|[Øø⌀]\s*)?\d+(?:[.,]\d+)?(?:\s*\(\d+\))?(?:\s*/\s*[A-Za-z0-9()]+)?\s*", rw[0])]
    for r, w in _lettering_index(page).bars:
        cx, cy = (r.x0 + r.x1) / 2.0, (r.y0 + r.y1) / 2.0
        if not (box.x0 <= r.x0 <= r.x1 <= box.x1 and box.y0 <= r.y0 <= r.y1 <= box.y1):
            continue
        side = None
        if rows:
            near = min(dimension_rows or rows, key=lambda rw: abs((rw[1].y0 + rw[1].y1) / 2 - cy))
            side = "over" if cy < (near[1].y0 + near[1].y1) / 2 else "under"
        out.append({"y": round(cy, 2), "x0": round(r.x0, 2),
                    "x1": round(r.x1, 2), "width": round(w, 2), "side": side})
    out.sort(key=lambda b: b["y"])
    return out



def _diacritic_marks(page, box, margin=None):
    """Umlaut dots and rings drawn over the lettering of one box.

    CAD lettering draws the two dots of Ö / Ä as two tiny strokes (0.3-0.7
    pt) side by side above the letter, and the ring of Å as a tiny closed
    curve.  Tesseract never sees them — rendered at lettering weight they
    are specks — so "ÖFG" comes back as "OFG" on every level row (63 of 67
    on 0111).  They are geometry, though, and this reads them as such.
    Returns [(x, y, kind)] with kind "dots" or "ring", x/y the mark centre."""
    tc = TYPE_CONFIG
    if margin is None:
        margin = tc["label_edge_margin"]
    idx = _lettering_index(page)
    ids = idx.in_box(box, margin)
    tiny = []
    for k in ids:
        sg = idx.segs[idx.owner == k]
        if not len(sg):
            continue
        ext = max(sg[:, [0, 2]].max() - sg[:, [0, 2]].min(),
                  sg[:, [1, 3]].max() - sg[:, [1, 3]].min())
        if ext > tc["diacritic_max_size"]:
            continue
        # a ring is one path of several curve pieces that closes on itself;
        # a dot is a single short stroke.  Glyph fragments (the arcs of an
        # "8" or "S") are neither: open, or too long for a dot.
        closed = (len(sg) >= 3 and
                  math.hypot(sg[0, 0] - sg[-1, 2], sg[0, 1] - sg[-1, 3]) < 0.2)
        if closed:
            tiny.append((float(idx.cx[k]), float(idx.cy[k]), "ring"))
        elif len(sg) <= 2 and ext <= tc["diacritic_dot_max"]:
            tiny.append((float(idx.cx[k]), float(idx.cy[k]), "dot"))
    marks, used = [], set()
    tiny.sort()
    for i, (x, y, kind) in enumerate(tiny):
        if i in used:
            continue
        if kind == "ring":
            marks.append((x, y, "ring"))
            used.add(i)
            continue
        for j in range(i + 1, len(tiny)):
            x2, y2, kind2 = tiny[j]
            if x2 - x > tc["diacritic_dot_gap"][1]:
                break
            if j in used or kind2 != "dot" or x2 - x < tc["diacritic_dot_gap"][0]:
                continue
            if abs(y2 - y) < 0.4:
                marks.append(((x + x2) / 2, (y + y2) / 2, "dots"))
                used.update((i, j))
                break
    return marks


_DIACRITIC = {"dots": {"O": "Ö", "A": "Ä", "o": "ö", "a": "ä"},
              "ring": {"A": "Å", "a": "å"}}


def _apply_diacritics(rows, marks):
    """Put the drawn dots / rings onto the letters tesseract read under them.

    A mark belongs to the row whose top it sits on, and to the character
    whose slot in that row lies under it: CAD lettering is set at a fixed
    pitch, so the slot is the row's width divided by its character count.
    Only a letter that can carry the mark is changed; anything else is left
    as read."""
    if not marks or not rows:
        return rows
    out = list(rows)
    for x, y, kind in marks:
        best, bi = None, -1
        for i, (t, r, c) in enumerate(out):
            if not (r.x0 - 1.0 <= x <= r.x1 + 1.0):
                continue
            # the mark sits on the upper part of its row (or just above it)
            if not (r.y0 - 1.5 <= y <= r.y0 + 0.45 * r.height):
                continue
            d = abs(y - r.y0)
            if best is None or d < best:
                best, bi = d, i
        if bi < 0:
            continue
        t, r, c = out[bi]
        if not t:
            continue
        pitch = r.width / len(t)
        k = int((x - r.x0) / pitch) if pitch > 0 else 0
        table = _DIACRITIC[kind]
        for kk in (k, k - 1, k + 1):
            if 0 <= kk < len(t) and t[kk] in table:
                out[bi] = (t[:kk] + table[t[kk]] + t[kk + 1:], r, c)
                break
    return out


def _row_quality(row):
    t, _r, c = row
    return (max(c, 0.0), sum(ch.isalnum() for ch in t))


def _best_rows_per_line(candidates):
    """Combine the OCR passes row by row.

    `candidates` is a list of row lists, one per pass, each [(text, Rect,
    conf)].  Rows of different passes that sit on the same line (centres
    closer than half a row height) are one line; the line keeps the row read
    with the highest confidence.  A pass that reads "S3-R8" well at 10 px/pt
    and one that reads the "75" under it well at 4 px/pt thus both
    contribute — one render never suits every row of a box.

    Returns [(row, alternatives)] top to bottom, `alternatives` being the
    other distinct texts read on that line with their best confidence."""
    lines = []   # [centre_y, height, best_row, {text: best_conf}]
    for rows in candidates:
        for row in rows:
            t, r, c = row
            cy, h = (r.y0 + r.y1) / 2.0, r.height
            for ln in lines:
                if abs(ln[0] - cy) < 0.5 * max(h, ln[1]):
                    ln[3][t] = max(ln[3].get(t, -1.0), c)
                    if _row_quality(row) > _row_quality(ln[2]):
                        ln[0], ln[1], ln[2] = cy, h, row
                    break
            else:
                lines.append([cy, h, row, {t: c}])
    lines.sort(key=lambda ln: ln[0])
    return [(ln[2], {t: c for t, c in ln[3].items() if t != ln[2][0]})
            for ln in lines]


def _system_min_dim(system):
    """Smallest pipe dimension a system is drawn with: fixture branches on
    gravity systems (S*, D*, not SL) start at DN32, pressure pipes at DN8."""
    s = (system or "").upper()
    return 32 if (s[:1] in ("S", "D") and s != "SL") else 8


def _settle_dimension_rows(lines):
    """Where the passes disagree on a bare dimension row, let the system
    decide the tie.

    Tesseract reads the CAD "7" as "1" in some renders and as "7" in others
    ("75" under "S3-R8" came back as 75, 15 and 715 across scales, all with
    confidence 70-93).  Both readings are dimensions, so only the system
    tells them apart: a spillvatten branch is never DN15.  When the chosen
    read is not a possible dimension for the system on the row above and a
    competing read within `dim_tie_conf` confidence points is, the competing
    read is taken.  Nothing is invented — every candidate was read off the
    render — and the choice is recorded nowhere else than in which read
    survives, exactly like the confidence pick."""
    tc = TYPE_CONFIG
    out, system = [], None
    for row, alts in lines:
        t, r, c = row
        m = re.match(r"^\(?([A-ZÅÄÖ]{1,4}\d{0,3})-", t.strip().upper())
        if m:
            system = m.group(1)
        dm = re.match(r"^(\d{1,3})(.*)$", t.strip())
        if dm and system and alts:
            lo = _system_min_dim(system)
            if int(dm.group(1)) < lo or int(dm.group(1)) not in tc["dims"]:
                best = None
                for at, ac in alts.items():
                    am = re.match(r"^(\d{2,3})(.*)$", at.strip())
                    if not am or am.group(2) != dm.group(2):
                        continue
                    d = int(am.group(1))
                    if d >= lo and d in tc["dims"] and \
                            ac >= c - tc["dim_tie_conf"]:
                        if best is None or ac > best[1]:
                            best = (at, ac)
                if best is not None:
                    row = (best[0], r, best[1])
        out.append(row)
    return out


def read_label_content(page, rect, pad=2.0):
    """Read EVERYTHING inside one label box, with no grammar imposed.

    Label boxes are not a fixed format.  Besides the SYS-MAT-DIM code they
    carry whatever the projector wrote next to it — an installation elevation
    ("CL 3250 OFG", "VG+18.92"), a floor or room reference, a fall, a count,
    a note.  What this reads IS the label (`labels_from_boxes` names the
    label with it), so nothing in the box may be lost and nothing outside it
    may leak in: only words whose centre lies inside the box count, and ink
    beyond `label_edge_margin` outside the box is painted white before OCR.

    Returns (text, rows, src):
      text  every row joined with newlines, top to bottom, verbatim
      rows  [(text, Rect, conf)] the individual rows, in page points
      src   "text" when the drawing carried real PDF text, "ocr" otherwise

    Vector text wins when the drawing has it: it is lossless and needs no
    alphabet.  Otherwise the box is rendered and read with the wide
    `ocr_text_chars` alphabet in psm 6 (a block of lines) and psm 11
    (sparse), ink-only and greyscale, at several scales.

    On a page that draws its labels as strokes the render is made from the
    LETTERING STROKES only (`lettering_strokes`): the leader and its shelf,
    the heavy bars of the vertical-pipe notation, grid lines and grey stamps
    never reach tesseract (0111 OCR feedback, 2026-09-05).  The passes are
    then combined line by line (`_best_rows_per_line`), a disputed bare
    dimension row is settled by what is a possible dimension for the system
    above it (`_settle_dimension_rows`), and the umlaut dots / rings drawn
    over the letters are read from the vectors (`_apply_diacritics`).  On a
    page without such strokes (a raster) the pixmap is read as before and the
    pass with the most confidently read characters wins.
    """
    tc = TYPE_CONFIG
    S = tc["text_scale"]
    box = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    # the render is padded (tesseract wants a quiet margin), the WORDS are
    # not: only what has its centre inside the box belongs to this label
    r = fitz.Rect(box.x0 - pad, box.y0 - pad, box.x1 + pad, box.y1 + pad)

    rows = _text_rows_in(page, box)
    if rows:
        return ("\n".join(t for t, _, _ in rows), rows, "text")

    whitelist = f'tessedit_char_whitelist="{tc["ocr_text_chars"]}"'
    # Ink outside the box is painted white before tesseract sees it, beyond
    # a thin band that rescues a glyph the detector's box cut through.  The
    # next label of a stack starts right under this box, and its glyph tops
    # in the crop are what tesseract otherwise merges into this box's row.
    m = tc["label_edge_margin"]
    best_rows, best_q, passes = [], -1.0, []
    # Lettering only, when the page draws its labels as strokes: the leader,
    # the stroke bars, grid lines and grey stamps never reach tesseract.
    segs, lw = lettering_strokes(page, box, m)
    scales = (S * 2, S * 1.5, S) if lw else (S * 1.5, S)
    renders = []
    for scale in scales:
        if lw:
            gray = render_lettering(segs, lw, r, scale)
        else:
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=r)
            img = np.frombuffer(pix.samples, np.uint8).reshape(
                pix.height, pix.width, pix.n)
            gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY) \
                if pix.n >= 3 else img[:, :, 0]
            gray = np.ascontiguousarray(gray)
            h, w = gray.shape
            x0 = max(0, int((box.x0 - m - r.x0) * scale))
            y0 = max(0, int((box.y0 - m - r.y0) * scale))
            x1 = min(w, int(math.ceil((box.x1 + m - r.x0) * scale)))
            y1 = min(h, int(math.ceil((box.y1 + m - r.y0) * scale)))
            gray[:y0, :] = 255
            gray[y1:, :] = 255
            gray[:, :x0] = 255
            gray[:, x1:] = 255
        gray = cv2.copyMakeBorder(gray, 8, 8, 8, 8, cv2.BORDER_CONSTANT,
                                  value=255)
        origin = (r.x0 - 8 / scale, r.y0 - 8 / scale)
        _, bw = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        renders.append(((bw, gray), scale, origin))
    for got in _ocr_render_variants(renders, whitelist, box):
        got = [(t.strip(), rr, c) for t, rr, c in got if t.strip()]
        if not got:
            continue
        passes.append(got)
        # the pass with the most CONFIDENTLY read characters wins:
        # a pass that dropped a row loses that row's characters, a
        # pass that read fragments as garbage carries them at low
        # confidence.  Confidence is per row (its weakest word).
        q = sum(sum(ch.isalnum() for ch in t) * max(c, 0.0) / 100.0
                for t, _, c in got)
        if q > best_q:
            best_rows, best_q = got, q
    if lw:
        # lettering render: the rows are compared line by line across the
        # passes, and the drawn umlaut dots / rings go back onto the letters
        best_rows = _settle_dimension_rows(_best_rows_per_line(passes))
        best_rows = _apply_diacritics(best_rows, _diacritic_marks(page, box, m))
    return ("\n".join(t for t, _, _ in best_rows), best_rows, "ocr")


def read_label_codes(page, rect, pad=2.0):
    """Read the codes inside one label box on the rendered page.

    The GRAMMAR reader.  Not on the ML path any more: an ML box is named by
    `read_label_content`, whatever it says.  Kept for callers that want the
    parsed SYS-MAT-DIM codes of a box (one per row of a stack).

    Returns (codes, raw_text, src): codes as [(code, Rect, conf)] top to
    bottom — a stacked label yields one per row — raw_text as the best text
    read when nothing parsed (so the user can correct it), and src "text"
    when the drawing carried the label as real PDF text, "ocr" otherwise.

    Vector text first: when the drawing carries the label as real PDF text
    (the 0122-family sheets), reading it beats OCR every time.  Otherwise
    the box is rendered at `text_scale` and read with tesseract in several
    ways — near-black ink only and full greyscale, as one block (psm 6) and
    as sparse text (psm 11) — and the first pass whose rows parse to a code
    wins; the grammar (`_parse_codes`) is the judge, so a misread in one
    pass costs nothing when another gets it right.
    """
    tc = TYPE_CONFIG
    S = tc["text_scale"]
    r = fitz.Rect(rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad)

    box = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    rows = [(t.upper(), rr, c) for t, rr, c in _text_rows_in(page, box)]
    if rows:
        codes = _parse_codes(rows)
        if codes:
            return codes, " ".join(c for c, _, _ in codes), "text"
        raw = " ".join(t for t, _, _ in rows).strip()
        if raw:
            return [], raw, "text"

    whitelist = tc["ocr_config"].split("-c ", 1)[1]
    best_raw, best_n = "", -1
    passes = []
    # the sharper render first: at 4 px/pt tesseract drops a digit now and
    # then ("110(L)" -> "10(L)", both valid dimensions), at 6 px/pt it does
    # not.  Every pass that parses is a candidate and the best row confidence
    # wins; a confident read ends the search early.
    for scale in (S * 1.5, S):
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=r)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)
        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY) \
            if pix.n >= 3 else img[:, :, 0]
        # a quiet margin helps tesseract with small crops
        gray = cv2.copyMakeBorder(gray, 8, 8, 8, 8, cv2.BORDER_CONSTANT,
                                  value=255)
        origin = (r.x0 - 8 / scale, r.y0 - 8 / scale)
        # near-black ink only: background linework the box happens to cross
        # is usually grey or thin and drops out of the threshold
        _, bw = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        for img_ in (bw, gray):
            for psm in (6, 11):
                passes.append((img_, scale, origin, psm))
    best = None                    # (confidence, codes)
    for img_, scale, origin, psm in passes:
        cfg = f"--psm {psm} -c {whitelist}"
        try:
            rows = _ocr_word_rows(img_, scale, origin, cfg, inside=box)
        except Exception:
            continue
        if not rows:
            continue
        # brackets and dots the OCR picks up from the frame or the
        # underline are not part of any code
        rows = [(re.sub(r"^[^A-Z0-9]+|[^A-Z0-9/)]+$", "", t), r, c)
                for t, r, c in rows]
        rows = [(t, r, c) for t, r, c in rows if t]
        if not rows:
            continue
        codes = _parse_codes(rows)
        if not codes:
            raw = " ".join(t for t, _, _ in rows).strip()
            code = find_code(raw)
            if code:
                # a rescued read is a weak one, whatever tesseract says
                codes = [(code, fitz.Rect(rect), min(rows[0][2], 30.0))]
            else:
                n = sum(ch.isalnum() for ch in raw)
                if n > best_n:
                    best_raw, best_n = raw, n
                continue
        conf = min((c for _, _, c in codes), default=-1.0)
        if best is None or conf > best[0]:
            best = (conf, codes)
        if conf >= 60.0:
            break
    if best is not None:
        codes = best[1]
        return codes, " ".join(c for c, _, _ in codes), "ocr"
    return [], best_raw, "ocr"


def read_label_text(page, rect, pad=2.0):
    """Read a single label box straight from the rendered page.

    Used when the review app's user draws a label box by hand.  Returns
    (name, text): the label name — everything inside the box on one line,
    exactly as `labels_from_boxes` would name it — and the same content with
    one row per line.  Both are "" when nothing readable is there.
    """
    text, _rows, _src = read_label_content(page, rect, pad)
    text = (text or "").strip()
    return label_name(text), text


def _labels_from_words(words, frames):
    """Cluster words into blocks, parse the grammar, grow plain boxes.

    One word source at a time: mixing OCR words with vector-text words before
    clustering lets a stray OCR misread land on the same text line as a
    genuine code and corrupt its parse, so `detect_labels` runs this per
    source and merges the results instead.
    """
    grow = TYPE_CONFIG["plain_label_grow_down"]
    n_framed = n_square = n_grown = 0
    labels, n_noise = [], 0
    for idxs in _cluster_words(words):
        ws = [words[i] for i in idxs]
        # group block words into text lines by y-centre
        lines = []  # (yc, [word])
        for t, r, cf in sorted(ws, key=lambda w: (w[1].y0, w[1].x0)):
            yc = (r.y0 + r.y1) / 2
            for ln in lines:
                if abs(ln[0] - yc) < r.height * 0.6:
                    ln[1].append((t, r, cf))
                    break
            else:
                lines.append([yc, [(t, r, cf)]])
        lines.sort(key=lambda ln: ln[0])
        merged = []
        for _, lws in lines:
            lws.sort(key=lambda w: w[1].x0)
            lr = fitz.Rect(lws[0][1])
            for _, r, _c in lws[1:]:
                lr |= r
            confs = [c for _, _, c in lws if c >= 0]
            merged.append((" ".join(t for t, _, _ in lws), lr,
                           min(confs) if confs else -1.0))
        codes = _parse_codes(merged)
        block = fitz.Rect()
        for _, r, _c in ws:
            block |= r
        if codes:
            # The block travels with every row, so it grows on its own shape.
            blk = _grow_down(block, grow) if _is_oblong(block) and \
                not _is_framed(block, frames) else block
            for code, rect, conf in codes:
                # A plain, oblong label's leader runs just under the text, a
                # couple of points below the OCR box — grow the box down to
                # reach it.  Every oblong row of a stack has its own line
                # beneath it, so every one of them grows.  Framed labels are
                # already bounded by their frame, and a square-ish box is a
                # two-line code whose own bottom row already sits on the line.
                if _is_framed(rect, frames):
                    n_framed += 1
                elif not _is_oblong(rect):
                    n_square += 1
                else:
                    n_grown += 1
                    labels.append(Label(code, _grow_down(rect, grow), blk, conf))
                    continue
                labels.append(Label(code, rect, blk, conf))
        else:
            n_noise += 1
    return labels, {"words": len(words), "noise": n_noise, "grown": n_grown,
                    "framed": n_framed, "square": n_square}


def detect_labels(page, drawings, clip):
    frames = _label_frames(drawings, clip)
    txt_labels, ts = _labels_from_words(_text_words(page, clip), frames)
    txt_labels = [l._replace(src="text") for l in txt_labels]
    ocr_labels, os_ = _labels_from_words(_ocr_words(page, drawings, clip),
                                         frames)
    # The same label never exists as both text and strokes, but be safe: an
    # OCR label overlapping a text label is the same thing read twice, and the
    # text version is the lossless one.
    labels = list(txt_labels)
    labels += [l for l in ocr_labels
               if not any(l.rect.intersects(t.rect) for t in txt_labels)]
    log(f"T1/T2: {ts['words']} text words + {os_['words']} OCR words -> "
        f"{len(labels)} valid label codes ({len(txt_labels)} from vector "
        f"text, {len(labels) - len(txt_labels)} from glyph OCR; "
        f"{ts['noise'] + os_['noise']} noise blocks, "
        f"{ts['grown'] + os_['grown']} plain labels grown "
        f"{TYPE_CONFIG['plain_label_grow_down']:g}pt down)")
    return labels


def label_name(text):
    """The label name from the text read inside a box: the rows in reading
    order on one line, single-spaced.  The name IS what the box says."""
    return " ".join(str(text or "").split())


def labels_from_boxes(page, boxes):
    """One Label per box the ML detector found, named by what is inside it.

    boxes  [(x0, y0, x1, y1, score)] in page points, score 0-1

    Every box is exactly one label, and its name (`code`) is the text read
    inside that box — no grammar decides what counts, because label boxes are
    not a fixed format: the code, an installation elevation ("CL 3250 ÖFG",
    "VG+18.92"), a room number, a note, whatever the projector wrote.  `text`
    keeps the same content with one row per line for display; `code` is the
    single-line form.  Only words whose centre lies inside the box belong to
    it, so the neighbouring label of a stack never reads into this one.

    The box comes through as it was detected, as both `rect` and `block`;
    nothing is grown, clipped or re-fitted to the text.  A box nothing could
    be read in is a label with an empty name, so the review UI shows the box
    and lets the user type it.
    """
    out = []
    n_text = n_blank = 0
    for x0, y0, x1, y1, score in boxes:
        r = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
        try:
            content, rows, src = read_label_content(
                page, [r.x0, r.y0, r.x1, r.y1])
        except Exception as exc:               # one unreadable box is not fatal
            log(f"T2 (ML box): OCR failed on {r}: {exc}")
            content, rows, src = "", [], "ocr"
        name = label_name(content)
        confs = [c for _, _, c in rows if c >= 0]
        conf = min(confs) if confs else -1.0
        if name:
            if src == "text":
                n_text += 1
        else:
            n_blank += 1
        out.append(Label(code=name, rect=fitz.Rect(r), block=fitz.Rect(r),
                         conf=float(conf), src=src, text=content.strip(),
                         score=float(score)))
    log(f"T2 (ML boxes): {len(boxes)} label boxes -> {len(out)} labels "
        f"({n_text} read from vector text, {len(out) - n_blank - n_text} by "
        f"OCR, {n_blank} unreadable)")
    return out


def use_ai_detector():
    """The ML detector finds the label boxes unless AI_DETECTOR is switched
    off (0/false/off), which restores the vector/glyph label rules.  Joining
    points come from the vector content (the drawn circles) either way."""
    return os.environ.get("AI_DETECTOR", "1").strip().lower() not in \
        ("0", "false", "no", "off")


def detect_marks(page, drawings, clip, conf=None):
    """Labels, joining marks and the learned signature of one page.  `conf`
    is the ML score floor (default pipe_ai.CONFIG["conf"]).

    Returns (labels, marks, signature):
      labels     every label found — code may be "" for a box nothing parsed in
      marks      the designation marks a connection line ends on, as
                 (cx, cy, r); `assign_types` snaps leader ends to them
      signature  pipe_signature.Signature: the pipe families, connection-line
                 and glyph weights read AT the joining points.  Every joining
                 point sits on a valid pipe, so the widest stroke under it is
                 pipe ink whatever the drawing style — the vector stages then
                 recognise every pipe of those styles across the whole sheet,
                 with the configured width band only as the fallback
                 (`signature.source == "config"`).

    Joining points are ALWAYS the drawn joining circles of the vector content
    (`find_join_circles`); the model (v3) detects labels only.  With the ML
    detector (default): the model's label boxes — both classes, `Label_Box`
    and `type2_label` — read by OCR (`labels_from_boxes`), and the signature
    is learned at the drawn circles a connection line lands on
    (`vector_join_seeds`, the joining points the model used to detect).  With
    AI_DETECTOR=0: the glyph/vector label rules, as before.  Nothing here is
    gated by the frame clip or the walls — callers filter what feeds
    assignment (`assignable_labels`), what is shown stays whole.
    """
    import pipe_signature
    marks = find_join_circles(drawings, clip)
    if use_ai_detector():
        import pipe_ai
        ai = pipe_ai.detect_on_page(page, conf=conf)
        labels = labels_from_boxes(page, ai.label_boxes)
        seeds = vector_join_seeds(drawings, labels, clip, marks)
        sig = pipe_signature.learn_signature(drawings, clip, seeds,
                                             list(ai.label_boxes))
        n_type2 = sum(1 for b in ai.label_boxes
                      if getattr(b, "kind", "") == pipe_ai.TYPE2_LABEL_CLASS)
        log(f"T1-T3 (ML): {len(ai.label_boxes)} label boxes ({n_type2} "
            f"type2_label) on {ai.provider}; {len(marks)} drawn joining "
            f"circles, {len(seeds)} of them at a connection-line end")
        return labels, marks, sig
    return (detect_labels(page, drawings, clip), marks,
            pipe_signature.Signature())


def vector_join_seeds(drawings, labels, clip, circles, pad=2.0):
    """The drawn joining circles a connection line ends on, as signature
    seeds (cx, cy, r, 1.0).

    The v1/v2 model detected joining points, and the signature was learned
    at the confident ones.  The v3 model detects labels only, and a sheet
    carries many more small circles than joining points (valves, fittings,
    symbols), so seeding at EVERY drawn circle would teach annotation weights
    as pipe families.  A circle a traced connection line (at the configured
    leader weights) ends within `pad` pt of is a joining point; those give
    the same signature the model's joining points gave.
    """
    if not circles:
        return []
    ends = [p for ch in trace_leaders(drawings, labels, clip)
            for p, _ in ch["ends"]]
    if not ends:
        return []
    pts = [Point(p) for p in ends]
    tree = STRtree(pts)
    out = []
    for cx, cy, r in circles:
        c = Point(cx, cy)
        reach = r + pad
        if any(pts[int(i)].distance(c) <= reach
               for i in tree.query(c.buffer(reach))):
            out.append((cx, cy, r, 1.0))
    return out


def assignable_labels(labels, clip, wall_geom):
    """The labels assignment may use: with a code, inside the drawing frame,
    outside the wall regions.  Returns (labels, indices into `labels`)."""
    keep = []
    for i, l in enumerate(labels):
        if not l.code:
            continue
        cx, cy = (l.rect.x0 + l.rect.x1) / 2, (l.rect.y0 + l.rect.y1) / 2
        if clip is not None and not (clip.x0 < cx < clip.x1 and
                                     clip.y0 < cy < clip.y1):
            continue
        keep.append(i)
    walled = set()
    if wall_geom is not None and not wall_geom.is_empty:
        for i in keep:
            l = labels[i]
            if wall_geom.contains(Point((l.rect.x0 + l.rect.x1) / 2,
                                        (l.rect.y0 + l.rect.y1) / 2)):
                walled.add(i)
        if walled:
            log(f"T2b: dropped {len(walled)} labels inside wall regions")
    keep = [i for i in keep if i not in walled]
    return [labels[i] for i in keep], keep


def share_ladder_notes(labels, chains, tol=None):
    """Give every label on a ladder line the note its last label carries.

    One connection line often serves a whole stack of labels: it runs past
    each box and on to the joining point.  The installation note that applies
    to all of them — "CL 3200", "CL 2650 ÖFG" — is written once, on the LAST
    label in reading order (bottom of a vertical stack, right end of a row);
    the labels above it carry only their code.  A label on a line of its own
    says what it says, note or none, and is not touched.

    `labels` every detected label, `chains` from `trace_leaders`.  Returns the
    labels with the shared note appended to the name (`code`) and the rows
    (`text`) of each label that lacked one, and recorded in `inherited`;
    everything else is returned as it came, in the same order.  The rules
    themselves live in `pipe_rules` so the review app applies the same ones
    to the labels the user has edited.
    """
    if not labels or not chains:
        return list(labels)
    tol = TYPE_CONFIG["leader_label_tol"] if tol is None else tol
    coded = [i for i, l in enumerate(labels) if l.code]
    boxes = [(labels[i].block.x0, labels[i].block.y0,
              labels[i].block.x1, labels[i].block.y1) for i in coded]
    paths = [ch["segs"] for ch in chains if ch.get("segs")]
    groups = pipe_rules.ladder_groups(paths, boxes, tol)
    if not groups:
        return list(labels)
    names = [labels[i].code for i in coded]
    prior = [getattr(labels[i], "inherited", "") for i in coded]
    changes = pipe_rules.share_ladder_notes(names, groups, prior)
    out = list(labels)
    for k, (name, note) in changes.items():
        l = labels[coded[k]]
        # the rows: drop a stale inherited row, then add the shared note
        rows = [r for r in (l.text or "").split("\n") if r.strip()]
        if prior[k] and rows and rows[-1].strip() == prior[k]:
            rows = rows[:-1]
        rows.append(note)
        out[coded[k]] = l._replace(code=name, text="\n".join(rows),
                                   inherited=note)
    log(f"T2c: {len(groups)} label stacks on shared connection lines, "
        f"{len(changes)} labels took the last label's note")
    return out


# --------------------------------------------------------------------------- #
# T3 - leader tracing
# --------------------------------------------------------------------------- #
def trace_leaders(drawings, labels, clip, max_width=None):
    """Chain thin connection-line strokes; return chains as lists of segments
    plus their degree-1 endpoints.

    Which strokes qualify:
      max_width   every near-black stroke strictly thinner than this — the
                  signature learned from the ML joining points passes its
                  `leader_max` (thinner than the thinnest pipe family is
                  annotation ink), so the connection lines are found whatever
                  weight the drawing office picked
      None        the configured `leader_widths`, plus the glyph stroke width
                  when every detected label came from vector TEXT: on such
                  sheets (the 0122 family) no stroke is lettering, and the
                  label->pipe connection lines are drawn at exactly that
                  weight.  On glyph-stroke sheets (the 0134 family) that
                  width IS the lettering and must never be chained as leaders.
    """
    tc = TYPE_CONFIG
    widths = list(tc["leader_widths"])
    glyph_w = tc["glyph_stroke_width"]
    if labels and all(getattr(l, "src", "ocr") == "text" for l in labels) \
            and not any(abs(glyph_w - w) <= 0.05 for w in widths):
        widths.append(glyph_w)
    segs = []
    seen = set()
    for d in drawings:
        if d["type"] != "s":
            continue
        col = d.get("color")
        if max_width is not None:
            if col is None or max(col) > 0.3:
                continue
        elif col != (0.0, 0.0, 0.0):
            continue
        w = d.get("width") or 0.0
        if max_width is not None:
            if not (0.0 < w < max_width):
                continue
        elif not any(abs(w - lw) <= 0.05 for lw in widths):
            continue
        for a, b in flatten_items(d["items"]):
            if seg_len(a, b) < 1e-3:
                continue
            if max_width is not None:
                # CAD exports double-draw strokes (and a closed two-point path
                # is the same line there and back).  A duplicated leader has no
                # free end — every endpoint meets its twin — so the chain could
                # never be tied to a joining point.  Keep one copy.
                ka = (round(a[0], 2), round(a[1], 2))
                kb = (round(b[0], 2), round(b[1], 2))
                key = (ka, kb) if ka <= kb else (kb, ka)
                if key in seen:
                    continue
                seen.add(key)
            mx = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if not (clip.x0 < mx[0] < clip.x1 and clip.y0 < mx[1] < clip.y1):
                continue
            segs.append((a, b))

    # endpoint graph
    cell = tc["leader_snap"]
    grid = collections.defaultdict(list)
    pts = []
    for i, (a, b) in enumerate(segs):
        for p in (a, b):
            pts.append((i, p))
            grid[(round(p[0] / cell), round(p[1] / cell))].append(len(pts) - 1)

    parent = list(range(len(segs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    degree = collections.defaultdict(int)   # endpoint index -> contacts
    for idx, (i, p) in enumerate(pts):
        kx, ky = round(p[0] / cell), round(p[1] / cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for jdx in grid[(kx + dx, ky + dy)]:
                    j, q = pts[jdx]
                    if j == i or jdx <= idx:
                        continue
                    if seg_len(p, q) <= cell:
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            parent[rj] = ri
                        degree[idx] += 1
                        degree[jdx] += 1

    chains = collections.defaultdict(lambda: {"segs": [], "ends": []})
    for i, (a, b) in enumerate(segs):
        chains[find(i)]["segs"].append((a, b))
    for idx, (i, p) in enumerate(pts):
        if degree[idx] == 0:
            chains[find(i)]["ends"].append((p, segs[i]))
    return list(chains.values())


# --------------------------------------------------------------------------- #
# T4 - attach labels to pipe runs
# --------------------------------------------------------------------------- #
def _rect_dist(r, p):
    dx = max(r.x0 - p[0], 0, p[0] - r.x1)
    dy = max(r.y0 - p[1], 0, p[1] - r.y1)
    return math.hypot(dx, dy)


def find_join_circles(drawings, clip):
    """Small black circles drawn where a leader designates its pipe."""
    out = []
    for d in drawings:
        if d["type"] != "s" or d.get("color") != (0.0, 0.0, 0.0):
            continue
        r = d["rect"]
        dia = max(r.width, r.height)
        if not (0.8 < dia < 6.0):
            continue
        kinds = collections.Counter(it[0] for it in d["items"])
        if kinds.get("c", 0) >= 2 and kinds.get("l", 0) <= 1:
            cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
            if clip.x0 < cx < clip.x1 and clip.y0 < cy < clip.y1:
                out.append((cx, cy, dia / 2))
    return out


def filter_walled_labels(labels, wall_geom):
    """Labels inside hatched wall regions (out-of-scope areas) are ignored,
    matching pipe_seg's wall exclusion for the pipes themselves."""
    if wall_geom.is_empty:
        return labels
    kept = [l for l in labels
            if not wall_geom.contains(Point((l.rect.x0 + l.rect.x1) / 2,
                                            (l.rect.y0 + l.rect.y1) / 2))]
    if len(kept) != len(labels):
        log(f"T2b: dropped {len(labels) - len(kept)} labels inside wall regions")
    return kept


def assign_types(chains, labels, pipe_segs, seg_root, circles=(),
                 wall_geom=None):
    """Returns {comp_root: [(code, Point, seg_idx)]} and debug attachments."""
    tc = TYPE_CONFIG
    in_wall = (lambda x, y: False) if wall_geom is None or wall_geom.is_empty \
        else (lambda x, y: wall_geom.contains(Point(x, y)))
    # an empty STRtree is legal and simply matches nothing, so a drawing with
    # no readable labels (or no pipes) degrades to "everything Unknown"
    # instead of crashing
    label_tree = STRtree([Polygon([(l.block.x0, l.block.y0), (l.block.x1, l.block.y0),
                                   (l.block.x1, l.block.y1), (l.block.x0, l.block.y1)])
                          for l in labels])
    pipe_geoms = [LineString([sg["a"], sg["b"]]) for sg in pipe_segs]
    pipe_tree = STRtree(pipe_geoms)
    # designation marks: drawn circles (cx, cy, r) or ML joining points
    # (cx, cy, r, score) — the score is not needed here
    circles = [tuple(c[:3]) for c in circles] if circles else []
    circ_arr = np.array([(c[0], c[1]) for c in circles]) if circles else \
        np.zeros((0, 2))

    comp_attach = collections.defaultdict(list)
    debug_att = []
    n_bundles = 0
    used_labels = set()
    for ch in chains:
        if not ch["ends"]:
            continue
        # label codes this chain touches, nearest code-row first
        touched = []  # (dist to code rect, label idx)
        for p, _ in ch["ends"]:
            pt = Point(p)
            for li in label_tree.query(pt.buffer(tc["leader_label_tol"])):
                li = int(li)
                if _rect_dist(labels[li].block, p) <= tc["leader_label_tol"]:
                    touched.append((_rect_dist(labels[li].rect, p),
                                    getattr(labels[li], "row", 0), li))
        if not touched:
            continue
        # the drawn leader polyline, kept as its own geometry: it is
        # highlighted in the UI but never merged into a pipe polygon
        leader_path = [((a[0], a[1]), (b[0], b[1])) for a, b in ch["segs"]]
        touched.sort()
        # unique codes, nearest row first (a stack contributes all its rows,
        # ordered top->bottom for the N==M mapping)
        seen = set()
        cand = []
        cand_idx = []
        for _, _row, li in touched:
            if li not in seen:
                seen.add(li)
                cand.append(labels[li])
                cand_idx.append(li)
        # spatial order of the label rows: a vertical stack reads top->bottom,
        # a horizontal arrangement left->right
        _ys = [l.rect.y0 for l in cand]
        _xs = [l.rect.x0 for l in cand]
        row = lambda l: getattr(l, "row", 0)
        if (max(_ys) - min(_ys)) >= (max(_xs) - min(_xs)):
            cand_ordered = sorted(cand, key=lambda l: (l.rect.y0, row(l)))
        else:
            cand_ordered = sorted(cand, key=lambda l: (l.rect.x0, row(l)))
        codes_stacked = [l.code for l in cand_ordered]
        nearest_code = cand[0].code

        # pipe-side endpoints
        for p, last_seg in ch["ends"]:
            pt = Point(p)
            if _rect_dist(cand[0].block, p) <= tc["leader_label_tol"]:
                continue  # this end is the label end

            if in_wall(p[0], p[1]):
                continue  # joining points inside wall regions are not pipes
            # joining circle at the end?  Its centre is the authoritative
            # designation point.
            anchor = p
            if len(circ_arr):
                dc = np.hypot(circ_arr[:, 0] - p[0], circ_arr[:, 1] - p[1])
                ci = int(dc.argmin())
                # a drawn circle is a couple of points across; an ML joining
                # point box is read as its own radius, so reach that far
                if dc[ci] <= max(tc["circle_tol"], float(circles[ci][2]) + 1.0):
                    anchor = (float(circ_arr[ci][0]), float(circ_arr[ci][1]))
                    pt = Point(anchor)

            near_all = sorted(
                (int(j) for j in pipe_tree.query(pt.buffer(tc["leader_pipe_tol"]))
                 if pipe_geoms[int(j)].distance(pt) <= tc["leader_pipe_tol"]),
                key=lambda j: pipe_geoms[j].distance(pt))
            if not near_all:
                continue
            # touched contacts = within closest+slack only (a leader endpoint
            # sitting between a branch and its main must not grab both)
            dmin = pipe_geoms[near_all[0]].distance(pt)
            near = [j for j in near_all
                    if pipe_geoms[j].distance(pt) <= dmin + tc["near_slack"]]
            base_ang = seg_angle(pipe_segs[near[0]]["a"], pipe_segs[near[0]]["b"])
            near = [j for j in near
                    if angle_diff(seg_angle(pipe_segs[j]["a"], pipe_segs[j]["b"]),
                                  base_ang) <= tc["bundle_angle"]
                    or pipe_geoms[j].distance(pt) < 0.8]

            # bundle expansion: crossings of the leader tail, parallel to the
            # touched pipe, walked consecutively from the endpoint with a
            # spacing limit.  Wide spacing is only allowed when a stack of N
            # codes needs N members.
            a, b = last_seg
            # the far end of the last leader segment: p IS the near end, so
            # taking the near one would collapse the direction to zero
            tail_from = a if seg_len(a, p) > seg_len(b, p) else b
            tail_vec = (p[0] - tail_from[0], p[1] - tail_from[1])
            tl = math.hypot(*tail_vec)
            N = len(codes_stacked)
            max_gap = tc["bundle_gap_stacked"] if N > 1 else tc["bundle_gap_single"]
            offset_of = {seg_root[j]: 0.0 for j in near}
            if True:
                # Bundle members lie side by side PERPENDICULAR to the pipes,
                # so sweep along the pipe normal from the attachment point -
                # not along the leader, whose direction is arbitrary (it may
                # even run parallel to the pipes).  Distances measured on this
                # axis are the true pipe-to-pipe spacing.
                nrm = math.radians(base_ang + 90.0)
                nx, ny = math.cos(nrm), math.sin(nrm)
                win = tc["bundle_window"]
                tail = LineString([(p[0] - nx * win, p[1] - ny * win),
                                   (p[0] + nx * win, p[1] + ny * win)])
                crossings = []  # (|offset from endpoint|, signed offset, seg)
                for j in pipe_tree.query(tail):
                    j = int(j)
                    if j in near:
                        continue
                    g = pipe_geoms[j]
                    inter = g.intersection(tail)
                    if inter.is_empty:
                        continue
                    ang = seg_angle(pipe_segs[j]["a"], pipe_segs[j]["b"])
                    if angle_diff(ang, base_ang) > tc["bundle_angle"]:
                        continue
                    q = inter.centroid
                    off = (q.x - p[0]) * nx + (q.y - p[1]) * ny
                    crossings.append((abs(off), off, j))
                crossings.sort()
                prev = 0.0
                seen_roots = {seg_root[j] for j in near}
                for aoff, off, j in crossings:
                    if aoff - prev > max_gap:
                        break
                    if N > 1 and len(seen_roots) >= N:
                        break
                    if seg_root[j] not in seen_roots:
                        near.append(j)
                        seen_roots.add(seg_root[j])
                        offset_of[seg_root[j]] = off
                    prev = aoff

                # bundle members can also be designated by their own joining
                # circles near the tip (bracket leaders touch only one pipe)
                if len(circ_arr):
                    dc = np.hypot(circ_arr[:, 0] - p[0], circ_arr[:, 1] - p[1])
                    for ci in np.nonzero(dc <= tc["bundle_window"])[0]:
                        cx, cy, cr = circles[int(ci)]
                        cpt = Point(cx, cy)
                        for j in pipe_tree.query(cpt.buffer(cr + 1.0)):
                            j = int(j)
                            if pipe_geoms[j].distance(cpt) > cr + 1.0:
                                continue
                            ang = seg_angle(pipe_segs[j]["a"], pipe_segs[j]["b"])
                            if angle_diff(ang, base_ang) > tc["bundle_angle"]:
                                continue
                            if seg_root[j] not in seen_roots:
                                near.append(j)
                                seen_roots.add(seg_root[j])
                                offset_of[seg_root[j]] = \
                                    (cx - p[0]) * nx + (cy - p[1]) * ny

            roots, root_seg = [], {}
            for j in near:
                r = seg_root[j]
                if r not in roots:
                    roots.append(r)
                    root_seg[r] = j
            if len(roots) > 1:
                n_bundles += 1
            if len(codes_stacked) == 1:
                # one label serving a bundle types every pipe in it
                targets = [(nearest_code, r) for r in roots]
            else:
                # stacked labels <-> parallel pipes, matched by SPATIAL order:
                # top label -> top pipe (horizontal bundle) or
                # left label -> left pipe (vertical bundle).  Extras are dropped.
                horiz = angle_diff(base_ang, 0) <= 45
                def pipe_key(r):
                    g = pipe_geoms[root_seg[r]]
                    q = g.interpolate(g.project(pt))
                    return q.y if horiz else q.x
                roots_sorted = sorted(roots, key=pipe_key)
                targets = list(zip(codes_stacked, roots_sorted))
            for code, root in targets:
                j = root_seg[root]
                ap = pipe_geoms[j].interpolate(pipe_geoms[j].project(pt))
                # which detected label carried this code (for the API's
                # pipes[].labelId link)
                li = next((k for k in cand_idx if labels[k].code == code),
                          next(iter(cand_idx), None))
                comp_attach[root].append((code, ap, j, True, "leader", li))
                debug_att.append((code, anchor, (ap.x, ap.y), leader_path))
                used_labels.update(cand_idx)
    n_leader = sum(len(v) for v in comp_attach.values())

    # ---- proximity attachment: labels placed next to their pipe ------------ #
    # Blocks none of whose codes were consumed by a leader sit directly beside
    # the pipe(s) they describe (common for radiator runs).
    blocks = collections.defaultdict(list)
    for li, l in enumerate(labels):
        blocks[(round(l.block.x0, 1), round(l.block.y0, 1),
                round(l.block.x1, 1), round(l.block.y1, 1))].append(li)
    n_prox = n_ambig = 0
    for key_, lis in blocks.items():
        if any(li in used_labels for li in lis):
            continue
        block = labels[lis[0]].block
        rows = sorted(((li, labels[li]) for li in lis),
                      key=lambda t: t[1].rect.y0)
        cx, cy = (block.x0 + block.x1) / 2, (block.y0 + block.y1) / 2
        if in_wall(cx, cy):
            continue
        centre = Point(cx, cy)
        reach = centre.buffer(tc["prox_tol"] +
                              math.hypot(block.width, block.height) / 2)
        cands = {}  # root -> (dist, seg idx)
        for j in pipe_tree.query(reach):
            j = int(j)
            q = pipe_geoms[j].interpolate(pipe_geoms[j].project(centre))
            d = _rect_dist(block, (q.x, q.y))
            r = seg_root[j]
            if r not in cands or d < cands[r][0]:
                cands[r] = (d, j)
        near = sorted(((d, r, j) for r, (d, j) in cands.items()))
        near = [(d, r, j) for d, r, j in near if d <= tc["prox_tol"]]
        if not near:
            continue
        if len(rows) == len(near) and len(rows) > 1:
            # stack order (top->bottom) <-> pipe order across the bundle:
            # sort by the coordinate perpendicular to the pipes' orientation
            ang = seg_angle(pipe_segs[near[0][2]]["a"], pipe_segs[near[0][2]]["b"])
            horiz = angle_diff(ang, 0) < 45
            def perp(t):
                q = pipe_geoms[t[2]].interpolate(pipe_geoms[t[2]].project(centre))
                return q.y if horiz else q.x
            near = sorted(near, key=perp)
            pairs = zip(rows, near)
        elif len(rows) == len(near):
            pairs = zip(rows, near)
        elif len(rows) == 1:
            d0 = near[0][0]
            if len(near) > 1 and near[1][0] < max(2.0, d0) * tc["prox_max_ratio"]:
                n_ambig += 1
                continue
            pairs = [(rows[0], near[0])]
        else:
            n_ambig += 1
            continue
        for (li, l), (d, r, j) in pairs:
            ap = pipe_geoms[j].interpolate(pipe_geoms[j].project(centre))
            comp_attach[r].append((l.code, ap, j, True, "proximity", li))
            debug_att.append((l.code, (cx, cy), (ap.x, ap.y), []))
            n_prox += 1
    log(f"T4: {n_leader} leader + {n_prox} proximity attachments on "
        f"{len(comp_attach)} pipe runs ({n_bundles} bundle endpoints, "
        f"{n_ambig} ambiguous proximity blocks skipped)")
    return comp_attach, debug_att


# --------------------------------------------------------------------------- #
# T4c - type diffusion: an untyped run that collinearly continues a typed run
# across a small gap (valve battery, symbol cluster) inherits its type.
# Longitudinal continuation only - parallel neighbours never infect each other.
# --------------------------------------------------------------------------- #
def diffuse_types(segs, comp, comp_attach):
    tc = TYPE_CONFIG
    code_of = {}
    for root, atts in comp_attach.items():
        cs = {a[0] for a in atts}
        if len(cs) == 1:
            code_of[root] = next(iter(cs))

    seg_root = {i: r for r, ms in comp.items() for i in ms}
    # endpoint index over all pipe segments
    cell = tc["diffuse_gap"]
    grid = collections.defaultdict(list)
    eps = []  # (point, seg idx, outward direction deg)
    for i, sg in enumerate(segs):
        a, b = sg["a"], sg["b"]
        if seg_len(a, b) < 1e-6:
            continue
        for p, q in ((a, b), (b, a)):
            d = math.degrees(math.atan2(p[1] - q[1], p[0] - q[0]))
            eps.append((p, i, d))
            grid[(int(p[0] // cell), int(p[1] // cell))].append(len(eps) - 1)

    n_inherit = 0
    for _ in range(tc["diffuse_rounds"]):
        changed = False
        for root in list(comp.keys()):
            if root in code_of or root in comp_attach:
                continue
            best = None  # (gap, code, point, seg)
            for i in comp[root]:
                sg = segs[i]
                for p, q in ((sg["a"], sg["b"]), (sg["b"], sg["a"])):
                    out = math.degrees(math.atan2(p[1] - q[1], p[0] - q[0]))
                    kx, ky = int(p[0] // cell), int(p[1] // cell)
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            for ei in grid[(kx + dx, ky + dy)]:
                                p2, j, out2 = eps[ei]
                                r2 = seg_root.get(j)
                                if r2 is None or r2 == root or r2 not in code_of:
                                    continue
                                gap = seg_len(p, p2)
                                if gap < 1e-6 or gap > tc["diffuse_gap"]:
                                    continue
                                if angle_diff(out % 180, out2 % 180) > \
                                        tc["diffuse_angle"]:
                                    continue
                                gv = math.degrees(math.atan2(p2[1] - p[1],
                                                             p2[0] - p[0]))
                                if angle_diff(gv % 180, out % 180) > \
                                        tc["diffuse_offaxis"] or \
                                   angle_diff(gv % 180, out2 % 180) > \
                                        tc["diffuse_offaxis"]:
                                    continue
                                # the two tips must face each other
                                fwd1 = math.cos(math.radians(out)) * (p2[0] - p[0]) \
                                    + math.sin(math.radians(out)) * (p2[1] - p[1])
                                fwd2 = math.cos(math.radians(out2)) * (p[0] - p2[0]) \
                                    + math.sin(math.radians(out2)) * (p[1] - p2[1])
                                if fwd1 <= 0 or fwd2 <= 0:
                                    continue
                                if best is None or gap < best[0]:
                                    best = (gap, code_of[r2], Point(p), i)
            if best is not None:
                code_of[root] = best[1]
                # an inherited type continues a run, so it fills the whole
                # component (directional=False) instead of claiming one side
                comp_attach[root].append(
                    (best[1], best[2], best[3], False, "diffused", None))
                n_inherit += 1
                changed = True
        if not changed:
            break

    # ---- tee inheritance: a branch is its pipe's class ------------------- #
    # A branch leaving a typed run BETWEEN two joining points belongs to that
    # stretch.  An untyped run whose ENDPOINT lands on a typed run — reaching
    # for it along itself, away from every joining point — inherits its code,
    # provided every run it lands on agrees on ONE code (a stem bridging two
    # differently-coded pipes stays untyped).  Repeated, so a branch of a
    # branch fills too.
    jpts = [(a[1].x, a[1].y) for atts in comp_attach.values()
            for a in atts if a[3]]
    tee_gap, n_tee = 6.0, 0
    for _ in range(tc["diffuse_rounds"]):
        typed_idx = [i for i, sg in enumerate(segs)
                     if seg_root.get(i) in code_of
                     and seg_len(sg["a"], sg["b"]) > 1e-6]
        if not typed_idx:
            break
        geoms = [LineString([segs[i]["a"], segs[i]["b"]]) for i in typed_idx]
        ttree = STRtree(geoms)
        changed = False
        for root in list(comp.keys()):
            if root in code_of:
                continue
            codes, hit = set(), None
            for i in comp[root]:
                sg = segs[i]
                if seg_len(sg["a"], sg["b"]) < 1e-6:
                    continue
                for p, q0 in ((sg["a"], sg["b"]), (sg["b"], sg["a"])):
                    pt = Point(p)
                    out = math.degrees(math.atan2(p[1] - q0[1], p[0] - q0[0]))
                    for k in ttree.query(pt.buffer(tee_gap)):
                        k = int(k)
                        g = geoms[k]
                        d = g.distance(pt)
                        if d > tee_gap:
                            continue
                        q = g.interpolate(g.project(pt))
                        mid = ((p[0] + q.x) / 2, (p[1] + q.y) / 2)
                        if any(seg_len(mid, jp) <= 4.0 for jp in jpts):
                            continue     # a joining point is a class change
                        if d > 0.75:
                            gv = math.degrees(math.atan2(q.y - p[1], q.x - p[0]))
                            if angle_diff(gv % 180, out % 180) > 35.0:
                                continue # lying beside it, not reaching for it
                            fwd = math.cos(math.radians(out)) * (q.x - p[0]) \
                                + math.sin(math.radians(out)) * (q.y - p[1])
                            if fwd <= 0:
                                continue
                        r2 = seg_root.get(typed_idx[k])
                        if r2 is not None and r2 != root:
                            codes.add(code_of[r2])
                            hit = (Point(p), i)
            if len(codes) == 1 and hit is not None:
                code_of[root] = codes.pop()
                comp_attach[root].append(
                    (code_of[root], hit[0], hit[1], False, "diffused", None))
                n_tee += 1
                changed = True
        if not changed:
            break
    log(f"T4c: {n_inherit} runs inherited a type by continuation, "
        f"{n_tee} branches took their pipe's class at a tee")
    return comp_attach


# --------------------------------------------------------------------------- #
# T4b/T5 - typed polygon generation (mirrors pipe_seg.build_polygons)
# --------------------------------------------------------------------------- #
def build_typed_polygons(segs, comp, wall_geom, comp_attach, label_rects=()):
    cfg = CONFIG
    tc = TYPE_CONFIG
    ltree, lrects = ps._label_tick_tree(label_rects)
    typed = []  # (shapely polygon, code)
    for root, members in comp.items():
        if any(segs[i].get("symbol") or segs[i].get("connector")
               for i in members):
            continue                    # valve bowties, stems, decoration
        lines = [LineString([segs[i]["a"], segs[i]["b"]]) for i in members]
        raw = unary_union(MultiLineString(lines))
        attached = any(segs[i].get("tee") for i in members) or root in comp_attach
        if ps.is_symbol_loop(segs, members, raw, root in comp_attach):
            continue
        if ps.is_decorative_curve(segs, members, raw):
            continue
        if ps.is_label_tick(segs, members, raw, attached, ltree, lrects):
            continue
        if not attached and raw.length < cfg["min_straight_frag"] and \
                len(members) <= 3 and \
                not any(segs[i].get("bridge") for i in members):
            pts = [segs[i][e] for i in members for e in ("a", "b")]
            chord = max(seg_len(p, q) for p in pts for q in pts)
            if chord > 1e-6 and raw.length <= chord * 1.05:
                continue
        geom = raw if wall_geom.is_empty else raw.difference(wall_geom)
        if geom.is_empty:
            continue
        if geom.length < cfg["min_pipe_len"] and not attached:
            continue
        width = max(segs[i]["w"] for i in members)

        atts = comp_attach.get(root, [])
        if not atts:
            groups = {"Unknown": geom}
        elif not any(a[3] for a in atts):
            # only inherited (non-directional) attachments: fill the whole run
            groups = {atts[0][0]: geom}
        else:
            groups = _split_directional(members, segs, atts, wall_geom)

        for code, g in groups.items():
            if g.is_empty:
                continue
            poly = g.buffer(width / 2.0 + 0.05,
                            cap_style="round", join_style="round")
            poly = poly.simplify(cfg["polygon_simplify"])
            if poly.is_empty:
                continue
            parts = poly.geoms if poly.geom_type == "MultiPolygon" else [poly]
            for p in parts:
                if p.area < width * cfg["min_clipped_len"]:
                    continue
                for q in split_holes(p):
                    typed.append((q, code))
    counts = collections.Counter(code for _, code in typed)
    log(f"T5: {len(typed)} typed polygons; "
        + ", ".join(f"{c}:{n}" for c, n in counts.most_common(6))
        + (f", ... ({len(counts)} types)" if len(counts) > 6 else ""))
    return typed


def _split_directional(members, segs, atts, wall_geom):
    """Cut the run at the joining points and give each stretch one class.

    The pipe is split ONLY at joining points.  Each stretch between two
    consecutive joining points is a single region: the class flows along it,
    following every bend, and changes only where a new joining point appears.

    Which stretch a joining point owns is decided by `pipe_rules`: the label
    at a tee names the branch; otherwise the stretch DOWNSTREAM of the joining
    point — sewer elevation, then diameter (larger -> smaller), then position
    (a dead-end stub behind the label is the entry, a side hanging off a main
    is fed by it, the wall the pipe came through is behind it), and finally
    TYPE_CONFIG["claim_direction"] as the page-reading fallback.  The stretches
    a joining point does not claim stay one pipe through it.

    Inherited attachments (directional=False) are continuations and simply
    fill whatever they can reach.
    """

    # 1. re-segment so that no segment straddles a joining point
    local = [{"a": segs[i]["a"], "b": segs[i]["b"], "src": i} for i in members]
    for _code, ap, _j, _dir, *_ in atts:
        P = (ap.x, ap.y)
        k = 0
        while k < len(local):
            s = local[k]
            if seg_len(P, s["a"]) > 0.25 and seg_len(P, s["b"]) > 0.25 and \
                    _point_on_segment(P, s["a"], s["b"], 0.35):
                tail = s["b"]
                s["b"] = P
                local.append({"a": P, "b": tail, "src": s["src"]})
            k += 1

    jpts = [(ap.x, ap.y) for _c, ap, _j, _d, *_ in atts]

    def at_join(p):
        """Index of the joining point sitting on this vertex, else -1."""
        for n, q in enumerate(jpts):
            if seg_len(p, q) <= 0.5:
                return n
        return -1

    # 2. adjacency, CUT at every joining point: two segments meeting at a
    #    joining point are not connected, so a class can never flow past one.
    snap = CONFIG["snap_tol"]
    grid = collections.defaultdict(list)
    for i, s in enumerate(local):
        for p in (s["a"], s["b"]):
            grid[(round(p[0] / snap), round(p[1] / snap))].append(i)
    adj = collections.defaultdict(set)
    for i, s in enumerate(local):
        for p in (s["a"], s["b"]):
            if at_join(p) >= 0:
                continue                      # boundary - do not link across
            kx, ky = round(p[0] / snap), round(p[1] / snap)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid[(kx + dx, ky + dy)]:
                        if j != i:
                            adj[i].add(j)
                            adj[j].add(i)

    # 3. regions = connected components of the cut graph
    region_of = {}
    regions = []
    for i in range(len(local)):
        if i in region_of or seg_len(local[i]["a"], local[i]["b"]) <= 1e-9:
            continue
        comp, stack = [], [i]
        region_of[i] = len(regions)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for k in adj[cur]:
                if k not in region_of:
                    region_of[k] = len(regions)
                    stack.append(k)
        regions.append(comp)

    # 4. each joining point hands its class to the DOWNSTREAM region next to
    #    it (pipe_rules: tee -> elevation -> diameter -> position), and the
    #    regions it does not claim stay connected through it, so a class
    #    follows the main straight past the tap of a labelled branch.
    #    Inherited (non-directional) attachments simply fill the nearest.
    n_reg = len(regions)
    reg_len = [sum(seg_len(local[i]["a"], local[i]["b"]) for i in comp)
               for comp in regions]
    reg_cent = []
    for comp in regions:
        cx = sum((local[i]["a"][0] + local[i]["b"][0]) / 2 for i in comp) / len(comp)
        cy = sum((local[i]["a"][1] + local[i]["b"][1]) / 2 for i in comp) / len(comp)
        reg_cent.append((cx, cy))
    reg_joins = collections.defaultdict(set)      # region -> {att index}
    join_regs = collections.defaultdict(list)     # att index -> [(region, seg, vertex)]
    for ri, comp in enumerate(regions):
        for i in comp:
            for p in (local[i]["a"], local[i]["b"]):
                n = at_join(p)
                if n >= 0:
                    reg_joins[ri].add(n)
                    join_regs[n].append((ri, i, p))

    def _other_end(i, p):
        s = local[i]
        return s["b"] if seg_len(p, s["a"]) <= seg_len(p, s["b"]) else s["a"]

    def _hangs(ri, i, p):
        """Walk from the joining point along the region; if the pipe runs into
        a tee where the two other arms continue each other and this one comes
        in from the side, it hangs off that run.  Returns the length of the
        run and everything beyond it (0 when the walk ends elsewhere)."""
        walked, cur, at = 0.0, i, p
        seen = {i}
        for _ in range(500):
            q = _other_end(cur, at)
            walked += seg_len(at, q)
            nxt = [k for k in adj[cur]
                   if k not in seen and (seg_len(q, local[k]["a"]) <= snap or
                                         seg_len(q, local[k]["b"]) <= snap)]
            if not nxt:
                return 0.0
            if len(nxt) == 1:
                seen.add(nxt[0])
                cur, at = nxt[0], q
                continue
            inc = seg_angle(local[cur]["a"], local[cur]["b"])
            angs = [seg_angle(local[k]["a"], local[k]["b"]) for k in nxt]
            for x in range(len(nxt)):
                for y in range(x + 1, len(nxt)):
                    if angle_diff(angs[x], angs[y]) <= 20 and \
                            angle_diff(inc, angs[x]) > 45:
                        return max(reg_len[ri] - walked, 1e-6)
            return 0.0
        return 0.0

    claims = collections.defaultdict(list)        # region -> [(dist, att n)]
    through = []
    claimed_by = {}

    def _decide(n, claimed_by):
        code, ap, j, directional = atts[n][:4]
        if not directional or n not in join_regs:
            return None
        axis = seg_angle(segs[j]["a"], segs[j]["b"])
        cands, by_key = [], {}
        for ri, i, p in join_regs[n]:
            if ri in by_key:
                continue
            c_axis = seg_angle(local[i]["a"], local[i]["b"])
            others = [m for m in reg_joins[ri] if m != n and atts[m][3]]
            # far labels: the other joining points bounding this region, less
            # any already known to describe another region (a branch label at
            # a tap says nothing about the main)
            far = [atts[m][0] for m in others if claimed_by.get(m, ri) == ri]
            hangs = _hangs(ri, i, p)
            c = pipe_rules.Candidate(
                ri, reg_cent[ri], far_codes=far, axis=c_axis, passes=False,
                hangs=hangs,
                stub=(reg_len[ri] <= 15.0 and not others and hangs == 0.0))
            by_key[ri] = c
            cands.append(c)
        if not cands:
            return None
        win, rule = pipe_rules.choose_downstream(
            cands, code, (ap.x, ap.y), axis, wall=wall_geom,
            claim_direction=TYPE_CONFIG["claim_direction"])
        return win, rule, [c.key for c in cands if c.key != win]

    def _record(n, win, rule, rest):
        claims[win].append((seg_len(jpts[n], reg_cent[win]), n))
        claimed_by[n] = win
        for a_, b_ in zip(rest, rest[1:]):
            through.append((a_, b_))

    pending = []
    for n in range(len(atts)):
        got = _decide(n, {})
        if got is None:
            continue
        if got[1] in ("tee", "single"):
            _record(n, *got)
        else:
            pending.append(n)
    for n in pending:
        got = _decide(n, claimed_by)
        if got is not None:
            _record(n, *got)

    code_of_region = {}
    for ri, lst in claims.items():
        lst.sort()
        code_of_region[ri] = atts[lst[0][1]][0]
    # inherited types fill the nearest region that has nothing yet
    for n, (code, ap, _j, directional, *_) in enumerate(atts):
        if directional or n not in join_regs:
            continue
        for ri, _i, _p in join_regs[n]:
            code_of_region.setdefault(ri, code)
    sadj = collections.defaultdict(set)
    for a_, b_ in through:
        sadj[a_].add(b_)
        sadj[b_].add(a_)
    queue = collections.deque(sorted(code_of_region, key=lambda r: -reg_len[r]))
    while queue:
        ri = queue.popleft()
        for t in sadj[ri]:
            if t not in code_of_region:
                code_of_region[t] = code_of_region[ri]
                queue.append(t)

    code_of = {}
    for ri, comp in enumerate(regions):
        if ri in code_of_region:
            for i in comp:
                code_of[i] = code_of_region[ri]

    # 5. group; a stretch no joining point starts stays Unknown
    pieces = collections.defaultdict(list)
    for i, s in enumerate(local):
        if seg_len(s["a"], s["b"]) <= 1e-9:
            continue
        pieces[code_of.get(i, "Unknown")].append(LineString([s["a"], s["b"]]))
    out = {}
    for c, ls in pieces.items():
        g = unary_union(MultiLineString(ls))
        if not wall_geom.is_empty:
            g = g.difference(wall_geom)
        out[c] = g
    return out


def _point_on_segment(p, a, b, tol):
    """Is p on segment a-b (within tol), strictly between the endpoints?"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return False
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    if t <= 0.0 or t >= 1.0:
        return False
    px, py = a[0] + t * dx, a[1] + t * dy
    return math.hypot(p[0] - px, p[1] - py) <= tol


# --------------------------------------------------------------------------- #
# T5 - outputs
# --------------------------------------------------------------------------- #
def save_typed_outputs(page, typed):
    cfg = CONFIG
    s = cfg["render_dpi"] / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s))
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    img = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2BGR).copy()

    records = []
    idx = 1
    for poly, code in typed:
        ext = export_ring(poly, s)
        if ext is None:
            continue
        records.append({"id": idx, "polygon": ext, "type": code})
        idx += 1
        pts = np.array(ext, np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(img, [pts], cfg["paint_color_bgr"])

    cv2.imwrite(cfg["out_painted"], img)
    with open(cfg["out_json"], "w") as f:
        json.dump(records, f)
    n_unknown = sum(1 for r in records if r["type"] == "Unknown")
    log(f"T5: wrote {cfg['out_painted']} and {cfg['out_json']} "
        f"({len(records)} pipes, {n_unknown} Unknown)")


def type_color(code):
    """Deterministic colour per type code, stable across sheets."""
    if code == "Unknown":
        return (47, 52, 229)             # BGR red — unclassified stands out
    import zlib
    rng = np.random.default_rng(zlib.crc32(code.encode()))
    return tuple(int(v) for v in rng.integers(50, 255, 3))


def save_typed_overview(page, typed, labels, debug_att, out_path):
    """One merged visualisation: pipes filled per type, each label's bounding
    box and its joining point(s) drawn in the SAME colour as the pipe type."""
    s = 2.0
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s))
    img = cv2.cvtColor(
        np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3],
        cv2.COLOR_RGB2BGR).copy()

    codes = sorted({c for _, c in typed} |
                   {l.code for l in labels} |
                   {a[0] for a in debug_att})
    cmap = {c: type_color(c) for c in codes}

    # pipes filled per type
    for poly, code in typed:
        pts = np.array([[int(x * s), int(y * s)] for x, y in poly.exterior.coords],
                       np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(img, [pts], cmap[code])
    # label bounding boxes in their code's colour
    for l in labels:
        r = l.rect
        cv2.rectangle(img, (int(r.x0 * s), int(r.y0 * s)),
                      (int(r.x1 * s), int(r.y1 * s)), cmap[l.code], 2)
    # leader connection + joining point in the code's colour
    for att in debug_att:
        code, p, ap = att[0], att[1], att[2]
        path = att[3] if len(att) > 3 else None
        # highlight the drawn leader line itself (never part of the pipe)
        for (a, b) in (path or [(p, ap)]):
            cv2.line(img, (int(a[0] * s), int(a[1] * s)),
                     (int(b[0] * s), int(b[1] * s)), cmap[code], 2)
        cv2.circle(img, (int(ap[0] * s), int(ap[1] * s)), 7, cmap[code], 3)
    # legend
    y = 40
    for c in codes:
        cv2.rectangle(img, (20, y - 14), (40, y + 2), cmap[c], -1)
        cv2.putText(img, c, (48, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        y += 26
    cv2.imwrite(out_path, img)


def save_type_debug(page, labels, chains, debug_att, typed, clip):
    cfg = CONFIG
    os.makedirs(cfg["debug_dir"], exist_ok=True)
    s = 2.0
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s))
    base = cv2.cvtColor(
        np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3],
        cv2.COLOR_RGB2BGR)

    # labels + leaders + joining points (raw detection view)
    img = base.copy()
    for l in labels:
        r = l.rect
        cv2.rectangle(img, (int(r.x0 * s), int(r.y0 * s)),
                      (int(r.x1 * s), int(r.y1 * s)), (0, 180, 0), 2)
        cv2.putText(img, l.code, (int(r.x0 * s), int(r.y0 * s) - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 130, 0), 1)
    for att in debug_att:
        code, p, ap = att[0], att[1], att[2]
        path = att[3] if len(att) > 3 else None
        for (a, b) in (path or [(p, ap)]):
            cv2.line(img, (int(a[0] * s), int(a[1] * s)),
                     (int(b[0] * s), int(b[1] * s)), (255, 0, 0), 1)
        cv2.circle(img, (int(ap[0] * s), int(ap[1] * s)), 6, (0, 0, 255), 2)
    cv2.imwrite(f"{cfg['debug_dir']}/t3_labels_and_joins.png", img)
    log(f"type debug artefacts written to {cfg['debug_dir']}/")


# --------------------------------------------------------------------------- #
def process(pdf_path):
    page, drawings, is_vector = ps.load_page(pdf_path)
    if not is_vector:
        raise SystemExit("typing requires a vector PDF")
    clip = ps.detect_frame_clip(drawings, page.rect)
    # the ML joining points anchor everything: they are read first, the pipe
    # styles are learned at them, and candidate extraction runs on those
    # styles (the configured band only when nothing could be learned)
    labels_all, marks, sig = detect_marks(page, drawings, clip)
    pipe_segs = ps.extract_candidates(
        drawings, clip, sig.candidate_matchers() if sig.families else None)
    wall_geom, hatch_raster = ps.build_wall_regions(drawings, clip, page.rect)
    segs, comp, bridges = ps.merge_segments(
        pipe_segs, wall_geom, ps.detect_circle_marks(drawings, clip))
    seg_root = {}
    for root, members in comp.items():
        for i in members:
            seg_root[i] = root

    labels, _idx = assignable_labels(labels_all, clip, wall_geom)
    chains = trace_leaders(drawings, labels, clip, max_width=sig.leader_max)
    # a stack of labels on one connection line shares the last one's note
    labels_all = share_ladder_notes(labels_all, chains)
    labels, _idx = assignable_labels(labels_all, clip, wall_geom)
    comp_attach, debug_att = assign_types(chains, labels, segs, seg_root,
                                          marks, wall_geom)
    comp_attach = diffuse_types(segs, comp, comp_attach)
    labels = labels_all
    tick_rects = [(l.block.x0, l.block.y0, l.block.x1, l.block.y1)
                  for l in labels]
    typed = build_typed_polygons(segs, comp, wall_geom, comp_attach,
                                 tick_rects)
    save_typed_outputs(page, typed)
    overview = CONFIG["out_painted"].replace(".png", "_typed.png")
    save_typed_overview(page, typed, labels, debug_att, overview)
    log(f"T5: wrote {overview} (types + label boxes + joining points, "
        f"one colour per class)")
    if CONFIG["debug"]:
        save_type_debug(page, labels, chains, debug_att, typed, clip)


def main(argv=None):
    import argparse
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)

    ap = argparse.ArgumentParser(description="Pipe type classification")
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    os.makedirs("output", exist_ok=True)
    for pdf in args.pdfs:
        stem = os.path.splitext(os.path.basename(pdf))[0]
        CONFIG["out_painted"] = f"output/{stem}.png"
        CONFIG["out_json"] = f"output/{stem}.json"
        CONFIG["debug"] = args.debug
        CONFIG["debug_dir"] = f"debug/{stem}"
        log(f"=== {pdf} ===")
        process(pdf)


if __name__ == "__main__":
    main()
