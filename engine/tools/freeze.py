"""Frys motorn: en hash per källfil och commit-id, så att en körning går att binda till exakt den kod som gjorde den.

    python3 engine/tools/freeze.py results/<dag>/hashmanifest-<namn>.json

Manifestet är det som gör en blind körning blind: det skrivs INNAN referensen öppnas, och den som vill veta om
motorn ändrats mellan körning och poängsättning jämför två manifest i stället för att lita på någons minne.
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = "/home/user/vvs5"
SCAN = ("engine/vvs_engine", "engine/tools", "backend/app")


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()[:16]


def manifest() -> dict:
    files = {}
    for top in SCAN:
        for dp, _, fs in os.walk(os.path.join(ROOT, top)):
            if "__pycache__" in dp:
                continue
            for f in sorted(fs):
                if f.endswith((".py", ".jhf", ".txt")):
                    p = os.path.join(dp, f)
                    files[os.path.relpath(p, ROOT)] = sha(p)
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--short", "--", *SCAN], cwd=ROOT, text=True).strip()
    except Exception:
        head, dirty = "", ""
    whole = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()[:16]
    return {"commit": head, "uncommitted": dirty.splitlines(), "n_files": len(files), "manifest_sha256": whole,
            "python": sys.version.split()[0], "files": files}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "results", "hashmanifest.json")
    m = manifest()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(m, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"{out}: {m['n_files']} filer, manifest {m['manifest_sha256']}, commit {m['commit'][:12]}, "
          f"{len(m['uncommitted'])} ändrade filer utanför commit")
