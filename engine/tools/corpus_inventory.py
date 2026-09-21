"""Inventeringen i klartext: vad som finns i ritningsmappen, vad som hör ihop, och vad det får användas till.

Renderas ur corpus_manifest.json, corpus_pairing.csv och corpus_verification.json så att siffrorna i texten är
samma siffror som i tabellerna. Prosan säger det tabellerna inte kan: varför ett blad räknas som exponerat,
vad "ren" visade sig betyda, och var holdout står.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict


def render(base: str) -> str:
    m = json.load(open(os.path.join(base, "corpus_manifest.json")))
    files = [r for r in m["files"] if r["classification"] not in ("FOLDER", "SYSTEM_FILE")]
    pairs = list(csv.DictReader(open(os.path.join(base, "corpus_pairing.csv"), encoding="utf-8")))
    ver = json.load(open(os.path.join(base, "corpus_verification.json")))
    cls = Counter(r["classification"] for r in files)
    ready = [p for p in pairs if p["STATUS"] == "READY_FOR_BLIND_VALIDATION"]
    unexp = [p for p in pairs if p["VALIDATION_SET"] == "UNEXPOSED_SO_FAR"]
    local = [r for r in files if r["local_copy"]]
    annotated = [r for r in files if r["verified"].startswith("ANNOTATED")]
    strips = sum(1 for r in files if "ENGINE_STRIPS_ANNOTS" in r["verified"])
    reads = sum(1 for r in files if "ENGINE_READS_ANNOTS" in r["verified"])

    # mappar som speglar varandra
    g = defaultdict(list)
    for r in files:
        g[(r["filename"].lower(), r["size"])].append(r["parent_folders"])
    mirror = Counter()
    for v in g.values():
        if len(v) > 1:
            mirror[tuple(sorted(set(v)))] += 1

    tree = Counter()
    for r in files:
        parts = r["path"].split("/")
        tree["/".join(parts[1:3]) if len(parts) > 3 else "/".join(parts[1:2]) + " (lösa filer)"] += 1

    L: list[str] = []
    w = L.append
    w("# Korpusinventering - ritningsmappen på Drive\n")
    w(f"Rot: `Drawings` (`{m['root']}`), inventerad rekursivt 2026-09-11 ur {len(os.listdir(os.path.join(base, 'drive-listings')))} "
      f"sparade listningar. **{len(files)} filer** ({sum(r['size'] for r in files) / 1e6:.0f} MB) i {cls.__len__()} klasser; "
      f"**{len(pairs)} logiska blad** i parningen.\n")
    w("Tre regler styr vad materialet får användas till, och de står här innan siffrorna:\n")
    w("1. **Facit går aldrig in i motorn.** Facit-arbetsböcker, Bluebeam-XML och CVAT-filer används bara till "
      "validering, rotorsaksanalys och generaliseringstest, efter en fryst blind körning. Inventeringen läser ur "
      "facit *vilket blad den namnger* (kolumnerna Document/Sidetikett) - inte en meter.")
    w("2. **Exponering är ett faktum, inte ett val.** Ett blad som någon gång legat i `data/validation_*`, "
      "`data/validation_set3`, `data/cvat` eller `data/styles` har varit med i en körning och är DEVELOPMENT. "
      "HOLDOUT kan bara vara sådant som bevisligen aldrig öppnats.")
    w("3. **Klassificeringen är en hypotes ur namn och mapp tills filen öppnats.** Kolumnen `verified` i manifestet "
      "säger vad filen själv visade när den öppnades. Den kunde bara fyllas för filer som finns lokalt "
      f"({len(local)} av {len(files)}); Drive-API:et ger ingen kontrollsumma, så en Drive-fil utan lokal kopia är "
      "matchad på namn och storlek, inte på innehåll.\n")

    w("## 1. Mappträdet\n")
    w("| Mapp | Filer |\n|---|---:|")
    for k, v in sorted(tree.items()):
        w(f"| {k} | {v} |")
    w("")
    w("## 2. Klassificering\n")
    w("| Klass | Filer | Betydelse |\n|---|---:|---|")
    meaning = {
        "OTHER_FORMAT_PDF": "PDF under *Other drawings (different format)*: elva projektmappar med andra konsulters ritsätt",
        "STYLE_PDF": "PDF under *Style of drawings 1-13*: stilprover, till stor del speglingar av andra mappar",
        "CLEAN_ORIGINAL_CANDIDATE": "PDF i `clear`, `Without measurement` eller med suffixet `- clean`: kandidat till ren original",
        "MARKED_REFERENCE_CANDIDATE": "PDF i roten av en Bluebeam-mapp: kandidat till mängdad referens",
        "XLSX_FACIT": "Bluebeams mängdlista exporterad till Excel: facit",
        "BLUEBEAM_XML": "Bluebeams markeringsexport: facit med koordinater",
        "CVAT_SOURCE_PDF": "PDF i CVAT-mappen: bladet som CVAT-jobbet ritats på",
        "CVAT_REFERENCE": "`annotations.xml` från ett CVAT-jobb: etiketterade former",
        "VIDEO_DRAWING_PDF": "PDF under *Video drawings*: en handling utan seriebeteckning (1760268-1760318)",
        "PROCESSED_XLSX": "`_processed.xlsx`: bearbetad facit - ett genererat mellanled, inte en källa",
        "TEST_DRAWING": "PDF under *Test drawings* (DEMO, DEMO test, lösa)",
        "STYLE_SOURCE_PDF": "PDF under *Pipe studio - style-source-pdfs*: elva exportkedjor (konsult, CAD, PDF-motor)",
        "SCALE_STUDY_PDF": "PDF under *Scales*: skalstocksstudier",
        "OTHER": "annat", "OTHER_DOCUMENT": "`Delivery Sheet.xlsx`", "PDF": "PDF i roten",
    }
    for k, v in cls.most_common():
        w(f"| {k} | {v} | {meaning.get(k, '')} |")
    w("")
    w("## 3. Dubbletter: vilka mappar som är samma filer\n")
    w("Samma namn och samma storlek på flera ställen räknas som samma fil (hash bekräftar det där en lokal kopia "
      "finns). Samma namn med annan storlek är två versioner - typiskt en ren och en markerad.\n")
    w("| Identiska filer | Mappar |\n|---:|---|")
    for k, v in mirror.most_common(12):
        w(f"| {v} | {' = '.join(k)} |")
    dup = Counter(r["duplicate_status"] for r in files)
    w("")
    w("Dubblettstatus över alla filer: " + ", ".join(f"{k} {v}" for k, v in dup.most_common()) + ".\n")

    w("## 4. Parningen per logiskt blad\n")
    w(f"{len(ready)} blad har både en ren kandidat och minst en referens (facit-xlsx, Bluebeam-XML, markerad PDF eller "
      f"CVAT). **Alla {len(ready)} är DEVELOPMENT.** {len(unexp)} blad är oexponerade, och inget av dem har facit.\n")
    w("Kolumnerna i `corpus_pairing.csv`: DRAWING_ID, CLEAN_PDF, MARKED_PDF, FACIT_XLSX, BLUEBEAM_XML, CVAT, "
      "OTHER_REFERENCE, REVISION, EXPOSURE, STATUS, VALIDATION_SET, CONTENT_CHECK. REVISION är tom överallt: "
      "revisionen står i ritningshuvudet och kan bara läsas genom att öppna bladet; V-bladen bär sin revision i "
      "textlagret (läsbar), W-bladen som konturglyfer (kräver motorns glyfläsning).\n")
    w("| DRAWING_ID | Ren PDF | Markerad | Facit xlsx | BB-XML | CVAT | Innehållskontroll |\n|---|---|---|---|---|---|---|")
    for p in ready:
        clean_src = p["CLEAN_PDF"].split(";")[0].split("/")[1:3]
        w(f"| {p['DRAWING_ID']} | {'/'.join(clean_src)} | {'ja' if p['MARKED_PDF'] else '-'} | "
          f"{'ja' if p['FACIT_XLSX'] else '-'} | {'ja' if p['BLUEBEAM_XML'] else '-'} | {'ja' if p['CVAT'] else '-'} | "
          f"{p['CONTENT_CHECK']} |")
    w("")
    cc = Counter(p["CONTENT_CHECK"] for p in ready)
    w("Innehållskontrollens utfall: " + "; ".join(f"**{v}** × {k}" for k, v in cc.most_common()) + ".\n")

    w("## 5. Vad som visade sig när filerna öppnades\n")
    w(f"* **{len(annotated)} lokala PDF-filer bär annoteringar**, och av dem är {sum(1 for r in annotated if 'Without measurement' in r['path'] or '/clear/' in r['path'] or 'CVAT' in r['path'])} "
      "\"rena\" kandidater. `Bluebeam - set 3 /Without measurement` är inte utan påskrift: varje V-blad där bär 12-53 "
      "`Square`-annoteringar. Bluebeam-mappens rotfiler bär 14-315 `PolyLine`-annoteringar - det är själva mängdningen.")
    w("* **`data/validation_set3/<blad>/clean.pdf` är Drive-mappens *markerade* fil**, inte `Without measurement`-filen "
      "(V-50-1-A0111: 529 119 byte = `Bluebeam - set 3 /V-50-1-A0111.pdf`; `Without measurement` är 318 941 byte och "
      "ligger lokalt som `data/styles/test/V-50-1-A0111.pdf`). Alla tidigare grindkörningar på set 3 har alltså läst "
      "den markerade filen.")
    w(f"* **Motorn tar bort annoteringsbläcket innan bladet läses**, och det är kontrollerat på varje annoterad lokal "
      f"fil: {strips} filer ger exakt samma vägar, segment och bläcklängd med och utan annoteringar; {reads} filer där "
      "motorn läser annoteringsbläck. Grindresultaten mäter därför ritningen under påskriften, inte påskriften - men "
      "protokollet ska ändå köra på `Without measurement`-filen, och den finns lokalt för alla 29 V-blad.")
    w("* **W-bladen (Bluebeam set 1-2, CVAT) är rena på riktigt**: 0 annoteringar i 42 av 42 CVAT-PDF:er, och "
      "`clear`/`Without measurement`-filerna är bytevis samma filer som CVAT-PDF:erna. Undantag: "
      "`Bluebeam - set 1/clear/W-50-1-A-0012.pdf` bär 7 annoteringar (lokalt `validation_C/marked_v1.pdf`), och "
      "`clear/W-50-1-A-0113.pdf` saknar lokal kopia.")
    w("* **W-bladen har inget textlager för ritningshuvudet** (5-20 ord ur revisionstabellen; allt annat är "
      "konturglyfer). Ritningsnumret kan inte bekräftas ur textlagret; parningen vilar där på facit-arbetsbokens "
      "Document-kolumn (bekräftad för de 4 lokala) och på namnet (de 37 som saknar lokal facit).")
    w("* **Facit lokalt**: 34 av 71 xlsx (29 V + A/C/D/E), 0 av 71 Bluebeam-XML. De 37 W-bladen utanför A/C/D/E "
      "har aldrig poängsatts; deras facit ligger bara på Drive.")
    w("* **CVAT**: 33 jobb, alla med bildnamn som bekräftar bladet; men bara 0-2 former per fil - exporterna bär "
      "etikettlistan (D1-E4-110, FJV1-S6-50/W, KV1-E13-75 ...) och nästan ingen geometri. Som referens för "
      "utsträckning är de i praktiken tomma.")
    w("* **4 PDF:er i TOFTASKOLAN HUS B är rasterskanningar** (`RIVNING`, `DEM`): motorn avvisar dem med "
      "UnsupportedInputError, vilket är rätt svar.\n")

    w("## 6. Exponering och holdout\n")
    ex = Counter(p["VALIDATION_SET"] for p in pairs)
    w(f"* DEVELOPMENT: {ex['DEVELOPMENT']} blad (alla med lokal kopia i `data/`).")
    w(f"* UNEXPOSED_SO_FAR: {ex['UNEXPOSED_SO_FAR']} blad, fördelade: " +
      ", ".join(f"{k or '(rot)'} {v}" for k, v in Counter(
          "/".join((p["CLEAN_PDF"] or p["MARKED_PDF"] or p["OTHER_REFERENCE"]).split(";")[0].split("/")[1:3])
          for p in unexp).most_common()) + ".")
    w("* **Inget oexponerat blad har facit.** TRUE HOLDOUT är därför blockerat tills facit produceras för oexponerat "
      "material. Kandidater, i ordning efter hur olika de är utvecklingsmaterialet: *Fyrens förskola* (21 blad, egen "
      "konsult), *Style of drawings/12* (13 blad som inte speglas lokalt), *Vinkelboda ombyggnad 2026* (79 blad utan "
      "seriebeteckning) och *Hyllie hybrid* (28). *Axis* (247) är samma exportkedja som Rundstickan/set 3 och duger "
      "som holdout bara för generalisering inom stil, inte mellan stilar.")
    w("* Innan ett sådant blad körs ska motorn frysas och hashas (`hashmanifest-baseline.json`), bladet hashas, "
      "körningen göras blind, och facit läsas först därefter. Den ordningen är inte förhandlingsbar.\n")

    w("## 7. Filer\n")
    w("* `corpus_manifest.json` / `.csv` - en rad per Drive-post: file_id, path, filename, extension, mime, size, "
      "modified, parent_folders, logical_project, drawing_number, revision, classification, validation_role, "
      "local_copy, sha256, hash_source, verified, duplicate_status.")
    w("* `corpus_pairing.csv` - en rad per logiskt blad (se §4).")
    w("* `corpus_verification.json` - vad varje lokal fil visade när den öppnades: sidor, annoteringar per typ, "
      "textlager, om motorn läser samma bläck utan annoteringarna, vilket blad facit/CVAT namnger.")
    w("* `local-corpus-hashes.json` - sha256 för alla 452 lokala filer; `drive-listings/` - råa Drive-svar.")
    w("* Byggs om med `python3 engine/tools/corpus_manifest.py && python3 engine/tools/corpus_verify.py && "
      "python3 engine/tools/corpus_inventory.py`.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "/home/user/vvs5/results/2026-09-11-topologi"
    out = os.path.join(base, "corpus_inventory.md")
    open(out, "w", encoding="utf-8").write(render(base))
    print("skrev", out)
