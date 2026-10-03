"""Ändringskommandona i ritbordet: flytta, kopiera, rotera, spegla, skala, förskjut, mönster, trimma, förläng och mät.

Modellen är skriven i TypeScript och delar kod med ritbordet i webbläsaren, så provet körs där koden lever: den
buntas med esbuild och körs i node, och varje rad i utskriften är ett påstående som jämförts med ett tal räknat
för hand (frontend/src/cad/modify.test.ts). Provet här är bara sändebudet: det faller om något påstående föll.
"""
import os
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONT = os.path.join(ROOT, "frontend")
ESBUILD = os.path.join(FRONT, "node_modules", ".bin", "esbuild")


@pytest.mark.skipif(not os.path.exists(ESBUILD), reason="frontend/node_modules saknas")
def test_the_cad_modify_commands_hold(tmp_path):
    out = str(tmp_path / "modify.test.js")
    b = subprocess.run([ESBUILD, "src/cad/modify.test.ts", "--bundle", "--platform=node", "--format=cjs", f"--outfile={out}", "--log-level=warning"],
                       cwd=FRONT, capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr
    r = subprocess.run(["node", out], capture_output=True, text=True, timeout=120)
    failed = [ln for ln in r.stdout.splitlines() if ln.startswith("  FEL")]
    assert r.returncode == 0 and not failed, "\n".join(failed) + "\n" + r.stderr[-800:]
    assert "alla ändringskommandon håller" in r.stdout
