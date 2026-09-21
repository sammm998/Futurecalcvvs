"""Byggmodellens kärna: ett hus byggs upp genom transaktioner, ångras, mängdas, snittas och kollisionskontrolleras.

Modellen är skriven i TypeScript och delar kod med ritbordet i webbläsaren, så provet körs där koden lever: den
buntas med esbuild och körs i node, och varje rad i utskriften är ett påstående som jämförts med ett tal räknat
för hand (frontend/src/cad/core.test.ts). Provet här är bara sändebudet: det faller om något påstående föll.
"""
import os
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONT = os.path.join(ROOT, "frontend")
ESBUILD = os.path.join(FRONT, "node_modules", ".bin", "esbuild")


@pytest.mark.skipif(not os.path.exists(ESBUILD), reason="frontend/node_modules saknas")
def test_the_building_model_holds_together(tmp_path):
    out = str(tmp_path / "core.test.js")
    b = subprocess.run([ESBUILD, "src/cad/core.test.ts", "--bundle", "--platform=node", "--format=cjs", f"--outfile={out}", "--log-level=warning"],
                       cwd=FRONT, capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr
    r = subprocess.run(["node", out], capture_output=True, text=True, timeout=120)
    failed = [ln for ln in r.stdout.splitlines() if ln.startswith("  FEL")]
    assert r.returncode == 0 and not failed, "\n".join(failed) + "\n" + r.stderr[-800:]
    assert "allt håller" in r.stdout
