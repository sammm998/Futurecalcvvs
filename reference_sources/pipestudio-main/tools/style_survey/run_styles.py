"""Run the pipeline (no model) on one sheet per style into debug_styles/<sheet>.
    .venv/bin/python tools/style_survey/run_styles.py [pdf ...]   (default: the 13 style sheets)
"""
import os, sys, time, traceback
sys.path.insert(0, os.getcwd())
from vectorascore import run as vrun

S = "/Users/zeeshankhan/Downloads/Style of drawings"
DEFAULT = [f"{S}/1/W-50-1-A-0131.pdf", f"{S}/2/V-50-1-A0122.pdf", f"{S}/3/Badskon 1.pdf", f"{S}/4/6.pdf", f"{S}/5/2.pdf",
           f"{S}/6/R1502.pdf", f"{S}/7/V50-1-0811 - Plan B2, Del 11, Värme & Sanitäranlägg-.pdf", f"{S}/8/R9UHA10-CLB001-002.pdf",
           f"{S}/9/10.pdf", f"{S}/10/Löpöglan 2.pdf", f"{S}/11/Bläckhornet.pdf", f"{S}/12/V-50-1-A0101.pdf", f"{S}/13/1760279_1.pdf"]
root = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--root"), "debug_styles")
pdfs = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--root"] or DEFAULT
for pdf in pdfs:
    t0 = time.time()
    try:
        d = vrun.run(pdf, upto=7, use_llm=False, debug_root=root, progress=lambda i, n: print(f"    [{i}] {n}", flush=True))
        print(f"OK   {os.path.basename(pdf)} -> {d} [{time.time() - t0:.0f}s]", flush=True)
    except Exception:
        print(f"FAIL {os.path.basename(pdf)} [{time.time() - t0:.0f}s]", flush=True); traceback.print_exc()
