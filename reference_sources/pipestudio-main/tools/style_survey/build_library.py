"""Build vectorascore/data/style_library.json from one representative PDF per style.

Each entry is the measured profile of that sheet (extract + profile + units; no
ML, no OCR - only the calibration-independent numbers the matcher compares) plus
hand-verified starting values where the pipe and leader pens are known (research
note "Style Adaptation for the Vector Parser", 2026-09-04, and the crops checked
on 2026-09-08). Starting values are only ever applied when a sheet confirms them
(``style.starting_values``), so a wrong or missing entry can only cost a
recognition, never invent a pipe family.

    .venv/bin/python tools/style_survey/build_library.py [--root "<folder with the sample PDFs>"]

The sample PDFs are looked up under --root (default: the two Downloads folders
the survey used) by file name; entries whose PDF is missing are kept from the
existing library when present, else skipped.
"""
import json
import os
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, os.getcwd())
from vectorascore import extract as ex_mod, profile as pr_mod, style   # noqa: E402

# id, file name, display name, note, starting values (None = only recognise)
ENTRIES = [
    ("sweco-pdfplot-strokes", "W-50-1-A-0131.pdf", "Vinnergi - AutoCAD 2023 - pdfplot16",
     "Sweco / AutoCAD MEP via pdfplot, lettering as 0.72 pt strokes, pipes 1.44 / 2.04, leader 0.48 (the reference family)",
     {"pipe_widths": [1.44, 2.04], "leader_width": 0.48}),
    ("sweco-pdfplot-text", "V-50-1-A0122.pdf", "Sweco - AutoCAD MEP 2020 - pdfplot15",
     "Sweco / AutoCAD MEP via pdfplot, real ISOCPEUR text, pipes 1.44 / 2.28, leader 0.72 (0.36 is revision clouds)",
     {"pipe_widths": [1.44, 2.28], "leader_width": 0.72}),
    ("priorn-shx", "V-50-1-A0101.pdf", "Sweco - AutoCAD 2018 - pdfplot14",
     "Sweco / AutoCAD 2018 via pdfplot14, SHX text as stroked glyphs (7 text objects), pipes 1.44",
     {"pipe_widths": [1.44]}),
    ("eon-hairline", "R9UHA10-CLB001-002.pdf", "Sweco - AutoCAD 2023 - pdfplot16 - Hairline",
     "Sweco / AutoCAD 2023 via pdfplot16, every width 0: families by (colour, layer), pipes on the V layers",
     None),
    ("axis-bluebeam", "V50-1-0842 - Plan B2, Del 42, Värme & Sanitäranlägg-.pdf", "VVS Konsulterna - Revit - Bluebeam Brewery 5.0",
     "Tyréns via Bluebeam Brewery: pipes 0.66, stroked text 0.48, fixtures 0.96, wall strokes 1.38; labels underlined, the leader continues the underline in the pipe pen",
     {"pipe_widths": [0.66], "leader_width": 0.66}),
    ("bd-ghostscript", "1760279_1.pdf", "Bengt Dahlgren - Ghostscript 9.21",
     "Bengt Dahlgren via Ghostscript 9.21: pipes 1.41 / 2.82, leader 0.51, glyphs 0.72, the leader ends in a ring",
     {"pipe_widths": [1.41, 2.82], "leader_width": 0.51}),
    ("hyllie-ghostscript", "10.pdf", "Vinnergi - Bluebeam Revu - Ghostscript 9.21",
     "Otto Magnusson / Bengt Dahlgren via Ghostscript: pipes 1.44 / 2.04, architecture in grey, leader 0.48",
     {"pipe_widths": [1.44, 2.04], "leader_width": 0.48}),
    ("badskon-a3-booklet", "Badskon 1.pdf", "PO Andersson - Ghostscript 9.21",
     "Ghostscript booklet, A3 plans at half size: pipes 0.48, text 5.5 pt, ring still 3 pt",
     {"pipe_widths": [0.48]}),
    ("lopoglan-booklet", "Löpöglan 2.pdf", "Bengt Dahlgren Syd - Ghostscript 9.21",
     "Ghostscript booklet with A4 covers, A1 plans: pipes 0.72, grid lines 0.27",
     {"pipe_widths": [0.72]}),
    ("blackhornet-2xa0", "Bläckhornet.pdf", "Arildssons Rör - Ghostscript 9.21",
     "Ghostscript booklet, double A0 sheets, lettering in heavy strokes (1.42 / 1.98 are glyphs): pipes 0.71",
     {"pipe_widths": [0.71]}),
    ("style4-heavy-dashed", "6.pdf", "PQR Malmö - Bluebeam Revu - Ghostscript 9.21",
     "Ghostscript export, two-line labels (code over underlined dimension), pipes 0.96 solid and dashed, leader 0.48",
     {"pipe_widths": [0.96], "leader_width": 0.48}),
    ("style5-sewer-plan", "2.pdf", "Rejlers - Bluebeam Revu - Ghostscript 9.21",
     "Ghostscript export, S1 sewer runs 0.96 dashed with VG levels, leader 0.24",
     {"pipe_widths": [0.96], "leader_width": 0.24}),
    ("style9-thin-dashdot", "10.pdf", "Kjell Petersson - Bluebeam Revu - Ghostscript 9.21",
     "Bluebeam Revu export, few labels, walls 0.99, dash-dot pipes 0.72: pipe family unresolved, recognition only",
     None),
    ("style6-single-width", "R1502.pdf", "Sweco - Bluebeam Brewery 5.0 - Uniform Stroke",
     "Every stroke 0.36 pt and no text objects: not solvable by width, labels only from the detector",
     None),
]

# where each sample lives (several folders hold a "10.pdf" or a "6.pdf")
FOLDERS = {
    "sweco-pdfplot-strokes": ["Style of drawings/1", "uploads"],
    "sweco-pdfplot-text": ["Style of drawings/2", "uploads"],
    "priorn-shx": ["Other drawings (different format)/Priorn", "Style of drawings/12"],
    "eon-hairline": ["Other drawings (different format)", "Style of drawings/8"],
    "axis-bluebeam": ["Other drawings (different format)/Ritningar", "Other drawings (different format)", "Style of drawings/7"],
    "bd-ghostscript": ["Other drawings (different format)/Fyrtornet 2", "Style of drawings/13"],
    "hyllie-ghostscript": ["Other drawings (different format)/Hyllie hybrid"],
    "badskon-a3-booklet": ["Other drawings (different format)", "Style of drawings/3"],
    "lopoglan-booklet": ["Other drawings (different format)", "Style of drawings/10"],
    "blackhornet-2xa0": ["Other drawings (different format)", "Style of drawings/11"],
    "style4-heavy-dashed": ["Style of drawings/4"],
    "style5-sewer-plan": ["Style of drawings/5"],
    "style9-thin-dashdot": ["Style of drawings/9"],
    "style6-single-width": ["Style of drawings/6"],
}
# drawing conventions that switch rules on which the sheet alone cannot justify
CONVENTIONS = {"axis-bluebeam": {"labels_underlined": True}}
DEFAULT_ROOTS = [os.path.expanduser("~/Downloads"), os.getcwd()]
from studio.styles import GROUPS
GROUP_BY_LIBRARY = {sid: g for g in GROUPS for sid in g['library_ids']}
ENTRIES = [(sid, filename, GROUP_BY_LIBRARY[sid]['name'] if sid in GROUP_BY_LIBRARY else name, note, start)
           for sid, filename, name, note, start in ENTRIES]

KEEP = ("format", "page", "page_no", "u_paper", "text_height", "text_mode", "font", "n_layers", "layered",
        "hairline", "width_ladder", "ring_pt", "ring_mm", "dash_gap_pt", "grey_share", "fill_share", "n_paths", "n_texts")


def find_pdf(sid, name, roots):
    # Manifest disambiguates repeated filenames and follows the consolidated folders.
    source_root = Path(__file__).resolve().parents[2] / 'style-source-pdfs'
    manifest = source_root / 'manifest.json'
    if manifest.exists():
        display = next((e[2] for e in ENTRIES if e[0] == sid), None)
        for folder in json.loads(manifest.read_text()):
            if folder['name'] == display:
                for p in (source_root / folder['folder']).glob('*.pdf'):
                    if unicodedata.normalize('NFC', p.name) == unicodedata.normalize('NFC', name):
                        return str(p)
    for root in roots:
        for sub in FOLDERS.get(sid, [""]):
            p = os.path.join(root, sub, name)
            if os.path.exists(p):
                return p
    return None


def measure_pdf(pdf, start):
    page_no, pages = style.select_page(pdf)
    ex = ex_mod.extract(pdf, page_no)
    P = pr_mod.profile(ex)
    U = style.units(ex, P)
    # the dash gap of the (known) pipe family, from the sheet's own collinear gaps
    C = {"pipe_widths": list((start or {}).get("pipe_widths") or []),
         "dash_gaps": {float(w): {"gap_mode": max(s["gap_hist"], key=lambda h: h[2])[:2]}
                       for w, s in P["collinear_gaps_by_width"].items()},
         "leader_width": (start or {}).get("leader_width")}
    m = style.measure(ex, P, U, C)
    m["page_no"] = page_no
    return {k: m.get(k) for k in KEEP}


def main(argv):
    roots = list(DEFAULT_ROOTS)
    if "--root" in argv:
        roots = [argv[argv.index("--root") + 1]] + roots
    old = style.load_library()
    old_by_id = {e["id"]: e for e in old.get("styles", [])}
    styles = []
    for sid, name, disp, note, start in ENTRIES:
        pdf = find_pdf(sid, name, roots)
        if pdf is None:
            if sid in old_by_id:
                styles.append(old_by_id[sid]); print(f"  {sid:24} kept from the existing library (no PDF found)")
            else:
                print(f"  {sid:24} SKIPPED: {name} not found under {roots}")
            continue
        prof = measure_pdf(pdf, start)
        entry = {"id": sid, "name": disp, "note": note, "sheet": os.path.basename(pdf), "profile": prof}
        if sid in GROUP_BY_LIBRARY:
            entry['studio_style_id'] = GROUP_BY_LIBRARY[sid]['id']
        if start:
            entry["starting_values"] = start
        if sid in CONVENTIONS:
            entry["conventions"] = CONVENTIONS[sid]
        styles.append(entry)
        print(f"  {sid:24} p{prof['page_no']} ladder={prof['width_ladder']} u={prof['u_paper']} th={prof['text_height']} "
              f"{prof['text_mode']} layers={prof['n_layers']} ring={prof['ring_pt']} gap={prof['dash_gap_pt']}")
    out = {"version": 2, "built": "2026-09-08", "accept_distance": 0.15,
           "note": "one measured profile per known drawing style; starting values apply only when the sheet confirms them",
           "styles": styles}
    json.dump(out, open(style.LIBRARY_PATH, "w"), indent=1, ensure_ascii=False)
    print(f"wrote {style.LIBRARY_PATH} with {len(styles)} styles")


if __name__ == "__main__":
    main(sys.argv[1:])
