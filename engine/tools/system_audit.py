"""Systemrevisionen: varje delsystem klassat efter vad koden gör, inte efter vad dokumenten säger.

En post per delsystem med filer, dom, bevis (lästa rader, mätta tal, körda prov) och vad som saknas. Renderas
till SYSTEM_AUDIT.md och SYSTEM_AUDIT.json ur samma lista, så att de två aldrig säger olika saker.

Domarna:
  GOOD              gör det den ska, med prov som håller det
  GOOD_BUT_FRAGILE  gör det den ska, men vilar på en gräns, ett antagande eller en väg som kan brista
  PARTIAL           gör en del av det uppdraget kräver; resten saknas och är namngiven
  BROKEN            gör fel på verkligt material, påvisat
  UNSAFE            kan ge fel säkerhet (meter utan grund) - måste stoppas före allt annat
  MISSING           finns inte
  MOCK              låtsas: fast svar, stubb, attrapp
  DEAD_CODE         finns men nås aldrig
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

AUDIT_DATE = "2026-09-11"
BASELINE = {"commit_before": "57eb537", "tests": "400 passed (engine/tests, Linux, Python 3.11.15, PyMuPDF 1.28.2)",
            "gate": "gate52: 33 blad, täckning 79,31 %, falska 27,26 %, 267/365 beteckningar rätt, 76 påhittade"}

E = []  # (subsystem, files, verdict, evidence, gap)

def add(area, subsystem, files, verdict, evidence, gap=""):
    E.append({"area": area, "subsystem": subsystem, "files": files, "verdict": verdict, "evidence": evidence, "gap": gap})

# ------------------------------------------------------------------ motor: läsningen av PDF:en
add("motor/pdf", "Råextraktion: vägar, text, lager, teckensnitt", ["engine/vvs_engine/pdf/extract.py"], "GOOD",
    "En läsning per sida; rotation via rotation_matrix; lager-id numreras ur sidans egna namn; stabila pid ur "
    "geometrin. Lat läsning (eager=False) håller en sida i taget. 14 prov på märken + omläsning. Verkliga blad: "
    "V-50-1-A0111 9 321 vägar / 45 262 segment identiskt med och utan sina 100 polylinjer.")
add("motor/pdf", "Annoteringar: inventering, borttagning med bevis, MARKUP_ONLY", ["engine/vvs_engine/pdf/extract.py"], "GOOD",
    "Rättat 2026-09-11: inventering (slag, rect, xref, AP/N, författare, text, avtryck) före klassificering; "
    "borttagning med drawings_before/after och annotations_left; delvis borttagning => sidan UNSAFE och oläst; "
    "markup-only flaggas i input_class. Kontrollerat på 231 annoterade lokala filer: 231 identiska, 0 där motorn "
    "läser annoteringsbläck (results/2026-09-11-topologi/corpus_verification.json).",
    "Inget - men protokollet ska köra på 'Without measurement'-filerna, inte de markerade (se corpus_inventory.md §5).")
add("motor/pdf", "Sidklassificering vektor/raster/tom", ["engine/vvs_engine/pdf/classify.py"], "GOOD_BUT_FRAGILE",
    "Trösklar: >=200 vägar, eller >=50 vägar + >=50 tecken => vektor; bild >=50 % => raster/mixed. Körs nu på sidan "
    "utan påskrift. 4 rasterblad i TOFTASKOLAN avvisas korrekt.",
    "Trösklarna är fasta tal, inte härledda ur bladet; ett glest vektorblad (<50 vägar) med en logotyp blir 'raster'.")
# ------------------------------------------------------------------ motor: text
add("motor/text", "Konturglyfer -> tecken -> textrader (W-stilen)",
    ["engine/vvs_engine/text/strokes.py", "engine/vvs_engine/text/recognize.py", "engine/vvs_engine/text/vector_text.py",
     "engine/vvs_engine/text/postprocess.py", "engine/vvs_engine/text/hershey.py"], "GOOD_BUT_FRAGILE",
    "Generisk igenkänning (storleksfamiljer, glyffamiljer, Hershey-referens). 267 av 365 facitbeteckningar rätt "
    "på 33 blad (gate52). Bara futural.jhf av tre listade Hershey-filer finns i text/data.",
    "Siffran 5 är svag över hela korpusen (S01-P3-160 läses som 5; '1:S0'); 76 påhittade beteckningar på 33 blad.")
add("motor/text", "Sökbar PDF-text", ["engine/vvs_engine/text/searchable.py"], "GOOD",
    "V-bladen läses ur textlagret direkt (rawdict, ligaturer bevarade), aldrig OCR.")
add("motor/text", "OCR-hjälp för onämnda tecken", ["engine/vvs_engine/text/ocr_assist.py", "engine/vvs_engine/review/ocr_check.py"], "PARTIAL",
    "Valbar (rapidocr_onnxruntime), av som standard, inte installerad i den här miljön; motorn kör utan.",
    "Ingen prov-täckning här; en andra åsikt, aldrig lastbärande.")
# ------------------------------------------------------------------ motor: semantik
add("motor/semantik", "Beteckningsgrammatik och DN-rekonstruktion",
    ["engine/vvs_engine/semantics/annotation.py", "engine/vvs_engine/semantics/grammar.py"], "GOOD_BUT_FRAGILE",
    "Grammatiken upptäcks per ritning (system-material-DN-former); staplade rader, understrykningar, ramar. "
    "Kontaminationsskannern förbjuder beteckningsliteraler i motorn (PASS i CI).",
    "Precisionen: 76 påhittade beteckningar/33 blad kommer huvudsakligen från glyfläsningen, inte grammatiken.")
add("motor/semantik", "Hänvisningslinjer (verkliga CAD-leaders, aldrig närmast)",
    ["engine/vvs_engine/semantics/leaders.py", "engine/vvs_engine/semantics/attachment.py"], "GOOD_BUT_FRAGILE",
    "Anknytning kräver att en leader faktiskt når rörgeometri; bijektion mellan rader och kompatibla grupper, annars "
    "AMBIGUOUS ('Never nearest-distance', attachment.py:6; kod följer). Bläckkontraktet (pipes/ink.py) gör att "
    "anknytning och topologi ser samma bläck (gate52 = gate51 på 33/33).",
    "Toleranser (TOUCH_TOL 0,15 pt, SYMBOL_OFF 0,6 pt, NEAR_MISS) är fasta konstanter, inte härledda ur bladets penna.")
add("motor/semantik", "Bladets egen beteckningslista och deklarationer",
    ["engine/vvs_engine/semantics/legend.py", "engine/vvs_engine/semantics/declarations.py"], "GOOD",
    "Legenden är inte obligatorisk (legend.own flaggar); platshållarkoder (BXXX) hanteras; en bladtabell kan "
    "deklarera anslutningsrör som ingen etikett når (DECLARED_CONNECTION_PIPE_BY_SHEET_TABLE).")
add("motor/semantik", "Andra läsaren (Astra) bunden till kandidater", ["engine/vvs_engine/semantics/astra.py", "engine/tools/astra_transport.py"], "GOOD",
    "verify() släpper bara igenom ett svar som ordagrant är en av kandidaterna; ser bara AMBIGUOUS-fall; utan "
    "transport svarar modulen ingenting. Nyckel läses ur OPENAI_API_KEY vid anrop (backend/app/jobs.py:110).",
    "Modellnamnet 'gpt-6-astra' är en miljödefault; aldrig i artefakter.")
# ------------------------------------------------------------------ motor: rör
add("motor/rör", "Representationsfamiljer, fragmentkedjor, dubbletter, sliver/parad vägg",
    ["engine/vvs_engine/pipes/representation.py"], "PARTIAL",
    "Familj = penna (lager, bredd, färg); dash/gap-mode rekonstrueras ur bladet; dubbletter tas bort på stämpel; "
    "figurer (radiatorer) läggs åt sidan (figure_pieces) och redovisas; sliver-par (två långsidor) degraderas "
    "(_demote_sliver_outlines, ownership.py). Bläck = struken penna med bredd (ink.py).",
    "split_t_junctions gör varje råkontakt ändpunkt-på-inre (<=0,15 pt) till en nod (en gren tar dock namnet bara "
    "med bevis vid sin ände, se ägande); figurer läggs åt sidan i stället för att bli FIGURE_CANDIDATE; "
    "graph_tolerances() returnerar en global konstant, inte bladets egen; ingen ritningslokal underfamilj på "
    "en penna; Bézier plattas med fast n=8 (geometry/core.py:120), inte adaptivt.")
add("motor/rör", "Ägande: identitet via leaders, korsningar, DN-gränser", ["engine/vvs_engine/pipes/ownership.py"], "PARTIAL",
    "Identitet bara från anknutna etiketter; korsning löses iterativt (kollineär genomgång, tick-gränser, "
    "DN-komplettering); konflikter => AMBIGUOUS med kandidater. Konservering: RAW = CONFIRMED+AMBIGUOUS+UNOWNED "
    "(reconcile.py VALID på alla 33 blad).",
    "Rättat 2026-09-11: en onämnd gren tar korsningens namn bara med bevis vid sin ände (komponent, bladkant, "
    "annan penna, annan pennas bläck, stråk med samma namn), annars AMBIGUOUS med kandidaten; flödesbudgeten "
    "vägs per sammanhängande stråk, inte per penna (gate53: falskt 27,3 -> 25,7 %, täckning 79,3 -> 77,9 %, "
    "89 m flyttade till tvetydigt). Kvar: 22,1 % missade och 25,7 % falska meter; 98 av 365 beteckningar läses "
    "inte alls; 384 brutna fortsättningar (gate53-rescore.json, frontier-census.json).")
add("motor/rör", "PipeExtentFrontier + pipe-extent-frontiers.json + overlay", ["engine/vvs_engine/pipes/frontier.py", "engine/vvs_engine/output/overlays.py", "frontend/src/frontier.ts"], "GOOD",
    "Byggt 2026-09-11: femton skäl i tre klasser, en post per kant på varje rör, silent_pipes tom på 33/33 blad "
    "(3 908 fronter), overlay-PDF och lager i granskningsvyn; nio prov.",
    "Skälen VERTICAL bygger på stigarsymboler som hittas efter ägandet; en gren som slutar i en stigare räknas "
    "ännu inte som bevis i ägandet (bara SYMBOL via symbolindexet).")
add("motor/rör", "T_CANDIDATE-verifiering: grenar med bevis, avvisad gren lämnar huvudstråket helt", ["engine/vvs_engine/pipes/ownership.py", "engine/vvs_engine/pipes/frontier.py"], "GOOD_BUT_FRAGILE",
    "Byggt 2026-09-11 (end_evidence + _branch_support): bevis vid grenens ände eller ett stråk med samma namn; "
    "utan bevis AMBIGUOUS med kandidaten; sex prov + omskrivna grenprov. Blind grind: −97 m falskt, −89 m ägt.",
    "Grafen har fortfarande inga typade kandidatkanter (TopologyCandidateEdge/PhysicalContinuityEdge); beviset "
    "ENDS_AT_OTHER_INK är brett (vilken annan penna som helst inom 3 pt) och kan ta en måttlinje som fixtur.")
# ------------------------------------------------------------------ motor: mått
add("motor/mått", "Skala per blad: text + skalstock, hela handlingen", ["engine/vvs_engine/measure/scale.py", "engine/vvs_engine/handling.py"], "GOOD_BUT_FRAGILE",
    "VERIFIED/TEXT_ONLY/BAR_ONLY/CONFLICT; enhetsmedveten skalstock (mm/cm/m); lånad skala från handlingen "
    "ger SCALE_FROM_THE_SET med källblad; en osäker skala blir aldrig CONFIRMED-meter (10 prov).",
    "Ingen skala per region (vyportar i olika skala på samma blad); D-bladet står i CONFLICT (text 1:S0 vs stock).")
add("motor/mått", "Mätning och mängdrader, vertikalt UNKNOWN", ["engine/vvs_engine/measure/measure.py"], "GOOD",
    "Meter bara med satt skala; vertikalt bara med nivåbevis, annars 'UNKNOWN' i raden; radstatus CONFIRMED/"
    "AMBIGUOUS/SCALE_UNSETTLED/SCALE_FROM_THE_SET/SCALE_GIVEN_BY_HAND/NO_SCALE.")
add("motor/mått", "Geometrikonservering och läsningens giltighet (två frågor)", ["engine/vvs_engine/reconcile.py", "engine/vvs_engine/coverage.py", "engine/vvs_engine/pipeline.py"], "GOOD",
    "reconcile: VALID/INVALID med residual och dubbelräkning; coverage-validity.json: åtta mått (lästa "
    "beteckningar, andel med DN, verifierade anknytningar, namn med meter, ägt/tvetydigt/oägt bläck, förlustfronter) "
    "och omdömet VALID/DEGRADED/INVALID med skäl - en läsning som konserverar ingenting är INVALID, inte perfekt; "
    "fem prov.",
    "Trösklarna för DEGRADED (50 % namn med meter, 30 % ägt bläck, 35 % förlustfronter) är satta, inte härledda.")
# ------------------------------------------------------------------ motor: kontroll
add("motor/kontroll", "Determinism: original / omvänd / slumpad ordning", ["engine/vvs_engine/determinism.py"], "GOOD_BUT_FRAGILE",
    "Semantisk signatur (beteckningar, leaders, ankare, rör, mängder, topologi, glyffamiljer) hashas för original, "
    "reversed, shuffled(11), shuffled(23); PASS krävs i freeze.",
    "Körs bara på sida 0 och bara när determinism=True (backend: settings.run_determinism).")
add("motor/kontroll", "Kontaminationsbrandvägg", ["engine/vvs_engine/contamination.py", ".github/workflows/checks.yml"], "GOOD_BUT_FRAGILE",
    "Regex över engine/vvs_engine: beteckningsliteraler, lagernamn, facit-vokabulär, DRAWING_[ABCD], objekt-id, "
    "kända koordinater; körs i CI och i varje analys. data/ är git-ignorerat; inga importer av valideringsdata.",
    "Mönsterlistan är smal (fångar inte hårdkodade totaler eller ritningsnummerfall); kompletteras av granskning.")
add("motor/kontroll", "Regelregister (per tråd, per konto)", ["engine/vvs_engine/rules.py"], "GOOD",
    "Varje gräns registrerad med skäl, default, intervall; using() binder ändringar till läsande tråd; prov håller "
    "register och kod lika.")
add("motor/kontroll", "Flervägsläsning och korskontroll", ["engine/vvs_engine/routes.py"], "GOOD_BUT_FRAGILE",
    "Samma blad läses på fler vägar; oenighet redovisas i route-crosscheck.json som fall, aldrig som meter.",
    "Rapporterande; vägarna delar underliggande geometri och kan vara eniga om samma fel.")
add("motor/kontroll", "Granskningsagenter, domare, regionförklaring", ["engine/vvs_engine/review/agents.py", "engine/vvs_engine/review/judge.py", "engine/vvs_engine/review/region.py"], "GOOD",
    "Agenter (skala, täckning, rimlighet, topologi, beteckning) ger fynd; domaren genomför bara svar bladet självt "
    "föreslagit, bara i öppna fall, som rättelser; ingen modell.")
add("motor/kontroll", "Syn (vision) efter läsningen", ["engine/vvs_engine/review/vision.py"], "GOOD",
    "Returtyp är fynd i namngivna rutor; ingen apply(); varje ruta förklaras ur vektorerna (region.py). Kan inte "
    "flytta en meter.")
add("motor/kontroll", "Rättelser och vad de får lära", ["engine/vvs_engine/corrections.py", "engine/vvs_engine/learning.py"], "GOOD",
    "En lektion gäller bara exakt samma situation (sex nycklar) och bara AMBIGUOUS-fall; skapar aldrig geometri.")
add("motor/kontroll", "Agent (frågor, förslag, projektfrågor)", ["engine/vvs_engine/agent/"], "GOOD_BUT_FRAGILE",
    "Svar ur artefakter; redigeringar är förslag som en person måste acceptera; identiteter utanför läsningen avvisas.",
    "Svaren är bara så bra som artefakterna; ingen frontier att fråga om än.")
# ------------------------------------------------------------------ motor: utdata
add("motor/utdata", "Artefakter (37 filer), version, kompatibilitetsadapter, frysmanifest, bevisgraf", ["engine/vvs_engine/output/artifacts.py", "engine/vvs_engine/output/schema.py"], "GOOD_BUT_FRAGILE",
    "Alla artefakter skrivs ur samma PageAnalysis och bär artifact_schema (3); backend läser genom upgrade() så "
    "att ett äldre resultat öppnas med tomma, inte felaktiga, fält (upgraded_from); freeze-manifest med hash, "
    "version, konfiguration; evidence-graph svarar 'varför' per rör; fyra prov.",
    "Adaptern täcker de fyra artefakter vars form bytts; nya formbyten måste läggas till för hand.")
add("motor/utdata", "Överlägg-PDF:er", ["engine/vvs_engine/output/overlays.py"], "GOOD",
    "Ritas ur pa.measures (samma PhysicalPipe-polylinjer som physical-pipes.json och mängdraderna); inga "
    "syntetiska strålar.")
add("motor/utdata", "Kanonisk geometri i viewer / PDF / tabell / export", ["backend/app/main.py", "frontend/src/components/PdfViewer.tsx", "frontend/src/three/model.ts", "backend/app/exports.py"], "GOOD",
    "Viewer ritar props.pipes = physical-pipes.json; 3D-vyn läser result.pipes (samma); exporter läser "
    "quantities.json-raderna som räknas ur samma measures; PDF-överlägg ur pa.measures. En källa.",
    "Ingen typad CanonicalMeasurementGeometry; likheten är en konsekvens av arkitekturen, inte ett kontrakt med prov.")
add("motor/utdata", "Filmen (stegvis redovisning)", ["engine/vvs_engine/film.py"], "GOOD", "Varje steg skickas medan det pågår; backend /film.")
add("motor/utdata", "CLI", ["engine/vvs_engine/cli.py"], "GOOD", "analyze_pdf: hela kedjan, handlingens skala, frys, determinism, kontamination.")
# ------------------------------------------------------------------ mängdning/CAD-motor
add("mängdning", "Mätmotorn för CAD och Mängda", ["engine/vvs_engine/takeoff/"], "GOOD",
    "En form, en skala, ett mått; formler utan användarkod; servern mäter (test_api: 'never by the browser').")
# ------------------------------------------------------------------ backend
add("backend", "Jobb: kö, körning, fel", ["backend/app/jobs.py"], "GOOD_BUT_FRAGILE",
    "ThreadPoolExecutor i processen; regler bundna per tråd; deadline; UnsupportedInputError => begripligt fel; "
    "andra fel loggas med spårning, användaren får en rad utan filvägar.",
    "Ett RUNNING-jobb överlever inte en omstart (ingen återupptagning/kö utanför processen).")
add("backend", "Exporter (xlsx/csv/json/PDF/rapport)", ["backend/app/exports.py"], "GOOD",
    "Vertikalt UNKNOWN skrivs 'OKÄNT' med vertical_source; antagen våningshöjd märks ANTAGET.")
add("backend", "Kalkyl och anbud, regelverk", ["backend/app/calc.py", "engine/vvs_engine/normtid.py"], "GOOD_BUT_FRAGILE",
    "REGELVERK (ABT 06, AB 04, ABS 18, Hantverkarformuläret 17, inget) påverkar bara anbudets klausuler; mängderna "
    "räknas oberoende av regelverk.",
    "Ingen typad ContractContext med prov som visar att mängderna är regelverksneutrala; normtidstabellerna är "
    "inte granskade mot källa här.")
add("backend", "Markeringar (Mängda) och CAD-blad", ["backend/app/markups.py", "backend/app/cad.py"], "GOOD",
    "Servern mäter varje markering; CAD-blad renderas till PDF med OCG-lager, stämpel, skalstock; DXF R12; "
    "motorn läser det utskrivna bladet som VERIFIED (7 + prov).")
add("backend", "Konto, projekt, lagring, admin, akademi, publik", ["backend/app/auth.py", "backend/app/projects_api.py", "backend/app/db.py", "backend/app/storage.py", "backend/app/admin.py", "backend/app/academy.py", "backend/app/public.py"], "GOOD_BUT_FRAGILE",
    "JWT, ägarskap per användare (404 för andras), SQLite/Postgres via SQLAlchemy, lokal lagring.",
    "main.py är 1 113 rader monolit; admin/affiliate/CRM är inte mängdningskritiska och inte granskade i djup.")
# ------------------------------------------------------------------ frontend
add("frontend", "Analysvy, PDF-viewer, rättelser, agent, 3D", ["frontend/src/pages/Analysis.tsx", "frontend/src/components/PdfViewer.tsx", "frontend/src/components/Drawing3DView.tsx"], "GOOD_BUT_FRAGILE",
    "Ritar samma physical pipes; klick -> varför; rättelser via API; typkontroll + eslint 0 varningar i CI.",
    "Ingen frontier att visa; smoke-testerna (frontend/smoke) körs manuellt, inte i CI.")
add("frontend", "CAD-rummet och Mängda", ["frontend/src/pages/CadSheet.tsx", "frontend/src/cad/", "frontend/src/pages/Takeoff.tsx"], "GOOD",
    "Verifierat i webbläsare (Playwright): fångst mot bläck, ortho, avdrag, lista, utskrift till PDF som motorn läser.")
add("frontend", "Landning, dokumentation, akademi, admin", ["frontend/src/pages/Landing.tsx", "frontend/src/pages/Docs.tsx", "frontend/src/components/Learn*.tsx", "frontend/src/pages/Admin.tsx"], "GOOD_BUT_FRAGILE",
    "Byggs och typkontrolleras; innehåll ej granskat mot motorn i denna revision.")
# ------------------------------------------------------------------ prov, verktyg, data
add("prov", "Enhets- och integrationsprov, e2e, CI", ["engine/tests/ (58 filer, 427 prov)", "engine/tools/e2e.py", ".github/workflows/checks.yml", "docs/REGRESSIONER.md"], "GOOD_BUT_FRAGILE",
    "Motor + API (TestClient) + kontamination + hela produkten end-to-end på det syntetiska bladet i CI; "
    "frontend-bygge (eslint 0 varningar, typkontroll) i CI; regressionsregistret pekar från varje namngivet "
    "ämne till sitt prov; webbläsarklickning (frontend/smoke/ui_smoke.py) körd för hand utan konsolfel.",
    "Webbläsarklickningen är inte i CI (kräver Playwright-chromium i bilden).")
add("prov", "Facitmått, felkatalog och grindkörning", ["engine/tools/gate_run.py", "engine/tools/facit_metrics.py", "engine/tools/freeze.py"], "GOOD_BUT_FRAGILE",
    "Blind körning (lästa namn, namn med meter, ankartillstånd, fronter, indatahash), frysmanifest, och "
    "poängsättning efteråt: COVERAGE, FALSE_OWNERSHIP, DESIGNATION_RECALL/PRECISION, LEADER_ATTACHMENT, "
    "FULL/PARTIAL/OVER/MISSED/WRONG per beteckning, felkatalog per stil (gate52/gate53 i results/).",
    "37 W-blad har aldrig poängsatts (facit bara på Drive); felkatalogen skiljer 'inte läst' från 'läst utan "
    "meter' men inte varför anknytningen brast.")
add("data", "Korpus: manifest, parning, innehållskontroll, exponering", ["engine/tools/corpus_manifest.py", "engine/tools/corpus_verify.py", "engine/tools/corpus_inventory.py", "results/2026-09-11-topologi/"], "GOOD",
    "1 520 filer, 500 blad, 71 par; parning bekräftad ur innehåll där lokal kopia finns; exponering per blad.",
    "Drive-API:et ger ingen kontrollsumma: 823 filer utan lokal kopia är matchade på namn+storlek.")
add("data", "TRUE HOLDOUT", [], "MISSING",
    "Alla 71 facitparade blad är DEVELOPMENT; 287 oexponerade blad saknar facit.",
    "Blockerat tills facit produceras för oexponerat material; kandidater namngivna i corpus_inventory.md §6.")
add("verktyg", "Systemvandring, andra åsikt, e2e, Astra-transport", ["engine/tools/syscheck.py", "engine/tools/second_opinion.py", "engine/tools/e2e.py", "engine/tools/astra_transport.py"], "GOOD_BUT_FRAGILE",
    "Fristående skript; astra_transport importeras av backend. Inga döda moduler: varje modul i vvs_engine "
    "importeras av någon annan eller av backend.", "syscheck/e2e/second_opinion körs för hand.")
add("säkerhet", "Nycklar och hemligheter", ["backend/app/config.py", "backend/app/jobs.py"], "GOOD",
    "OPENAI_API_KEY läses ur miljön vid anrop; tjänsten vägrar köra på hemligheten i källkoden (test_api); "
    "inga nycklar i repot.")


def render_md() -> str:
    L = []
    w = L.append
    c = Counter(e["verdict"] for e in E)
    w("# SYSTEM_AUDIT - vad varje delsystem gör, klassat efter läst kod\n")
    w(f"Datum {AUDIT_DATE}. Utgångsläge: commit {BASELINE['commit_before']}; {BASELINE['tests']}; {BASELINE['gate']}.\n")
    w("Domarna är satta efter implementationen (filerna i varje rad), efter körda prov och efter mätningar på "
      "referenskorpusen - inte efter dokumentationen. Där en dom vilar på ett tal står talet.\n")
    w("| Dom | Antal |\n|---|---:|")
    for k in ("GOOD", "GOOD_BUT_FRAGILE", "PARTIAL", "BROKEN", "UNSAFE", "MISSING", "MOCK", "DEAD_CODE"):
        w(f"| {k} | {c.get(k, 0)} |")
    w("")
    w("**Inga MOCK, inga BROKEN, inga UNSAFE, ingen DEAD_CODE hittade.** Svepet efter attrapper (mock/stub/placeholder/"
      "TODO/NotImplemented) träffar bara ordet 'placeholder' i legendkodernas Bxxx-hantering och i inmatningsfält. "
      "Importgrafen visar att varje modul i vvs_engine nås. Det som var UNSAFE i morse - ett skannat blad med "
      "påskrift lästes som vektor - är rättat och provat (test_marks_are_inventoried_before_the_page_is_classified.py).\n")
    w("Det som är MISSING är uppdragets kärna, och det står överst i arbetsordningen: PipeExtentFrontier med "
      "skälkoder, kandidatkanter med T-verifiering och lokal traversering i stället för en global flödesbudget, "
      "och en holdout som inte finns förrän någon producerar facit för oexponerat material.\n")
    cur = None
    for e in E:
        if e["area"] != cur:
            cur = e["area"]
            w(f"\n## {cur}\n")
            w("| Delsystem | Dom | Bevis | Vad som saknas |\n|---|---|---|---|")
        files = ", ".join(f"`{f}`" for f in e["files"]) if e["files"] else "-"
        w(f"| **{e['subsystem']}**<br>{files} | {e['verdict']} | {e['evidence']} | {e['gap'] or '-'} |")
    w("\n## Arbetsordning som följer av revisionen\n")
    w("1. `PipeExtentFrontier` + `pipe-extent-frontiers.json` + overlay: inget rör slutar tyst (MISSING, högsta prioritet).")
    w("2. Kandidatkanter med bevis: T_CANDIDATE kräver positivt bevis, inre-inre förblir frånkopplat, avvisad gren "
      "lämnar huvudstråket helt; FIGURE_CANDIDATE i stället för tidig radering; lokal traversering ersätter FLOW_LIMIT.")
    w("3. Facitmått som repo-verktyg (DESIGNATION_RECALL … MISSED_PIPE), felkatalog, de namngivna regressionerna som svit; "
      "W-bladens facit hämtas från Drive så att 71, inte 33, blad poängsätts.")
    w("4. Artefaktversion + kompatibilitetsadapter; CoverageValidity med åtta mått skild från konserveringen; adaptiv "
      "Bézier; toleranser härledda ur bladets penna.")
    w("5. Fullstack-e2e i CI; jobb som överlever omstart.")
    w("6. Holdout: frys/hash, sedan första körning på oexponerat blad med nyproducerat facit.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "/home/user/vvs5"
    open(os.path.join(root, "SYSTEM_AUDIT.md"), "w", encoding="utf-8").write(render_md())
    json.dump({"date": AUDIT_DATE, "baseline": BASELINE, "verdict_counts": dict(Counter(e["verdict"] for e in E)),
               "subsystems": E}, open(os.path.join(root, "SYSTEM_AUDIT.json"), "w"), indent=1, ensure_ascii=False)
    print("skrev SYSTEM_AUDIT.md/json:", dict(Counter(e["verdict"] for e in E)))
