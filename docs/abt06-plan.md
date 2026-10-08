# ABT 06 – totalentreprenad som eget projektläge

Steg 0 enligt uppdraget: föreslagen datamodell, UI-flöde, pipeline-ändringar, migreringar, risker och fasplan.
Ingen produktionskod är skriven för det här än. Planen är godkänd; varje fas avslutas med en sammanfattning och
väntar på underlag där det saknas.

**Det som gäller genom alla faser:** ett projekt i AB 04 – alla befintliga projekt – fungerar exakt som idag.
Läsningen, mängden och exporterna för AB 04 ändras inte, och golden-tester och korpusspärren visar det efter
varje fas.

## 1. Bakgrund

I en utförandeentreprenad (AB 04) mäter vi installationer som konsulten har ritat. I en totalentreprenad (ABT 06)
projekterar entreprenören själv, och förfrågningsunderlaget innehåller ofta inga ritade rör: A-ritningar med rum,
areor och sanitetssymboler, en rambeskrivning eller funktionsbeskrivning, ibland ett rumsfunktionsprogram och
principscheman. Kalkylatorn räknar då enheter och ytor och multiplicerar med egna nyckeltal, plus riskpåslag.

## 2. Nuläge – det ABT 06 bygger på

- **Projekt:** `db.Project` (namn, beskrivning, `analysis_mode`); skapas i `main.py` (`POST /api/projects`) och
  `pages/Projects.tsx`.
- **Rum:** `db.Space` finns redan (kind `rum`, code, name, polygon i `ring`, `props`), men skapas idag för hand.
- **Räknade saker:** `db.Markup` finns redan – verktyget `antal`, koppling till rum (`space_id`), källa,
  konfidens, granskningsstatus (`oppen`/`klar`/`avvisad`/`granskad`) och fritt `meta`.
- **Företag:** `db.Account`, med `users.account_id`.
- **Mängdraden:** motorns rader i meter (`measure/measure.py`) och markeringarna (m, m², m³, st) redovisas var för
  sig.
- **Katalog och kalkyl:** materialboken (global), `calc.py` med artikelval och Normtid VVS per kalkyl.
- **Exporter:** xlsx, csv, json, rapport, markerad pdf, kontroll-pdf. Wikells-export finns inte.
- **Credits:** pris per blad efter format och bläck; återbetalning när läsningen inte gav en enda meter.
- **Referensdata:** `reference_sources/swedish-vvs-drawings-main/data/sanitary_fixtures.json` (VK, TS, DK, DB,
  TM, UB …) och disciplinbokstaven i ritningsnumret (`vvs_engine/handling.py`).
- **Saknas helt:** rumsläsning ur A-planer, symbolräkning, nyckeltal, schablonrader, kravläsning ur text och en
  kalkyl på projektnivå.

## 3. Föreslagen datamodell (bakåtkompatibel – `''` betyder dagens beteende)

| Tabell / fält | Innehåll |
|---|---|
| `projects.contract_form VARCHAR(8) DEFAULT ''` | `''`/`AB04` = dagens flöde, `ABT06` = det nya. Byte i efterhand kräver bekräftelse i API:t och loggas. |
| `projects.discipline`, `drawings.discipline`, `analysis_jobs.discipline` | Disciplinvalet, se `docs/multi-discipline-plan.md`. |
| `drawings.flow VARCHAR(16) DEFAULT ''` | `''` = mätning (idag), `rum_symboler`, `kravtext`. Föreslås vid uppladdning; användaren bestämmer. |
| Rum → `spaces` (kind `rum`) | `props`: area_text_m2, area_geom_m2, area_source, confidence, state, evidence. |
| Symboler → `markups` (tool `antal`, source `symbol`) | confidence, status, space_id, `meta`: enhet, skäl, bbox, path-id. |
| Enhetsordlista (datafil) | Koder ur `sanitary_fixtures.json` plus golvbrunn och radiator ur referensdatan; utökningsbar per konto. |
| `key_figures` (ny) | konto (annars användare), namn, grund (per enhet / per m²), enhet, byggnadstyp, rumstyp, utfall `[{system/beteckning, artikel i materialboken, mättyp, värde, enhet}]`, timmar, status (utkast/bekräftad), källa. |
| `project_estimates` (ny) | Bara indata: riskpåslag per projekt och per post, valda nyckeltal. SCHABLON-raderna räknas fram vid läsning med proveniens (enheter × nyckeltal) – samma princip som `Calculation`. |
| `requirements` (ny) | projekt, dokument, sida, ordagrant utdrag, kategori, status (öppen/kopplad/hanterad), länkar, skapad av (ai/användare), `verified`. |
| **Källtyp** | UPPMÄTT (motorns rader), RÄKNAD (symboler och rum), SCHABLON (nyckeltal), MANUELL (manuella markeringar). Räknas fram i projektets samlade mängdvy; lagras aldrig i VVS-artefakterna. Visas och exporteras i ABT 06 och i nya discipliner; AB 04-exporterna är oförändrade. |

## 4. UI-flöde

- **Skapa projekt:** entreprenadform – **AB 04 – utförandeentreprenad** (förval; "vi mäter de ritade
  installationerna") eller **ABT 06 – totalentreprenad** ("du projekterar själv: vi räknar rum, ytor och
  enheter och kalkylerar med dina nyckeltal") – och därefter disciplin (VVS förvalt).
- **Projekthuvudet** visar entreprenadform och disciplin; byte går via en bekräftelsedialog.
- **Uppladdning i ABT 06:** per fil ett föreslaget flöde med skäl (ritningsnumrets disciplinbokstav, innehållet:
  rörbeteckningar, rum och areor, löptext). Användaren väljer. Mätflödet finns kvar för blad med ritade rör
  (hybrid).
- **ABT-vyn:** flikarna Rum, Symboler (granskningskö för osäkra), Nyckeltal, Schablon (proveniens och risk), Krav
  (checklista med sida och utdrag) och Kalkyl/Export. Varje rad har en synlig källtypsmärkning.

## 5. Pipeline-ändringar (AB 04: inga)

- **Klassning vid uppladdning:** billig textläsning som i `handling.py`, plus andelen rörbeteckningar på bladet.
- **Rumsläsare (vektortext först):** rumsnummer, rumsnamn och area-text samlas; polygonen tas från omslutande
  väggar när det går. Skalan verifieras innan någon area räknas ur geometri. Arean i ritningens text är
  förstahandskälla och den beräknade en kontroll; avvikelser flaggas.
- **Symbolräknare:** upprepade vektorgrupper (CAD-block, normaliserade för rotation, skala och spegling) klustras.
  En grupp får namn bara av bladets egen förklaring eller av användaren ("det här är WC"); därefter räknas alla
  identiska. Osäkra matchningar flaggas. Varje enhet kopplas till ett rum (punkt i polygon) och bär bbox och
  path-id.
- **Kravläsare:** textlagret (OCR via skannat-spåret för skannade dokument). AI-modellen extraherar kostnadsdrivande
  krav med obligatorisk hänvisning; servern kontrollerar att utdraget står ordagrant på den angivna sidan och
  flaggar det som inte kan styrkas. Inget krav påverkar kalkylen utan att användaren kopplar det.

## 6. Migreringar

- Kolumnerna `contract_form`, `discipline` och `flow` med `DEFAULT ''` via `_ADDED_COLUMNS`; de nya tabellerna via
  `create_all`. `''` betyder dagens beteende, så befintliga projekt är automatiskt AB 04 och VVS.
- Inga dataomskrivningar.

## 7. Credits (förslag – beslutas före implementation)

- Rum och symboler per A-blad: dagens bladpris (format och bläck).
- Textanalys: 1 credit per påbörjade 20 sidor.
- Återbetalning: när läsningen inte gav någon mängd av något slag (inga rum, inga antal, inga krav).
- Allt justerbart av administratören.

## 8. Risker

- **Symboler** ritas olika mellan kontor, och "exploderade" block saknar upprepning – reserv: användaren pekar ut
  en mall.
- **Rum** utan slutna polygoner; **area-text** i olika format.
- **AI-hallucination** i kravläsningen – spärras av den ordagranna kontrollen.
- **Nyckeltal** finns inte förrän användaren lämnar egna eller godkänner härledda; inga branschvärden hittas på.
- **Härledda nyckeltal** ur ett fåtal projekt är ett litet urval – visas med spridning och antal projekt.
- **Regression i AB 04** – spärras av golden-testerna.
- **Klientmaterial** – checkas aldrig in i det publika repot.

## 9. Testunderlag

Användaren har lämnat fyra handlingar från genomförda ABT 06-projekt (cirka 120 sidor; ligger lokalt, inte i
repot). Varje handling börjar med en handlingsförteckning, följd av VVS-planer ritade på A-underlag: rumsnamn,
rumsnummer och areor, lägenhetstyper, sanitetskoder och förklaringslistor. Några sidor har A-underlaget som
inbäddad bild, och några blad är mycket stora.

De används till:
1. **Fas 2** – rum, areor och enheter ur A-underlaget. Facit för areorna är ritningens egen text; antalen
   kontrolleras mot en handräkning på några blad.
2. **Fas 3 (förslag)** – nyckeltal härledda ur användarens egna projekt: meter uppmätta med VVS-motorn per system
   och dimension, delat med räknade enheter och m², med proveniens. Användaren godkänner, justerar eller ersätter
   med egna värden.
3. **QA och klassning** – flersidiga set (förteckning, plan, schema, detalj), mycket stora blad och blandade sidor.

**Saknas:** rambeskrivningar, funktionsbeskrivningar och RFP (fas 4), gärna även rena A-ritningar ur ett
förfrågningsunderlag.

## 10. Fasplan

**Fas 1 – projektläge och datamodell** (gemensam med disciplinerna)
1. Golden-tester före ändringarna (se `docs/multi-discipline-plan.md`).
2. `contract_form`, `discipline` och `flow` med `DEFAULT ''`; de nya tabellerna tomma.
3. API för att skapa och uppdatera projekt med entreprenadform och disciplin; byte kräver bekräftelse.
4. Valen i "Skapa projekt" med en kort förklaring av skillnaden, märken i projekthuvudet. ABT-flikarna visas som
   "under uppbyggnad".
5. Källtyp i den generiska radmodellen; AB 04-exporterna oförändrade.

**Fas 2 – A-ritningar: rum och symboler.** Rumsläsaren, symbolräknaren och granskningsgränssnittet (bekräfta,
rätta, lägg till, ta bort) på `Space` och `Markup`. Varje räknad enhet spårbar till sin plats på bladet; osäkra
markeras som tvetydiga med skäl.

**Fas 3 – nyckeltal och schablon.** Nyckeltalsbibliotek per företag kopplat till materialboken (per enhet eller
per m², eventuellt per byggnadstyp och rumstyp). SCHABLON-rader = räknade enheter × nyckeltal, där varje rad
visar sina enheter och sitt nyckeltal. Riskpåslag per projekt och per post, synligt i kalkylen och exporten.

**Fas 4 – rambeskrivning.** Uppladdning av rambeskrivning, funktionsbeskrivning eller RFP; kostnadsdrivande krav
(material, isolering, golvvärme, mätare, ljud, energi, beställarens tekniska krav) som en checklista med sida och
utdrag. Användaren kopplar en kravpunkt till nyckeltal eller rader, eller markerar den som hanterad.

Varje fas: små commits med tester, AB 04-regressionen körd, och en sammanfattning med vad som ändrats,
testresultat, kända begränsningar och vad nästa fas behöver.
