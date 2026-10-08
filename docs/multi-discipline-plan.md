# Flera discipliner: Sprinkler, Kyla, Ventilation – och senare El och Bygg

Steg 0 enligt uppdraget: nuläge, föreslagen arkitektur, migreringar, risker och fasplan. Ingen produktionskod är
skriven för det här än. Planen är godkänd i sin helhet; varje fas avslutas ändå med en sammanfattning och väntar
på underlag där det saknas.

**Det som gäller genom alla faser:** väljer man VVS fungerar allt exakt som idag. VVS-läsningen, VVS-mängden och
VVS-exporterna ändras inte, och golden-tester och korpusspärren visar det efter varje steg. Ventiler (`AVxxx`,
`SVxx` …) i en VVS-mängd lämnas som idag; räkning av komponenter (st) finns bara i de nya, separata disciplinerna.

## 1. Nuläge – var det ligger

| Del | Var |
|---|---|
| Läsningens kedja | `backend/app/jobs.py` → `analysis_worker.analyze_isolated` (egen process) → `engine/vvs_engine/pipeline.py` (`prepare_page`, `analyze_page`). Namnet "Meridian" finns inte i koden. |
| Inmatning | `pdf/classify.py` klassar sidan (vector/raster/mixed); `pdf/extract.py:161` avvisar rastersidor med `UnsupportedInputError`. |
| Text | `text/` (vektorglyfer, SHX, OCR-stöd); etikettdetektorn `models/pipestudio-labels.onnx` körs på rasterrutor. |
| Förklaringslista | `semantics/legend.py` – hittas på formen; koder får rollen system, komponent eller material av hur bladet använder dem. |
| Beteckningsparser | `semantics/grammar.py` hittar bladets egna mönster (inga värden hårdkodade, men dimensionen antas vara ett heltal – DN). Vendorad parser i `source_rules/pipestudio/vvs.py` (ändras aldrig). |
| Systemkatalog | `source_rules/data/system_designations.json` (26 koder: KV, VV, VVC, S, D, VS, VP … samt KB, KM, FK, BRL). |
| Hänvisningslinjer, koppling | `semantics/leaders.py`, `semantics/attachment.py`, `source_rules/native_*`. |
| Skala | `measure/scale.py` (text, skalstock, mått, rörbredd, schema). |
| Mätning | `measure/measure.py` – mängdrader i meter (`confirmed_horizontal_m`, vertikalt, stigare, DN, skrafferat, dubbellinje). |
| Artefaktversioner | `output/schema.py` (`ARTIFACT_SCHEMA`, `upgrade`). |
| Inställningar per läsning | `vvs_engine/rules.py`: `using()` binder värden till läsningens tråd (ContextVar). |
| Datamodell | `backend/app/db.py`; schemaändringar via `create_all` plus `_ADDED_COLUMNS` (ingen Alembic). `Project` har namn, beskrivning och `analysis_mode`. |
| Exporter | `main.py` (`/api/jobs/{id}/export/{fmt}`) och `exports.py`: xlsx, csv, json, rapport, markerad pdf, kontroll-pdf. |
| Kalkyl/anbud | `calc.py` och `vvs_engine/normtid.py` (Normtid VVS: timmar per meter efter dimension och material). |
| Materialbok | `backend/app/data/material.json.gz` – 55 161 artiklar, global; artikelval sparas per kalkyl. |
| Credits | `credits.py` – pris per blad efter format och bläck; återbetalning när läsningen inte gav en enda meter. |
| UI | `pages/Projects.tsx` (skapa projekt: namn, beskrivning), `Project.tsx`, `Analysis.tsx`, `components/QuantityTable.tsx`, `three/model.ts`, `pages/Takeoff.tsx` (manuell mängdning: m, m², m³, st). |

**Avvikelser mot hur produkten beskrivs:** Wikells-export finns inte i koden. "Bluebeam" förekommer bara som
ord i texter – det finns ingen markeringsexport med PDF-annoteringar. Materialboken är inte redigerbar per
företag; det som finns är artikelval per kalkyl.

## 2. Där VVS är hårdkodat

**Motorn**
- `source_rules/data/system_designations.json` – systemkoder med `line_count` (enkel/dubbel ledning).
- `source_rules/systems.py:29` och `source_rules/swedish.py:65` – självfall: system som börjar på S eller D (utom SL).
- `pipes/direction.py:36-43` – `GRAVITY_SYSTEMS`, `CIRCULATING_SYSTEMS`, `OWN_LABEL_SYSTEMS`.
- `semantics/attachment.py:118` – BSAB-lagren 52BB/52BC/52BD → KV/VV/VVC.
- `measure/measure.py:425-427` – stigare genom bjälklag gäller VS med S-material.
- `pipeline.py:2233` (`APPARATUS_HEADS`: AV, SV, RV …) och `pipeline.py:2274` (rörnamn ur standardsystem).
- `semantics/legend.py:507` – `COMPONENT_HEADS` (svenska ord för komponenter).
- Stigare och våningshöjden 2,8 m; DN som heltal i grammatik, mätning och 3D.
- Agentens och granskningens prompter ("Swedish HVAC/plumbing (VVS) drawing", `backend/app/solver.py:33`).
- Etikettmodellen är tränad på VVS-etiketter.

**Backend**
- `main.py` – skapa projekt utan disciplin; uppladdning tar bara `.pdf`.
- `exports.py:14` – kolumnerna (DN, Horisontellt m, Vertikalt m, Stigare …).
- `credits.py` – återbetalningen räknar meter.
- `calc.py`, `normtid.py` – timmar per meter efter DN.
- `cad_export.py:80` – färger efter KV/VV/S; akademin och `data/swedish-vvs-knowledge.json`.

**Frontend**
- `QuantityTable.tsx` (kolumner), `Analysis.tsx` (stigare, våningshöjd, DN), `three/model.ts:50` (rörradie ur DN),
  navigeringen "Lär dig VVS".

**Redan generiskt och återanvändbart:** skalverifieringen, förklaringslistan, grammatiken som hittar bladets egna
mönster, hänvisningslinjer och koppling, den manuella mängdningen (m, m², m³, st), disciplinbokstaven i
ritningsnumret (`vvs_engine/handling.py:41`: A, V/W, L = luftbehandling, E, B …), `rules.using()`,
artefaktversioneringen samt etikettdetektor och OCR på rasterrutor.

**Referensdata som redan finns** (svensk praxis, `reference_sources/swedish-vvs-drawings-main/data`):
`system_designations`, `sanitary_fixtures`, `valves`, `discipline_codes`.

## 3. Föreslagen arkitektur

1. **Disciplinregister** – nytt paket `engine/disciplines/` med en JSON-fil per disciplin: id, namn, status
   (aktiv/beta/planerad), slag (rör/kanal/symbol/yta), systemkoder, grammatik och dimensionsformat (DN, Ø, b×h),
   rubriker i förklaringslistan, komponenter, mättyper, katalogfilter, exportmappning och credit-faktor.
   Konfigurationen binds per läsning på samma sätt som `rules.using()`. **VVS-konfigurationen är exakt dagens
   konstanter:** de hårdkodade mängderna ovan läses via `value(...)` med identiska standardvärden, så en
   VVS-läsning ser samma tal som idag. Avvikelser per företag och projekt (`discipline_overrides`) gäller bara
   andra discipliner än VVS.
2. **Mättyper** – `LENGTH` (m), `AREA` (m²), `COUNT` (st) och förberedd `VOLUME` (m³). En rad i de nya
   disciplinerna:
   `{discipline, source_type, system, designation, dimension{format, value}, measures[{type, unit, value,
   derivation, state, confidence}], evidence{label, leader, geometry, scale}, state, reasons}`.
   En kanal bär till exempel meter, m² plåt (omkrets × längd) och m² isolering. VVS-artefakterna lämnas som de
   är; en vy-adapter ger dem `measures` där en gemensam lista behöver det.
3. **Kedjan** – `discipline in ('', 'vvs')` går dagens anropskedja oförändrad. Sprinkler och kyla återanvänder
   rörläsaren med sin konfiguration; ventilation får en kanalläsare som bygger vidare på dubbellinje- och
   rörbreddslogiken.
4. **UI** – disciplinval när projektet skapas (VVS förvalt; El och Bygg visas som "kommer senare"), åsidosättning
   per ritning vid uppladdning, filter per disciplin i mängdlistan och korrekta enheter överallt (m, m², st). Nya
   discipliner får en generisk mängdtabell; VVS-tabellen är orörd.
5. **Exporter** – VVS-filerna är byte-identiska med idag. Nya discipliner får ett generiskt blad: disciplin,
   källtyp, system, beteckning, dimension, mått, enhet, värde, härledning, status. Wikells och Bluebeam byggs när
   formaten är bestämda.
6. **Katalog** – materialboken filtreras per disciplin (artikelgrupp); redigering per företag kräver en egen
   tabell och föreslås separat.
7. **Credits (förslag, beslutas före implementation)** – samma pris per blad som idag (format och bläck) med en
   faktor per disciplin som administratören kan ändra (startvärde 1,0). Återbetalningen generaliseras till
   "läsningen gav ingen mängd av något slag" (m, m² eller st). Rastersidor kostar +1 credit.

### Skannade underlag och bilder (inmatning, oberoende av disciplin)

Idag avvisas rastersidor med flit. Förslaget är en inmatningsadapter som bara körs där dagens kod avvisar:

1. Bilder (PNG, JPG, TIFF) tas emot och läggs som en PDF-sida; sidstorleken tas ur DPI. Saknas DPI kan skalan
   bara komma ur skalstock, mått eller handinmatning.
2. Förbehandling: räta upp, avbrusa, binarisera.
3. Vektorisering: linjesegment med uppskattad linjebredd och streckmönster.
4. Text: etikettdetektorn på rasterrutor och OCR.
5. Primitiverna och textraderna matas in i samma läsning – grammatik, hänvisningslinjer, mätning och skala
   återanvänds.

**Förtroende:** allt som läses ur en bild markeras "granskas" med skäl och konfidens, och skalan måste vara
verifierad. Vektor-PDF:er påverkas inte. **Utvärdering:** de 15 facitbladen rastreras (150–300 dpi, med lutning,
brus och oskärpa) och mäts mot samma facit; riktiga skanningar behövs för slutlig validering.

## 4. Migreringar

- `projects.discipline`, `drawings.discipline`, `analysis_jobs.discipline` som `VARCHAR(24) DEFAULT ''` via
  `_ADDED_COLUMNS`. `''` betyder VVS, så varje befintligt projekt är oförändrat VVS.
- Ny tabell `discipline_overrides` via `create_all`.
- Inga dataomskrivningar; gamla artefakter läses som idag (`output/schema.py`).

## 5. Risker

- **Determinism:** detektorn går på två trådar; resultatet bekräftas lika vid två körningar innan golden-testerna
  låses.
- **Dold påverkan på VVS:** spärras av golden-tester (syntetiska, incheckade) och korpusspärren (verkliga blad,
  utanför repot).
- **Klientritningar i ett publikt repo:** bara syntetiska fixtures checkas in.
- **Kanaler:** kräver en ny detektor; precisionen är okänd tills det finns facit.
- **Exportförväntningar:** Wikells- och Bluebeam-export finns inte idag.
- **Koder:** beteckningar skiljer sig mellan beställare och konsulter; därför är de data per disciplin, företag
  och projekt – aldrig hårdkodade antaganden.

## 6. Fasplan

**Fas 1 – refaktorering utan beteendeändring** (gemensam med ABT 06, se `docs/abt06-plan.md`)
1. Golden-tester först: syntetiska fixtures med fullständiga `quantities.json`, `physical-pipes.json`,
   `reading-coverage.json`, xlsx-celler och csv-bytes i `engine/tests/golden/`; lokalt dessutom korpusens
   facitblad med artefakthashar.
2. Disciplinregistret med VVS; de hårdkodade konstanterna flyttas till VVS-konfigurationen med noll diff.
3. DB-kolumner och API (disciplin in och ut).
4. Disciplinval i UI; bara VVS kan väljas tills fas 2 och 3 är byggda.

Godkänt när golden-testerna och korpusspärren är identiska, hela sviten är grön och befintliga projekt öppnas
oförändrade.

**Skannat (C1–C3)** – C1: mottagning, förbehandling, vektorisering, OCR. C2: precision med egen gräns i
korpusspärren. C3: de andra disciplinerna.

**Fas 2 – Sprinkler och Kyla.** Systemkoder och katalog per disciplin, verifierade mot riktiga ritningar innan
något byggs. Rör mäts som i VVS. COUNT för sprinklerhuvuden, ventilstationer och kylaggregat där de kan
identifieras säkert – annars flaggas de. *Behöver:* sprinkler- och kylritningar, gärna med handmängd.

**Fas 3 – Ventilation.** Kanalbeteckningar med Ø och b×h, luftsystemen (tilluft, frånluft, uteluft, avluft) som
konfigurerbara koder, meter per system och dimension, m² plåt och m² isolering där isoleringsklass anges. COUNT
för don, spjäll, ljuddämpare och aggregat; böjar, T-stycken och reduktioner räknas om det går säkert ur
geometrin, annars flaggas de. 3D-tvärsnitt sist. *Behöver:* ventilationsritningar, gärna med handmängd.

**Senare – El och Bygg/A-K.** Symbolräkning och kabelstegar respektive areor och volymer behöver bara egna
läsare; registret och mättyperna är förberedda för dem.

Varje fas: små commits med tester, hela sviten, och en sammanfattning med vad som ändrats, testresultat, kända
begränsningar och vad nästa fas behöver.

## 7. Referenser (webbsökning – koderna verifieras ändå mot riktiga ritningar)

- Kyla – KP, KB och KM som systemkategorier: [Armatec, kunskapsguide vätskeburen kyla](https://armatec.com/sv/koncept/industriella-system/kunskap/kunskapsguide-vatskeburen-kyla/DownloadPdf); KBxxx i [Region Västerbottens beteckningssystem](https://regionvasterbotten.se/VLL\Filer\Beteckningssystem%20(bilaga).pdf); systembeteckningar i [Danderyds kommuns projekteringsanvisning](https://www.danderyd.se/contentassets/d4cf4c4f61dc47e4838d1202e3d916ad/styr-och-regler/danderyds-kommun-projekteringsanvisning--styr-och-overvakning_bilaga-2-beteckningssystem_v3.0.pdf).
- Sprinkler – [SBF 120](https://www.brandskyddsforeningen.se/webbshop/normer-och-regelverk/sbf-1208-rules-for-automatic-sprinkler-systems/) (gäller tillsammans med SS-EN 12845). Ingen svensk sprinklerritning hittades som exempel.
- Ventilation – T/F för tilluft/frånluft, TD/FD för don, TA/FA för aggregat, TF/FF för fläktar enligt ett svenskt [symbolblad](https://www.yumpu.com/sv/document/view/63511785/flik-26-ritningssymboler); märkbeteckningar i [Jönköpings kommuns anvisning](https://www.jonkoping.se/download/18.18363ea31862b16dbb8212f8/1676357560481/Bilaga%201.2%20M%C3%A4rkbeteckningar.pdf); termer i [EN 12792](https://genorma.com/en/standards/en-12792-2003/amp).
- Allmänt – [AMA VVS & Kyla 25](https://byggtjanstcms.byggtjanst.se/globalassets/bokhandeln/provlas/ama-vvs-kyla-25_6361461.pdf).
