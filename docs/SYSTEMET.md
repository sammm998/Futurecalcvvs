# Så fungerar systemet

Det här är dokumentet man läser för att förstå vad VVS Mängdning gör, hur det gör det, vilka AI-modeller som
används och exakt var, och vad det aldrig gör. Det är skrivet efter koden, inte före den: varje påstående går
att slå upp i den fil som nämns.

Kompletterande dokument: `ARCHITECTURE.md` (läsvägen steg för steg), `ANALYSARKITEKTUR.md` (vad som bär och
brister, med mätningar), `LATHUND.md` (mängdningsstandarden och vad av den som är genomfört), `LIMITATIONS.md`
(kända begränsningar), `RORTYPER.md`, `FLERVAGSANALYS.md`.

---

## 1. Principen

En mängd finns bara där ritningen själv pekar.

Systemet läser en ritnings egna vektorer - linjerna CAD-programmet skrev in i PDF:en - och bygger identitet
bara där tre saker möts: en beteckning bladet skriver, en ritad hänvisningslinje från den, och den graf
geometrin bildar. **Aldrig närhet.** Ett rör som ligger nära en etikett men som ingen linje pekar på får inget
namn. Det redovisas som *onämnt* - med sina meter - i stället för att gissas.

Därför är `AMBIGUOUS` ett giltigt svar. Två etiketter som båda kan äga en sträcka ger en tvetydig sträcka, inte
en gissning. Fel säkerhet är värre än ett saknat svar, för ett saknat svar syns och ett felaktigt gör det inte.

Allt upptäcks per ritning. Vilken penna som ritar rör, hur beteckningarna är byggda, vilken skala bladet har,
vilka lager som är text - ingenting av det är inställt i förväg. Två kontor ritar olika, och systemet läser
varje blad på bladets egna villkor.

---

## 2. Vad som händer med en ritning

Läsvägen, i den ordning den körs (`engine/vvs_engine/pipeline.py`):

| Steg | Vad | Var |
|---|---|---|
| 1 | **Extraktion.** PDF:ens vektorobjekt läses råa: linjer, kurvor (plattade), transformationer, XObjects, lager (OCG), sökbar text. Annotationer - någons påskrift ovanpå ritningen, till exempel en Bluebeam-mängdning - läggs åt sidan och redovisas för sig; de är aldrig det ritaren ritade. | `pdf/extract.py` |
| 2 | **Text.** Sökbar text läses som text. CAD-text som exporterats som streck (SHX-typsnitt) sätts ihop till tecken av streckens form, mot generiska referensalfabet. Ett tecken som inte går att läsa blir `?` - det repareras aldrig ur ett förväntat ord. | `text/` |
| 3 | **Beteckningar.** Textrader blir block, block blir etiketter. Grammatiken - hur det här kontoret bygger sina koder (system, material, dimension, kvalificerare) - upptäcks ur bladets egna etiketter och dess beteckningslista. | `semantics/annotation.py`, `semantics/grammar.py`, `semantics/legend.py` |
| 4 | **Hänvisningslinjer.** Från varje etiketts kant följs de ritade linjerna ut i bladet: raka, böjda, delade. En etikett utan linje pekar inte på något. | `semantics/leaders.py` |
| 5 | **Vilka pennor ritar rör.** Linjernas ändar röstar på de familjer (lager + penna) de rör vid. En familj blir rörgeometri bara om den är kedjelik och har stöd - lagernamnet bär systemets kod, markeringsstreck, eller tillräckligt många etiketter. Läsningen körs två gånger: först obegränsat, sedan med de pennor som visade sig vara *skrivpennor* undantagna. Bladets egna etiketter avgör vilken läsning som står. | `pipeline.py` |
| 6 | **Kontakt.** Var linjen möter röret: direkt, via ett markeringsstreck, via en symbol (stigare, brunn), via en samlingslinje - ett kort streck på skrivpennan som samlar flera etiketter ned till ett rör. | `semantics/attachment.py` |
| 7 | **Topologi.** Rörgeometrin blir en graf: mikroglapp överbryggas, T-korsningar delas, och en korsning är inte en anslutning - en linje som passerar går in på ena sidan av noden och ut på den andra. | `pipes/representation.py` |
| 8 | **Ägande.** Varje kedja i grafen får en identitet från de etiketter som når den, eller står som tvetydig eller onämnd. Dimensionsbyten sätts bara vid ritade markeringsstreck. En stump kortare än kontakttoleransen bär aldrig ett namn vidare. | `pipes/ownership.py` |
| 9 | **Skala och mått.** Skalan läses ur skaltexten och verifieras mot den ritade skalstocken; skiljer de sig är det en konflikt och inte ett medelvärde. Horisontella meter mäts längs geometrin. Vertikala meter finns bara med uttryckligt stöd - en våningshöjd användaren anger, eller höjdangivelser på bladet. | `measure/` |
| 10 | **Avstämning och artefakter.** Allt bladet ritade summeras: mätt, tvetydigt, påpekat men onämnt, onämnt, bortvalt. Summan ska stämma med det ritade, och avvikelsen redovisas i stället för att justeras bort. Allt skrivs som filer så att varje meter går att spåra bakåt (`why`). | `reconcile.py`, `output/` |

Efter mätningen kommer **granskningen** (`review/`): agenter som frågar om resultatet är trovärdigt - är det
ritade röret redovisat, finns bladets alla beteckningar i mängdtabellen, är längder och dimensioner fysiskt
rimliga, hänger nätet ihop, håller skalan. De ändrar ingenting; en granskning som kunde ändra resultatet skulle
dölja den oenighet den finns för att visa. En **domare** (`review/judge.py`) går igenom fynden och säger vad som
ska hända - utan modell, ur artefakterna, så samma läsning dömd två gånger ger samma domar.

**Determinism.** Samma blad läst två gånger ger samma signatur, och ett blad läst mellan två andra påverkas inte
av dem. Det prövas (`determinism.py`) och det gäller så länge ingen andra läsare kopplas in (se §3).

**Kontamineringsbrandväggen.** Produktionskoden får inte läsa facit eller referensritningar, och innehåller inga
ritningsspecifika literaler. Det skannas (`contamination.py`) och står som `PASS` i varje läsnings sammanfattning.

---

### 2b. Vad bladet förklarar i ord

En ritning kan säga en sak om rör utan att skriva den vid varje rör. Ett helt projekt skriver på varje blad
*"Kopplingsledningar från fördelare till apparat enligt tabell om inget annat anges"* och en tabell med
beteckningsstammen per system (VV01-X31, KV01-X31) och dimensionen per apparat (16), och drar sedan nittio korta
rör från fördelarskåpen till blandare, tvättställ och toaletter utan en enda etikett. Läsningen, som bara följer
hänvisningslinjer, ägde inget av det - fjortonhundra meter på trettiotre blad.

`semantics/declarations.py` läser den regeln av form och av ritspråkets få ord för den (ett stycke som nämner
kopplingsledningar och säger "enligt tabell" eller "om inget annat anges", och under det en rad stammar med
talkolumner). Ägandet (`pipes/ownership.py`) tillämpar den sist av allt och bara på geometri som ingen annan
läsning rört: en primitiv som är **oägd** - aldrig tvetydig, aldrig en som en etikett nått - på en penna vars
lagernamn bär det förklarade systemet får den förklarade identiteten. Ett lager som två förklarade system skulle
kunna heta får inget. Varje sådan meter märks `DECLARED_CONNECTION_PIPE_BY_SHEET_TABLE` och redovisas som
`declared_m` på mängdraden, med `label_count` 0, så att en människa ser skillnaden på ett rör som pekats ut och
ett rör som förklarats. Regeln som lästes skrivs till `drawing-declarations.json`.

Det är inget närmaste-antagande: det är ritningens egen regel, skriven i ord, för exakt de rör ritaren inte
namngett. Utan tabellen ägs ingenting. Och regeln namnger kopplingsledningar, som är korta: en onämnd,
sammanhängande sträcka längre än `pipes.ownership.DECLARED_RUN_MAX_M` (15 m) på den förklarade pennan är en stam
vars etikett läsningen inte nådde, och den står kvar som onämnd i stället för att döpas efter tabellen.

### 2c. Vad som är ett rör: streck-prick, ventiler, dubbellinjer

Tre ritkonventioner som läsningen läser som geometri, inte som antaganden (`pipes/representation.py`,
`measure/measure.py`):

* **Streck-prick-linjen** är ett rör. Pricken är en och en halv punkt lång och exportens avrundning vrider den
  några grader, så den har ingen riktning att lita på; strecket vars stråle den ligger på gör anspråk på den
  (`DOT_MAX`), på geometrin ensam - en prick inom `DOT_GAP_MAX` på strålen hör till linjen oavsett om pennan
  ritar nog många prickar för att springan ska bli ett mönster. Då är springan streck-till-prick en springa av
  linjens stil och bryggas, även där en prick saknas och även i en svag knäck. Utan regeln blev nittio meter
  värmeledning tvåhundrafyrtiosju bitar.
* **En ventil i linjen** avslutar inte röret. Ritaren drar röret fram till ventilsymbolen, ritar ventilen med
  symbolpennan och drar vidare på andra sidan. Två fria, kollineära ändar med en liten symbol av en annan
  penna i springan (`SYMBOL_SPAN`, `SYMBOL_SIZE`) hör ihop: bryggan heter `symbol` i grafen och bär symbolens
  id.
* **En skrafferad figur** är inget rör. En radiator ritas som en tunn rektangel fylld med ett par dussin
  skrafferstreck, på en penna för sig, och den pennan vägdes som rör: varje hänvisningslinje som gick förbi en
  radiator fick en andra kandidatfamilj, ankaret blev tvetydigt, och metrarna på det riktiga röret gick till
  ingen. En knut av streck vars bläck är mer än `pipes.representation.FIGURE_INK` (6) gånger sin egen
  utsträckning står still och fyller sin ruta: den sätts åt sidan innan någon graf byggs och redovisas som
  avvisad med skälet `DRAWN_FIGURE_NOT_A_RUN`, med strecken kvar att titta på. Mätt över korpusen ligger
  rörpennor på 0,8-2,9 och skrafferade radiatorer på 8,8-15,7.
* **Ett rör ritat som två linjer** är ett rör. Ett grövre rör ritas som sina två kanter, ytterdiametern isär i
  bladets skala, och etiketten med ett streck på var kant namnger båda. Två sträckor med samma namn och samma
  penna sida vid sida längs större delen av den kortare, på det avstånd rörets diameter ger (1,6 × dy i skala,
  aldrig över `measure.measure.DOUBLE_LINE_MAX`), räknas en gång: den längre kanten bär metrarna, den andra
  redovisas som `double_line_m` på raden och i exporten. Avståndet följer dimensionen av ett skäl: ett DN16-rör
  är en punkt brett i 1:50 och kan inte ritas som två kanter, så två DN16-linjer några punkter isär är två
  kopplingsledningar i en bunt - och båda räknas. Utan känd dimension eller skala viks ingenting.

## 3. Vilka AI-modeller som används, och exakt hur

Det här är det viktigaste avsnittet att läsa rätt, så det är rakt.

**Mätningen använder ingen språkmodell.** Varje meter i mängdtabellen kommer ur geometri, hänvisningslinjer och
regler i Python. Ingenting i mätvägen når nätverket. Det är vad som gör läsningen deterministisk och möjlig att
spåra.

Det finns fyra ställen där en modell *kan* kopplas in, alla utanför mätvägen, alla avstängda utan nyckel, och
ingen av dem kan hitta på en meter:

### 3.1 Andra läsaren (`semantics/astra.py`, transport i `engine/tools/astra_transport.py`)

*Modell:* OpenAI, standard `gpt-6-astra` (miljövariabeln `VVS_SECOND_READER_MODEL`), via Responses-API:et.

*När:* bara för ett fall som motorn själv redan förklarat tvetydigt, och bara där ritningen erbjuder en kort
lista av verkliga kandidater. Frågan bär kandidaterna. Svaret måste vara en av dem, tecken för tecken -
`verify` vägrar allt annat. Modellen kan alltså aldrig namnge ett rör, en penna, en dimension eller en meter som
läsningen inte redan lagt fram; den kan bara göra `AMBIGUOUS` till ett av svaren som redan låg på bordet.

*Bevis:* varje avgjort fall skriver ned att en modell valde, mellan vilka kandidater och varför, så att en
läsare kan se det och säga emot.

*Av/på:* av utan `OPENAI_API_KEY`. Med nyckel: på. `VVS_SECOND_READER=false` stänger av oavsett; `true` tvingar
på bakom en proxy som fäster referensen. En läsning som rådfrågat den säger det, och påstår då inte
determinism.

### 3.2 Agenten (`backend/app/agent.py`, verktygen i `engine/vvs_engine/agent/tools.py`)

*Modell:* samma transport och modell som ovan (`agent_transport`).

*Delningen:* modellen bestämmer **vad** som ska frågas, verktygen bestämmer **vad svaret är**. Modellen ser
verktygens namn och deras svar - aldrig geometri den kunde hitta på ur. Varje siffra i chatten kommer ur ett
verktygsanrop över de artefakter mätningen skrev, så ett svar i chatten och en rad i mängdtabellen kan inte
skilja sig åt. 26 verktyg för en ritning (mängda, hitta rör, följ nätet, varför äger det här röret sina meter,
vad togs inte som rör, och fem `foresla_`-verktyg som bara föreslår), 8 för hela handlingen (projektagenten, `agent/project_tools.py`: hus, blad,
mängder per hus, versioner, ändringar, vad som bör tittas på).

*Förslag är ord.* Verktyg som föreslår en rättelse skriver ingenting: de säger vilken rättelse de skulle skriva
och vad läsningen säger att den kostar. Först när en människa godkänner körs samma anrop igen på servern, och
det som kommer ut är det som skrivs - metrarna i loggen är läsningens, aldrig modellens.

*De färdiga frågorna* i panelen går rakt in i verktygen utan modell. De kan inte hitta på en siffra. Fritext
behöver modellen för att välja verktyg; det är hela skillnaden.

### 3.3 Vision (`review/vision.py`)

*Modell:* samma, med bilder (`vision_transport`). Sidan renderas som bild, rutas in, och modellen får se den
tillsammans med läsningens egna sträckor ritade ovanpå.

*Vad den får göra:* titta och säga. Fynden är ord: "här ser det ut som om..." De kan aldrig bli geometri -
`vision.look` har ingen väg in i en läsning. Risken är kostnad och tid, aldrig en fel meter.

### 3.4 OCR (`review/ocr_check.py`) - ingen språkmodell

`rapidocr-onnxruntime`, en lokal teckenigenkännare. Två användningar: som en oberoende andra läsning av bladets
text i granskningen (finns det beteckningar vektorläsningen missade?), och för att namnge de tecken
streckigenkännaren inte kunde. Den läser aldrig ritningen på egen hand; vektorgeometrin förblir mätningens källa.

**Båda är avstängda som standard, och det är mätt.** Samma blad kört med och utan:

| blad | allt på | utan OCR-korsprov | utan teckenhjälp | ändrad mängd |
|---|---:|---:|---:|---|
| A (A1, 176 beteckningar) | 74,8 s | 58,1 s | 57,8 s | nej - identisk rad för rad |
| A0124 | 34,6 s | – | 17,4 s | nej |
| B0122 | 34,0 s | – | 18,7 s | nej |

Korsprovet **kan** aldrig ändra ett mått: granskningen får inte röra läsningen, och mängderna var byte för byte
lika med och utan. Teckenhjälpen **kunde** ha ändrat något men gjorde det inte: på A0124 löste den 0 av 59
okända tecken, på B0122 0 av 30, på A 3 av 24 - och mängden blev densamma i alla tre fallen. På de tyngre
bladen är den halva analystiden.

Vad man förlorar är alltså en varning, inte en meter. Slå på dem under **Administration → Vad läsningen kör**
(eller `VVS_REVIEW_OCR=true` / `VVS_OCR_ASSIST=true`) på en installation vars ritningar läses sämre - det syns i
granskningen, och analysen tar då ungefär dubbelt så lång tid.

### 3.4b Vad andra läsaren är värd, i meter

Andra läsaren (3.1) rör bara fall motorn förklarat tvetydiga. Över de 33 bladen i porten är det **179,5 m** -
2,9 % av facit, 14 % av det vi missar - och det är ett *tak*: så mycket skulle den flytta om den svarade rätt
på varje fråga. Ett fel svar gör i stället en saknad meter till en falsk, vilket är dyrare. Porten kördes utan
den (`consulted: false`), så 80,0 % täckning och 27,3 % falskt är siffror utan språkmodell.

De stora felkällorna ligger någon annanstans: deklarerade anslutningsrör som facit inte räknar, och lodräta
meter som tabellen har men planen inte ritar. Ingen av dem är en tvetydighet en modell kan avgöra.

**Var tiden faktiskt går** (blad A, 94 s): hänvisningslinjer och fästen 52,8 s, teckenrekonstruktion 5,3 s,
PDF-läsning 0,7 s, mätning 0,6 s. Att stänga av båda OCR-passen tar bort ungefär en tredjedel av tiden; resten
är geometri.

### 3.5 Vad som *inte* är AI: inlärningen (`learning.py`, `corrections.py`)

Systemet "blir smartare" av rättelser, men inte genom träning och inte genom en modell. Regeln är smal och
uttalad:

En rättelse får göra exakt en sak på ett senare blad: **avgöra ett fall motorn själv redan markerat tvetydigt**,
till förmån för det svar en människa gav i samma situation. Den får aldrig skapa en sträcka, aldrig namnge
geometri ingen linje nådde, aldrig ändra en sträcka motorn är säker på, och aldrig rösta ned ritningen.

"Samma situation" är inte en likhetspoäng. Det är exakt träff på sex saker, alla lästa ur ritningen: pennan
(bredd och färg, utan lagret), hur bladet ritar sina hänvisningslinjer, motorns eget skäl att stanna,
beteckningens form (bokstäver och skiljetecken, inte siffror), fallets topologi (räknat, inte koordinater), och
vilka kandidater bladet erbjöd. Matchar inte alla sex talar lärdomen inte - två blad som bara liknar varandra
är två olika ritningar. Att bredda avtrycket kan bara få lärdomar att tala mer sällan, vilket är den riktning
det är säkert att ha fel åt.

Adminsidans "Inlärning" visar precis det: vilka lärdomar som finns, hur många gånger var och en talat, och
vilka rättelser som inte bar någon lärdom alls.

### 3.6 Nycklar

Ingen nyckel finns i repot, i en fil, i en logg eller i ett svar. `OPENAI_API_KEY` läses ur miljön i det
ögonblick anropet görs och läggs på tråden, ingen annanstans. Bakom en agentproxy som fäster referensen efter
att anropet lämnat maskinen skickas ingen nyckel alls härifrån.

---

## 4. Rättelser: vad en människa kan ändra, och vad det får lära ut

En människa som läser samma blad ser saker ritningen säger på sätt motorn inte har någon regel för ännu. Fem
sorters rättelse finns (`corrections.py`): förläng en sträcka, rita en ny, sudda, byt beteckning, sätt mängden
för hand. De läggs *ovanpå* läsningen, aldrig i den: motorns egen siffra står kvar bredvid den rättade
(`engine_total_m`), så det alltid syns vad som lästes och vad som ändrades. Varje rättelse går att ångra.

Rättelsen sparas med den **situation** den gjordes i (§3.5). Det är servern som läser av situationen ur sina
egna artefakter - en påhittad situation från klienten avvisas - för en tom situation skulle tyst stänga av hela
inlärningen.

Exporterna bär den rättade läsningen, med motorns siffra bredvid. En fil som visade en siffra läsaren redan
avvisat på skärmen, i det dokument de prissätter ur, vore fel sorts fil.

---

## 5. Projektanalysen: hela handlingen som en modell

En enkel analys läser en ritning och svarar med meter. Projektanalysen (`handling.py`, `backend/app/projects_api.py`)
läser alla blad i ett projekt och svarar med vad handlingen består av: hus, discipliner, skeden, versioner,
vad som hör ihop och vad som inte gick att avgöra.

Läsningen är billig med flit - den läser namnrutorna, inte geometrin, sekunder per blad - och den har en egen kö
så att den aldrig står bakom en halvtimmes mängdning.

**Ett före och ett efter får aldrig hittas på.** Ett par påstås bara när handlingarna själva bär ordningen: en
revisionsbeteckning, ett revisionsdatum, ett handlingsdatum eller ett skede. Ett tal i filnamnet är ingen
revision (`Hus A (2).pdf` är vad en webbläsare gör), och två handlingar från samma dag med samma status är två
discipliner i samma skede, inte två versioner. Det som inte går att ordna står som oklart, med vad det verkar
vara.

**Ändringsregistret** jämför två *läsningar*, inte två ritningar. Att en beteckning bara finns på ena bladet är
starkt. Att dess meter skiljer sig är svagt - två läsningar av samma oförändrade rör rör sig något - och under en
halvmeter eller fem procent räknas skillnaden inte som en ändring. Saknas läsningen på någon sida finns ingen
lista alls: att fylla i den saknade sidan med noll skulle göra hela den lästa sidan till "tillkommet".

Mängderna summeras **per hus och aldrig över projektet**: hus A och hus B har var sin beteckningslista.

Varje fält läsningen kom fram till går att rätta för hand, och rättelsen ligger kvar när analysen körs om. En
mapp som hette "Hus B" visade sig innehålla hus C:s ritningar - läsningen hade rätt och mappnamnet fel - men den
har inte alltid rätt.

---

## 6. Mängda för hand (mät, räkna, markera)

**Mängda** är en egen flik i sidomenyn och ett eget arbetsbord (`/mangda`, `frontend/src/pages/Takeoff.tsx`):
bladet till vänster, verktyget till höger. Det ligger vid sidan av läsningen, aldrig i den; de två redovisas var
för sig (eget blad i Excel-filen, eget namn i JSON:en). Fliken **Markera** på en läsning finns kvar för den som
vill rita medan hon läser.

Verktygen är de en mängdare behöver: **längd**, polylinje och frihand, med *multiplikator* och *tillägg* (en
stigare räknad som en punkt bär ändå sina meter); **yta**, rektangel och moln, med *avdrag* för hål i ytan och
*djup* som gör kvadratmetrarna till kubikmeter; **antal**, där varje klick får sitt löpnummer inom lagret; och
**anteckning**. Varje markering bär lager och beteckning, listan summerar per lager, verktyg och beteckning, och
hela listan går att ta ut som CSV.

**Skalan** kommer ur läsningen av bladet - men går den inte att läsa, eller gäller den inte för ett urklipp,
mäter mängdaren upp den själv: dra en linje över något vars längd är känd och skriv måttet. Den uppmätta skalan
går före läsningens för det bladet och den sidan, varje markering på sidan räknas om i den, och varje rad säger
vilken skala den mättes i. Utan skala står måttet i punkter, aldrig i påhittade meter.

**Verktygslådan** sparar förval - lager, beteckning, djup, multiplikator - som följer med till nästa blad.

Måtten räknas på servern ur punkterna och bladets egen skala (`backend/app/markups.py`) - aldrig i webbläsaren,
för ett mått klienten räknar fram går inte att härleda till någonting. Utan en färdig läsning finns ingen
skala, och då står det "ingen skala" i stället för påhittade meter. En ytas omkrets räknas aldrig in i
meterraden. En struken markering står kvar i lagret så att den går att få tillbaka.

---

## 6b. Kalkyl och anbud

Knappen **Kalkylera →** i analysens flikrad (och på ritningssidan efter en färdig analys) leder till kalkylens
egen sida, `/jobs/{id}/kalkyl`. Den gör mängden till pris, i två steg som hålls isär så att varje krona går att
spåra till en rad på ritningen (`backend/app/calc.py`):

*Material.* Varje beteckning matchas mot materialboken (55 000 artiklar med nettopris). Bladets egen
förklaringslista säger vad materialkoden betyder ("R8 = LEDNINGAR AV ROSTFRIA RÖR"), men boken använder andra
ord ("rostfritt rör", "rf AISI 304", "EN1.4432"), så förklaringen läses först till en *materialklass* (pex,
koppar, rostfri, pp, pe, pvc, gjut, galv, stål) och boken söks på klassens egna ord, som metervara, i rätt
dimension - DN för plaströr och rostfria avloppsrör, ytterdiametern för övriga metallrör. Bland träffarna går
ett riktigt pris före ett tomt, sedan den som bär flest av förklaringens egna ord (står det RIR vinner
rör-i-rör), sedan det billigaste. Matchningen är ett förslag med alternativ bredvid - den som räknar väljer, och
valet sparas. Där förklaringen inte säger vad röret är gjort av föreslås inget: alternativen i rätt dimension
finns att välja bland, men ett rör i fel material prissatt med säker min är värre än en tom ruta, så raden står
som förbehåll tills någon valt.

*Arbete.* Timmarna kommer ur Normtid VVS (`vvs_engine/normtid.py`): grundtid per meter efter ytterdiameter och
material, tillägg för skarvmetod och höjd, avvikelseanalysens bedömning av objektet. Stigare räknas som en
våningshöjd där ritningen inte anger höjden. Där boken inte har någon tid står det, och timmen skrivs för hand -
en gissad normtid är värre än ingen, för den ser ut som ett besked. Tabellerna är avlästa ur boken och ska
kontrolleras mot utgåvan innan ett anbud lämnas; det står i gränssnittet.

Sedan spill (kalkylmängd = netto + spill), påslag på material och arbete var för sig, och moms - allt utskrivet.
Det som sparas är valen och antagandena, aldrig resultatet: talen räknas om ur läsningen varje gång, med kundens
rättelser ovanpå, så kalkylen och bladet aldrig visar två olika meter.

**Anbudet** skrivs ur den sparade kalkylen som en formgiven PDF i A4, satt i Liberation Sans. Kroppen -
inledning, specifikation rad för rad, förutsättningar, avtalsvillkor, förbehåll, underskrift - flödas av PyMuPDF
Story; huvudet (mörkt block med anbudsnummer, datum, giltighet, beställare, referens), summeringskortet (exkl.
moms, moms, att betala) och foten med sidnummer ritas ovanpå med sid-API:et, eftersom Story ritar om ett blocks
bakgrund överst på varje följande sida. **Avtalsvillkoren** väljs i kalkylen: ABT 06, AB 04, ABS 18,
Hantverkarformuläret 17 eller inget; valet ger anbudet en villkorsrubrik med entreprenörens vanliga förbehåll under
det regelverket (ÄTA, garantitid, ansvar) - anbudets egna formuleringar, inte avtalstexten. Rader utan artikel
eller normtid står som förbehåll, liksom det onämnda röret och det som inte ingår (fittings, genomföringar,
isolering som egen post, rivning). **Förhandsgranskningen** i appen visar anbudets sidor som bilder ur samma PDF
som laddas ner (`/calc/anbud/sida-{n}.png`) - det dokument som skickas, inte en efterlikning av det.

---

## 6c. CAD-rummet (rita på bladet, markeringslista, status)

**CAD** är en egen flik i sidomenyn och ett eget rum (`/cad`, `frontend/src/pages/Cad.tsx`). Det är
varken läsning eller mängdning: här ritas *frågor* på bladet - ett moln runt något som inte stämmer, en
anteckning, ett kontrollmått - och sedan arbetas listan tills varje fråga har ett svar.

**Markeringslistan** (`frontend/src/components/MarkupsList.tsx`) är rummets arbetsbord: sortering på sida,
verktyg, ämne, lager, mått och status; filter på fritext, sida, lager, verktyg och status; status ändrad på en
rad eller på många på en gång; och radering. Urvalet följer med åt båda hållen - väljs en rad bläddrar bladet
dit och zoomar in på markeringen, pekas en markering ut på bladet hoppar listan dit.

En fråga hör till **handlingen och inte till bladet**: listan läser alla sidor (`?all_pages=true`) och säger
vilken sida raden hör hemma på. Statusflödet är **öppen → åtgärdad → godkänd**, med **avvisad** för den fråga
vars svar är att ingen åtgärd behövs; färgen syns både i listan och på bladet, och sammanställningen högst upp
räknar hur många som står i varje läge.

Att svara i listan (`PATCH`) rör aldrig geometrin, och därför räknas måttet inte om: ett svar är ord, inte en
ny mätning. Ska markeringen mätas om ritas den om på bladet. Ett svep över flera markeringar är helt eller
inte alls - träffar id-listan något som inte finns på handlingen avvisas hela anropet, så att den som markerade
tjugo rader aldrig behöver gissa vilka sjutton som gick igenom. Listan går att ta ut som CSV med ämne, status,
kommentar och källa, hela handlingen eller ett blad.

Måtten räknas av samma mätmotor som mängdningen använder (`engine/vvs_engine/takeoff/`). En granskning som
räknade själv skulle kunna komma till ett annat tal än mängden, och då vore den ingen granskning.

---

## 7. Akademin

Nio kurser, tjugotvå steg, femton kunskapsfrågor och tre fristående övningar med facit
(`frontend/src/learn.ts`, `components/Learn*.tsx`). Sidan har tre delar och visar en åt gången: **Kurser**, med
kurslistan som en gång till vänster - nummer, framstegsstapel, låsta märkta - och den valda kursens steg till
höger; **Öva**, de fristående övningarna; **Utmärkelser**. Kurserna tas i ordning - den man är på står öppen, de
framför är låsta tills den är gjord, men varje låst kurs går att öppna ändå. I väntan på en läsning visas samma
akademi i ett kompakt läge, som kort, utan navigering.

Framstegen ligger på kontot (`backend/app/academy.py`), inte i webbläsaren, så man fortsätter där man slutade
även från en annan dator. Poängen räknas på servern ur stegen själva - rätt på första försöket är värt mer än
rätt till slut - och utmärkelserna prövas mot tabellen. Ett resultat klienten får bestämma är ett önskemål.

---

## 8. Adminportalen

Allt som styr tjänsten står här, i tre delar som aldrig blandas ihop (`backend/app/admin.py`,
`frontend/src/pages/Admin.tsx`). Portalen är ett skal: sektionerna i en gång till vänster, sidan till höger, och
märken i gången på det som väntar på någon.

*Läsningen:* **överblick** med "att ta hand om" - misslyckade läsningar, en kö som växer, regler flera konton
flyttat åt samma håll, öppna utbetalningar - och kurvan per dygn, där staplarna är hur mycket som lästs och
linjen hur långt läsningen kom; att staplarna växer säger något om marknadsföringen, att linjen sjunker säger att
något gått sönder. Sedan **läsningar** (varje blad, hur långt det kom, hur lång tid det tog), **rättelser** med
sin situation, **inlärningen**, **reglerna** och **antagandena**.

*Företaget:* konton och planer, partners och ambassadörer med två procenttal (rabatten till kunden och
provisionen till partnern, satta var för sig), utbetalningar räknade i ören ur samma funktion som visar
provisionen - beloppet skrivs aldrig av från en skärm - kundvård, innehåll (CMS), A/B-prov med Wilson-intervall
så att ett prov utan tillräckligt underlag säger det, och heatmap.

*Systemet:* byggningen som kör, om andra läsaren nås, kön och trådarna, lagret, databasen och hur många regler
som flyttats. Bara fakta som går att kontrollera; byggningen och andra läsaren svarar dessutom utan inloggning
på `/api/version`.

Ingenting på företagssidan får avgöra hur en ritning läses. Den dagen en rabattsats kan flytta en meter går det
inte längre att svara på varför en mängd blev som den blev.

**Reglerna** (`rules.py`) är öppna: varje tröskel läsningen använder står med namn, förklaring, enhet,
standardvärde, tillåtet intervall och en levande figur som visar vad den handlar om. De bodde förr per konto, i
en egen inställningssida; nu bor de i portalen och gäller **tjänsten**. Alla som är inloggade får läsa katalogen -
en mängd som inte går att ifrågasätta är inget belägg - men bara administratören flyttar en regel, med skäl och
gärna en skärmbild av fallet, eftersom en flyttad regel gäller varje ritning som läses härnäst. Varje läsning
skriver ned vilka regler den kördes med (`ServiceSetting`, `backend/app/main.py`).

**Antagandena** är inte regler för hur ritningen läses utan för hur det lästa räknas ihop: våningshöjden en
stigare räknas som, om stigare räknas ur etiketter eller ritade symboler, och om rör i skrafferade ytor ingår i
den vågräta mängden. De sätts av administratören för tjänsten och är utgångsläget i varje ny läsning; den som
tittar på en enskild läsning kan avvika för just den, och exporten säger vad den räknat med.

## 9. Säkerhet

* Inloggning med JWT; lösenord hashade med bcrypt.
* **Nyckeln som undertecknar bevisen** har ett standardvärde i källkoden, och tjänsten **vägrar starta på en
  driftplattform** så länge det står kvar (`config.demand_a_real_secret`). Ett bevis undertecknat med en publik
  sträng är inget bevis.
* Broms mot gissning: efter tio fel på en adress inom en kvart svarar tjänsten 429, också på rätt lösenord.
  Räknat per adress och per avsändare. En okänd adress kostar lika lång tid som en känd med fel lösenord, så
  svarstiden inte avslöjar vilka konton som finns.
* Varje id-bärande väg prövar ägarskap; en annan användares projekt, ritning, jobb, markering eller
  projektanalys svarar 404.
* Uppladdningar läses bit för bit och stoppas vid 200 MB innan de ligger i minnet. En lösenordsskyddad, tom
  eller icke-PDF avvisas med en mening. En stackspårning når aldrig felrutan.
* Lagrets nycklar och webbappens filvägar prövas mot roten *med avskiljaren emellan* - ett prefix utan
  avskiljare släpper igenom grannen.
* Adminvägar kräver rollen `admin` (partners ser sina egna rader via `current_staff`). Rollen kommer från
  servern, aldrig från webbläsaren.

---

## 10. Drift

En container (`Dockerfile`, `railway.json`): webbappen byggs, motorn och API:t installeras, och API:t serverar
webbappen själv. Lokalt: `docker compose up` ger PostgreSQL, API och nginx. Se `README.md` och `.env.example`.

Miljö som betyder något: `VVS_SECRET_KEY` (krävs i drift), `VVS_DATABASE_URL` (SQLite som standard, PostgreSQL
i compose), `VVS_STORAGE_ROOT`, `VVS_WORKER_THREADS` (mängdningens kö), `VVS_ANALYSIS_DEADLINE_S` (tidsbudget per
blad), `OPENAI_API_KEY` och `VVS_SECOND_READER` (§3), `VVS_RUN_REVIEW`/`VVS_REVIEW_OCR`/`VVS_OCR_ASSIST`
(granskningen).

**Andraläsarna.** `OPENAI_API_KEY` ger Astra-läsaren, `ANTHROPIC_API_KEY` ger Claude-läsaren. Är båda satta
frågas båda om varje öppet fall, oberoende av varandra, och fallet avgörs **bara när de väljer samma kandidat**
ur ritningens egen lista; är de oense, eller svarar bara den ena, står fallet kvar tvetydigt. `VVS_SECOND_READERS`
väljer vilka som används (`auto`, `none`, `astra`, `claude`, `astra,claude`), och modellnamnen sätts med
`VVS_SECOND_READER_MODEL` respektive `VVS_CLAUDE_MODEL`. En nyckel läses ur miljön i anropsögonblicket och
skrivs aldrig ned, loggas aldrig och kommer aldrig tillbaka i ett resultat.

I Railway sätts de som miljövariabler på tjänsten; ingen av dem hör hemma i en fil i repot. Behöver bara en
läsare användas räcker det att sätta den ena nyckeln - panelen faller då tillbaka till den ensamma läsaren och
beter sig som förut.

SQLite körs i WAL-läge med väntetid, så att mätningens framsteg och API:ts läsningar samsas.

`/api/version` säger vilken byggning som kör, vilka andraläsare som är konfigurerade, om de går att nå och om
enighet krävs - utan inloggning, för en läsning är bara kontrollerbar om man kan säga vilken kod som gjorde den
och vem som fick vara med och avgöra det öppna.

---

## 11. Hur det valideras, och var det står

Ett facit-set på 33 ritningar från flera kontor, med mängdarens egna utsättningar som referens, ligger utanför
repot och nås aldrig av produktionskoden. En grind kör hela setet genom den riktiga tjänsten - registrera,
ladda upp, mängda, läs av API:t - och poängsätts efteråt av ett skript som aldrig kör motorn.

Två tal bär: **täckning** (andel av facits meter läsningen äger under rätt namn) och **falskhet** (meter under
fel namn, i andel av facit). Bara de system facit faktiskt täcker poängsätts.

Kurvan över de senaste rättelserna, en regel i taget:

| grind | regel | täckning | falskt |
|---|---|---|---|
| 45 | samlarlinjen bär ledaren till röret | 56,1 % | 12,5 % |
| 46 | bladets tabell namnger de onämnda kopplingsledningarna (§2b) | 76,5 % | 22,2 % |
| 47 | streck-prick-linjen är ett rör; en ventil avslutar det inte (§2c) | 79,5 % | 27,5 % |
| 48 | dubbellinjen viks ihop - för brett: DN16-buntar vek sig också | 72,7 % | 22,7 % |
| 49 | dubbellinjen följer diametern i skala; pricken bryggas på geometrin; tabellen namnger bara korta sträckor | 79,7 % | 26,8 % |
| 50 | skrafferade figurer (radiatorer) vägs inte som rör (§2c) | 80,0 % | 27,3 % |

Senaste grinden är alltså **80,0 % täckning, 27,3 % falskt**, 270 av 365 beteckningar rätt.

Det falska steg med täckningen, och det är den siffran som ska ner. Där den kommer ifrån, blad för blad:
en del är facit-policy som läsningen inte kan veta (kopplingsledningar och avloppsgrenar som facit inte räknat
på vissa blad men på andra; rör ritade utanför bladets egen del av byggnaden, bortom "DEL 21 | DEL 22"-linjen,
som facit inte tar med), en del är riktiga överanspråk: värmeledningar där DN15-etiketterna flödar in i en
DN22-stam som bara har en egen etikett vid stigaren, och rör ritade som par (tillopp och retur på samma penna)
där facit räknar paret en gång. Nästa steg är kända: ventilernas egna beteckningar (AV601-22, RV601-15) som
dimensionsgräns i linjen, och bladets delgräns som klippning.

Det som fattas i täckningen är till största delen det systemet vägrar gissa: rör som ingen hänvisningslinje når,
och blad exporterade utan lagernamn där väggar och rör ritas med samma penna. Där står metrarna som *onämnda*
med sina siffror, och en människa kan rita in dem med en rättelse som sedan lär ut det den kan.

Dessutom: närmare trehundra automatiska prov (motor, API, gränssnitt), ett rökprov som klickar igenom hela webbappen med
konsolen öppen, determinismprovet, kontamineringsskanningen, och en isolationsprövning som prövar varje
id-bärande väg med fel ägare.

---

## 12. Vad systemet inte gör

* Det läser inte skannade eller bildbaserade PDF:er. Det gissar aldrig ur bildpunkter.
* Det hittar inte på en anslutning där linjer bara korsas, en meter där ingen linje pekar, en vertikal längd
  utan höjd, en revision ur ett filnamn, eller ett före och ett efter ur två discipliner.
* Det låter ingen modell avgöra en meter, och ingen rättelse skapa en.
* Det mängdar inte fittings, genomföringar, isolering som egen post, status (nytt/befintligt/rivs) eller
  beställningsmängd i handelslängder. Det står i `LATHUND.md` vad som är gjort och vad som inte är det.
