"""Baseline: what extract+profile+calibrate make of one sheet per style (no OCR, no ML).
    .venv/bin/python tools/style_survey/baseline.py "<pdf>" ...
"""
import sys, os, json, traceback
sys.path.insert(0, os.getcwd())
from vectorascore import extract as ex_mod, profile as pr_mod, bucket as bu_mod
import numpy as np

for pdf in sys.argv[1:]:
    try:
        ex = ex_mod.extract(pdf)
        P = pr_mod.profile(ex)
        th = np.median([t.size for t in ex.texts]) if ex.texts else None
        try:
            C = bu_mod.calibrate(P)
            cal = f"pipe_w={C['pipe_widths']} leader={C['leader_width']} circle={C['circle'] and C['circle']['diameter']} layers={C['has_layers']}"
        except Exception as e:
            cal = f"CALIBRATE FAILED: {type(e).__name__}: {e}"
        top = ", ".join(f"{c['width']}{c['colour'][0]}x{c['count']}" for c in P["stroke_classes"][:8] if c["kind"] != "f")
        print(f"{os.path.basename(pdf)[:38]:38} page={ex.page[0]:.0f}x{ex.page[1]:.0f} paths={len(ex.paths)} texts={len(ex.texts)} th={th} layers={len(P['layers'])}\n    widths: {top}\n    {cal}")
    except Exception:
        print(pdf); traceback.print_exc()
