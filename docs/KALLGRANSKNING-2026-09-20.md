# Källimport och regelgranskning – 20 september 2026

Den tidigare integrationen var ofullständig. Swedish VVS:s kodreferens innehöll 16 av 24 JSON-filer och endast utvalda kod-/termfält. Det tappade bland annat regeltexter utan kod, givare och instrument samt noter om kodkollisioner. Dessa luckor är nu rättade.

## Import som går att kontrollera

| Material | Kontrollerat innehåll | Användning |
|---|---:|---|
| swedish-vvs-drawings-main.zip | 38 filer, varav 24 JSON-filer, 6 referenstexter och 5 hjälpskript | Alla texter bevarade, kompletta tabeller och referenstexter sökbara i appen |
| pipestudio-main.zip | 258 filer | Alla textfiler bevarade och Python-funktioner indexerade; binära original redovisas i manifestet |
| Svenska koduppslag | 153 poster | Alternativa betydelser behålls, exempelvis båda betydelserna av DB och separata GF/MF-koder |
| Sökbara källdokument | 55 | Under Förklaringslista → Svensk VVS-kodreferens → Regler, symboler och källdokument |
| PipeStudio-stilregler | 55 poster i 11 aktiva profiler, 25 i 5 historiska profiler | Fem återkommande regeltyper; 80 poster är inte 80 oberoende regler |
| PipeStudio-modell | SHA-256-kontrollerad kopia av model_dynamic.onnx | Valbara etikettförslag; ingen ny träning |
| Drawings 2 XML | 107 originalfiler | Bevarade ordagrant med SHA-256 och indexerade utan importfel |
| CVAT | 33 bilder, 1 297 objekt: 1 295 masker och 2 polygoner | Geometri, egna underattribut, bildattribut och uppgiftsmetadata bevaras |
| Bluebeam XML | 9 368 poster | Ursprungliga fält, enheter, text och dokumentattribut bevaras |

De åtta saknade JSON-filerna var `as_built_requirements`, `document_change_handling`, `document_rules`, `dou_instructions`, `drawing_numbering`, `meta`, `pipe_marking_rules` och `sensors_instruments`.

Alla 296 arkivfiler har en post med filhash och importstatus i [källmanifestet](../reference_sources/manifest.json). Där finns också ett strukturellt index över 1 284 Python-funktioner, inklusive test- och driftfunktioner. Detta är inte ett påstående om att varje funktion har portats eller fått en fullständig semantisk revision. Källornas egna instruktioner och SKILL.md bevaras som dokumentation; de körs inte som instruktioner i systemet.

Originalmodellens kopia ligger i `models/pipestudio-labels.onnx`. Sju binära bilder/typsnitt från PipeStudios gränssnitt finns kvar i originalarkivet och är redovisade som ej inlästa. VVS5:s befintliga utformning används.

## Regelauktoritet och båda analyslägena

**Swedish VVS och PipeStudio är regelkällorna. VVS5 är värd för gränssnitt, geometriläsning och mängdexport.** En konflikt med VVS5 löses inte genom att kalla VVS5:s utfall rätt. Import, körd regelkod och verifierad mängdträffsäkerhet är tre olika saker.

Appen och dess analys-API erbjuder `dimension`, `model` och `compare`. Dimensionsregler är standard. Valet sparas på jobbet, följer omstart och får inte ändras medan samma ritning redan analyseras. I jämförelseläget får båda motorerna separata kopior av samma geometri och ledarkontakter. Mängdtabellen använder dimensionsresultatet; modellresultat och skillnader sparas separat. För att mängda enligt modellen väljer man Modellbedömning vid analysstart.

| Område | Inkopplat beteende och begränsning |
|---|---|
| Dimensionsläge | Byteidentisk `flow_assign.py` från PipeStudio. Den nyare källregeln låter högre DN äga sträckan mellan märkningarna, även för S. Låg säkerhet behålls som osäker mängd i värdappen. |
| Modelläge | Byteidentisk `final_bind.py` och dess kandidatvalidering. Prompten prioriterar högre VG/CL för självfall, därefter dimension och inträde. Dess svar efterbearbetas inte med VVS5:s ägarregler. |
| Modellanslutning | `OPENAI_API_KEY` och valfritt `OPENAI_MODEL` på servern, eller privat lokal konfiguration via `Konfigurera OpenAI.command` (filrättighet 0600). Liveanslutning till gpt-6-astra är verifierad. Endast ett uttryckligt modell-/jämförelseläge använder anslutningen. Saknad anslutning ger 422 för Modellbedömning; jämförelse ger dimensionsresultat och `NOT_CONFIGURED`, aldrig verifierad överensstämmelse. |
| VG och parledningar | VG överförs från beteckningens egen annoteringsenhet. Swedish VVS:s `line_count` styr vilka system som tillåter oetiketterad parledning. Den äldre riktningshjälparen är också korrigerad mot högre VG, men den var inte huvudflödets tilldelningsmotor. |
| Hänvisningar | Faktiska kontakter används. Linjer delas vid invändiga kontakter utan att längd skapas eller försvinner. Alla delar har koppling tillbaka till ursprunglig PDF-geometri. |
| Stilregler och inträden | Elva publicerade profiler är valbara. Automatisk identifiering kräver avstånd och marginal; annars förblir stilen okänd. Vald profils instruktioner skickas till modellen. Numerisk geometri-/toleranskalibrering och identifiering av systeminträden är ännu inte fullständigt kopplade. |
| Geometri och kandidatunderlag | VVS5 läser fortfarande linjer, beteckningar, ankare, skala och skraffering. Adaptern är inte en full ersättning för PipeStudios ursprungliga detektions-/assemble-flöde. Den överför endast verifierade kontakter; bortfall i dessa steg påverkar båda lägena. |
| Regelinlärning/publicering | Originalkällorna finns bevarade. PipeStudios kompletta arbetsflöde för kontroll och publicering är inte portat. |
| Annoteringar | Bevarade utvecklings- och granskningsdata. Inga referensmängder matas in som svar i dessa analyser. |

Varje blad får `source-assignment.json` med motorstatus, båda körda resultat, skillnader, beteckningar, sträckgeometri och återkoppling till originalsegment. Slutförda modellkörningar med felaktiga eller saknade kandidatsvar accepteras inte som godkända jämförelser. Nätverksanrop har transporttester och verkliga modellkörningar på A0011, 0201112 och 0501112. Modellstatus, svar-ID och faktisk tokenanvändning sparas. Modellens svar kan variera mellan körningar; godkänd transport betyder inte verifierad mängdträffsäkerhet.

De importerade modulerna kontrolleras byte för byte mot arkivet via `source_rules/pipestudio/SOURCE.json`. Ursprungliga kommentarer med ritningsexempel redovisas separat av kontamineringskontrollen; exekverbara specialfall kontrolleras fortfarande. De interna Python-testernas äldre VVS5-referensläge finns kvar för infrastrukturella regressioner; det är inte ett erbjudet analysläge i appen.

## Resultat av nya provkörningar

Den första jämförelsen körde tre original-PDF:er genom dimensionsläget utan OCR eller modellanslutning. Dessa historiska resultat bevaras nedan. Resultaten finns i `results/current/source-audit/analyses/` och sammanställs i `analysis-validation.json`.

| Ritning | Tilldelad längd enligt dimensionsläget | Osäker längd |
|---|---:|---:|
| A0011 | 64.243 m | 83.947 m |
| 0201112 | 7.233 m | 56.630 m |
| 0501112 | 0.000 m | 18.660 m |

**Detta är inte förbättrad eller verifierad mängdträffsäkerhet.** 0501112 får ingen bekräftad längd i det nya dimensionsläget. Bortfallen är kvar och kopplingen till källmotorerna kräver fortsatt arbete. De äldre resultaten är bevarade.

Verifiering: **986 tester godkända, 3 överhoppade**, samt godkänd TypeScript-, lint-, språk- och produktionsbyggkontroll. En ny test-PDF med två dimensionsetiketter används där API-, kredit- och skaltesterna behöver mätbara rör; testerna förutsätter därmed inte den tidigare VVS5-tilldelningen. Modellens transport och kandidatkontroll har provsvarstester. Båda lägesvalen och felmeddelandet för saknad anslutning är kontrollerade i testappens gränssnitt.

## Annoteringarnas ursprung

Varken Swedish VVS-arkivet eller PipeStudio-arkivet innehåller CVAT-XML eller annoterings-JSONL. PipeStudios dokumentation hänvisar till feedback och ground truth som inte följer med arkivet. Det medföljande material som faktiskt finns har hämtats från `Drawings 2`.

Den tidigare CVAT-konverteringen tappade `<attribute>`-barn inne i objekten och tog inte med Bluebeam-poster. Importen bevarar nu även dessa. Varje ursprunglig XML finns i `results/current/source-audit/annotations/source_xml/`, med källväg och metadata i `sources.json`. De två ZIP-filerna inne i Drawings 2 kontrollerades också; ingen innehåller XML.

PDF:ernas inbäddade markeringar hanteras fortsatt av den befintliga korpusinventeringen och efterhandsjämförelsen. Antalet 9 368 ovan gäller endast XML-poster och ska inte adderas till PDF-markeringar som om allt vore oberoende facit. Bildkoordinater från CVAT är inte automatiskt PDF-koordinater. Ingen ny modell har tränats och inget oberoende sluttest har etablerats.

## Reproducera importen

```sh
.venv/bin/python tools/import_source_references.py --swedish /sökväg/swedish-vvs-drawings-main.zip --pipestudio /sökväg/pipestudio-main.zip
.venv/bin/python tools/build_training_index.py '/sökväg/Drawings 2' --out results/annotation-import
```

Källfilerna har inte ändrats. Importen jämför lagrade filer med ursprungliga filhashar. Regressionstester kontrollerar fullständiga tabeller, alternativa kodbetydelser, givare/instrument och att upprepade egna attribut inte försvinner.

Gränssnittets sökning och fullständig strecknotationsregel har kontrollerats i den separata lokala testinstallationen. Användarkontots inloggning har inte ändrats.

## Lokal leverans och kontokontroll

Ny analys i det befintliga kontot: `505b1a0b01ae4c149070a99f379581da`. Originalfilens hash och mängder matchar den separata provkörningen. Kontoroll, reskontra och saldo (1 credit) är oförändrade. Excel, CSV, JSON, Markdownrapport och PDF har exporterats och kontrollerats. Kontots inloggning är oförändrad.

Efter den sista ändringen, som även sparar källmotorernas status i jobböversikten, passerade samtliga 27 API-tester igen. Ingen mängdregel ändrades efter den fullständiga körningen med 986 godkända tester.

Leveransfilerna ligger i arbetsytans `leverans/`: `VVS-system-2026-09-20-kallregler.zip` och `VVS-annoteringar-2026-09-20.zip`. Varje arkiv har en separat SHA-256-manifestfil. Systempaketet innehåller källkod, byggt gränssnitt och importerade referenser. Annoteringspaketet innehåller de bevarade XML-originalen samt index. Konton, hemligheter, uppladdade projekt och lokala databaser ingår inte.

## Senare kontroll: modellanslutning och missade rörbuntar

OpenAI-modellen körs nu på riktigt. Före bunträttningen gav modellkörningarna 81,291 m på 0201112 (2,188 m osäkert) och 27,546 m på 0501112 (0,066 m osäkert). A0011 gav 161,940 m. Dessa är modellens tilldelningar, inte kontrollmängder.

PipeStudios byteidentiska `_complete_bundle_landings` var importerad men saknades i anropskedjan. Den körs nu före båda lägena med källans standardavstånd. På A0011 hittas därmed fem kontakter för 5×KV2 och fem för 5×VV1. Inga längder multipliceras för att fylla bortfall. Två andra 2×-märkningar har fortfarande bara en kontakt vardera; detta visas uttryckligen i analysen.

Den svarta KV1-ledningen i användarens skärmbild hade dessutom ett geometrifel: kopplingsstreck lästes som `I / / / /`, vilket skapade en falsk anteckning och tog bort den intilliggande rörböjen som hänvisningslinje. Upprepade symbolstreck räknas nu inte som självständig vektortext. Verklig PDF-text och riktiga detaljnoter behålls. På originalritningen återkommer bågens sex segment och ledningen förbinds från (1081,68; 844,12) till (1526,64; 918,88).

En separat OCR-kontroll av 0501112 ökade antalet lästa beteckningar från 63 till 65 men gav inte fler verifierade ledarkontakter. OCR räknas därför inte som en lösning på det kvarvarande bortfallet. Fullständig obevakad mängdträffsäkerhet är ännu inte styrkt mot oberoende handmängdning.

Slutlig kontroll av skärmbildens ritning: jobb `e28f1ebe465047438cb3ff45ebc5759a` på användarkontot. Den tidigare svarta ledningen är nu tilldelad KV1-X31-16 genom hela den återställda böjen. KV1:s horisontella mängd ökade från 8,782 till 16,958 m (+8,176 m). Totalt tilldelades 193,566 m horisontellt och 0,550 m vertikalt. Noll tvetydig mängd betyder inte att allt är upptäckt: 153 primitiv saknar fortfarande tilldelning och två 2×-märkningar saknar varsin kontakt.

Verifieringen finns i `results/current/source-live/screenshot-validation.json`, bild `bundle-final.png`. Full svit: 990 godkända, 3 överhoppade. Ny API-kontroll för stilval, autentisering och hemlighetsfri status tillkommer separat. Inga kreditposter skapades för de två nya lokala analysjobben. OpenAI-användningen är separat och sparas som faktiska tokenantal; ingen okänd prislista används för att gissa kostnaden.

API-sviten efter tillagd anslutningskontroll: 28 godkända. Slutligt gränssnittsbygge passerade språk-, typ- och lintkontroller. Aktuell leverans: `VVS-system-2026-09-20-rordetektion.zip`; den tidigare källimportleveransen är bevarad.
