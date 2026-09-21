# Kartan över systemet

En fullständig genomgång av vad som finns, var det ligger och hur det hänger ihop — skriven för den som ska
sätta sig in i hela kodbasen och rätta det som är fel. `SYSTEMET.md` förklarar *varför*; den här filen är
*vad och var*.

Sist i filen ligger en maskingenererad lista över **varje modul och varje publik funktion** i motorn och
tjänsten, med första raden av vad den säger att den gör.

---

## 0. Vad systemet är, på tio rader

En VVS-mängdare laddar upp en ritning (vektor-PDF). Motorn läser ritningens egna vektorkoder — inga bildpunkter,
ingen gissning — hittar rörbeteckningarna, följer hänvisningslinjerna från varje beteckning till det rör den
pekar på, bygger fysiska rör ur linjerna, och mäter dem i bladets skala. Resultatet är en mängdtabell där varje
meter går att spåra bakåt till en linje och en etikett på bladet.

Grundprincipen, som allt annat är underordnat: **identitet bara via riktiga hänvisningslinjer, aldrig via
närmaste.** `AMBIGUOUS` är ett giltigt svar. Fel säkerhet är det inte.

Runt läsningen finns: rättelser som lär, en kalkyl som gör mängd till pris och anbud, ett mängdningsverktyg för
hand, ett granskningsrum, en 3D-vy, en akademi och en adminportal.

---

## 1. Grundreglerna — bryt dessa och produkten är trasig

Den som rättar kod ska känna till dessa först. De är inte stilfrågor.

1. **Mätvägen når aldrig nätverket.** Varje meter kommer ur geometri och regler i Python. Ingen språkmodell,
   ingen extern tjänst, ingen slump. Det är vad som gör läsningen deterministisk.
2. **Ingen identitet utan ledare.** Ett rör får sitt namn av en hänvisningslinje som faktiskt landar på det.
   Närmaste etikett är inget bevis. Går det inte att avgöra blir svaret `AMBIGUOUS_PIPE_ATTACHMENT`.
3. **Inga ritningsspecifika värden i `engine/vvs_engine/`.** Inga lagernamn, inga beteckningar, inga
   koordinater från en viss ritning. Kontrolleras av `contamination.py::scan_source` — den ska stå på `PASS`.
4. **Facit och valideringsdata ligger utanför repot** (`data/validation_*`, `data/validation_set3`,
   `data/styles`, `data/cvat` är git-ignorerade). Produktionskod får aldrig importera eller läsa dem.
5. **Granskningen får inte röra läsningen.** Agenterna i `review/` returnerar fynd; de ändrar aldrig ett mått.
6. **En rättelse får bara avgöra ett fall motorn redan kallat tvetydigt.** Den får aldrig skapa geometri,
   namnge något ingen linje nådde, eller ändra något motorn är säker på (`learning.py`, `corrections.py`).
7. **Klienten räknar aldrig ett mått som sparas.** Förhandsvisningen medan man ritar är ungefärlig; siffran som
   sparas kommer från servern (`backend/app/markups.py` → `engine/vvs_engine/takeoff/`).
8. **Zoomen kan inte påverka en mängd.** Mätmotorn ser inga skärmkoordinater. Det finns ett prov för det.
9. **Utan skala finns ingen meter.** Ett blad utan läsbar skala svarar i ritningens punkter, med skälet
   utskrivet. En påhittad meter är värre än ingen.
10. **Nycklar läses ur miljön i anropsögonblicket.** Ingen nyckel i repo, fil, logg eller svar.

---

## 2. Var saker ligger

```
engine/vvs_engine/      läsningen: allt som gör en PDF till en mängd. Inga webbberoenden.
engine/tests/           41 provfiler. Kör: cd engine && python3 -m pytest -q tests
engine/tools/           transporter (astra/agent/vision) och e2e-verktyg
backend/app/            FastAPI: konton, projekt, jobb, resultat, export, mängdning, kalkyl, admin
frontend/src/           React + TypeScript, svenskt gränssnitt
frontend/smoke/         rökprov som klickar i en riktig webbläsare (Playwright)
docs/                   SYSTEMET.md (varför), KARTA.md (den här filen)
data/                   lokal lagring och (git-ignorerad) valideringsdata
```

Kör allt lokalt:

```bash
cd engine && python3 -m pytest -q tests           # 337 prov
cd frontend && npm run build                      # eslint --max-warnings=0 && tsc --noEmit && vite build
python3 frontend/smoke/serve_seeded.py            # tjänsten seedad med två analyserade blad, port 8077
python3 frontend/smoke/ui_smoke.py                # klickar igenom läsningen
python3 frontend/smoke/ui_smoke3.py               # mängdningsbordet
python3 frontend/smoke/ui_smoke4.py               # granskningsrummet
```

`frontend/dist` är git-ignorerad och serveras av API:t. **Bygg frontend innan ett rökprov**, annars provas en
gammal version.

---

## 3. Läsningens kedja, steg för steg

Ingången är `vvs_engine/cli.py::analyze_pdf(pdf, out_dir, ...)`. Den läser dokumentet, kör varje sida genom
`pipeline.py::analyze_page`, och skriver artefakterna.

| # | Steg (`progress`-namn) | Modul | Vad som händer |
|---|---|---|---|
| 1 | `CLASSIFYING_INPUT` | `pdf/classify.py` | Är det en vektor-PDF? En skannad avvisas med besked, inte med gissning. |
| 2 | `EXTRACTING` | `pdf/extract.py` | Varje vektorobjekt, segment, tecken och OCG ut ur PDF:en med härkomst. |
| 3 | `DISCOVERING_DRAWING_GRAMMAR` | `profile/layers.py`, `profile/hatch.py` | Bladets egna familjer: pennor (lager + bredd + färg), skraffering, textstilar. |
| 4 | `RECONSTRUCTING_TEXT` | `text/strokes.py`, `text/recognize.py`, `text/vector_text.py` | Streckklumpar sätts ihop till tecken och rader. En ritning skriver ofta text som streck, inte som text. |
| 5 | `RESOLVING_UNREADABLE_TEXT` | `text/ocr_assist.py` | *(valfritt, av som standard)* OCR får namnge tecken streckläsaren inte kunde. |
| 6 | `READING_DESIGNATIONS` | `semantics/grammar.py` | Vilka rader är rörbeteckningar? Formen lärs ur bladet självt; DN rekonstrueras. |
| 7 | `FINDING_LEADERS` | `semantics/leaders.py` | Hänvisningslinjernas familjer och deras ändar. |
| 8 | — | `semantics/attachment.py` | Ledare → rör. Det här är kärnan: `VERIFIED`, `AMBIGUOUS` eller `NO_PIPE_ATTACHMENT`, med skäl. |
| 9 | `BUILDING_TOPOLOGY` | `pipes/representation.py` | Rörens primitiv, bryggor över streck-prick, symboler och dubbellinjer; skrafferade figurer sorteras bort. |
| 10 | `BUILDING_PHYSICAL_PIPES` | `pipes/ownership.py` | Vem äger vilken sträcka. Systemgränser, dimensionsgränser, kedjor från ankare. |
| 11 | `MEASURING` | `measure/scale.py`, `measure/measure.py` | Skalan ur text och skalstock; sedan meter. Lodrätt ur stigare och etiketter. |
| 12 | — | `reconcile.py`, `determinism.py`, `contamination.py` | Stämmer summorna? Ger två körningar samma svar? Finns ritningsspecifika värden i koden? |
| 13 | — | `review/agents.py` | Granskningsagenterna säger om resultatet är trovärdigt. De ändrar ingenting. |
| 14 | — | `output/artifacts.py`, `output/overlays.py` | `quantities.json`, överlägg, rapporter, sökbar PDF. |

Sidöverskridande: `handling.py` (hela handlingen som en modell), `semantics/legend.py` (förklaringslistan och
hur koder används), `semantics/declarations.py` (bladets egen tabell över anslutningsrör), `routes.py`
(vägvalen mellan strategier), `rules.py` (varje tröskel som en namngiven regel som går att flytta).

### Artefakterna en läsning skriver

`quantities.json` (mängden och allt som bär den), `reading.json`, överlägg som SVG/PNG, `ocr-assisted-characters.json`,
`performance.json`, samt rapporter. `backend/app/jobs.py` lagrar dem under `results/{drawing}/{job}`.

---

## 4. Datamodellen (SQLAlchemy, `backend/app/db.py`)

23 tabeller:

`users`, `projects`, `project_analyses`, `document_overrides`, `drawings`, `analysis_jobs`, `corrections`,
`rule_settings`, `accounts`, `partners`, `payouts`, `crm_notes`, `content`, `experiments`, `events`,
`course_progress`, `calibrations`, `drawing_viewports`, `spaces`, `tool_presets`, `service_settings`,
`calculations`, `markups`.

De viktigaste:

- **`drawings`** — den uppladdade filen, dess lagringsnyckel och sidantal. Originalet ändras aldrig.
- **`analysis_jobs`** — en läsning: status, steg, framsteg, sammanfattning, `result_key`.
- **`corrections`** — vad en människa ändrade, och vad det fick lära ut.
- **`markups`** — allt någon ritat för hand: verktyg, punkter, lager, beteckning, `props` (djup, multiplikator,
  tillägg, avdrag), `measure` (serverns svar), och granskningens fält `subject`, `status`, `comment`, `meta`,
  `source`, `confidence`, `space_id`, `seq`.
- **`calibrations`** — en uppmätt skala per blad och sida. Går före läsningens skala.
- **`drawing_viewports`** — ett område på sidan med egen skala (detaljen i hörnet).
- **`spaces`** — rum/ytor att knyta markeringar till.
- **`service_settings`** — nycklar `rule:*` (flyttade regler), `assume:*` (antaganden för mängden), `run:*`
  (vad läsningen kör: `review_ocr`, `ocr_assist`).

---

## 5. Mätmotorn — en form, en skala, ett mått

`engine/vvs_engine/takeoff/` är **den enda platsen** där något mäts åt användaren. Den används av mängdningen,
av granskningen och av allt som kommer sedan.

- `geometry.py` — `length_of`, `perimeter_of`, `signed_area`, `ring_area`, `area_with_holes` (ett hål räknas
  bara om dess tyngdpunkt ligger inne i ytan), `point_in_ring`, `bbox`, `centroid`, `angle_between`.
- `measure.py` — `Scale` (meter per punkt, källa, `from_ratio`), `scale_from_two_points` (kalibrering),
  `Viewport` (område med egen skala, `order` avgör överlapp deterministiskt), `scale_at`, `convert` (mm…yard,
  med `power` för ytor och volymer), `measure(kind, points, scale, ...)` → `Measurement` med `value`, `raw`,
  `steps`, `warnings`.
- `formulas.py` — räknade kolumner utan att köra användarens kod: uttrycksträd med tillåtna noder,
  `FUNCTIONS` = abs/min/max/round/sqrt/floor/ceil/sum/om, `referenced_names`, `order_of_evaluation` (cirklar
  avvisas med namn), `evaluate_all`.

Prov: `engine/tests/test_the_measurement_engine.py` — 18 stycken, inklusive *zoomen kan aldrig ändra ett mått*
och att `__import__`, `open`, comprehensions och lambda avvisas i en formel.

---

## 6. Tjänsten — 108 rutter

Alla registrerade rutter finns i tabellen längst ned (avsnitt 12). Modulerna:

| Modul | Ansvar |
|---|---|
| `main.py` | app, CORS, statiska filer, SPA-fallback, regler (`/api/rules`), inställningar (`/api/settings`), lärdomar |
| `auth.py` | registrering, inloggning, JWT, `current_user` / `current_admin` |
| `projects_api.py` | projekt, ritningar, uppladdning, projektanalys |
| `jobs.py` | analysjobb: kö, körning, framsteg, andra läsaren, filmen |
| `exports.py` | Excel, JSON, CSV, sökbar PDF, rapporter |
| `markups.py` | mängdning och granskning: markeringar, kalibrering, viewportar, verktygslåda, CSV |
| `calc.py` | kalkyl, normtid, priser, anbud som PDF |
| `agent.py` | chatt-agenten över en läsning och över hela handlingen |
| `admin.py` | överblick, uppmärksamhet, systemhälsa, affiliate, CRM, CMS, A/B, heatmaps |
| `academy.py` | akademins kurser, framsteg och utmärkelser |
| `public.py` | landningssida, innehåll, händelser |
| `storage.py` | filer på disk, en katalog per ritning |
| `config.py` | inställningar ur miljön (`VVS_*`) |
| `db.py` | tabellerna |

---

## 7. Gränssnittet

Sidomenyns flikar och deras vägar:

| Flik | Väg | Sida |
|---|---|---|
| Projekt | `/projekt`, `/projects/:id`, `/drawings/:id` | `Projects.tsx`, `Project.tsx`, `Drawing.tsx` |
| — (läsningen) | `/jobs/:id` | `Analysis.tsx` |
| — (kalkylen) | `/jobs/:id/kalkyl` | `CalcPage.tsx` |
| Lär dig VVS | `/lar` | `LearnPage.tsx` |
| Mängda | `/mangda`, `/mangda/:id` | `TakeoffPick.tsx`, `Takeoff.tsx` |
| CAD | `/cad`, `/cad/:id` | `CadPick.tsx`, `Cad.tsx` |
| Material | `/material` | `Material.tsx` |
| Administration | `/admin` | `Admin.tsx` |

Bärande komponenter:

- **`PdfViewer.tsx`** — bladet, zoom/panorering, alla överlägg (rör, tvetydiga, oägda, beteckningar, ledare,
  ankare, bortvalt, skrafferat), ritgester (`draw`, `extend`, `erase`), markeringar med status och urval,
  `cloudPath` (granskningsmoln), `identityColor` (lånad ur `palette.ts`). `ViewerHandle`: `zoomIn`, `zoomOut`,
  `fitPage`, `fitWidth`, `fullscreen`, `zoomTo(bbox)`.
- **`QuantityTable.tsx`** — mängdtabellen med antaganden, filter, urval.
- **`MarkupsList.tsx`** — markeringslistan: sortering, filter, status per rad och i klump, radering.
- **`Corrections.tsx`**, **`Reasoning.tsx`**, **`LegendView.tsx`**, **`AgentChat.tsx`**, **`AnalysisFilm.tsx`**,
  **`Markups.tsx`**, **`Boundary.tsx`**, **`Status.tsx`**, **`LearnWizard.tsx`**.
- **3D:** `three/model.ts` (rena funktioner: resultat in, `BuildingModel` ut), `Drawing3DView.tsx` (three.js:
  scen, ljus, väggar som `InstancedMesh`, rör som `TubeGeometry`, skyltar som sprites, orbit/panorering/zoom,
  gå-läge med pointer lock, plockning av rör och väggar), `Drawing3DControls.tsx`,
  `DrawingTo3DTransition.tsx`, `AnalysisGateAnimation.tsx`, `AnalysisCompletionReveal.tsx`.
- **`palette.ts`** — `identityColor(key)`: samma rör får samma färg på bladet, i tabellen och i 3D.
- **`api.ts`** — hela klienten mot API:t, ett anrop per rutt.

---

## 8. 3D-vyn

`three/model.ts::buildModel(result, opts)` gör läsningens svar till en modell:

- **Rör** ur `result.pipes[].geometry` (polylinjer i punkter), grovlek ur DN-tabellen, färg ur `identityColor`,
  stigare ur mängdtabellens `riser_count`, plus bitarna genom vägg ur `hatched_geometry` (märkta `inWall`).
- **Väggar** ur `declined_geometry.families` och `.unconsidered`: bara sammanhängande bläck på lager som inte
  är rörlika (`on_a_pipe_like_layer`), segment längre än en halv meter, inom planområdet (rörens utbredning
  med marginal — så att namnruta, förklaringslista och logotyp inte reses till väggar), och familjer vars bläck
  nästan bara går åt ett håll sorteras bort som skraffering (`isHatchFill`).
- Tjocklek ur avståndet till en parallell granne, höjd ur antagen våningshöjd.

`Drawing3DView.tsx` lägger till: vridbar vy ovanifrån (upp-vektorn vänds ned i planet när vyn blir brant),
beteckningsskyltar som alltid är vända mot betraktaren och växer med avståndet, genomskinliga väggar, ett
gå-läge i ögonhöjd (WASD/piltangenter, mus för blicken, skift för att springa, Esc för att sluta), och
plockning som ger rörets mängdrad eller väggens mått.

---

## 9. Var AI *kan* kopplas in (allt utanför mätvägen)

| Ställe | Modul | Vad den får göra | Standard |
|---|---|---|---|
| Andra läsaren | `semantics/astra.py` | Välja bland kandidater i ett fall motorn redan kallat tvetydigt. `verify` avvisar allt som inte står i listan. | På om `OPENAI_API_KEY` finns |
| Chatt-agenten | `backend/app/agent.py`, `agent/tools.py` | Välja vilket verktyg som ska svara. Siffrorna kommer ur verktygen. | Samma |
| Vision | `review/vision.py` | Titta på bilden och säga något. Kan aldrig bli geometri. | Samma |
| OCR (ingen språkmodell) | `review/ocr_check.py`, `text/ocr_assist.py` | Korsprov respektive teckenhjälp. | **Av** — mätt att de kostar ~16 s/blad och inte ändrade mängden |

Mätt: andra läsaren kan som mest röra 179,5 m av portens 6 245 m facit (2,9 %). Porten kördes utan den.

---

## 10. Regler, inställningar och miljö

- **Regler** (`vvs_engine/rules.py`): varje tröskel har ett id, en enhet, ett standardvärde och ett tillåtet
  intervall. De går att flytta per tjänst (`/api/rules`, admin) och binds till tråden under en läsning
  (`rules.using`).
- **Antaganden** (`assume:*`): våningshöjd för stigare, var stigare räknas ifrån, om rör i skrafferade ytor
  ingår.
- **Vad läsningen kör** (`run:*`): `review_ocr`, `ocr_assist`.
- **Miljö** (`VVS_*`): `VVS_DATABASE_URL`, `VVS_STORAGE_ROOT`, `VVS_SECRET_KEY`, `VVS_WORKER_THREADS`,
  `VVS_ANALYSIS_DEADLINE_S`, `VVS_RUN_REVIEW`, `VVS_REVIEW_OCR`, `VVS_OCR_ASSIST`, `VVS_SECOND_READER`,
  `VVS_SECOND_READER_MODEL`, `VVS_CORS_ORIGINS`, `VVS_ALLOW_REGISTRATION`, `VVS_STATIC_DIR`.
  `demand_a_real_secret()` vägrar starta med utvecklingsnyckeln i skarpt läge.

---

## 11. Var systemet står, och vad som inte är gjort

**Porten (33 blad mot facit):** 80,0 % av facits meter ägs, 27,3 % falska meter. Skalan `VERIFIED` på alla
blad. Determinism och kontaminering `PASS`.

De två stora kvarvarande felkällorna, båda kända och båda strukturella:

1. **Deklarerade anslutningsrör.** Vissa blad har en tabell över anslutningsrör som facit inte räknar (A0521:
   114 m deklarerat mot ~1 m i facit). Systemet redovisar dem separat (`declared_m`, märket "tabell"), men de
   ligger i totalen.
2. **Lodräta meter.** Facit har meter som planen inte ritar. `riser_count` och våningshöjd är antaganden.

**Inte byggt än:**

- CAD-rummet (rityta, lager, snap, redigering, egenskaper) — ingen kod finns.
- Rum/ytor i gränssnittet, dynamisk fyllning, symbolsökning, jämför/överlägg, ritningsset med revisioner och
  slip-sheet, batchjobb, stämplar, hyperlänkar, XLSX/PDF-rapporter ur markeringslistan, viewport-redigering i
  gränssnittet, samarbete i realtid.

---

## 12. Alla rutter

| Metod | Väg | Modul | Funktion | Vad den gör |
|---|---|---|---|---|
| GET | `/api/academy/awards` | `academy.py` | `awards` | Alla utmärkelser som finns, och vilka av dem som är tagna. En låst utmärkelse säger vad som krävs. |
| GET | `/api/academy/progress` | `academy.py` | `progress` | Allt den inloggade har gjort, per kurs. |
| PUT | `/api/academy/progress/{course}` | `academy.py` | `save_step` | Skriv ned ett gjort steg, räkna om poängen och dela ut det som förtjänats. |
| GET | `/api/admin/academy` | `admin.py` | `academy` | Hur långt folk kommer i akademin, och var de fastnar. |
| GET | `/api/admin/accounts` | `admin.py` | `list_accounts` |  |
| POST | `/api/admin/accounts` | `admin.py` | `create_account` |  |
| PUT | `/api/admin/accounts/{account_id}` | `admin.py` | `update_account` |  |
| GET | `/api/admin/attention` | `admin.py` | `attention` | Det som väntar på någon: misslyckade läsningar, en kö som växer, regler flera konton flyttat åt samma |
| GET | `/api/admin/content` | `admin.py` | `list_content` |  |
| GET | `/api/admin/content/{slug}` | `admin.py` | `get_content` |  |
| PUT | `/api/admin/content/{slug}` | `admin.py` | `put_content` | Spara som utkast, eller publicera. |
| GET | `/api/admin/corrections` | `admin.py` | `corrections` | Varje rättelse en kund gjort, med situationen den gjordes i. |
| GET | `/api/admin/crm` | `admin.py` | `crm` |  |
| POST | `/api/admin/crm` | `admin.py` | `add_note` |  |
| PUT | `/api/admin/crm/{note_id}` | `admin.py` | `close_note` |  |
| GET | `/api/admin/experiments` | `admin.py` | `list_experiments` | Varje prov med utfallet, och med intervallet runt utfallet. |
| POST | `/api/admin/experiments` | `admin.py` | `create_experiment` |  |
| PUT | `/api/admin/experiments/{key}` | `admin.py` | `update_experiment` |  |
| GET | `/api/admin/heatmap` | `admin.py` | `heatmap` | Var folk klickar på en sida, som ett rutnät av andelar. |
| GET | `/api/admin/learning` | `admin.py` | `learning` | Vad rättelserna faktiskt lärt systemet - och vad de inte kan lära det. |
| GET | `/api/admin/overview` | `admin.py` | `overview` | Tjänsten på en sida. |
| GET | `/api/admin/partners` | `admin.py` | `list_partners` | Alla partners för en admin; sin egen rad för en partner. |
| POST | `/api/admin/partners` | `admin.py` | `create_partner` |  |
| PUT | `/api/admin/partners/{partner_id}` | `admin.py` | `update_partner` |  |
| GET | `/api/admin/paths` | `admin.py` | `paths` | Vilka sidor som alls har klick att titta på. |
| GET | `/api/admin/payouts` | `admin.py` | `list_payouts` |  |
| POST | `/api/admin/payouts` | `admin.py` | `create_payout` |  |
| POST | `/api/admin/payouts/draft` | `admin.py` | `draft_payout` | Skapa en utbetalning ur den provision som faktiskt räknats fram. |
| PUT | `/api/admin/payouts/{payout_id}` | `admin.py` | `settle_payout` |  |
| GET | `/api/admin/readings` | `admin.py` | `readings` | Varje läsning någon kört, med vem som körde den och vad den gav. |
| GET | `/api/admin/rules` | `admin.py` | `rule_settings` | Varje regel något konto flyttat, med skälet och skärmbilden. |
| GET | `/api/admin/rules/{rule_id}/shot/{user_id}` | `admin.py` | `rule_shot` | Skärmbilden någon lade vid en flyttad regel: fallet som fick dem att flytta den. |
| GET | `/api/admin/system` | `admin.py` | `system_health` | Vad som kör, och hur det mår: byggning, andra läsaren, kön, lagret, databasen. Bara fakta som går att |
| GET | `/api/admin/timeline` | `admin.py` | `timeline` | En rad per dygn: hur många läsningar, hur de gick, och hur mycket av bladen de kom igenom. |
| PUT | `/api/admin/users/{user_id}` | `admin.py` | `update_user` |  |
| GET | `/api/agent/tools` | `main.py` | `agent_tools` | The contract, so the interface can show what the agent is actually able to do. |
| POST | `/api/auth/login` | `main.py` | `login` |  |
| GET | `/api/auth/me` | `main.py` | `me` |  |
| POST | `/api/auth/register` | `main.py` | `register` |  |
| GET | `/api/content/{slug}` | `public.py` | `published` | Den publicerade texten för en sida. Ett utkast syns aldrig här. |
| DELETE | `/api/drawings/{drawing_id}` | `main.py` | `delete_drawing` |  |
| GET | `/api/drawings/{drawing_id}` | `main.py` | `get_drawing` |  |
| POST | `/api/drawings/{drawing_id}/analyze` | `main.py` | `analyze` |  |
| DELETE | `/api/drawings/{drawing_id}/calibration` | `markups.py` | `drop_calibration` | Ta bort den uppmätta skalan: läsningens egen gäller igen. |
| GET | `/api/drawings/{drawing_id}/calibration` | `markups.py` | `read_calibration` |  |
| PUT | `/api/drawings/{drawing_id}/calibration` | `markups.py` | `set_calibration` | Dra en linje över något vars längd är känd och skriv vad det är. Måtten på bladet räknas om direkt. |
| GET | `/api/drawings/{drawing_id}/corrections` | `main.py` | `list_corrections` |  |
| POST | `/api/drawings/{drawing_id}/corrections` | `main.py` | `add_correction` |  |
| DELETE | `/api/drawings/{drawing_id}/corrections/{correction_id}` | `main.py` | `undo_correction` |  |
| GET | `/api/drawings/{drawing_id}/file` | `main.py` | `drawing_file` |  |
| GET | `/api/drawings/{drawing_id}/markups` | `markups.py` | `list_markups` | Markeringarna på ett blad, eller i hela handlingen. |
| PATCH | `/api/drawings/{drawing_id}/markups` | `markups.py` | `patch_many` | Samma ändring på flera markeringar: tjugo frågor som är besvarade stängs i ett svep. |
| POST | `/api/drawings/{drawing_id}/markups` | `markups.py` | `add_markup` |  |
| GET | `/api/drawings/{drawing_id}/markups.csv` | `markups.py` | `markups_csv` | Markeringslistan som en fil att öppna i Excel: en rad per markering, med måttet och vad det räknades på. |
| DELETE | `/api/drawings/{drawing_id}/markups/{markup_id}` | `markups.py` | `drop_markup` | Markeringen stryks men står kvar i lagret. Den som ritat tjugo sträckor och råkar ta bort en ska kunna |
| PATCH | `/api/drawings/{drawing_id}/markups/{markup_id}` | `markups.py` | `patch_markup` | Ändra vad markeringen handlar om utan att röra det den mätte. |
| PUT | `/api/drawings/{drawing_id}/markups/{markup_id}` | `markups.py` | `edit_markup` |  |
| POST | `/api/events` | `public.py` | `post_events` | Ta emot vad som hände. Aldrig mer än ett samlat knippe åt gången, och aldrig något okänt. |
| GET | `/api/experiments/active` | `public.py` | `active_experiments` | Vilka prov som pågår och vad den här besökaren ska se av dem. |
| GET | `/api/health` | `main.py` | `api_health` |  |
| GET | `/api/jobs/{job_id}` | `main.py` | `job_status` |  |
| POST | `/api/jobs/{job_id}/agent` | `main.py` | `agent_ask` | Ask the agent about this reading. |
| POST | `/api/jobs/{job_id}/agent/edit` | `main.py` | `agent_edit` | Accept a change the agent proposed, and write it to the correction log. |
| POST | `/api/jobs/{job_id}/agent/tool` | `main.py` | `agent_tool` | Run one tool against this reading and say what it found, with no model in the way. |
| GET | `/api/jobs/{job_id}/artifacts` | `main.py` | `list_artifacts` |  |
| GET | `/api/jobs/{job_id}/artifacts/{name}` | `main.py` | `get_artifact` |  |
| GET | `/api/jobs/{job_id}/calc` | `calc.py` | `latest` |  |
| PUT | `/api/jobs/{job_id}/calc` | `calc.py` | `save` | Spara kalkylen: antagandena och valen. Talen räknas om ur läsningen varje gång - de är aldrig lagrade fakta. |
| GET | `/api/jobs/{job_id}/calc/anbud` | `calc.py` | `anbud_info` | Hur många sidor anbudet har, så att förhandsgranskningen kan hämta dem en och en. |
| GET | `/api/jobs/{job_id}/calc/anbud.html` | `calc.py` | `anbud_html` | Anbudet som HTML, för den som vill läsa det som text: samma kropp, huvudet skrivet i stället för ritat. |
| GET | `/api/jobs/{job_id}/calc/anbud.pdf` | `calc.py` | `anbud_pdf` |  |
| GET | `/api/jobs/{job_id}/calc/anbud/sida-{n}.png` | `calc.py` | `anbud_page` | Sidan n av anbudet som bild: det dokument som skickas, inte en efterlikning av det. |
| POST | `/api/jobs/{job_id}/calc/preview` | `calc.py` | `preview` |  |
| GET | `/api/jobs/{job_id}/calc/underlag` | `calc.py` | `underlag` | Normtidsunderlaget och standardantagandena, så att gränssnittet kan visa vad som går att ställa in. |
| GET | `/api/jobs/{job_id}/export/{fmt}` | `main.py` | `export` |  |
| GET | `/api/jobs/{job_id}/film` | `main.py` | `job_film` | What each stage of the reading found, as far as it has got. Available while the job is still running. |
| GET | `/api/jobs/{job_id}/judge` | `main.py` | `job_judge` | What, out of everything the reading and its reviewers found, should actually change. |
| GET | `/api/jobs/{job_id}/result` | `main.py` | `job_result` |  |
| POST | `/api/jobs/{job_id}/vision` | `main.py` | `vision_check` | A second opinion by eye on a reading that is already finished. |
| GET | `/api/jobs/{job_id}/why/{pipe_id}` | `main.py` | `why` |  |
| GET | `/api/lessons` | `main.py` | `my_lessons` | What this account's corrections have taught, and how often each answer was given. |
| GET | `/api/materials` | `main.py` | `materials` | Artiklar ur materialboken, sökta på benämning eller artikelnummer. |
| GET | `/api/me/role` | `public.py` | `my_role` | Vad den inloggade får se. Gränssnittet visar admin-länken efter det här och inget annat. |
| GET | `/api/projects` | `main.py` | `list_projects` |  |
| POST | `/api/projects` | `main.py` | `create_project` |  |
| DELETE | `/api/projects/{project_id}` | `main.py` | `delete_project` |  |
| GET | `/api/projects/{project_id}` | `main.py` | `get_project` |  |
| POST | `/api/projects/{project_id}/agent` | `projects_api.py` | `project_agent` | Fråga hela handlingen. Modellen väljer verktyg, verktygen svarar ur det som lästs. |
| POST | `/api/projects/{project_id}/agent/tool` | `projects_api.py` | `project_agent_tool` | Ett verktyg rakt av, utan modell: de färdiga frågorna i panelen. Kan inte hitta på en siffra. |
| GET | `/api/projects/{project_id}/agent/tools` | `projects_api.py` | `project_agent_tools` |  |
| GET | `/api/projects/{project_id}/analysis` | `projects_api.py` | `latest_analysis` |  |
| POST | `/api/projects/{project_id}/analysis` | `projects_api.py` | `start_analysis` | Starta projektanalysen. Körs på samma kö som mängdningen. |
| GET | `/api/projects/{project_id}/analysis/changes` | `projects_api.py` | `changes` | Ändringsregistret för ett versionspar. Nyckeln är parets egen, ur den senaste projektanalysen. |
| POST | `/api/projects/{project_id}/drawings` | `main.py` | `upload_drawing` |  |
| GET | `/api/projects/{project_id}/mode` | `projects_api.py` | `get_mode` | Vad projektet valt, och om det redan finns arbete gjort under valet. |
| PUT | `/api/projects/{project_id}/mode` | `projects_api.py` | `set_mode` | Vilken sorts analys projektet använder. Valet sparas på projektet och går att se senare. |
| GET | `/api/projects/{project_id}/overrides` | `projects_api.py` | `list_overrides` |  |
| POST | `/api/projects/{project_id}/overrides` | `projects_api.py` | `set_override` | Rätta vad läsningen kom fram till om ett blad. |
| GET | `/api/rules` | `main.py` | `rules_catalogue` | Every rule the reading follows, what it decides, and what it stands at for this service. |
| PUT | `/api/rules/{rule_id:path}` | `main.py` | `set_rule` | Move one rule for the service, or put it back. |
| GET | `/api/settings` | `main.py` | `read_settings` | Antagandena mängden räknas ihop med: våningshöjd för stigare, var stigare räknas ifrån, om rör i |
| PUT | `/api/settings` | `main.py` | `write_settings` | Ändra antagandena för tjänsten. Ett värde utanför vad det kan betyda avvisas, aldrig klipps. |
| GET | `/api/tools` | `markups.py` | `list_presets` |  |
| POST | `/api/tools` | `markups.py` | `add_preset` |  |
| DELETE | `/api/tools/{preset_id}` | `markups.py` | `drop_preset` |  |
| GET | `/api/version` | `main.py` | `version` | What is running here, and what it can reach - answerable without logging in. |
| GET | `/health` | `main.py` | `health` |  |
| GET | `/{full_path:path}` | `main.py` | `spa` |  |

108 rutter.

---

## 13. Alla moduler och funktioner: motorn

### `vvs_engine/__init__.py`
VVS pipe takeoff engine: drawing-adaptive vector analysis of clean VVS PDFs.


### `vvs_engine/agent/answers.py`
A tool result, said in Swedish, without a model.

- `say(name, result)` — One tool's result as a sentence. Unknown tools get their own numbers back rather than a shrug.

### `vvs_engine/agent/edits.py`
Changes to a reading, proposed rather than made.

- `foresla_radera_ror(m, ror_id, skal)`
- `foresla_byt_beteckning(m, ror_id, till_beteckning, skal)`
- `foresla_andra_dimension(m, ror_id, ny_dimension, skal)`
- `foresla_dela_ror(m, ror_id, vid_punkt, pa_delen, ny_beteckning, skal)`
- `hitta_omatt_geometri_att_rita(m)`
- `foresla_rita_ror(m, geometri_id, beteckning, skal)`

### `vvs_engine/agent/model.py`
The drawing as a model the agent can ask questions of.

- `DrawingModel · quantities, pipes, anchors, designations, legend, topology, declined, issues, review, profile, reconciliation, scale, meters_per_pt, pipe_by_id, anchor_by_id, designation_by_id, systems, components, bbox_of_pipe, adjacency, connected, path_between, nodes_by_family, free_ends, size_frontiers` *(klass)* — Everything one analysed drawing is, as the reading left it.

### `vvs_engine/agent/project_tools.py`
Vad projektagenten kan göra: frågor till hela handlingen, besvarade ur det som redan lästs.

- `tool(name, description, params)`
- `ProjectModel · documents, doc, val, cite` *(klass)* — Projektet som agenten ser det: rapporten, mängderna per blad, rättelserna, ändringslistorna.
- `hamta_handling(m)`
- `hitta_blad(m, hus, plan, disciplin, nummer)`
- `mangder_per_hus(m, hus, system)`
- `mangder_for_beteckning(m, beteckning)`
- `versioner(m)`
- `vad_andrades(m, nyckel)`
- `rattelser(m)`
- `kontrollera_handlingen(m)`
- `run(name, model, args)`
- `schemas()`
- `writes(name)`

### `vvs_engine/agent/tools.py`
What the agent can actually do, as functions rather than as text.

- `tool(name, description, params, writes)` — Register one tool. `writes` marks the ones that propose a change rather than report a fact.
- `hamta_ritning(m)`
- `hamta_forklaringslista(m)`
- `hitta_ror(m, system, dimension, beteckning, sida, omrade)`
- `hitta_beteckningar(m, text, sida, omrade)`
- `vad_finns_i_omradet(m, omrade, sida)`
- `hamta_ror(m, ror_id)`
- `mat_ror(m, ror_id)`
- `mangda(m, gruppera_pa, system, dimension)`
- `visa_hur_mangden_raknades(m, beteckning)`
- `varfor_ror(m, ror_id)`
- `folj_natet(m, ror_id)`
- `grannar(m, ror_id)`
- `vag_mellan(m, fran_ror_id, till_ror_id)`
- `hitta_dubbelritad_geometri(m)`
- `hitta_fria_rorandar(m)`
- `hitta_dimensionsbyten(m)`
- `hitta_omatt_geometri(m)`
- `hitta_olosta(m)`
- `kontrollera_lasningen(m)`
- `kontrollera_skala(m)`
- `run(name, model, args)` — Call one tool by name. Unknown names and bad arguments are answers, not exceptions.
- `schemas()` — The contract, in the shape a tool-calling model expects.
- `writes(name)` — Whether this tool proposes a change. It still only proposes; nothing in the agent writes.

### `vvs_engine/cli.py`
Command line interface: analyze a clean vector VVS PDF and write all artifacts.

- `AnalysisTookTooLong` *(klass)* — A reading that ran past its budget. Raised between pages, so what is reported is a refusal, not a guess.
- `scale_of_the_set(sheets)` — The scale the set is drawn in, where its sheets agree about it.
- `sheet_record(pa)` — One sheet of the set, as the takeoff for the whole set needs it.
- `analyze_pdf(pdf_path, out_dir, name, determinism, contamination, progress, pages, review, review_ocr, film_sink, ocr_assist, deadline_s, second_reader, known_families, known_legend)` — deadline_s: a wall-clock budget for the whole document, checked between pages.
- `main(argv)`

### `vvs_engine/contamination.py`
Contamination firewall: production source must not contain drawing-specific designations, DN inventories,

- `scan_source(root)`

### `vvs_engine/corrections.py`
Corrections a person made to a reading, applied on top of it.

- `apply(quantities, corrections, meters_per_pt)` — Return the corrected quantity rows plus an account of what each correction changed.

### `vvs_engine/determinism.py`
Determinism: semantic results must not depend on PDF object enumeration order.

- `semantic_signature(pa)` — Order-independent canonical description of the semantic result.
- `signature_hash(sig)`
- `run_determinism(doc, page_index, base_pa)` — context: whatever the reading was given besides the page itself - the set's designation list, the pens the

### `vvs_engine/film.py`
What each stage of the reading found, small enough to send while it is still running.

- `Film · note, frame, page, seeing, text, designations, leaders, families, pipes, measured` *(klass)* — Collects the frames. `sink(stage, payload)` is called once per stage, in order.

### `vvs_engine/geometry/core.py`
Deterministic geometry helpers (pure numpy / python; no enumeration-order semantics).

- `stable_id(prefix)` — Content-derived identifier. Never uses enumeration order.
- `rnd(v, nd)`
- `Seg · length, angle, mid, bbox` *(klass)*
- `dist(a, b)`
- `point_seg_distance(px, py, s)` — Return (distance, t) of point to segment; t in [0,1] is the projection parameter.
- `seg_intersection(a, b, eps)` — Proper/touching intersection of two segments. Returns (x, y, ta, tb) or None.
- `angle_diff(a, b)` — Smallest difference between two undirected angles in degrees.
- `collinear(a, b, ang_tol, off_tol)`
- `bbox_union(boxes)`
- `bbox_expand(b, m)`
- `bbox_intersects(a, b)`
- `bbox_contains_point(b, x, y, m)`
- `flatten_bezier(p0, p1, p2, p3, n)`
- `polyline_length(pts)`
- `GridIndex · insert, query, query_point` *(klass)* — Deterministic uniform-grid spatial hash over bboxes. Query results are sorted by item key.

### `vvs_engine/handling.py`
Vad en handling är, läst ur bladet självt.

- `Field · as_dict` *(klass)* — Ett värde och var det kom ifrån. Utan källan är värdet ett påstående ingen kan pröva.
- `Handling · key, as_dict` *(klass)* — Ett blad, så som det beskriver sig självt.
- `read_handling(path, page)` — Vad ett blad säger om sig självt. Bara text - snabbt nog för hundratals blad.
- `Pair · as_dict` *(klass)* — Två blad av samma ritning i olika version, och varför de anses vara det.
- `NotAPair · as_dict` *(klass)* — Två blad som liknar ett par men inte är det, och vad de är i stället.
- `pair_versions(docs)` — Vilka blad som är samma ritning i två versioner, och vilka som bara ser ut så.
- `as_report(docs)` — Handlingsförteckningen, versionsparen, och det som inte gick att avgöra.

### `vvs_engine/learning.py`
What a correction is allowed to teach a later reading.

- `situation()` — The fingerprint of a case, taken from the drawing.
- `lessons(corrections)` — Corrections turned into lessons, one per situation, with how often a person answered the same way.
- `settle(ambiguous, lessons_)` — For each ambiguous case, the lesson that applies to it - if one does, exactly.

### `vvs_engine/measure/measure.py`
Measurement and quantity aggregation. Meters only with verified scale; vertical only with explicit evidence.

- `double_line_gap(dn, mpp)` — How far apart the two edges of a pipe of this size lie on this sheet - or None when the size or the
- `twin_edges(pipes, mpp)` — physical_pipe_id -> the pipe it is the second edge of. Runs are compared within one pen and one identity,
- `PipeMeasure` *(klass)*
- `measure_pipes(own, scale, elevations, hatched_pt)` — elevations: anchor_id -> list of {tag, value} elevation annotations attached to the anchor's label unit.
- `aggregate(measures, ambiguous_pt, mpp, risers, label_counts, label_risers)` — label_counts: identity key -> number of verified labels on the drawing, which is what a reader counts;

### `vvs_engine/measure/scale.py`
Scale discovery from the PDF itself: scale text (1:N with optional page-format qualifier) and vector scale bars

- `ScaleEvidence` *(klass)*
- `ScaleResult · as_dict` *(klass)*
- `scale_from_the_set(known, why)` — The scale the rest of the drawing set settled, for a sheet that could not settle its own.
- `discover_scale(page, lines)`
- `find_tick_bar(page)` — A scale bar read as geometry, without reading the numbers under it.

### `vvs_engine/normtid.py`
Normtid VVS: grundtider, tillägg och avvikelseanalys.

- `Table · as_dict` *(klass)* — En tabell ur boken, med var den står.
- `Supplement · as_dict` *(klass)*
- `Factor · as_dict` *(klass)* — En faktor i avvikelseanalysen, med skalan boken sätter för den.
- `base_time(table_id, key, column)` — Grundtiden för en dimension eller vikt: första raden vars gräns räcker till.
- `hours(base, quantity, supplements, deviation_pct)` — Timmar för en post, och varje steg dit.
- `catalogue()` — Hela normtidsunderlaget, som gränssnittet behöver det.

### `vvs_engine/output/artifacts.py`
Artifact writers: all per-drawing JSON / markdown outputs and the evidence graph.

- `drawing_profile(pa, doc)`
- `profile_report_md(prof, name)`
- `evidence_graph(pa)`
- `why(pa, pipe_id)`
- `unresolved_issues(pa)`
- `declined_geometry(pa)` — The drawn families the reading looked at and did not take, with their strokes and the reason.
- `document_quantities(sheets)` — The takeoff for the whole set, sheet by sheet and added up.
- `write_all(pdf_path, doc, analyses, out_dir, name, timings, determinism, contamination, overlays, config, review, sheets, doc_legend)`
- `physical_pipe_dict(m)`
- `performance_report(pa, timings)`
- `source_revision()`
- `analysis_report_md(pa, name, timings, determinism, contamination, files)`

### `vvs_engine/output/overlays.py`
Overlay PDFs drawn on top of the original drawing (actual geometry only; no synthetic rays).

- `OverlayWriter · add, replace, close` *(klass)* — The marked-up copies of the drawing, drawn a sheet at a time.
- `write_overlays(pdf_path, analyses, out_dir)` — analyses: list of PageAnalysis (one per analyzed page). Returns {name: path}.
- `identity_color(key)` — Deterministic colour per designation+DN. The hash is the one the viewer uses, so a pipe keeps its colour

### `vvs_engine/pdf/classify.py`
Input classification per page: clean vector, scanned (raster) or mixed.

- `InputClass · as_dict` *(klass)*
- `classify_page(page)` — `page` is a PyMuPDF page.

### `vvs_engine/pdf/extract.py`
Raw PDF forensics: one extraction pass per page.

- `RawPath · length, as_dict` *(klass)*
- `TextChar` *(klass)*
- `TextSpan · as_dict` *(klass)*
- `PageInfo` *(klass)*
- `RawPage` *(klass)*
- `LazyPages · release` *(klass)* — The document's readable pages, each built the first time it is asked for.
- `UnsupportedInputError` *(klass)* — The PDF carries no page the engine can read: every page is a scan, an image or empty.
- `RawDocument · inventory` *(klass)*
- `extract_document(pdf_path, pages, progress, eager)` — Read the vector content of every page: paths with their segments, layers, stroke widths and text spans.

### `vvs_engine/pipeline.py`
Pipeline orchestration: RAW PDF -> DrawingProfile -> annotations -> designations -> leaders -> attachments

- `PageAnalysis` *(klass)*
- `reached_labels(anchors, pipe_labels)` — The sheet's own pipe labels whose leader ended on the geometry they name.
- `reach_is_poor(families, anchors, pipe_labels)` — Whether the sheet's own labels found the geometry that was taken, whatever its layers are called.
- `label_reach_fails(families, anchors, pipe_labels)` — Whether a reading is poor enough to be thrown away entirely.
- `claimed_runs(anchors, ownership, graphs)` — The lines a label points at that no identity could take, and which labels point at them.
- `pen_key(family)` — A pen as an office draws it, with the sheet it happened to be drawn on taken off.
- `settle_bundles_by_sheet_consistency(anchors, graphs, known)` — The bundles a sheet cannot settle one at a time, settled by taking the sheet as a whole.
- `PreparedPage` *(klass)* — Everything about a sheet that can be worked out before anything is claimed about its pipes.
- `prepare_page(page, progress, ocr_assist, film)` — Read the sheet as far as its own words go, and no further.
- `analyze_page(page, progress, ocr_assist, film_sink, second_reader, known_families, known_legend, known_scale, prepared)` — second_reader: an optional transport for putting the reading's own open cases to a language model.
- `reading_coverage(pa)` — How much of what the sheet names the reading actually carried through to a metre.
- `summarize(pa)`

### `vvs_engine/pipes/ownership.py`
Physical pipe ownership.

- `Identity · key, compatible` *(klass)*
- `PrimState` *(klass)*
- `PhysicalPipe · length_pt` *(klass)*
- `OwnershipResult` *(klass)*
- `identity_of(a, dn_token_index)` — The identity an anchor's label names (see identity_from_text).
- `identity_from_text(text, dn, system_token, dn_token_index)` — The identity a label names: its designation without the dimension token, plus the dimension.
- `complete_identities(identities)` — What a label leaves out, read off the rest of the sheet - but only where the sheet says it once.
- `propagate(graphs, anchors, page, identities, spelled_out, declared, declared_max_pt)` — identities: anchor_id -> Identity (only anchors that are verified AND belong to pipe-designation families).

### `vvs_engine/pipes/representation.py`
Pipe representation discovery and fragment chaining.

- `SymbolIndex · covering` *(klass)* — The small drawn things of a page - valves, pumps, filters, markers - by place, built once per page.
- `page_symbols(page)` — The page's symbol index, built the first time it is asked for.
- `GraphTolerances` *(klass)* — Geometric precision the graph builder may assume of the source (exported vectors are exact).
- `graph_tolerances(page)`
- `Prim · a, b` *(klass)* — A straight primitive of a pipe-candidate family (one segment of a raw path).
- `Node · degree` *(klass)*
- `PipeGraph · neighbours` *(klass)*
- `RepresentationFamily · as_dict` *(klass)*
- `stroke_family(layer, width, color)` — A drawn line's family: the layer it is on, its stroke width, and its colour.
- `family_key(p)`
- `is_sheet_border(p, page)` — A few square-on segments ruled around nearly the whole sheet: the drawing's own border, never a pipe.
- `duplicate_overlaps(prims)` — Where the drawing drew the same line twice, and how much length that is.
- `figure_pieces(prims)` — (runs, figures): the strokes that go somewhere, and the knots that stand still and fill a box.
- `collect_prims(page, families, exclude_pids, figures_out)` — Primitives of the given families. exclude_pids drops individual paths - the leader lines of the drawing,
- `split_t_junctions(prims)` — An endpoint lying on the interior of another primitive of the same family is a proven T-contact
- `split_prims_at_points(prims, points, tol)` — Split primitives at drawn boundary points (tick marks of verified leaders) so that the boundary becomes a
- `build_graph(prims, family, tol, symbols)` — Nodes: shared endpoints (within TOUCH_TOL) incl. proven T-junctions. Then bridge collinear micro-gaps
- `chains(graph)` — Maximal degree-2 chains of primitives (deterministic order).
- `describe_family(fk, prims, graph)`

### `vvs_engine/profile/hatch.py`
Hatched areas (regions filled with regularly spaced parallel lines).

- `HatchFamily · as_dict` *(klass)*
- `discover_hatch(page, pipe_families)`
- `inside_hatch(fams, x, y)` — The point lies between two adjacent strokes of a hatch family (one on each side within 1.5 spacings).

### `vvs_engine/profile/layers.py`
CAD / vector structural family statistics (per layer, per style). Purely descriptive.

- `style_key(p)`
- `layer_tokens(layer)` — Split a layer name into structural tokens (separators: | - _ space $ . ,).
- `LayerStats · as_dict` *(klass)*
- `compute_layer_stats(page)`
- `width_classes(page)` — Distinct stroke widths sorted ascending (drawing-derived).

### `vvs_engine/reconcile.py`
Geometry conservation: RAW RELEVANT PIPE GEOMETRY = CONFIRMED + AMBIGUOUS + UNOWNED, no double counting.

- `reconcile(pa)`

### `vvs_engine/review/__init__.py`
Post-analysis review: independent agents that check the result instead of trusting it.


### `vvs_engine/review/agents.py`
Review agents.

- `Finding · as_dict` *(klass)*
- `run_review(pa, ocr, progress)` — Run every agent over a finished PageAnalysis. `ocr` enables the optional cross-check agent.

### `vvs_engine/review/judge.py`
The last word: what, out of everything the reading and its reviewers found, should actually change.

- `judge(model, proposals)` — Go through the reading and say what should happen to each open case.

### `vvs_engine/review/ocr_check.py`
Optional OCR second opinion over the rendered page.

- `ocr_words(page, dpi, progress, regions, budget_s, seen)` — Read the page with OCR. Returns (word, bbox in page points, confidence) in the page's display space.

### `vvs_engine/review/region.py`
What the vectors say about one place on the sheet.

- `explain_region(pa, bbox, page_index)` — Every drawn thing inside `bbox`, by what the reading made of it, and why there are no metres.

### `vvs_engine/review/vision.py`
Looking at the drawing, after having read it - to find what the reading missed, never to measure.

- `Finding · as_dict` *(klass)*
- `VisionReview · as_dict` *(klass)*
- `tiles(width, height, cols, rows)` — The page cut into named rectangles. The names are the only places a finding may be put.
- `grid_png(png, tl, dpi)` — The same view with the tiles drawn and named, so the eye and the vectors mean the same place.
- `render_page_png(page_doc, page_index, dpi, clip)` — The page as the eye would see it. Used for looking, never for measuring.
- `overlay_png(png, runs, dpi, colour)` — The same view with the reading's own confirmed runs drawn over it, so the two can be compared.
- `compose(pa, max_labels)` — What the reading claims, in words, so the eye is checking a stated answer rather than free-associating.
- `look(pa, page_doc, ask, dpi)` — Ask the eye about a page that has already been read. Without a transport, nothing is asked.
- `parse(raw, tl)` — Lines the eye wrote, kept only where they name one of the questions - and one of the tiles.

### `vvs_engine/routes.py`
Reading the same drawing by more than one route, and saying where the routes disagree.

- `Claim` *(klass)* — One route saying that one primitive belongs to one identity.
- `RouteReport` *(klass)*
- `writing_route(pa)` — Labels written along the run they name.
- `run_routes(pa)`
- `cross_check(pa, reports)` — Put the routes side by side, primitive by primitive, and say where they agree.
- `apply_routes(pa, reports)` — Let a second route add what the first missed, and let a disagreement take a run out of the quantity.
- `review(pa, cross)` — What the reading did not reach, and why - so nothing is missing quietly.

### `vvs_engine/rules.py`
Varje regel läsningen följer, samlad på ett ställe.

- `Rule · module, const, as_dict` *(klass)*
- `value(rule_id, default)` — What a rule stands at for the reading running on this thread.
- `using(overrides)` — Bind rule changes to one reading.
- `live_default(r)` — What the constant actually stands at in the code, so the register can be held against it.
- `catalogue(overrides)` — The whole register, as a reader of the drawing needs it rather than a reader of the code.

### `vvs_engine/semantics/annotation.py`
VVS annotation population: text lines -> annotation blocks (stacked rows + underlines/boxes) -> designations + DN.

- `one_reading_per_place(rows, report)` — En läsning per ställe på bladet.
- `merge_lines(rows, page)` — Merge rows sharing angle + baseline whose gap is <= 1.6 H into one line (words separated by a space).
- `row_span(r, d)` — Extent of a row along axis d, from glyph centers +- half glyph size (robust for rotated text).
- `FreeSeg` *(klass)*
- `free_segments(page, consumed_pids)`
- `BlockRow` *(klass)*
- `AnnotationBlock · unit_of_row, unit_for_point, boundary_points` *(klass)*
- `Designation · display_text, as_dict` *(klass)*
- `build_blocks(page, lines, free)` — Group lines into annotation blocks using stacking geometry and underline/box lines.
- `extract_designations(page, blocks)`

### `vvs_engine/semantics/astra.py`
A second reader for cases the drawing leaves genuinely open - bounded, verified, and never load-bearing.

- `Question · as_prompt` *(klass)* — One open case, with the only answers that may be given to it.
- `Answer · as_dict` *(klass)*
- `verify(q, raw)` — The only door an answer comes through. An answer that is not one of the candidates is not an answer.
- `settle(questions, ask)` — Ask, verify, and return only what survived verification.
- `Settlement · settled, as_dict` *(klass)* — What a round of second reading did, kept beside the reading rather than folded into it.
- `questions_for(anchors)` — One question per open attachment case, carrying only families the leader actually touched.
- `apply_answers(anchors, answers)` — Fold verified answers back in, checking each one against the reading a second time.

### `vvs_engine/semantics/attachment.py`
Leader endpoint -> physical pipe attachment and PipeCodeAnchors.

- `Contact · as_dict` *(klass)*
- `PipeCodeAnchor · pipe_prims, as_dict` *(klass)*
- `layer_system_tokens(page)` — Every layer-name token of the page shaped like a system code (letters then digits).
- `system_layer_rank(system_token, layer, spelled_out)` — The strongest statement the layer name makes about this system: (how exactly it names it, the token).
- `system_layer_match(system_token, layer, spelled_out)` — Return the matching layer token if the layer name structurally carries the designation's system token.
- `contact_points(ld)`
- `GeometryIndex · symbols_near, paths_near, hits` *(klass)* — Index over stroke segments of candidate (non-annotation) families.
- `family_of(p)`
- `leader_contacts(ld, gidx, pipe_families, all_paths)` — Contacts at each attachment point.
- `parallel_runs(contacts, paths)` — The contacts split into the distinct parallel runs they sit on, ordered across the bundle.
- `bundle_at(contacts, gidx, want, skip, paths)` — De parallella rören vid kontaktpunkten, när en etikett namnger fler än linjen råkade träffa.
- `resolve_block(block, rows, ld, contacts, system_tokens_in_drawing, spelled_out, paths, gidx)` — Map designation rows of a block to contacted vector-family groups (bijection required).

### `vvs_engine/semantics/declarations.py`
Vad bladet förklarar i ord om rör som ingen etikett når.

- `DeclaredPipe · text, as_dict` *(klass)*
- `Declarations · as_dict` *(klass)*
- `read_declarations(lines)` — The sheet's written rules for pipes it does not label: today the one about connection pipes.

### `vvs_engine/semantics/grammar.py`
Drawing-local VVS designation grammar.

- `char_class(c)`
- `strip_count_prefix(word)`
- `token_shape(tok)` — Shape of a token: A<alpha-run-length>D<digit-run-length> for prefix-letters-then-digits tokens.
- `compress_pattern(word)`
- `is_code_like(word)` — Structural test: letters AND digits present, only code characters, starts with a letter or a count prefix.
- `WordReading` *(klass)*
- `word_readings(glyphs)` — Enumerate alternative readings of a word over its twin-ambiguous glyphs (capped).
- `GrammarFamily` *(klass)*
- `DesignationGrammar · observe, typicality, nominal_tokens, choose, finalize, as_dict` *(klass)* — Drawing-local statistics of code-like word structures (patterns + token shapes).
- `split_tokens(word)`
- `dn_plausible(v)`

### `vvs_engine/semantics/leaders.py`
Actual CAD leader discovery.

- `Leader · length, n_bends, path_ids, as_dict` *(klass)*
- `annotation_layers(blocks)` — Drawing-derived annotation layer family: layers carrying underline/box frames of designation blocks
- `discover_leaders(page, blocks, free, marks, ann_layers, report)`
- `claim_rank(b, ep, ptype, f)` — How good this label's claim on a drawn line is. Lower is better; the whole tuple is compared in order.
- `leader_family(ld)`
- `leader_family_report(leaders)`

### `vvs_engine/semantics/legend.py`
The drawing's own designation list.

- `is_code_token(tok)` — A legend code, as opposed to a heading word.
- `code_matches(label, code)` — Whether a drawn label is this legend code.
- `LegendEntry · as_dict` *(klass)*
- `DrawingLegend · by_code, systems, code_for, role_of_head, names_a_pipe, components, names_a_component, bbox, as_dict` *(klass)*
- `densest_edge(xs, tol)` — The left edge that carries the most rows: the start of the narrow window holding the most of them.
- `read_legend(lines, designations)` — Find the sheet's designation list and read it.
- `adopt(legend)` — The same designation list, as it stands for a sheet that does not carry it.
- `merged(a, b)` — The set's vocabulary after reading one more of its sheets.
- `roles_of(legend)` — What each code was settled as, in the form another sheet of the set can be given it.
- `learn_roles(vocab, sheet)` — Carry back into the set's vocabulary what a sheet settled about its codes by using them.
- `role_from_words(description)` — Vad listan säger att koden är, eller None om den inte säger något om saken.
- `assign_roles(legend, designations, prior)` — Settle what each legend code is, from how the drawing uses it.

### `vvs_engine/takeoff/__init__.py`
Mängdning: den gemensamma mätmotorn och det som räknas ur den.


### `vvs_engine/takeoff/formulas.py`
Räknade kolumner i mängdtabellen, utan att någonsin köra användarens kod.

- `FormulaError` *(klass)* — Formeln går inte att läsa eller räkna, och kolumnen ska säga det i klartext.
- `referenced_names(expr)` — Vilka kolumner formeln läser.
- `evaluate(expr, values)` — Räkna en formel mot en rads värden.
- `order_of_evaluation(formulas, known)` — I vilken ordning formlerna kan räknas, så att den som läser en annan räknas efter den.
- `evaluate_all(formulas, values)` — Räkna alla formler i beroendeordning. En formel som inte går att räkna får sitt fel som text.

### `vvs_engine/takeoff/geometry.py`
Geometrin både CAD och PDF-mängdningen behöver, och ingenting mer.

- `length_of(points)` — Sträckans längd: summan av avstånden mellan punkterna, öppen kedja.
- `perimeter_of(points)` — Omkretsen av den slutna formen: sista punkten binds till den första.
- `signed_area(points)` — Skoformeln med tecken. Tecknet säger åt vilket håll ringen går, vilket hål och yttre kant skiljs på.
- `ring_area(points)` — Ytan av en ring, alltid positiv.
- `area_with_holes(outer, holes)` — Ytan innanför den yttre ringen minus hålen i den.
- `point_in_ring(pt, ring)` — Ligger punkten innanför ringen? Strålmetoden, med kanten räknad som innanför.
- `bbox(points)`
- `centroid(points)` — Formens tyngdpunkt: ytans om den har en, annars punkternas medelvärde.
- `angle_between(a, vertex, b)` — Vinkeln vid hörnet, i grader, mellan 0 och 180.

### `vvs_engine/takeoff/measure.py`
Mätmotorn: en form, en skala, ett mått.

- `ScaleError` *(klass)* — Skalan går inte att använda, och måttet ska inte låtsas om det.
- `convert(value, frm, to, power)` — Räkna om ett mått mellan enheter. power=2 för ytor, 3 för volymer.
- `Scale · ratio, from_ratio` *(klass)* — Hur många meter en punkt på pappret är, och varifrån det beskedet kommer.
- `scale_from_two_points(a, b, real_length, unit, source)` — Skalan ur en sträcka någon dragit över något vars mått hon vet.
- `Viewport · holds` *(klass)* — Ett område på sidan med en egen skala: detaljen i hörnet är inte i planens skala.
- `scale_at(pt, scale, viewports)` — Skalan som gäller där formen ligger, och namnet på den viewport som avgjorde det.
- `Measurement · as_dict` *(klass)* — Vad formen mätte, och hur talet kom fram.
- `measure(kind, points, scale)` — Mät en form.

### `vvs_engine/text/hershey.py`
Hershey stroke font loader (generic single-line CAD reference glyphs).

- `hershey_fonts()` — font name -> char -> stroke segments (y grows downward like PDF page space).

### `vvs_engine/text/model.py`
Text model shared between searchable PDF text and vector stroke/outline glyphs.

- `Glyph · cx, cy, h, w` *(klass)*
- `TextRow · cx, cy, as_dict` *(klass)*
- `make_row(page, glyphs, angle, source, layer, font, family)` — Build a row from glyphs already ordered in reading direction.
- `row_axes(angle)`
- `project(pt, axis)`

### `vvs_engine/text/ocr_assist.py`
OCR-assisted resolution of characters the stroke recogniser could not name.

- `resolve_unknown_glyphs(page, rows, min_conf, budget_s, progress, seen)` — Fill '?' glyphs from an OCR pass over the same page. Returns a report; rows are edited in place.

### `vvs_engine/text/postprocess.py`
Structural post-processing of recognized rows: letter/digit twin resolution inside homogeneous tokens.

- `resolve_twins(glyphs)`

### `vvs_engine/text/recognize.py`
Generic character recognition for vector glyphs.

- `rasterize_segments(segs, angle_deg)`
- `rasterize_segments_oriented(segs, angle_deg)` — Rasterize stroke segments into a GRID x GRID binary image after rotating by -angle (so text reads left->right).
- `rasterize_polygon_fill(segs, angle_deg)` — Rasterize closed outline contours (filled glyphs) with even-odd filling, then thin to a skeleton.
- `skeleton_orientation(img)` — Orientation bins of a skeleton image from local 5x5 neighbourhood PCA (deterministic).
- `zhang_suen(img)` — Deterministic Zhang-Suen thinning (vectorized).
- `count_holes(img)` — Number of enclosed background regions in a (dilated) binary image (vectorized border flood).
- `distance_transform(img)`
- `RefGlyph` *(klass)*
- `oriented_dts(img, omap)`
- `reference_alphabet(embedded)` — Reference shapes to recognise a drawn glyph against.
- `chamfer(img_a, dt_a, img_b, dt_b)`
- `FamilyResult` *(klass)*
- `family_fingerprint(img, aspect, size_class, has_diacritic)`
- `classify(img, aspect, holes, allow_lower, rel_height, has_diacritic, rel_size, omap, embedded)` — Score glyph against all reference glyphs (batched symmetric chamfer + capped aspect + hole penalties).
- `decide(char, score, alternatives)` — The character to use, and whether it was accepted on a relaxed rule.

### `vvs_engine/text/searchable.py`
Searchable PDF text -> TextRows (used directly; never OCR'd).

- `searchable_rows(page)` — Group spans into rows: same orientation, same baseline (within 0.35*size), contiguous along the reading axis.

### `vvs_engine/text/strokes.py`
Vector glyph assembly: raw stroke/outline paths -> connected components -> row clusters -> glyphs.

- `StrokeComponent · w, h, cx, cy` *(klass)*
- `GlyphCandidate · path_ids` *(klass)*
- `RowCluster` *(klass)*
- `build_components(page, max_diag, tol)` — Connected components of small stroke paths that touch at endpoints (same layer + style).
- `size_families(comps, min_count)` — Dominant glyph heights (pt): clusters (within 12 %) of the component-height histogram (per drawing).
- `cluster_rows(page, comps, H)` — Cluster glyph-sized components of one size family into rows and segment rows into glyphs.

### `vvs_engine/text/vector_text.py`
Vector glyph text: components -> size families -> rows -> glyph families -> characters -> TextRows.

- `Mark` *(klass)* — An isolated straight stroke (1-2 segments) on a glyph-carrying layer: a tick/marker candidate, not text.
- `VectorTextResult` *(klass)*
- `layer_vocabulary(page)` — The code-like words the file writes about itself.
- `vector_text_rows(page, timing, say)` — say: an optional line-by-line account of the rebuilding, for a reader watching it happen.

---

## 14. Alla moduler och funktioner: tjänsten

### `app/academy.py`
Akademin: var någon är, vad de klarat och vad de fått för det.

- `Award` *(klass)* — En utmärkelse och vad den kräver. Villkoret prövas mot vad som står i tabellen, aldrig mot vad klienten säger.
- `progress(user, db)` — Allt den inloggade har gjort, per kurs.
- `StepIn` *(klass)* — Ett steg någon gjort. Klienten säger vad som hände, servern avgör vad det är värt.
- `save_step(course, body, user, db)` — Skriv ned ett gjort steg, räkna om poängen och dela ut det som förtjänats.
- `awards(user, db)` — Alla utmärkelser som finns, och vilka av dem som är tagna. En låst utmärkelse säger vad som krävs.

### `app/admin.py`
Att driva tjänsten: vad som lästs, vem som läser, vad de betalar och vad de rättat.

- `overview(days, admin, db)` — Tjänsten på en sida.
- `timeline(days, admin, db)` — En rad per dygn: hur många läsningar, hur de gick, och hur mycket av bladen de kom igenom.
- `readings(limit, offset, status, q, admin, db)` — Varje läsning någon kört, med vem som körde den och vad den gav.
- `corrections(limit, offset, kind, user_id, admin, db)` — Varje rättelse en kund gjort, med situationen den gjordes i.
- `learning(admin, db)` — Vad rättelserna faktiskt lärt systemet - och vad de inte kan lära det.
- `rule_settings(admin, db)` — Varje regel något konto flyttat, med skälet och skärmbilden.
- `rule_shot(rule_id, user_id, admin, db)` — Skärmbilden någon lade vid en flyttad regel: fallet som fick dem att flytta den.
- `AccountIn` *(klass)*
- `attention(admin, db)` — Det som väntar på någon: misslyckade läsningar, en kö som växer, regler flera konton flyttat åt samma
- `system_health(admin, db)` — Vad som kör, och hur det mår: byggning, andra läsaren, kön, lagret, databasen. Bara fakta som går att
- `list_accounts(q, admin, db)`
- `create_account(body, admin, db)`
- `update_account(account_id, body, admin, db)`
- `MemberIn` *(klass)*
- `update_user(user_id, body, admin, db)`
- `PartnerIn` *(klass)*
- `list_partners(staff, db)` — Alla partners för en admin; sin egen rad för en partner.
- `create_partner(body, admin, db)`
- `update_partner(partner_id, body, admin, db)`
- `PayoutIn` *(klass)*
- `list_payouts(staff, db)`
- `create_payout(body, admin, db)`
- `DraftIn` *(klass)*
- `draft_payout(body, admin, db)` — Skapa en utbetalning ur den provision som faktiskt räknats fram.
- `settle_payout(payout_id, status, admin, db)`
- `NoteIn` *(klass)*
- `crm(account_id, open_only, admin, db)`
- `add_note(body, admin, db)`
- `close_note(note_id, done, admin, db)`
- `ContentIn` *(klass)*
- `list_content(admin, db)`
- `get_content(slug, admin, db)`
- `put_content(slug, body, publish, admin, db)` — Spara som utkast, eller publicera.
- `ExperimentIn` *(klass)*
- `list_experiments(admin, db)` — Varje prov med utfallet, och med intervallet runt utfallet.
- `create_experiment(body, admin, db)`
- `update_experiment(key, status, winner, admin, db)`
- `heatmap(path, days, cols, rows, admin, db)` — Var folk klickar på en sida, som ett rutnät av andelar.
- `paths(days, admin, db)` — Vilka sidor som alls har klick att titta på.
- `academy(admin, db)` — Hur långt folk kommer i akademin, och var de fastnar.

### `app/agent.py`
The agent that works against a finished reading.

- `run_turn(model, ask, question, selection, history, tools)` — One question, answered through the tools. Returns the words, the calls made and what to light up.

### `app/auth.py`
- `hash_password(p)`
- `verify_password(p, h)`
- `create_token(user)`
- `current_user(token, db)`
- `current_admin(user)` — The one gate the service side sits behind.
- `current_staff(user)` — A partner sees their own referrals and their own commission; an admin sees everyone's.
- `login_blocked(email, ip)` — Sekunder kvar av spärren, eller noll.
- `login_failed(email, ip)`
- `login_succeeded(email)`
- `verify_or_burn(password, stored_hash)` — Pröva lösenordet, och bränn lika lång tid när det inte finns något att pröva mot.

### `app/calc.py`
Kalkylen och anbudet: från mängd till pris.

- `build(rows, legend, assumptions, overrides)` — Kalkylen ur mängdraderna. Varje rad bär sina egna steg, så en krona går att spåra till en meter.
- `CalcIn` *(klass)*
- `underlag(job_id, user, db)` — Normtidsunderlaget och standardantagandena, så att gränssnittet kan visa vad som går att ställa in.
- `preview(job_id, body, user, db)`
- `save(job_id, body, user, db)` — Spara kalkylen: antagandena och valen. Talen räknas om ur läsningen varje gång - de är aldrig lagrade fakta.
- `latest(job_id, user, db)`
- `tender_meta(calc, meta)` — Det anbudet skriver i sitt huvud: parter, objekt, datum, giltighet, nummer.
- `tender_html(calc, meta)` — Anbudets kropp: samma tal som kalkylen, i en form en beställare läser. Inledning, specifikation rad för
- `tender_pdf(html_doc, calc, meta)` — Anbudet som PDF: kroppen flödad av Story, huvud, summering och fot ritade ovanpå.
- `tender_pages(pdf, dpi)` — Sidorna som PNG, för förhandsgranskningen i appen - samma dokument som skickas, inte en efterlikning.
- `anbud_html(job_id, user, db)` — Anbudet som HTML, för den som vill läsa det som text: samma kropp, huvudet skrivet i stället för ritat.
- `anbud_info(job_id, user, db)` — Hur många sidor anbudet har, så att förhandsgranskningen kan hämta dem en och en.
- `anbud_page(job_id, n, user, db)` — Sidan n av anbudet som bild: det dokument som skickas, inte en efterlikning av det.
- `anbud_pdf(job_id, user, db)`

### `app/config.py`
- `Settings · static_root` *(klass)*
- `demand_a_real_secret()` — Vägra starta i drift med den nyckel som står i källkoden.

### `app/db.py`
- `Base` *(klass)*
- `User` *(klass)*
- `Project` *(klass)*
- `ProjectAnalysis` *(klass)* — Projektet läst som en handling: vad varje blad är, vad som hör ihop, och vad som inte gick att avgöra.
- `DocumentOverride` *(klass)* — Vad en människa rättade om ett blad.
- `Drawing` *(klass)*
- `AnalysisJob` *(klass)*
- `Correction` *(klass)* — One thing a person changed about a reading.
- `RuleSetting` *(klass)* — A rule a person changed, and what they changed it to.
- `Role` *(klass)* — Vad ett konto får se. En medlem ser sitt eget; en admin ser tjänsten.
- `Account` *(klass)* — Kontot bakom en användare: företaget, planen, rabatten och vem som förde dem hit.
- `Partner` *(klass)* — En affiliate eller ambassadör: vem som värvar, vad kunden får och vad partnern får.
- `Payout` *(klass)* — En utbetalning till en partner, med perioden den avser.
- `CrmNote` *(klass)* — Vad som hänt med en kund: ett samtal, ett mejl, ett löfte, ett problem.
- `Content` *(klass)* — En text på webbplatsen, redigerad utan att koden byggs om.
- `Experiment` *(klass)* — Ett A/B-prov: två sätt att göra samma sak, och vilket som visade sig bättre.
- `Event` *(klass)* — En sak som hände i gränssnittet.
- `CourseProgress` *(klass)* — Var någon är i akademin: vilket steg i vilken kurs, och vad de fått för det.
- `Calibration` *(klass)* — Skalan någon mätt upp själv på ett blad.
- `DrawingViewport` *(klass)* — Ett område på en sida med en egen skala: detaljen i hörnet är inte i planens skala.
- `Space` *(klass)* — Ett ställe i bygget: hus, plan, rum, lägenhet - ritat som ett område på ett blad.
- `ToolPreset` *(klass)* — Ett verktyg mängdaren ställt in och vill ha kvar: lager, färg, djup, multiplikator, beteckning.
- `ServiceSetting` *(klass)* — Det tjänsten själv går efter, satt av en administratör: en flyttad regel, ett antagande.
- `Calculation` *(klass)* — Kalkylen för en läsning: antagandena och valen. Talen räknas om ur läsningen varje gång.
- `Markup` *(klass)* — Vad någon ritat själv ovanpå ritningen - mätt, markerat eller antecknat.
- `init_db()`
- `get_db()`

### `app/exports.py`
Exports: Excel, CSV, JSON, analysis report and marked PDF are produced from the frozen artifacts.

- `to_xlsx(result_dir, floor_height, include_hatched, rows, riser_source, markups)`
- `to_csv(result_dir, floor_height, include_hatched, rows, riser_source)`

### `app/jobs.py`
Background analysis jobs: a thread-pool worker executes the engine; stages reflect real pipeline stages.

- `second_reader_state()` — Whether a model may settle a case *during the measurement*, and the reason.
- `project_system_families(db, drawing)` — What the rest of this project's drawings have already stated: drawn family -> system.
- `project_legend(db, drawing)` — The designation list the rest of this project already read, for a drawing that carries none.
- `account_rules(db, drawing)` — The rules this account has moved, for the reading about to run.
- `run_job(job_id)`
- `submit(job_id)`

### `app/main.py`
- `health()`
- `api_health()`
- `version()` — What is running here, and what it can reach - answerable without logging in.
- `RegisterIn` *(klass)*
- `register(body, db)`
- `login(request, form, db)`
- `me(user)`
- `ProjectIn` *(klass)*
- `list_projects(user, db)`
- `create_project(body, user, db)`
- `get_project(project_id, user, db)`
- `delete_project(project_id, user, db)`
- `upload_drawing(...)`
- `get_drawing(drawing_id, user, db)`
- `drawing_file(drawing_id, user, db)`
- `delete_drawing(drawing_id, user, db)`
- `analyze(drawing_id, user, db)`
- `job_status(job_id, user, db)`
- `CorrectionIn` *(klass)*
- `list_corrections(drawing_id, user, db)`
- `add_correction(drawing_id, body, user, db)`
- `undo_correction(drawing_id, correction_id, user, db)`
- `materials(q, group, unit, limit, offset, user)` — Artiklar ur materialboken, sökta på benämning eller artikelnummer.
- `service_rules(db)` — Reglerna som flyttats för tjänsten: regel-id -> värde.
- `rules_catalogue(user, db)` — Every rule the reading follows, what it decides, and what it stands at for this service.
- `set_rule(rule_id, body, admin, db)` — Move one rule for the service, or put it back.
- `read_settings(user, db)` — Antagandena mängden räknas ihop med: våningshöjd för stigare, var stigare räknas ifrån, om rör i
- `run_setting(db, key)` — Vad tjänsten kör, med installationens miljö som utgångsläge.
- `write_settings(body, admin, db)` — Ändra antagandena för tjänsten. Ett värde utanför vad det kan betyda avvisas, aldrig klipps.
- `my_lessons(user, db)` — What this account's corrections have taught, and how often each answer was given.
- `job_film(job_id, user, db)` — What each stage of the reading found, as far as it has got. Available while the job is still running.
- `job_result(job_id, user, db)`
- `list_artifacts(job_id, user, db)`
- `get_artifact(job_id, name, user, db)`
- `job_judge(job_id, user, db)` — What, out of everything the reading and its reviewers found, should actually change.
- `AgentAsk` *(klass)*
- `agent_tools(user)` — The contract, so the interface can show what the agent is actually able to do.
- `ToolAsk` *(klass)*
- `agent_tool(job_id, body, user, db)` — Run one tool against this reading and say what it found, with no model in the way.
- `EditAsk` *(klass)*
- `agent_edit(job_id, body, user, db)` — Accept a change the agent proposed, and write it to the correction log.
- `agent_ask(job_id, body, user, db)` — Ask the agent about this reading.
- `vision_check(job_id, page, user, db)` — A second opinion by eye on a reading that is already finished.
- `why(job_id, pipe_id, user, db)`
- `export(job_id, fmt, floor_height, include_hatched, riser_source, user, db)`

### `app/markups.py`
Vad mängdaren själv ritar ovanpå ritningen.

- `MarkupIn` *(klass)*
- `MarkupPatch` *(klass)* — Det listan ändrar: ord om markeringen, aldrig dess geometri.
- `BulkPatch` *(klass)*
- `list_markups(drawing_id, page, all_pages, user, db)` — Markeringarna på ett blad, eller i hela handlingen.
- `add_markup(drawing_id, body, user, db)`
- `edit_markup(drawing_id, markup_id, body, user, db)`
- `patch_markup(drawing_id, markup_id, body, user, db)` — Ändra vad markeringen handlar om utan att röra det den mätte.
- `patch_many(drawing_id, body, user, db)` — Samma ändring på flera markeringar: tjugo frågor som är besvarade stängs i ett svep.
- `drop_markup(drawing_id, markup_id, user, db)` — Markeringen stryks men står kvar i lagret. Den som ritat tjugo sträckor och råkar ta bort en ska kunna
- `markups_csv(drawing_id, page, all_pages, user, db)` — Markeringslistan som en fil att öppna i Excel: en rad per markering, med måttet och vad det räknades på.
- `CalibrationIn` *(klass)*
- `read_calibration(drawing_id, page, user, db)`
- `set_calibration(drawing_id, body, user, db)` — Dra en linje över något vars längd är känd och skriv vad det är. Måtten på bladet räknas om direkt.
- `drop_calibration(drawing_id, page, user, db)` — Ta bort den uppmätta skalan: läsningens egen gäller igen.
- `PresetIn` *(klass)*
- `list_presets(user, db)`
- `add_preset(body, user, db)`
- `drop_preset(preset_id, user, db)`

### `app/projects_api.py`
Projektanalys: hela handlingen läst som en modell.

- `ModeIn` *(klass)*
- `set_mode(project_id, body, user, db)` — Vilken sorts analys projektet använder. Valet sparas på projektet och går att se senare.
- `get_mode(project_id, user, db)` — Vad projektet valt, och om det redan finns arbete gjort under valet.
- `run_project_analysis(analysis_id)` — Läs varje blad och bygg handlingen. Körs på jobbkön, som mängdningen.
- `changes(project_id, key, user, db)` — Ändringsregistret för ett versionspar. Nyckeln är parets egen, ur den senaste projektanalysen.
- `start_analysis(project_id, user, db)` — Starta projektanalysen. Körs på samma kö som mängdningen.
- `latest_analysis(project_id, user, db)`
- `ProjectAsk` *(klass)*
- `project_agent(project_id, body, user, db)` — Fråga hela handlingen. Modellen väljer verktyg, verktygen svarar ur det som lästs.
- `ProjectToolIn` *(klass)*
- `project_agent_tool(project_id, body, user, db)` — Ett verktyg rakt av, utan modell: de färdiga frågorna i panelen. Kan inte hitta på en siffra.
- `project_agent_tools(project_id, user, db)`
- `OverrideIn` *(klass)*
- `set_override(project_id, body, user, db)` — Rätta vad läsningen kom fram till om ett blad.
- `list_overrides(project_id, user, db)`

### `app/public.py`
Det gränssnittet skickar in, och det gränssnittet får ut utan att vara admin.

- `variant_for(key, session, split_b)` — Vilken sida av provet den här besökaren hamnar på.
- `active_experiments(session, db)` — Vilka prov som pågår och vad den här besökaren ska se av dem.
- `EventIn` *(klass)*
- `EventsIn` *(klass)*
- `post_events(body, request, db)` — Ta emot vad som hände. Aldrig mer än ett samlat knippe åt gången, och aldrig något okänt.
- `published(slug, db)` — Den publicerade texten för en sida. Ett utkast syns aldrig här.
- `my_role(user)` — Vad den inloggade får se. Gränssnittet visar admin-länken efter det här och inget annat.

### `app/storage.py`
File storage abstraction: local filesystem now; the same interface can back an object store (S3-compatible).

- `Storage · put, path, exists, open, list, delete_prefix` *(klass)*
- `LocalStorage · put, path, exists, open, list, delete_prefix` *(klass)*

---

## 15. Gränssnittets filer

### Sidor

- `src/pages/Admin.tsx` — Att driva tjänsten.  
  exporterar: AdminPage
- `src/pages/Analysis.tsx` — private window */ }  
  exporterar: AnalysisPage
- `src/pages/CalcPage.tsx` — Kalkylen: från mängd till pris, och anbudet. En egen sida, för det är ett eget arbete.  
  exporterar: CalcPage
- `src/pages/Docs.tsx` — —  
  exporterar: Docs
- `src/pages/Drawing.tsx` — Whether anything on the page is still moving. A list of finished readings does not change on its own. */  
  exporterar: DrawingPage
- `src/pages/Landing.tsx` — The drawing in the hero is the product's own subject: a dash-dot waste run with a branch, two labels on  
  exporterar: Landing
- `src/pages/LearnPage.tsx` — The academy as a page of its own, so it is a place in the product and not only something to do while waiting. */  
  exporterar: LearnPage
- `src/pages/Login.tsx` — The same run as on the front page, drawn small: a labelled pipe and one the drawing does not name. */  
  exporterar: Login
- `src/pages/Material.tsx` — Materialboken.  
  exporterar: MaterialPage
- `src/pages/Project.tsx` — En ritning i taget svarar med meter. Hela handlingen svarar med vad den består av. */}  
  exporterar: ProjectPage
- `src/pages/ProjectAnalysis.tsx` — Projektet läst som en handling.  
  exporterar: ModeChooser, ProjectAnalysisPage
- `src/pages/Projects.tsx` — —  
  exporterar: Projects
- `src/pages/Cad.tsx` — Granskningsrummet: handlingen, frågorna på den, och listan man arbetar i.  
  exporterar: ReviewPage
- `src/pages/CadPick.tsx` — Vilken handling ska öppnas i CAD-rummet? Ritningarna, och en väg att lägga upp en ny.  
  exporterar: ReviewPickPage
- `src/pages/Takeoff.tsx` — Mängda för hand: mät, räkna och markera direkt på bladet.  
  exporterar: TakeoffPage
- `src/pages/TakeoffPick.tsx` — Vilket blad ska mängdas? Projekten och deras ritningar, med den senaste först. */  
  exporterar: TakeoffPickPage

### Komponenter

- `src/components/AcademySection.tsx` — The academy, on the front page, because it is part of what the product is and not a waiting-room toy.  
  exporterar: AcademySection
- `src/components/AdminBusiness.tsx` — Företagets halva av administrationen: konton, partners, provision, kundvård, innehåll, prov och heatmaps.  
  exporterar: Accounts, Partners, Crm, Content, Experiments, Heatmap
- `src/components/AdminReading.tsx` — Läsningens halva av administrationen: vad som lästs, vad kunderna rättat, och vad rättelserna lärt.  
  exporterar: Readings, Corrections, Learning, RulesMoved
- `src/components/AdminRules.tsx` — Reglerna läsningen följer, öppna för den som driver tjänsten.  
  exporterar: RulesCatalogue
- `src/components/AdminSettings.tsx` — Antagandena mängden räknas ihop med. Inte regler för hur ritningen läses, utan för hur det lästa blir en  
  exporterar: Assumptions
- `src/components/AdminSystem.tsx` — Vad som kör och hur det mår: bara fakta som går att kontrollera. En läsning är bara kontrollerbar om man kan  
  exporterar: SystemHealth
- `src/components/AgentChat.tsx` — The agent, working against the reading rather than against a picture of it.  
  exporterar: AgentChat
- `src/components/AgentShowcase.tsx` — The agent, shown as what it is: a conversation whose every number came out of the drawing.  
  exporterar: AgentShowcase
- `src/components/AnalysisCompletionReveal.tsx` — Resultatet avslöjas när det finns.  
  exporterar: EngineStatus, AnalysisCompletionReveal
- `src/components/AnalysisFilm.tsx` — One colour per identity, stable across frames, so a run keeps its colour as the reading fills in. */  
  exporterar: AnalysisFilm
- `src/components/AnalysisGateAnimation.tsx` — Portarna som öppnar sig när läsningen är klar.  
  exporterar: AnalysisGateAnimation
- `src/components/Boundary.tsx` — En vit sida är det sämsta ett fel kan göra.  
  exporterar: Boundary
- `src/components/Corrections.tsx` — hashed on the identity key, the same string the run on the sheet and the table hash, so the  
  exporterar: Draft, Corrections
- `src/components/Drawing3DControls.tsx` — Kamerans knappar. Egen komponent, för vyn ska kunna byta renderare utan att knapparna skrivs om. */  
  exporterar: ViewName, Drawing3DControls
- `src/components/Drawing3DView.tsx` — Ritningen som byggnad.  
  exporterar: Drawing3DView
- `src/components/DrawingTo3DTransition.tsx` — Övergången från plan till byggnad.  
  exporterar: DrawingTo3DTransition
- `src/components/EvidenceSection.tsx` — What the reading leaves behind, drawn rather than listed.  
  exporterar: EvidenceSection
- `src/components/LandingScene.tsx` — The stages the scene walks through as the reader scrolls, in the order the engine does them. */  
  exporterar: LandingScene
- `src/components/LayerStack.tsx` — The three layers a reading actually works in, as three planes that come apart.  
  exporterar: LayerStack
- `src/components/Learn.tsx` — VVS-akademin.  
  exporterar: Exercise, Learn
- `src/components/LearnExercises.tsx` — Övningarna.  
  exporterar: LearnExercise, EXERCISE_IDS
- `src/components/LearnFigures.tsx` — Levande infografik för akademin.  
  exporterar: LearnFigure, FIGURE_IDS
- `src/components/LearnWizard.tsx` — Akademin som en guide ovanpå det man höll på med.  
  exporterar: LearnWizard
- `src/components/LegendView.tsx` — The drawing's own designation list, and what the reading made of every line in it.  
  exporterar: LegendView
- `src/components/Markups.tsx` — Egna markeringar: mät, markera och anteckna direkt på ritningen.  
  exporterar: MarkTool, MarkDraft, Markups
- `src/components/MarkupsList.tsx` — Markeringslistan: allt någon ritat på handlingen, som en lista att arbeta i.  
  exporterar: MarkupRow, STATUSES, TOOL_LABEL, measureText, MarkupsList, sourceLabel
- `src/components/PdfViewer.tsx` — What a finished edit gesture produced: the line drawn, and what it does to the measurement. */  
  exporterar: Layer, EditKind, Drawn, InkVerdict, ViewerProps, cloudRadius, cloudPath, markupColor
- `src/components/ProjectAgentChat.tsx` — Projektagenten: frågor till hela handlingen.  
  exporterar: ProjectAgentChat
- `src/components/QuantityTable.tsx` — the takeoff has eleven columns and the panel beside a drawing is narrow: the table scrolls in its own  
  exporterar: identityKey, riserCount, withFloorHeight, QuantityTable
- `src/components/Reasoning.tsx` — How the reading got to its answer, from the first pass over the PDF to the last verdict.  
  exporterar: Reasoning
- `src/components/Status.tsx` — A stage may carry a detail after its name - "RESOLVING_UNREADABLE_TEXT ruta 3/7" - so a slow step can say where  
  exporterar: STAGE_LABELS, stageText, StatusBadge
- `src/components/StyleFan.tsx` — One method, not one template.  
  exporterar: StyleFan
- `src/components/Tilted.tsx` — A plane that leans towards the reader.  
  exporterar: Tilted
- `src/components/lp-motion.ts` — How far down the page we are, 0 to 1. One passive listener, read on the frame. */  
  exporterar: useScrollProgress, useInView, useSectionProgress, useCountUp
- `src/components/tilt.ts` — Depth, driven by where the reader actually is.  
  exporterar: Tilt, useTilt, tiltStyle, usePointerParallax, useStaggerIn

### Moduler

- `src/App.tsx` — private window */ }  
  exporterar: App
- `src/agents.ts` — Who does what in a reading, said once so the live film and the finished account never disagree.  
  exporterar: Agent, AGENTS, AGENT_SV, frameSays
- `src/api.ts` — The signed-in address, read out of the token the server issued. Display only - the server checks the token. */  
  exporterar: getToken, setToken, currentEmail, api, sessionKey, flushEvents, track, fileSize
- `src/learn.ts` — VVS-akademin: vad en mängdare behöver kunna, i delmoment som går att göra en i taget.  
  exporterar: Block, Quiz, Lesson, Module, MODULES, ALL_LESSONS, readProgress, syncProgress
- `src/legend.ts` — Bladets förklaringslista, som den läses på ritningen.  
  exporterar: LegendEntry, ROLE_COLOR, ROLE_LABEL, codeMatches, legendOwner
- `src/main.tsx` — —
- `src/palette.ts` — Färgerna en beteckning har i hela produkten.  
  exporterar: identityColor
- `src/vite-env.d.ts` — / <reference types="vite/client" />

### Tre dimensioner

- `src/three/model.ts` — Från ritningens läsning till en byggnad i tre dimensioner.  
  exporterar: Vec2, ModelPipe, ModelWall, BuildingModel, pipeRadius, isHatchFill, buildModel
