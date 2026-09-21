"""Corpusmanifestet: varje fil i ritningsmappen, vad den är, och vad den hör ihop med.

Listningarna kommer från Google Drive (sparade som JSON i results/.../drive-listings). Härifrån byggs tre
saker: ett manifest per fil (JSON + CSV), en parningstabell per logiskt blad (ren PDF, markerad PDF, facit,
Bluebeam-XML, CVAT), och en inventering i klartext.

Tre saker sägs rakt ut, för de avgör vad materialet får användas till:

* **Klassificeringen är en hypotes ur namn, mapp och storlek** tills filen faktiskt inspekterats. "clear",
  "Without measurement" och "Bluebeam" är starka ledtrådar, inte sanning; kolumnen `verified` säger om
  innehållet kontrollerats (bara de blad som finns lokalt kan kontrolleras härifrån).
* **Dubbletter avgörs på storlek och namn, och på hash där en lokal kopia finns.** Samma namn i två mappar med
  olika storlek är två versioner - en ren och en markerad, eller två revisioner - och det står så.
* **Exponeringen är vad den är.** Varje blad som någon gång legat i data/validation_* eller data/validation_set3
  eller data/cvat är DEVELOPMENT; det har varit med i tidigare körningar. HOLDOUT kan bara vara sådant som
  bevisligen aldrig öppnats av motorn, och det får inte vara nära släkt (samma projekt, samma konsult, samma
  exportkedja) med något på utvecklingssidan.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

ROOT_ID = "1XXbhHA7D52kBEMVKOdvU2yil2txTwWr6"
ROOT_NAME = "Drawings"
DRAWING_RE = re.compile(r"\b([VW])-?(\d{2,3})-?(\d)-?([A-Z]{1,3})?-?(\d{3,4})\b", re.IGNORECASE)
# ritningsnummer som saknar seriebokstav: "R9UHA10-CLB001-004", "1760274_1", "3.pdf"
OTHER_RE = re.compile(r"^(R9UHA10-CLB001-\d{3}|17602\d\d_1|17603\d\d_1)$")

# vilka blad motorn redan läst - allt som ligger i det lokala materialet under de här katalogerna
DEVELOPMENT_DIRS = ("validation_A", "validation_C", "validation_D", "validation_E", "validation_set3", "cvat",
                    "dev", "openworld_quarantine", "styles")


def load_listings(folder: str) -> dict[str, dict]:
    """Alla poster ur alla sparade listningar, med id som nyckel (dubbletter mellan listningar faller bort)."""
    out: dict[str, dict] = {}
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".txt") and not fn.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(folder, fn), encoding="utf-8"))
        except Exception:
            continue
        for f in d.get("files", []):
            out[f["id"]] = f
    return out


def paths_of(items: dict[str, dict]) -> dict[str, str]:
    """Mappvägen till varje post, byggd ur parentId-kedjan."""
    names = {ROOT_ID: ROOT_NAME}
    parents = {ROOT_ID: None}
    for f in items.values():
        names[f["id"]] = f["title"]
        parents[f["id"]] = f.get("parentId")
    out = {}
    for fid in items:
        chain = []
        cur = fid
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            chain.append(names.get(cur, cur))
            cur = parents.get(cur)
        out[fid] = "/".join(reversed(chain))
    return out


def drawing_id(name: str) -> str | None:
    base = name.rsplit(".", 1)[0]
    base = re.sub(r"\s*-\s*clean$", "", base, flags=re.IGNORECASE)
    base = re.sub(r"_processed$|_cvat_job\d+$", "", base, flags=re.IGNORECASE)
    m = DRAWING_RE.search(base)
    if m:
        s, a, b, letters, n = m.groups()
        letters = (letters or "").upper()
        # V-50-1-A0312 och W-50-1-A-0312 skrivs på två sätt av samma sorts nummer: normalisera till ett
        return f"{s.upper()}-{a}-{b}-{letters}{n.zfill(4)}"
    m = OTHER_RE.match(base)
    if m:
        return base
    if re.fullmatch(r"\d{1,3}", base):
        return None                       # "3.pdf" utan sammanhang: bladet namnges av sin mapp i stället
    return None


def classify(f: dict, path: str) -> tuple[str, str]:
    """(classification, validation_role_hint) ur namn, mapp och typ - en hypotes tills filen setts."""
    name = f["title"]
    low = name.lower()
    mime = f.get("mimeType", "")
    folder = path.lower()
    if mime == "application/vnd.google-apps.folder":
        return "FOLDER", ""
    if low in ("icon_", ".ds_store", ".gitkeep") or f.get("fileSize") == "0":
        return "SYSTEM_FILE", ""
    if low.endswith(".xlsx"):
        if "_processed" in low:
            return "PROCESSED_XLSX", "GENERATED_ARTIFACT"
        if low == "delivery sheet.xlsx":
            return "OTHER_DOCUMENT", ""
        return "XLSX_FACIT", "VALIDATION"
    if low.endswith(".xml"):
        if low == "annotations.xml" or "cvat" in folder:
            return "CVAT_REFERENCE", "VALIDATION"
        return "BLUEBEAM_XML", "VALIDATION"
    if low.endswith(".pdf"):
        if "/cvat/" in folder + "/":
            return "CVAT_SOURCE_PDF", "DEVELOPMENT"
        if "clear" in folder or "without measurement" in folder or "- clean" in low:
            return "CLEAN_ORIGINAL_CANDIDATE", ""
        if "bluebeam - set" in folder:
            return "MARKED_REFERENCE_CANDIDATE", "VALIDATION"
        if "test drawings" in folder or "demo" in folder:
            return "TEST_DRAWING", ""
        if "scales" in folder:
            return "SCALE_STUDY_PDF", ""
        if "video drawings" in folder:
            return "VIDEO_DRAWING_PDF", ""
        if "pipe studio" in folder:
            return "STYLE_SOURCE_PDF", ""
        if "style of drawings" in folder:
            return "STYLE_PDF", ""
        if "other drawings" in folder:
            return "OTHER_FORMAT_PDF", ""
        return "PDF", ""
    return "OTHER", ""


def local_index(hash_file: str) -> tuple[dict[tuple[str, int], dict], dict[str, list[dict]]]:
    """Lokala kopior: (namn, storlek) -> post, och storlek -> poster (för att känna igen samma innehåll
    under ett annat namn, t.ex. clean.pdf i validation_set3)."""
    by_name_size: dict[tuple[str, int], dict] = {}
    by_size: dict[int, list[dict]] = defaultdict(list)
    if not os.path.isfile(hash_file):
        return by_name_size, by_size
    for r in json.load(open(hash_file)):
        by_name_size[(r["name"].lower(), r["size"])] = r
        by_size[r["size"]].append(r)
    return by_name_size, dict(by_size)


def build(listings_dir: str, hash_file: str, out_dir: str) -> dict:
    items = load_listings(listings_dir)
    paths = paths_of(items)
    by_name_size, by_size = local_index(hash_file)
    rows = []
    for fid, f in items.items():
        path = paths[fid]
        cls, role = classify(f, path)
        size = int(f.get("fileSize") or 0)
        name = f["title"]
        local = by_name_size.get((name.lower(), size))
        same_size = [r for r in by_size.get(size, []) if r["ext"] == (name.rsplit(".", 1)[-1].lower() if "." in name else "")] if size else []
        if local is None and len(same_size) == 1:
            local = same_size[0]                 # samma storlek och typ, annat namn: sannolikt samma innehåll
        exposure = ""
        if local is not None:
            top = local["path"].split("/")[0]
            exposure = "DEVELOPMENT" if top in DEVELOPMENT_DIRS else "LOCAL_OTHER"
        parts = path.split("/")
        did = drawing_id(name)
        if did is None and len(parts) > 2:
            # "annotations.xml" i mappen V-50-1-A0111_cvat_job3293971, eller "3.pdf" i en bladmapp: numret är mappens
            did = drawing_id(parts[-2])
        rows.append({
            "file_id": fid, "path": path, "filename": name,
            "extension": (name.rsplit(".", 1)[-1].lower() if "." in name and not name.startswith(".") else ""),
            "mime": f.get("mimeType", ""), "size": size, "modified": f.get("modifiedTime", ""),
            "parent_folders": "/".join(parts[1:-1]),
            "logical_project": parts[1] if len(parts) > 1 else "",
            "drawing_number": did or "",
            "revision": "",                        # avgörs bara genom att öppna ritningshuvudet
            "classification": cls,
            "validation_role": (exposure if exposure == "DEVELOPMENT" else role),
            "local_copy": local["path"] if local else "",
            "sha256": local["sha256"] if local else "",
            "hash_source": ("lokal kopia, samma namn och storlek" if local and local["name"].lower() == name.lower()
                            else "lokal kopia, samma storlek och typ" if local else "ej hämtad"),
            "verified": "",
        })
    # dubbletter: samma namn och storlek på flera ställen är samma fil; samma namn med annan storlek är en version
    by_ns: dict[tuple[str, int], list[dict]] = defaultdict(list)
    by_n: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        if r["classification"] in ("FOLDER", "SYSTEM_FILE"):
            continue
        by_ns[(r["filename"].lower(), r["size"])].append(r)
        by_n[r["filename"].lower()].add(r["size"])
    for r in rows:
        k = (r["filename"].lower(), r["size"])
        n = len(by_ns.get(k, []))
        versions = len(by_n.get(r["filename"].lower(), set()))
        r["duplicate_status"] = ("UNIQUE" if n == 1 and versions == 1 else
                                 f"IDENTICAL_IN_{n}_PLACES" if n > 1 and versions == 1 else
                                 f"{versions}_VERSIONS_BY_SIZE" + (f"_x{n}" if n > 1 else ""))
    # parningstabell per logiskt blad
    pairs: dict[str, dict] = {}
    for r in rows:
        did = r["drawing_number"]
        if not did or r["classification"] in ("FOLDER", "SYSTEM_FILE"):
            continue
        p = pairs.setdefault(did, {"DRAWING_ID": did, "CLEAN_PDF": [], "MARKED_PDF": [], "FACIT_XLSX": [],
                                   "BLUEBEAM_XML": [], "CVAT": [], "OTHER_REFERENCE": [], "REVISION": "",
                                   "EXPOSURE": set()})
        c = r["classification"]
        col = {"CLEAN_ORIGINAL_CANDIDATE": "CLEAN_PDF", "CVAT_SOURCE_PDF": "CLEAN_PDF",
               "MARKED_REFERENCE_CANDIDATE": "MARKED_PDF", "XLSX_FACIT": "FACIT_XLSX",
               "BLUEBEAM_XML": "BLUEBEAM_XML", "CVAT_REFERENCE": "CVAT",
               "PROCESSED_XLSX": "OTHER_REFERENCE"}.get(c)
        if col is None:
            if c.endswith("PDF") or c == "PDF":
                col = "OTHER_REFERENCE"
            else:
                continue
        p[col].append(r["path"])
        if r["validation_role"] == "DEVELOPMENT":
            p["EXPOSURE"].add("DEVELOPMENT")
    table = []
    for did, p in sorted(pairs.items()):
        has_clean = bool(p["CLEAN_PDF"])
        has_ref = bool(p["MARKED_PDF"] or p["FACIT_XLSX"] or p["BLUEBEAM_XML"] or p["CVAT"])
        status = ("READY_FOR_BLIND_VALIDATION" if has_clean and has_ref else
                  "CLEAN_ONLY_NO_FACIT" if has_clean else
                  "REFERENCE_WITHOUT_CLEAN" if has_ref else "UNPAIRED")
        table.append({**{k: (v if not isinstance(v, (list, set)) else "; ".join(sorted(v))) for k, v in p.items()},
                      "STATUS": status,
                      "VALIDATION_SET": ("DEVELOPMENT" if "DEVELOPMENT" in p["EXPOSURE"] else "UNEXPOSED_SO_FAR")})
    os.makedirs(out_dir, exist_ok=True)
    json.dump({"root": ROOT_ID, "files": rows}, open(os.path.join(out_dir, "corpus_manifest.json"), "w"),
              indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, "corpus_manifest.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    with open(os.path.join(out_dir, "corpus_pairing.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        w.writeheader(); w.writerows(table)
    return {"files": rows, "pairs": table, "paths": paths}


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "/home/user/vvs5/results/2026-09-11-topologi"
    r = build(os.path.join(base, "drive-listings"), os.path.join(base, "local-corpus-hashes.json"), base)
    from collections import Counter
    files = [f for f in r["files"] if f["classification"] not in ("FOLDER", "SYSTEM_FILE")]
    print("poster:", len(r["files"]), "varav filer:", len(files))
    print("klassificering:", Counter(f["classification"] for f in files).most_common())
    print("roll:", Counter(f["validation_role"] or "-" for f in files).most_common())
    print("hash:", Counter(f["hash_source"] for f in files).most_common())
    print("blad i parningen:", len(r["pairs"]), Counter(p["STATUS"] for p in r["pairs"]).most_common())
    print("exponering:", Counter(p["VALIDATION_SET"] for p in r["pairs"]).most_common())
