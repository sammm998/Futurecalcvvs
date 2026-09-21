"""Build one Pipe Studio style package per drawing style of the survey library.

For every entry of vectorascore/data/style_library.json except the reference
family (that is ``style-1`` and stays untouched) this writes
vectorascore/data/styles/<id>.json: the package Studio shows under "Styles &
rules" with its "Scale-independent adjustments" filled in.

The adjustments are the engine's own derived tolerances for that style's sample
sheet, expressed as ratios of the sheet's leader stroke width (the unit Studio
scales them with). So on the sample sheet the package reproduces exactly what
the automatic calibration does; on another sheet of the same style with a
different pen base the same ratios follow that sheet's leader pen. Values that
fall outside a parameter's allowed range are clamped and noted in the package.

The vector signature is captured from the sample sheet as Studio's "Capture
signature" button would (``styles.signature``), so ``style=auto`` can match the
style; the Astra binding rules start as a copy of style-1's.

    .venv/bin/python tools/style_survey/build_studio_styles.py [--root "<sample PDFs>"] [--debug debug_styles] [--debug debug]

``--debug`` folders (run_styles.py output, one folder per sample sheet) supply the
detector's label boxes and the OCR'd labels; a sample without one is calibrated
from the PDF's text objects alone.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from vectorascore import extract as ex_mod, profile as pr_mod, style, bucket, labels as la   # noqa: E402
from studio import styles as st                                                              # noqa: E402
from tools.style_survey.build_library import find_pdf, DEFAULT_ROOTS                          # noqa: E402

OUT = os.path.join(os.path.dirname(style.__file__), "data", "styles")
REFERENCE = "sweco-pdfplot-strokes"          # = style-1, the existing style: never generated here


derived_tolerances = st.derived_tolerances

def package(entry, pdf, folder=None):
    """``folder``: a stored analysis of the sample sheet (01_extract, 03_detect,
    06_labels from run_styles.py) - then the detector's boxes and the OCR'd labels
    anchor the calibration as in production; without it only the PDF's own text
    objects make label boxes, which stroke-lettering styles lack."""
    if folder:
        ex = ex_mod.load(os.path.join(folder, "01_extract.json")); page_no = ex.page_no
        P = pr_mod.profile(ex)
        det = json.load(open(os.path.join(folder, "03_detect.json")))
        L = json.load(open(os.path.join(folder, "06_labels.json")))
        from vectorascore import vvs
        valid = {l["id"] for l in L if la.label_valid([vvs.sanitize_dimension(d) for d in l["designations"]], l.get("score"))}
        boxes = [b["rect"] for b in det["label_boxes"] if b["id"] in valid] or [b["rect"] for b in det["label_boxes"]]
    else:
        page_no, _ = style.select_page(pdf)
        ex = ex_mod.extract(pdf, page_no)
        P = pr_mod.profile(ex)
        det = la.text_label_boxes(ex, {"label_boxes": []}, text_height=style.text_height(ex)[0])
        boxes = [b["rect"] for b in det["label_boxes"]]
    C = bucket.calibrate(P, ex, boxes)
    unit = st.leader_unit(C)
    calibration, clamped = {}, []
    for key, value in derived_tolerances(C).items():
        lo, hi, _ = st.PARAMETERS[key]
        ratio = value if key.endswith("tick_rel_min") else value / unit
        r = round(min(hi, max(lo, ratio)), 3)
        if r != round(ratio, 3):
            clamped.append(f"{key} {ratio:.2f} -> {r}")
        calibration[key] = r
    base = st.get_style("style-1")
    derivation = (f"Adjustments are the engine's derived tolerances on this sheet as ratios of the {unit} pt leader pen "
                  f"(pipe family by {C['family_method']}; {'detector boxes and OCR labels' if folder else 'label boxes from the PDF text only'}).")
    if clamped:
        derivation += " Clamped to the allowed range: " + ", ".join(clamped) + "."
    return {
        "id": entry["id"], "name": entry["name"],
        "description": entry["note"] + ". Baseline derived from one sample sheet of the style survey (2026-09-08); not a measured accuracy claim.",
        "version": 1, "calibration": calibration,
        "signatures": [st.signature(P)],
        "rules": base["rules"],
        "library_id": entry["id"],
        "pen_table": {"sheet": os.path.basename(pdf), "page_no": page_no, "pipe_widths": C["pipe_widths"],
                      "leader_width": C["leader_width"], "text_height": C["text_height"], "u_paper": C["u_paper"],
                      "hairline": C["hairline"], "family_method": C["family_method"], "derivation": derivation},
    }


def main(argv):
    roots = list(DEFAULT_ROOTS)
    if "--root" in argv:
        roots = [argv[argv.index("--root") + 1]] + roots
    # stored analyses (run_styles.py output folders, named after the PDF stem)
    # matched to a sample by the PDF path recorded in 02_profile.json (several
    # styles ship a "10.pdf" or a "6.pdf"), else by the folder name
    by_path, by_stem = {}, {}
    for i, a in enumerate(argv):
        if a == "--debug":
            for d in sorted(os.listdir(argv[i + 1])):
                f = os.path.join(argv[i + 1], d)
                if not os.path.exists(os.path.join(f, "06_labels.json")):
                    continue
                src = json.load(open(os.path.join(f, "02_profile.json"))).get("source_pdf") if os.path.exists(os.path.join(f, "02_profile.json")) else None
                if src:
                    by_path[os.path.abspath(src)] = f
                else:
                    by_stem.setdefault(d, f)
    lib = style.load_library()
    from tools.style_survey.build_library import ENTRIES
    names = {sid: name for sid, name, *_ in ENTRIES}
    for entry in lib["styles"]:
        if any(entry['id'] in g['library_ids'] for g in st.GROUPS):
            print(f"  {entry['id']:24} belongs to a merged Studio package: left untouched")
            continue
        if entry["id"] == REFERENCE:
            print(f"  {entry['id']:24} is style-1: left untouched")
            continue
        pdf = find_pdf(entry["id"], names.get(entry["id"], entry.get("sheet", "")), roots)
        if pdf is None:
            print(f"  {entry['id']:24} SKIPPED: sample PDF not found"); continue
        stem = os.path.basename(pdf).rsplit(".", 1)[0]
        pkg = package(entry, pdf, by_path.get(os.path.abspath(pdf)) or by_stem.get(stem))
        path = os.path.join(OUT, entry["id"] + ".json")
        json.dump(pkg, open(path, "w"), indent=1, ensure_ascii=False)
        print(f"  {entry['id']:24} unit={pkg['pen_table']['leader_width']} pipes={pkg['pen_table']['pipe_widths']} "
              + " ".join(f"{k.split('.')[1]}={v}" for k, v in pkg["calibration"].items()))


if __name__ == "__main__":
    main(sys.argv[1:])
