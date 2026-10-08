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
inbäddad bild, och några blad är mycket stora. Här kallas de handling A–D; namnen står inte i repot.

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

## 11. Fas 2a – genomförd: rum och ytor ur rumsetiketterna

**Rumsläsaren** (`engine/vvs_engine/abt/rooms.py`):
- En rumsetikett är raderna ovanpå en rad som slutar med en area. Raderna står i linje (vänsterkant eller mitt),
  är satta med samma penna (typsnitt och färg) i ungefär samma storlek och står utan lucka. Exempel:
  "1-1106 / FRD / 3 m²" eller "005 / 2 ROK, 1 PERS / 44 m²".
- Pennan håller isär installationens text och arkitektens bakgrund där de står ovanpå varandra i samma typsnitt.
  En rörbeteckning med ett känt systemnamn (KV, VV, VS …, ur motorns egen systemtabell) blir aldrig en rad i ett rum.
- Varje etikett ger nummer, namn eller lägenhetstyp ("N ROK", "N PERS") och arean som står skriven.
- En etikett som börjar med ett ytmått ur SS 21054 (BTA, BOA, LOA, BRA …) är en summa och räknas inte som rum.
- En sida vars etiketter står exakt som på en tidigare sida är samma plan och räknas en gång. Det står vid sidan, och
  användaren avgör.
- Samma rumsnummer med samma area på två sidor är ett rum. Rum utan nummer slås aldrig ihop.

**I produkten:**
- I ett ABT 06-projekt finns fliken Rum och ytor.
- Läsning per ritning, med priset visat först: bladpriset för sidorna med rum, gånger `rooms_factor` som admin kan
  ändra, draget en gång per ritning.
- Visas: rum, rumsarea, lägenheter och lägenhetsarea; lägenheter per typ; en sidtabell med räknas/räknas inte och
  samma plan som; rumslistan med källtyp RÄKNAD och var raden lästes.
- Export till CSV med källtyp och spårbarhet.
- Rummen lagras som `Space` (slag rum, lägenhet eller summa) och följer med när ritningen eller projektet tas bort.

**Prövat på tre av dina fyra handlingar** (lokalt, inget incheckat):

| Handling | Etiketter | Rum | Lägenheter per typ | Sidor som upprepar en annan |
|---|---|---|---|---|
| A | 431 | 386 | 6 × 3 ROK | 1 |
| B | 691 | 511 | 13 × 1 ROK, 7 × 2 ROK, 17 × 3 ROK, 3 × 4 ROK | 5 |
| C | 444 | 371 | 6 × 1 ROK, 48 × 2 ROK, 8 × 3 ROK, 11 × 5 ROK | 0 |

Handling D har inga rumsetiketter, eftersom dess planer saknar A-underlag med rum.

**Kända begränsningar:**
- Rummens polygoner läses inte än. Arean är den som står skriven, och någon kontroll mot geometrin görs inte.
- Två våningar som är ritade exakt likadant på samma plats på bladet ser ut som samma plan, och tvärtom. Därför
  avgör användaren per sida.
- Antalen är inte kontrollerade mot en handräkning. Det behövs några blad som du räknat själv.

## 12. Fas 2b – genomförd: enheter ur koderna vid inredningen

**Enhetsläsaren** (`engine/vvs_engine/abt/units.py`):
- Det mesta i badrum och kök ritas i förenklat ritsätt: en kontur och en kod bredvid. En enhet är en sådan kod:
  - två eller tre bokstäver, ensam på sin rad;
  - satt med samma penna som bladets rumsetiketter, alltså arkitektens;
  - inte en rad i en rumsetikett och inte ett ord som används som rumsnamn.
- Installationens text ("ANSL.DB+DM") räknas inte. Inte heller enstaka bokstäver, som oftast är axlar, blad eller
  konsulter.
- Samma kod skriven två gånger tätt intill varandra är en enhet.
- **Namnet tas, i den här ordningen,** från:
  1. det användaren angett;
  2. bladets förklaringslista – en tabell med kodkolumn och termkolumn, minst tre koder med fler än en bokstav,
     där minst hälften används på bladet; en namnrutas konsult- eller revisionslista är ingen förklaringslista;
  3. referensdatan för sanitetsinredning (TM Tvättmaskin, DM Diskmaskin, TS Tvättställ …).

  Annars är koden okänd. Ingen betydelse hittas på.

**I produkten:**
- Enheterna läses samtidigt som rummen, till samma pris.
- Varje enhet blir en räknemarkering på lagret "ABT enheter" i Mängda. Där kan den granskas, flyttas, avvisas eller
  tas bort, och då räknas den inte längre. En ny läsning ersätter bara läsarens egna markeringar.
- Fliken Enheter visar per kod: antal på de sidor som räknas, med (+N) för upprepade sidor, namnet och vem som gav
  det, och sidorna. Där kan du namnge en kod.
- Export till CSV med källtyp RÄKNAD.

**Prövat:**

| Handling | Enheter | Namngivna ur referensdatan |
|---|---|---|
| A | 265 | DM 26 |
| B | 623 | DM 69, TM 58, TS 4 |
| C | 189 | TM 6, SLH 1 |

- Handling B med upprepade sidor borträknade: 488 enheter i 22 koder.
- Handling D ritar sin inredning som symboler, utan koder. Dess förklaringslista ("DB Diskbänk", "VK Vattenklosett",
  "VVB Varmvattenbredare" …) läses korrekt och väntar på symbolräkningen.
- Stickprov på handling B sida 3 och 5 i webbläsaren: varje DM sitter vid diskmaskinen i köket, och TM och TT vid
  tvättmaskin och torktumlare.

**Kända begränsningar:**
- Koder som ingen förklarar (KPH, KL, AK, VS, KM …) räknas men heter okänd tills du namnger dem. Arkitektens egen
  förklaringslista finns inte i handlingarna.
- Handling B:s komponentlista är ritad som streck eller bild och läses inte som text.
- Koder med index (TS1, VK3, DB1, DM02) räknas inte. I handlingarna står de flesta med installationens penna och är
  VVS-konsultens beteckningar; med arkitektens penna finns ett fåtal (34 mot 138). Att räkna bara de senare skulle
  ge en ojämn räkning.
- Enheterna kopplas inte till rum än, eftersom rummens polygoner saknas.
- Antalen är inte kontrollerade mot en handräkning.

## 13. Fas 2c – genomförd: symboler, alltså block som upprepas

**Symbolläsaren** (`engine/vvs_engine/abt/symbols.py`):
- Ett CAD-block skrivs ut som en följd i ritningsströmmen: linjer med samma penna, tätt intill varandra. Läsaren
  delar strömmen i sådana följder och beskriver var och en med det som inte ändras när den vrids eller speglas:
  antal linjer, deras längder och hur långt ändarna ligger från mitten. Följder som är lika, på avrundningen när,
  är samma del av samma block.
- Ett block i flera pennor (kontur, skål, kran) blir flera följder. De står på samma ställe och direkt efter
  varandra i strömmen, nästan varje gång. Då slås de ihop till en symbol.
- Detta sorteras bort:
  - långa och tunna följder: väggar, fönster, streckade linjer;
  - vita masker bakom text;
  - bokstäver ritade som streck, alltså låga följder i samma penna på rad, en bokstavs bredd isär.
- **Namnet** kommer från en av två källor. Annars räknas gruppen inte, och ingen betydelse hittas på.
  1. Bladets egen symbolförklaring. Det är en tabell: symbolerna i en kolumn, namnen i en annan med samma penna,
     varje namn tätt intill sin symbol, raderna utan glapp, minst tre rader med en egen symbol och ett eget namn
     på varje. Exemplaret i förklaringen räknas inte.
  2. Användaren.
- Varje grupp behålls, också en som ritas bara en gång. Ett projekt levereras ofta som ett blad per PDF. Därför
  avgörs i hela projektet om en grupp utan namn ska visas: den behöver minst tre exemplar.
- Samma block får samma id i projektets alla ritningar. Ett namn gäller därför överallt, också ett namn ur en
  annan ritnings förklaring.

**I produkten:**
- Symbolerna läses samtidigt som rum och enheter. Läsningen sparas per ritning (`results/<id>/abt/`), så prisfrågan
  och läsningen delar den.
- Pris enligt beslutet "rum och symboler per A-blad": bladpriset för sidor där läsningen hittar rum, enheter eller
  minst tre exemplar av upprepade symboler. En ritning som redan är betald läses om utan kostnad.
- Fliken Symboler är ett galleri med en bild av varje grupp, antal exemplar och sidor:
  - grupper med namn står först och räknas;
  - övriga står med flest exemplar först;
  - du skriver vad en grupp är ("WC") och sparar.
- Varje exemplar av en namngiven grupp blir en räknemarkering på lagret "ABT symboler" i Mängda.
  - Markeringen kan granskas, flyttas, avvisas eller tas bort, och räknas då inte.
  - Ett nytt namn byter namn på markeringarna där de står.
  - Sidor som rumsläsaren tar som en upprepad plan räknas inte heller för symbolerna (+N).
- Export till CSV med källtyp RÄKNAD.

**Prövat:**
- **Syntetiska blad i CI:**
  - samma block rakt, vridet 90° och 37° och speglat blir en grupp;
  - ett block i två pennor blir en symbol;
  - förklaringen namnger och räknas inte själv;
  - väggar, streck och ord blir inga symboler;
  - samma id i två ritningar;
  - namnet ur den ena ritningens förklaring gäller i den andra.
- **Handling D** (21 sidor, inredningen ritad som symboler):
  - prisfrågan tar 30 s; själva läsningen tar sedan 3 s eftersom den är sparad;
  - 387 grupper med minst tre exemplar;
  - toaletter i två varianter (74 + 64) och tvättställ i tre (71 + 53 + 20);
  - stickprov på sida 9: markeringarna sitter på toaletterna och tvättställen.
- **Handling B:** bokstäver ritade som streck sorteras bort, så galleriet visar mest symboler.

**Kända begränsningar:**
- Samma föremål ritat på olika sätt blir olika grupper, till exempel en annan modell eller ett föremål delvis dolt
  bakom rör. Varje variant namnges för sig, och liknande grupper föreslås inte än.
- Många grupper är annat än inredning: dörrar, fönster, pelare, träd, rörsymboler. De räknas inte om de inte
  namnges, men de gör galleriet långt.
- Enheter ur koder och symboler räknas var för sig i flikarna Enheter och Symboler. I schablonunderlaget räknas
  ett exemplar som står där dess kod är skriven (koden själv, eller namnet koden har) som en enhet, inte två.
  Galleriet visar hur många exemplar det gäller.
- Symbolerna kopplas inte till rum än, eftersom rummens polygoner saknas.
- Antalen är inte kontrollerade mot en handräkning.

## 14. Fas 3 – strukturen genomförd: nyckeltal och schablonrader

Enligt beslutet "jag skickar egna nyckeltal" finns bara strukturen. Inga värden är ifyllda och inga branschvärden
hittas på. Biblioteket är tomt tills användaren lägger in sina egna.

**Nyckeltalen** (`backend/app/keyfigures.py`, tabellen `key_figures`):
- Ett nyckeltal har:
  - ett namn och en grund: per enhet eller per m²;
  - vad det gäller: en enhetskod (TM, VK …), ett symbolnamn ("WC") eller en lägenhetstyp ("2 ROK"); för m² en
    rumstyp, eller alla rum;
  - vad det ger: rader med system eller beteckning, mått (längd, antal, yta, volym), värde och en valfri artikel ur
    materialboken;
  - timmar per enhet eller m², och en källa i fritext (var värdet kommer ifrån).
- Biblioteket hör till företaget, eller till användaren om hon inte har något företag. Ingen annan ser det eller
  kan använda det.
- Ett nyckeltal är ett utkast tills någon bekräftar det, och ett utkast kan inte väljas för ett projekt. Ändras ett
  bekräftat nyckeltal blir det ett utkast igen och lämnar projektets rader tills det bekräftas på nytt.

**Schablonraderna:**
- En rad är underlaget gånger nyckeltalet:
  - räknade enheter (koder och namngivna symboler), lägenheter av en typ, eller m² av rummen;
  - allt räknat på de sidor som räknas.
- Raden räknas fram varje gång och lagras aldrig. Den visar sitt underlag ("2 st TM (koder)") och sin uträkning
  ("2 st × 2.5 m = 5 m").
- Riskpåslag:
  - per projekt, och en rad kan ha ett eget;
  - båda syns i raden och i exporten.
- En artikel ger raden materialbokens nettopris (pris × (1 − rabatt)) och en kostnad. Timmarna blir en egen rad.
- En symbol som står där dess kod är skriven är samma enhet som koden. Den räknas en gång när både koden och
  symbolen hör till ett nyckeltals underlag, och raden säger hur många det gällde.
- Export till CSV med källtyp SCHABLON och nyckeltalets källa.
- Det som lagras per projekt är bara besluten: valda nyckeltal, påslaget och radernas egna påslag
  (`project_estimates`).

**I produkten:**
- **Fliken Nyckeltal:** biblioteket med status. Där finns ett formulär med förslag ur projektets koder, symbolnamn,
  lägenhetstyper och rumsnamn, och sökning i materialboken. Där bekräftar du nyckeltal och väljer dem för projektet.
- **Fliken Schablon:** raderna med underlag, uträkning, påslag, artikel och kostnad, samt summor för timmar och
  materialkostnad.

**Prövat:** API-test med påhittade värden:
- ett utkast nekas;
- rader per enhet, per m² och per lägenhetstyp;
- projektets påslag och radens eget;
- nettopris och kostnad ur materialboken;
- ett ändrat nyckeltal blir utkast och lämnar raderna;
- ett annat konto ser inte biblioteket;
- ett borttaget nyckeltal lämnar projektet;
- felaktiga nyckeltal nekas.

**Prövat i webbläsaren** på handling B, lokalt och med ett påhittat nyckeltal:
- formuläret med artikelsök;
- att ett utkast inte går att välja, och att det sedan bekräftas och väljs för projektet;
- tre rader på 47 räknade TM (koder på sidor som räknas);
- påslaget 10 %;
- svenska, engelska och mobilbredd, utan konsolfel.

**Kvar i fas 3:**
- Dina nyckeltal, eller ditt ja till att härleda förslag ur de fyra projekten (avsnitt 9).
- Schablonraderna i kalkylens och anbudets dokument. I dag finns de som en egen lista och i CSV-exporten.
- Byggnadstyp används inte än som filter.
