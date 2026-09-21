"""A second model's reading of this code, asked for and then checked.

Two models miss different things. Running one over the measurement path turns up defects the other walked past,
and on this codebase it has already found metres being minted by a correction and fifty metres of pipe invented
from a millimetre level read as metres. That is worth having.

What it is NOT, and the line is absolute: no model reads a drawing here, and no model decides a metre. The
engine's answer comes from the sheet's own geometry and its own leaders, and nothing in the measurement path
calls out to anything. This tool sends SOURCE FILES and gets back PROSE about them. Its output is a list of
claims to verify against the code, never a patch to apply and never evidence about a quantity.

Two rules it enforces rather than trusts:

  * it refuses to send anything under data/, so no facit, drawing or annotation can leave the machine through it
  * it never handles a key. The agent proxy attaches the credential after the request leaves this machine, so
    there is nothing here to leak and nothing to commit

Usage:
    python3 tools/second_opinion.py vvs_engine/pipes/ownership.py vvs_engine/measure/measure.py
    python3 tools/second_opinion.py --out /tmp/review vvs_engine/corrections.py

Every finding it returns is a claim. Check each one against the code before you change a line: on this codebase
roughly two thirds held up and the rest did not, and one that did hold up was still not worth fixing because the
fix cost more correct metres than the defect cost wrong ones.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

API = "https://api.openai.com/v1/responses"
MODEL = "gpt-6-astra"
# Reasoning tokens count against this budget, and a hard question spends thousands of them before writing a
# word. Too small a budget returns a completed-looking response with nothing in it.
MAX_OUTPUT_TOKENS = 45000
# The proxy gives up long before a high-effort answer arrives, so the request is queued and polled instead.
POLL_SECONDS = 15
POLL_ROUNDS = 80

PROMPT = """Du granskar en modul ur mätkärnan i ett system som mängdar VVS-rör ur vektor-PDF-ritningar.

Principen koden ska hålla: ett rör får identitet ENBART via en verklig ledarlinje från en beteckning till just
den geometrin, aldrig via närhet. AMBIGUOUS är ett giltigt svar; fel säkerhet är det inte. Falskt ägda meter
(geometri som tillskrivs fel beteckning, eller som inte är rör men mäts) är det dyraste felet; missade meter är
billigare men inte gratis.

Leta efter KONKRETA defekter. För varje fynd: funktion, exakt vad som går fel, ett konkret scenario
(indata -> fel utdata), och om det ger falskt ägda meter, missade meter, eller är kosmetiskt.

Var strikt. Hitta inte på fynd; om något ser rätt ut, säg inget om det. Svenska, numrerad lista, hårdast först,
max 6 fynd. Om du inte hittar något verkligt: svara "inga fynd".

===== {name} =====
{source}
"""


def _curl(args: list[str], timeout: int = 120) -> dict:
    r = subprocess.run(["curl", "-sS", "--max-time", str(timeout), *args], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        raise SystemExit(f"svar som inte är JSON från {API}:\n{(r.stdout or r.stderr)[:400]}")


def _refuse_validation_data(path: str) -> None:
    """Nothing under data/ may be sent anywhere. The facit exists to judge the engine from outside it."""
    p = os.path.abspath(path)
    parts = p.replace("\\", "/").split("/")
    if "data" in parts:
        raise SystemExit(f"vägrar skicka {path}: allt under data/ är facit, ritningar och annoteringar")


def ask(path: str, out_dir: str) -> str:
    _refuse_validation_data(path)
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    body = {"model": MODEL,
            "input": PROMPT.format(name=path, source=source),
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "reasoning": {"effort": "high"},
            "background": True}
    req = os.path.join(out_dir, os.path.basename(path) + ".request.json")
    with open(req, "w", encoding="utf-8") as fh:
        json.dump(body, fh)
    d = _curl([API, "-H", "Content-Type: application/json", "-d", f"@{req}"])
    if d.get("error"):
        raise SystemExit(f"{path}: {d['error']}")
    rid = d.get("id")
    print(f"  {path} -> {rid} ({d.get('status')})", flush=True)
    return rid


def collect(rid: str) -> tuple[str, str]:
    for _ in range(POLL_ROUNDS):
        d = _curl([f"{API}/{rid}"], timeout=60)
        status = d.get("status")
        if status in ("completed", "failed", "incomplete"):
            text = "".join(c.get("text", "")
                           for o in d.get("output", []) for c in (o.get("content") or [])
                           if c.get("type") == "output_text")
            if status == "incomplete" and not text.strip():
                why = (d.get("incomplete_details") or {}).get("reason", "okänd")
                text = f"(inget svar: {why} - höj MAX_OUTPUT_TOKENS)"
            return status, text.strip()
        time.sleep(POLL_SECONDS)
    return "timeout", "(hann inte bli klar)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="En andra modells läsning av den här koden. Fynden ska verifieras.")
    ap.add_argument("files", nargs="+", help="källfiler att granska (inget under data/)")
    ap.add_argument("--out", default=None, help="katalog för svaren (default: en temporär)")
    args = ap.parse_args(argv)

    out_dir = args.out or os.path.join(os.environ.get("TMPDIR", "/tmp"), "second-opinion")
    os.makedirs(out_dir, exist_ok=True)
    for f in args.files:
        _refuse_validation_data(f)

    print(f"frågar {MODEL} om {len(args.files)} fil(er); svaren hamnar i {out_dir}", flush=True)
    queued = [(f, ask(f, out_dir)) for f in args.files]

    print("\nväntar på svaren (varje fråga tänker i flera minuter)…", flush=True)
    findings = 0
    for f, rid in queued:
        status, text = collect(rid)
        dest = os.path.join(out_dir, os.path.basename(f) + ".review.md")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(f"# {f}\n\nmodell: {MODEL}\nstatus: {status}\n\n{text}\n")
        print(f"\n########## {f} [{status}] -> {dest}\n{text}", flush=True)
        if status == "completed" and "inga fynd" not in text.lower():
            findings += 1

    print(f"\n{findings} av {len(queued)} fil(er) fick fynd.")
    print("Varje fynd är ett påstående, inte ett faktum: verifiera mot koden innan du ändrar något, och mät mot\n"
          "referensritningarna efteråt. Ett fynd kan stämma och ändå inte vara värt att åtgärda, om rättningen\n"
          "kostar fler riktiga meter än defekten kostar felaktiga.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
