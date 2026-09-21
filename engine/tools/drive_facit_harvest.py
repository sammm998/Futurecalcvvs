"""Plockar Drive-textformen av W-arbetsböckerna ur sessionsloggen och de sparade verktygsresultaten.

Drive-API:et ger arbetsboken som en enda textrad i ett verktygssvar. Svaren ligger i sessionsloggen (JSONL) och,
när de är för stora, som egna filer i tool-results/. Här samlas de per blad till data/validation_W/_drive/<blad>.txt
(git-ignorerat) och konverteras med drive_facit.save(). Ett blad som redan finns skrivs inte om.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from drive_facit import DATA, drawing_id, save  # noqa: E402

PROJ = "/root/.claude/projects/-home-user-vvs5"


def _texts():
    for line in open(f"{PROJ}/7ee765b4-ebb4-57f7-b191-c6a2444953b5.jsonl", encoding="utf-8"):
        if '"fileContent"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        for c in (obj.get("message", {}).get("content") or []):
            if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                continue
            cont = c.get("content")
            parts = [cont] if isinstance(cont, str) else [x.get("text", "") for x in (cont or []) if isinstance(x, dict)]
            for t in parts:
                if '"fileContent"' in t:
                    try:
                        yield json.loads(t)["fileContent"]
                    except Exception:
                        pass
    for p in glob.glob(f"{PROJ}/7ee765b4-ebb4-57f7-b191-c6a2444953b5/tool-results/mcp-Google_Drive-read_file_content-*.txt"):
        try:
            yield json.load(open(p, encoding="utf-8"))["fileContent"]
        except Exception:
            pass


def main(force: bool = False) -> None:
    out = f"{DATA}/validation_W/_drive"
    os.makedirs(out, exist_ok=True)
    seen: dict[str, int] = {}
    for fc in _texts():
        m = re.search(r"1,(W-50-1-A-\d{4}[^,]*\.pdf),", fc)
        if not m:
            continue
        did = drawing_id(m.group(1))
        if not did:
            continue
        if did in seen and seen[did] >= len(fc):
            continue
        seen[did] = len(fc)
        path = f"{out}/{did}.txt"
        if os.path.exists(path) and not force and os.path.getsize(path) >= len(fc.encode("utf-8")):
            continue
        open(path, "w", encoding="utf-8").write(fc)
    for did in sorted(seen):
        d = save(open(f"{out}/{did}.txt", encoding="utf-8").read(), did)
        n = sum(1 for _ in open(f"{d}/facit.csv", encoding="utf-8")) - 1
        print(f"{did}: {n} längdrader, clean.pdf={'ja' if os.path.exists(f'{d}/clean.pdf') else 'NEJ'}")


if __name__ == "__main__":
    main("--force" in sys.argv)
