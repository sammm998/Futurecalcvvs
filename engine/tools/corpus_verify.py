"""Parningen kontrollerad mot innehållet, inte mot filnamnet.

Manifestet säger vad en fil *troligen* är, utifrån mapp och namn. Det här steget öppnar de filer som finns
lokalt och frågar dem själva: står ritningsnumret i bladets text? Har det rena bladet noll annoteringar? Vilket
blad säger facit-arbetsboken att den mäter? Vilken bild säger CVAT-filen att den ritats på?

Av facit läses bara *vilket blad* den hör till (kolumnerna Document/Sidetikett) - inte en meter. Metrarna hör
till poängsättningen, som är ett eget steg efter en fryst blind körning. Ingenting härifrån når motorn.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter

DATA = "/home/user/vvs5/data"


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def id_variants(did: str) -> set[str]:
    """V-50-1-A0312 skrivs också V-50-1-A-0312, V50-1-A0312 ... ett normaliserat jämförelsevärde räcker."""
    return {norm(did)}


def check_pdf(path: str, did: str) -> dict:
    import pymupdf
    doc = pymupdf.open(path)
    annots = Counter()
    n_annots = 0
    text_hits = 0
    words = 0
    for page in doc:
        for a in page.annots():
            n_annots += 1
            annots[a.type[1]] += 1
        raw = page.get_text("text")
        words += len(raw.split())
        if did and norm(did) in norm(raw):
            text_hits += 1
    # ett blad vars text är konturglyfer (W-serien) har bara revisionstabellen i textlagret; då kan
    # ritningshuvudet inte frågas den vägen, och det är inte samma sak som att numret saknas
    out = {"kind": "pdf", "pages": doc.page_count, "annotations": n_annots,
           "annotation_types": dict(annots), "id_in_text_pages": text_hits, "text_words": words,
           "id_in_text": (True if text_hits else False if words >= TEXT_LAYER_MIN_WORDS else None) if did else None}
    doc.close()
    if n_annots:
        out["engine_strips_annotations"] = engine_strips_annotations(path)
    return out


# under så många ord finns inget textlager att fråga om ritningshuvudet (W-bladen: 5-20 ord ur revisionstabellen)
TEXT_LAYER_MIN_WORDS = 50


def engine_strips_annotations(path: str) -> dict:
    """Läser motorn samma bläck med och utan bladets annoteringar? Det är kontraktet i pdf/extract.py
    (ANNOTATION_INK_IS_REVIEW) - och det är bara ett kontrakt om det stämmer på det här bladet."""
    import tempfile
    import pymupdf
    sys.path.insert(0, "/home/user/vvs5/engine")
    from vvs_engine.pdf.extract import extract_document

    def fingerprint(p):
        pg = extract_document(p).pages[0]
        return (len(pg.paths), sum(len(x.segs) for x in pg.paths), round(sum(x.length for x in pg.paths), 1))
    with_ = fingerprint(path)
    doc = pymupdf.open(path)
    n = 0
    for pg in doc:
        # samma slinga som motorn: delete_annot lämnar tillbaka nästa, en lista av Annot-objekt blir obunden
        a = pg.first_annot
        while a:
            a = pg.delete_annot(a); n += 1
    tmp = tempfile.mktemp(suffix=".pdf")
    doc.save(tmp); doc.close()
    without = fingerprint(tmp)
    os.unlink(tmp)
    return {"removed": n, "paths_with": with_, "paths_without": without, "identical": with_ == without}


def check_xlsx(path: str, did: str) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    docs: Counter = Counter()
    labels: Counter = Counter()
    n_rows = 0
    head = None
    for ws in wb.worksheets:
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                head = [str(c) if c is not None else "" for c in row]
                continue
            if not any(c is not None for c in row):
                continue
            n_rows += 1
            if head:
                for key in ("Document", "Sidetikett"):
                    if key in head:
                        v = row[head.index(key)]
                        if v:
                            (docs if key == "Document" else labels)[str(v)] += 1
    wb.close()
    ids = {norm(re.sub(r"^\[\d+\]\s*", "", d).rsplit(".", 1)[0]) for d in list(docs) + list(labels)}
    return {"kind": "xlsx", "rows": n_rows, "documents": sorted(docs), "page_labels": sorted(labels)[:5],
            "id_in_workbook": (norm(did) in ids) if did else None,
            "other_ids_in_workbook": sorted(i for i in ids if did and i != norm(did))}


def check_cvat_xml(path: str, did: str) -> dict:
    txt = open(path, encoding="utf-8", errors="replace").read()
    names = re.findall(r'<image[^>]*\bname="([^"]+)"', txt)
    shapes = len(re.findall(r"<(polyline|polygon|box|points)\b", txt))
    labels = sorted(set(re.findall(r"<label>\s*<name>([^<]+)</name>", txt)))
    hit = any(norm(did) in norm(n) for n in names) if did and names else None
    return {"kind": "cvat_xml", "images": names[:3], "shapes": shapes, "labels": labels[:40],
            "id_in_image_name": hit}


def verify(manifest_path: str) -> dict:
    m = json.load(open(manifest_path))
    rows = m["files"]
    out: dict[str, dict] = {}
    seen_local: dict[str, dict] = {}
    for r in rows:
        lc = r.get("local_copy")
        if not lc:
            continue
        p = os.path.join(DATA, lc)
        if not os.path.isfile(p):
            r["verified"] = "LOCAL_COPY_MISSING"
            continue
        did = r.get("drawing_number") or ""
        try:
            if lc in seen_local:
                res = seen_local[lc]
            elif p.lower().endswith(".pdf"):
                res = check_pdf(p, did)
            elif p.lower().endswith(".xlsx"):
                res = check_xlsx(p, did)
            elif p.lower().endswith(".xml"):
                res = check_cvat_xml(p, did)
            else:
                res = {"kind": "other"}
            seen_local[lc] = res
        except Exception as e:  # en trasig fil är ett fynd, inte ett stopp
            res = {"kind": "error", "error": f"{type(e).__name__}: {e}"}
        out[r["file_id"]] = {"path": r["path"], "local_copy": lc, "drawing_number": did, **res}
        # domen i manifestets kolumn
        v = []
        if res.get("kind") == "pdf":
            v.append("ANNOTATED(%d)" % res["annotations"] if res["annotations"] else "NO_ANNOTATIONS")
            if res.get("engine_strips_annotations"):
                v.append("ENGINE_STRIPS_ANNOTS" if res["engine_strips_annotations"]["identical"] else "ENGINE_READS_ANNOTS")
            if res.get("id_in_text") is True:
                v.append("ID_IN_SHEET_TEXT")
            elif res.get("id_in_text") is False:
                v.append("ID_NOT_IN_SHEET_TEXT")
            elif did:
                v.append("NO_TEXT_LAYER_FOR_TITLE_BLOCK")
        elif res.get("kind") == "xlsx":
            v.append("FACIT_NAMES_THIS_SHEET" if res.get("id_in_workbook") else "FACIT_NAMES_OTHER_SHEET")
            if res.get("other_ids_in_workbook"):
                v.append("ALSO:" + ",".join(res["other_ids_in_workbook"][:3]))
        elif res.get("kind") == "cvat_xml":
            v.append("CVAT_IMAGE_IS_THIS_SHEET" if res.get("id_in_image_name") else "CVAT_IMAGE_UNNAMED_OR_OTHER")
            v.append("SHAPES(%d)" % res["shapes"])
        elif res.get("kind") == "error":
            v.append("UNREADABLE")
        r["verified"] = " ".join(v)
    return {"files": out, "manifest": m}


def pair_verdicts(pairs_csv: str, m: dict) -> list[dict]:
    """Per logiskt blad: är paret ren PDF + referens bekräftat av innehållet?"""
    by_path = {r["path"]: r for r in m["files"]}
    table = list(csv.DictReader(open(pairs_csv, encoding="utf-8")))
    for p in table:
        clean = [by_path.get(x.strip()) for x in p["CLEAN_PDF"].split(";") if x.strip()]
        facit = [by_path.get(x.strip()) for x in p["FACIT_XLSX"].split(";") if x.strip()]
        cvat = [by_path.get(x.strip()) for x in p["CVAT"].split(";") if x.strip()]
        marked = [by_path.get(x.strip()) for x in p["MARKED_PDF"].split(";") if x.strip()]
        vc = [r["verified"] for r in clean if r and r.get("verified")]
        vf = [r["verified"] for r in facit if r and r.get("verified")]
        vx = [r["verified"] for r in cvat if r and r.get("verified")]
        vm = [r["verified"] for r in marked if r and r.get("verified")]
        notes = []
        if p["STATUS"] != "READY_FOR_BLIND_VALIDATION":
            p["CONTENT_CHECK"] = "NOT_A_PAIR"
            continue
        if not vc and not vf:
            p["CONTENT_CHECK"] = "UNVERIFIED_NO_LOCAL_COPY"
            continue
        ok = True
        if vc:
            if not any("NO_ANNOTATIONS" in v for v in vc):
                if all("ENGINE_STRIPS_ANNOTS" in v for v in vc if "ANNOTATED" in v):
                    notes.append("ren kandidat bär annoteringar som motorn bevisligen tar bort")
                else:
                    ok = False; notes.append("ren kandidat bär annoteringar som motorn läser")
            if any("ID_NOT_IN_SHEET_TEXT" in v for v in vc):
                ok = False; notes.append("ritningsnumret står inte i bladets text")
            elif not any("ID_IN_SHEET_TEXT" in v for v in vc):
                notes.append("inget textlager att läsa ritningshuvudet ur (konturglyfer)")
        else:
            notes.append("ren PDF ej lokalt")
        if vf:
            if not any("FACIT_NAMES_THIS_SHEET" in v for v in vf):
                ok = False; notes.append("facit namnger ett annat blad")
        else:
            notes.append("facit ej lokalt")
        if vx and not any("CVAT_IMAGE_IS_THIS_SHEET" in v for v in vx):
            notes.append("CVAT-bilden namnger inte bladet")
        if vm and not any("ANNOTATED" in v for v in vm):
            notes.append("markerad PDF saknar annoteringar")
        p["CONTENT_CHECK"] = ("PAIR_VERIFIED_BY_CONTENT" if ok and vc and vf else
                              "PAIR_PARTLY_VERIFIED" if ok else "PAIR_MISMATCH") + (": " + "; ".join(notes) if notes else "")
    return table


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "/home/user/vvs5/results/2026-09-11-topologi"
    mp = os.path.join(base, "corpus_manifest.json")
    r = verify(mp)
    m = r["manifest"]
    json.dump(m, open(mp, "w"), indent=1, ensure_ascii=False)
    with open(os.path.join(base, "corpus_manifest.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(m["files"][0].keys()))
        w.writeheader(); w.writerows(m["files"])
    table = pair_verdicts(os.path.join(base, "corpus_pairing.csv"), m)
    with open(os.path.join(base, "corpus_pairing.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        w.writeheader(); w.writerows(table)
    json.dump(r["files"], open(os.path.join(base, "corpus_verification.json"), "w"), indent=1, ensure_ascii=False)
    print("kontrollerade filer:", len(r["files"]))
    print("domar:", Counter(v["verified"].split(" ")[0] if v.get("verified") else "-" for v in m["files"] if v.get("local_copy")).most_common())
    print("par:", Counter(p["CONTENT_CHECK"].split(":")[0] for p in table).most_common())
    for p in table:
        if p["CONTENT_CHECK"].startswith(("PAIR_MISMATCH", "PAIR_PARTLY")):
            print("  ", p["DRAWING_ID"], p["CONTENT_CHECK"])
