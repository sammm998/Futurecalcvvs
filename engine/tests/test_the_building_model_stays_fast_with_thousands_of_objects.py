"""Ett hus med tusentals objekt räknas, valideras, snittas och kollisionskontrolleras på sekunder.

Provet ligger i frontend/src/cad/perf.test.ts (samma kod som ritbordet kör) och körs här med node; varje
steg har en tidsgräns som är rymlig för en långsam maskin och snäv nog att fånga en kvadratisk algoritm.
"""
import os
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONT = os.path.join(ROOT, "frontend")
ESBUILD = os.path.join(FRONT, "node_modules", ".bin", "esbuild")


def test_thousands_of_objects_stay_fast(tmp_path):
    if not os.path.exists(ESBUILD):
        pytest.skip("frontend/node_modules saknas")
    out = str(tmp_path / "perf.test.js")
    b = subprocess.run([ESBUILD, "src/cad/perf.test.ts", "--bundle", "--platform=node", "--format=cjs", f"--outfile={out}", "--log-level=warning"],
                       cwd=FRONT, capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr
    r = subprocess.run(["node", out], capture_output=True, text=True, timeout=300)
    print(r.stdout)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-800:]
    assert "snabbt nog" in r.stdout
