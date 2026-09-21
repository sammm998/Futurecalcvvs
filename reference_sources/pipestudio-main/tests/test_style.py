"""Per-drawing style profile (vectorascore/style.py): units, families, the pipe
family by leader landings, text label boxes, page selection. Synthetic sheets,
no PDFs needed except the one this test writes itself.

    .venv/bin/python tests/test_style.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vectorascore import style, profile as pr_mod, bucket, labels
from vectorascore.extract import Extraction, Path, Text

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


class Sheet:
    def __init__(self, page=(2384.0, 1684.0)):
        self.ex = Extraction(sheet="synthetic", page=list(page), rotation=0)

    def line(self, a, b, width, color=(0, 0, 0), layer=""):
        i = len(self.ex.paths)
        r = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
        self.ex.paths.append(Path(id=i, kind="s", width=width, color=list(color), fill=None, dashes="",
                                  layer=layer, closed=False, rect=r, items=[["l", a[0], a[1], b[0], b[1]]]))
        return i

    def ring(self, c, d, width=0.48):
        i = len(self.ex.paths)
        r = d / 2
        k = 0.5523 * r
        x, y = c
        items = [["c", x + r, y, x + r, y + k, x + k, y + r, x, y + r],
                 ["c", x, y + r, x - k, y + r, x - r, y + k, x - r, y],
                 ["c", x - r, y, x - r, y - k, x - k, y - r, x, y - r],
                 ["c", x, y - r, x + k, y - r, x + r, y - k, x + r, y]]
        self.ex.paths.append(Path(id=i, kind="s", width=width, color=[0, 0, 0], fill=None, dashes="",
                                  layer="", closed=True, rect=[x - r, y - r, x + r, y + r], items=items))
        return i

    def text(self, s, x, y, size=11.0):
        i = len(self.ex.texts)
        w = 0.6 * size * len(s)
        self.ex.texts.append(Text(id=i, text=s, bbox=[x, y, x + w, y + size], font="ISOCPEUR", size=size, dir=[1, 0]))
        return [x, y, x + w, y + size]


def dashed(sh, y, x0, x1, width, dash=12.0, gap=4.0, layer=""):
    x = x0
    while x < x1:
        sh.line((x, y), (min(x + dash, x1), y), width, layer=layer)
        x += dash + gap


def test_units_from_text_height():
    sh = Sheet()
    for i in range(40):
        sh.text("VS1-S13-22", 100 + i * 50, 100, size=11.0)
    U = style.units(sh.ex, pr_mod.profile(sh.ex))
    check("A1 sheet with 11 pt text is the reference: u_paper 1.0", abs(U["u_paper"] - 1.0) < 0.02 and U["source"] == "text height")
    sh3 = Sheet(page=(1191.0, 842.0))
    for i in range(40):
        sh3.text("VS1-S13-22", 50 + i * 20, 100, size=5.5)
    U3 = style.units(sh3.ex, pr_mod.profile(sh3.ex))
    check("A3 sheet with 5.5 pt text is at half size: u_paper 0.5", abs(U3["u_paper"] - 0.5) < 0.02)
    sh_nt = Sheet(page=(1191.0, 842.0))
    U_nt = style.units(sh_nt.ex, pr_mod.profile(sh_nt.ex))
    check("no text: the paper format decides (A3 -> 0.5)", abs(U_nt["u_paper"] - 0.5) < 0.02 and U_nt["source"] == "paper format")
    big = Sheet(page=(7152.0, 3371.0))
    for i in range(40):
        big.text("S1-P2-110", 100 + i * 60, 100, size=11.0)
    check("a double A0 sheet with normal text keeps u_paper 1.0", abs(style.units(big.ex, pr_mod.profile(big.ex))["u_paper"] - 1.0) < 0.02)


def test_world_scale_from_skala_text():
    sh = Sheet()
    sh.text("SKALA 1:50", 2000, 1600)
    W = style.world_scale(sh.ex)
    check("SKALA 1:50 read", W["denominator"] == 50 and not W["verified"] and W["sources"] == ["skala text"])


def axis_like_sheet():
    """Pipes at 0.66 pt with leaders from labels; 222 short 1.38 wall strokes that
    the old width rule took for pipes (the Axis case)."""
    sh = Sheet()
    boxes = []
    # a pipe network: two long 0.66 runs with a tee
    for y in (300.0, 600.0):
        dashed(sh, y, 100, 1500, 0.66, dash=40, gap=3)
    for k in range(40):                    # vertical connectors between them
        x = 120 + k * 35
        sh.line((x, 300), (x, 600), 0.66)
    # labels with leaders down to the top run
    for k in range(12):
        x = 150 + k * 100
        r = sh.text("VS1-13-28", x - 20, 200, size=11.0)
        boxes.append(r)
        sh.line((x, r[3] + 1.0), (x, 300.0), 0.48)          # the leader: label box -> pipe
    # wall strokes: many short heavy lines nowhere near labels
    for k in range(222):
        x = 100 + (k % 74) * 30
        y = 1000 + (k // 74) * 40
        sh.line((x, y), (x + 20, y), 1.38)
    # glyph-like strokes of a stroke-lettering family, 1-6 pt long, some near labels
    for k in range(400):
        x = 100 + (k % 100) * 14
        y = 1300 + (k // 100) * 6
        sh.line((x, y), (x + 2 + (k % 5), y), 0.72)
    # the 30-span requirement for text height
    for k in range(30):
        sh.text("RUM 12", 100 + k * 40, 1500, size=11.0)
    return sh, boxes


def test_pipe_family_from_leader_landings():
    sh, boxes = axis_like_sheet()
    P = pr_mod.profile(sh.ex)
    old = sorted(w for w, s in {float(w): s for w, s in P["single_line_by_width"].items()}.items()
                 if w >= 1.0 and s["count"] >= 30 and s["len_median"] >= 4.0)
    check("the old width rule would pick the 1.38 wall strokes", old == [1.38])
    C = bucket.calibrate(P, sh.ex, boxes)
    check("leader landings pick the 0.66 family as pipes", C["pipe_widths"] == [0.66] and C["family_method"].startswith("leader landings"))
    check("the width rule's answer is kept for the record", C["legacy"]["pipe_widths"] == [1.38] and C["family_confidence"] == "high")
    check("the leader family is 0.48", abs(C["leader_width"] - 0.48) < 0.01)
    check("units are in the calibration", C["u_paper"] == 1.0 and C["text_height"] == 11.0 and C["pipe_base"] == 0.66)
    check("the 0.72 glyph family is not a pipe family", 0.72 not in C["pipe_widths"])
    check("a style profile was measured and matched or flagged", "style" in C and "new_style" in C["style"])


def reference_like_sheet():
    """The Sweco family: 1.44 pt pipes, 0.48 pt leaders from the labels, 0.72 pt
    stroke lettering - and a 0.36 pt class of long lines (revision clouds, grid)
    that no leader is drawn in."""
    sh = Sheet()
    boxes = []
    for y in (300.0, 600.0):
        dashed(sh, y, 100, 1500, 1.44, dash=40, gap=3)
    for k in range(40):
        sh.line((120 + k * 35, 300), (120 + k * 35, 600), 1.44)
    for k in range(12):
        x = 150 + k * 100
        r = sh.text("VS1-S13-22", x - 20, 200, size=11.0)
        boxes.append(r)
        sh.line((x, r[3] + 1.0), (x, 300.0), 0.48)
    for k in range(60):                                  # long thin lines nobody points at
        sh.line((100, 900 + k * 8), (1500, 900 + k * 8), 0.36)
    for k in range(400):
        sh.line((100 + (k % 100) * 14, 1300 + (k // 100) * 6), (102 + (k % 100) * 14 + (k % 5), 1300 + (k // 100) * 6), 0.72)
    for k in range(30):
        sh.text("RUM 12", 100 + k * 40, 1500, size=11.0)
    return sh, boxes


def test_reference_style_keeps_the_width_rule():
    """The existing style must calibrate exactly as before: the width rule's
    families and tolerances, whatever the labels add."""
    sh, boxes = reference_like_sheet()
    P = pr_mod.profile(sh.ex)
    old = bucket.legacy_pipe_widths(P)
    C = bucket.calibrate(P, sh.ex, boxes)
    check("the width rule finds the 1.44 family", old == [1.44])
    check("calibrate keeps the width rule's family and says the labels confirm it",
          C["pipe_widths"] == [1.44] and C["family_method"].startswith("width rule, confirmed by"))
    check("the leader pen is the landing leaders' 0.48, not the 0.36 lines nobody points at", abs(C["leader_width"] - 0.48) < 0.01)
    check("u_paper is exactly 1 on an A1 sheet with 11 pt text (tolerances unchanged)", C["u_paper"] == 1.0 and C["pipe_base"] == 1.44)
    # the profile-only call (Studio signatures, tolerances) is the plain width rule
    C0 = bucket.calibrate(P)
    check("profile-only calibration is the width rule alone", C0["pipe_widths"] == [1.44] and C0["family_method"] == "width rule")
    # a few landings on some other family never flip a healthy width rule
    for k in range(4):
        r = sh.text("KV1-13-16", 100 + k * 300, 850, size=11.0)
        boxes.append(r)
        sh.line((120 + k * 300, r[3] + 1.0), (120 + k * 300, 900.0), 0.48)     # points at the 0.36 lines
    C2 = bucket.calibrate(pr_mod.profile(sh.ex), sh.ex, boxes)
    check("four landings on the 0.36 lines do not overrule twelve on the 1.44 pipes", C2["pipe_widths"] == [1.44])


def test_u_paper_snaps_to_the_reference_within_seven_percent():
    sh = Sheet()
    for i in range(40):
        sh.text("VS1-S13-22", 100 + i * 50, 100, size=10.6)
    U = style.units(sh.ex, pr_mod.profile(sh.ex))
    check("10.6 pt text on A1 is the reference size", U["u_paper"] == 1.0 and abs(U["u_paper_raw"] - 0.964) < 0.01)
    sh2 = Sheet()
    for i in range(40):
        sh2.text("VS1-S13-22", 100 + i * 50, 100, size=8.8)
    check("8.8 pt text is a smaller sheet (0.8)", abs(style.units(sh2.ex, pr_mod.profile(sh2.ex))["u_paper"] - 0.8) < 0.01)


def test_calibrate_without_labels_never_crashes():
    sh = Sheet()
    for k in range(50):
        sh.line((100 + k * 20, 100), (100 + k * 20, 300), 0.42)        # only thin ink
    C = bucket.calibrate(pr_mod.profile(sh.ex), sh.ex, [])
    check("a sheet with no pipe-weight ink calibrates to its heaviest common class, marked low confidence",
          C["pipe_widths"] == [0.42] and C["family_confidence"] == "low")
    empty = Sheet()
    C0 = bucket.calibrate(pr_mod.profile(empty.ex), empty.ex, [])
    check("an empty sheet gives an empty pipe family, no exception", C0["pipe_widths"] == [] and C0["leader_width"] >= 0)
    C1 = bucket.calibrate(pr_mod.profile(sh.ex))
    check("the profile-only call (Studio signatures) still works", isinstance(C1["pipe_widths"], list))


def test_hairline_families_by_layer():
    sh = Sheet()
    boxes = []
    for y in (300.0, 600.0):
        dashed(sh, y, 100, 1500, 0.0, dash=40, gap=3, layer="X|V-53BB-FE--VS1-")
    for k in range(40):
        sh.line((120 + k * 35, 300), (120 + k * 35, 600), 0.0, layer="X|V-53BB-FE--VS1-")
    for k in range(12):
        x = 150 + k * 100
        r = sh.text("VS1-S13-22", x - 20, 200)
        boxes.append(r)
        sh.line((x, r[3] + 1.0), (x, 300.0), 0.0, layer="X|V-53BB-T--VS1--")
    for k in range(200):
        sh.line((100 + (k % 50) * 30, 1000 + (k // 50) * 40), (130 + (k % 50) * 30, 1000 + (k // 50) * 40), 0.0, layer="X|A-40-WALL")
    for k in range(30):
        sh.text("RUM 12", 100 + k * 40, 1500)
    fam, hair = style.families(sh.ex)
    check("all widths 0 -> hairline plot, families by (colour, layer)", hair and all(len(k) == 3 for k in fam))
    C = bucket.calibrate(pr_mod.profile(sh.ex), sh.ex, boxes)
    check("the pipe layer is the one the leaders land on", C["hairline"] and C["pipe_layers"] == ["X|V-53BB-FE--VS1-"])
    check("pipe width 0 and leader width 0 on a hairline plot", C["pipe_widths"] == [0.0] and C["leader_width"] == 0.0)


def test_text_label_boxes():
    sh = Sheet()
    sh.text("VS1-S13-22", 100, 100)
    r2 = sh.text("S1-P2", 400, 100)                 # two-line form: code over dimension
    sh.text("110", 405, 100 + 12)
    sh.text("RUM 12", 700, 100)                     # not a label
    sh.text("KV01-X7-20-W40", 900, 100)             # suffix form
    det = labels.text_label_boxes(sh.ex, {"label_boxes": [{"id": 0, "rect": [98, 98, 170, 113], "score": 0.9}]}, text_height=11.0)
    rects = [b["rect"] for b in det["label_boxes"] if b.get("src") == "text"]
    check("two new boxes: the two-line label and the suffixed one; the detected one is not duplicated", len(rects) == 2)
    two = [r for r in rects if r[0] < 500]
    check("the two-line label box spans code and dimension row", two and two[0][3] > r2[3] + 8)


def test_select_page_skips_covers():
    import pymupdf
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_style_booklet.pdf")
    doc = pymupdf.open()
    cover = doc.new_page(width=595, height=842)
    for k in range(50):
        cover.draw_line((50, 50 + k * 10), (500, 50 + k * 10))
    plan = doc.new_page(width=1191, height=842)
    for k in range(400):
        plan.draw_line((50 + k * 2, 100), (50 + k * 2, 700))
    plan2 = doc.new_page(width=1191, height=842)
    for k in range(600):
        plan2.draw_line((50 + k, 100), (50 + k, 700))
    doc.save(out)
    try:
        page, rows = style.select_page(out)
        check("the first drawing page is chosen, not the busiest and not the cover", page == 1 and len(rows) == 3)
    finally:
        os.remove(out)


def test_style_library_match():
    lib = {"accept_distance": 0.15,
           "styles": [{"id": "ref", "name": "reference", "profile": {"u_paper": 1.0, "text_height": 11.0,
                                                                     "ring_pt": 2.76, "grey_share": 0.1, "fill_share": 0.05, "n_layers": 50,
                                                                     "text_mode": "strokes", "layered": True, "hairline": False,
                                                                     "width_ladder": [0.72, 0.48, 1.44, 0.0, 0.96, 2.04]},
                       "starting_values": {"pipe_widths": [1.44, 2.04], "leader_width": 0.48}}]}
    same = dict(lib["styles"][0]["profile"])
    m = style.match(same, lib)
    check("a profile equal to a library entry matches it", m["status"] == "matched" and m["style"] == "ref" and not m["new_style"])
    other = dict(same, u_paper=0.5, text_mode="text", layered=False, n_layers=0, width_ladder=[0.48, 0.66, 0.96, 1.38])
    m2 = style.match(other, lib)
    check("a far profile is a new style", m2["new_style"] and m2["style"] is None)
    # starting values are taken only when the sheet confirms them
    fam = {(1.44, "black"): {"count": 500, "len_p90": 12.0}, (2.04, "black"): {"count": 80, "len_p90": 12.0}, (0.48, "black"): {"count": 900, "len_p90": 26.0}}
    land = {"landings": 40, "votes": {"1.44|black": {"landings": 30}, "0.48|black": {"landings": 10}}}
    keys, lk, why = style.starting_values(lib["styles"][0], fam, land, False)
    check("confirmed starting values: pipe families and leader", keys == [(1.44, "black"), (2.04, "black")] and lk == (0.48, "black"))
    keys2, _, why2 = style.starting_values(lib["styles"][0], {(0.66, "black"): {"count": 300, "len_p90": 200.0}}, land, False)
    check("starting widths not drawn on the sheet are refused", keys2 is None and "not drawn" in why2)
    land3 = {"landings": 40, "votes": {"0.96|black": {"landings": 40}}}
    keys3, _, why3 = style.starting_values(lib["styles"][0], fam, land3, False)
    check("starting widths no leader lands on are refused", keys3 is None and "no leader lands" in why3)


def test_calibrate_uses_library_when_confirmed():
    sh, boxes = axis_like_sheet()
    P = pr_mod.profile(sh.ex)
    C = bucket.calibrate(P, sh.ex, boxes)
    # the real library is on disk: whatever it matches, the sheet's own landings
    # must never be overruled by unconfirmed starting values
    check("pipe family stays 0.66 with the library present", C["pipe_widths"] == [0.66])
    check("the match result is recorded", "style" in C and C["style"]["status"] in ("matched", "new_style"))


def test_manual_mode_applies_the_chosen_style_only():
    """A chosen style is analysed as chosen: its pen table when drawn, else the
    width rule - no landings, no library matching, even where that is wrong."""
    sh, boxes = axis_like_sheet()
    P = pr_mod.profile(sh.ex)
    C = bucket.calibrate(P, sh.ex, boxes, style_hint="axis-bluebeam", mode="manual")
    check("manual Axis on an Axis-like sheet applies the 0.66 pen table", C["pipe_widths"] == [0.66] and abs(C["leader_width"] - 0.66) < 0.01
          and C["style"]["manual"] and C["style"]["style"] == "axis-bluebeam" and C["landings"] is None)
    C2 = bucket.calibrate(P, sh.ex, boxes, style_hint="hyllie-ghostscript", mode="manual")
    check("manual Hyllie on it falls to the width rule (1.38 wall strokes) - wrong, but as chosen",
          C2["pipe_widths"] == [1.38] and "width rule" in C2["family_method"] and C2["style"]["style"] == "hyllie-ghostscript")
    C3 = bucket.calibrate(P, sh.ex, boxes, mode="manual")
    check("manual Style 1 (no library entry) is the plain width rule", C3["pipe_widths"] == [1.38] and C3["family_method"] == "manual style: width rule")
    ref, rboxes = reference_like_sheet()
    Pr = pr_mod.profile(ref.ex)
    check("manual Style 1 on the reference family equals the old calibration",
          bucket.calibrate(Pr, ref.ex, rboxes, mode="manual")["pipe_widths"] == bucket.legacy_pipe_widths(Pr) == [1.44])


def test_resolve_style_auto_manual_and_fallback(tmp_path=None):
    """Studio's style choice for a stored drawing: 'auto' detects the style from
    the stored extraction and falls back to style-1 (flagged) when nothing
    matches; a named style is 'manual' and still reports what the drawing
    matches."""
    import json, os, tempfile
    from vectorascore import extract as ex_mod
    os.environ.setdefault("PIPE_STUDIO_DATA", tempfile.mkdtemp())
    from studio import engine
    d = tempfile.mkdtemp()
    sh, boxes = axis_like_sheet()                     # matches no library profile: a synthetic sheet
    ex_mod.save(sh.ex, os.path.join(d, "01_extract.json"))
    json.dump(pr_mod.profile(sh.ex), open(os.path.join(d, "02_profile.json"), "w"))
    style_, m = engine.resolve_style(d, "auto")
    check("auto resolves to a real style and says how", isinstance(style_["id"], str) and m["selection"] in ("auto", "fallback") and m["used_style_id"] == style_["id"])
    check("the nearest library style is still reported", "library" in m and "nearest" in m["library"])
    # nothing matches: the drawing runs as style-1 and is flagged
    real = engine.detect_style
    engine.detect_style = lambda ex, P: {"style_id": None, "status": "needs_style_review", "method": "test", "library": {"nearest": None}}
    try:
        style0, m0 = engine.resolve_style(d, "auto")
    finally:
        engine.detect_style = real
    check("an unknown drawing on auto runs as style-1 and is flagged fallback", style0["id"] == "style-1" and m0["selection"] == "fallback" and m0["used_style_id"] == "style-1")
    style2, m2 = engine.resolve_style(d, "axis-bluebeam")
    check("a named style is manual and used as given, nothing detected", style2["id"] == "axis-bluebeam" and m2["selection"] == "manual"
          and m2["used_style_id"] == "axis-bluebeam" and m2["style_id"] is None and "library" not in m2)
    json.dump({"metadata": {"style_id": "axis-bluebeam", "style_match": dict(m2)}}, open(os.path.join(d, "09_review.json"), "w"))
    style3, m3 = engine.resolve_style(d, "auto", detect=False)
    check("without detection a manual analysis on auto still yields a valid style", isinstance(style3["id"], str) and m3["used_style_id"] == style3["id"])
    check("the reference library id maps to style-1", engine.LIBRARY_TO_STUDIO.get("sweco-pdfplot-strokes") == "style-1")


if __name__ == "__main__":
    for t in [test_units_from_text_height, test_world_scale_from_skala_text, test_pipe_family_from_leader_landings,
              test_reference_style_keeps_the_width_rule, test_u_paper_snaps_to_the_reference_within_seven_percent,
              test_calibrate_without_labels_never_crashes, test_hairline_families_by_layer, test_text_label_boxes,
              test_select_page_skips_covers, test_style_library_match, test_calibrate_uses_library_when_confirmed,
              test_manual_mode_applies_the_chosen_style_only, test_resolve_style_auto_manual_and_fallback]:
        print("--", t.__name__)
        t()
    print("\nSTYLE TESTS " + ("PASSED" if not FAILED else f"FAILED: {FAILED}"))
    sys.exit(1 if FAILED else 0)
