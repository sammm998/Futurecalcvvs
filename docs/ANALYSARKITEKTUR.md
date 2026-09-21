# Analysdelen: vad som bär, vad som brister, och vad som görs åt det

En genomgång av läsvägen — från PDF-objekt till mängd — med mätningar i stället för omdömen där mätningar
finns. Sista avsnittet är en rangordnad lista; posterna som är genomförda är märkta så.

## Vägen genom en ritning

```
PDF  →  extract        RawPath / TextSpan            råa vektorer, per sida
     →  prepare_page   glyfer → text → rader         den halva som inte beror på några val
                       block → beteckningar
                       beteckningslista
     →  analyze_page   ledarlinjer → familjer        vilken penna ritar rör på just det här bladet
                       topologi → PipeGraph
                       identitet → PhysicalPipe
                       skala → mängd
     →  artifacts      allt läsningen kom fram till, som filer
```

Tre lager, och gränserna mellan dem är verkliga: `RawPath/Seg` är vad filen säger, `Prim/PipeGraph` är vad
geometrin bildar, `PhysicalPipe` är vad någon kan prissätta. Identitet uppstår bara där tre saker möts — en
beteckning bladet skriver, en ritad hänvisningslinje från den, och den graf geometrin bildar. Aldrig närhet.

## Det som bär

**Bevis före svar.** En mängd finns bara där ritningen själv pekar. `AMBIGUOUS` är ett giltigt svar, och varje
meter går att spåra tillbaka genom `why()` och bevisgrafen. Det syns i siffrorna: på de fyra referensbladen
100 % precision och recall på beteckningar, 386,05 ägda meter mot facit, 2,53 falska (0,6 %).

**Allt upptäcks per ritning.** Familjer, grammatik, skala, ledarpennor, beteckningslista — inget är inställt
någonstans, och en kontamineringsskanning ser till att ingen ritningsspecifik konstant smyger in i källkoden.

**Determinism som grind.** Uppräkningsordningen i PDF:en får inte ändra svaret, och det kontrolleras vid varje
körning genom att sidan läses om i omkastad och blandad ordning.

**Vägran framför gissning.** Familjer som avvisas bär sitt skäl, geometri utan ägare rapporteras, och en läsning
som spränger sin budget kastas hellre än levereras halv.

**Artefakterna är API:et.** Agenten, gränssnittet och exporterna läser samma filer som mätningen skrev, så
chatten och mängdtabellen kan inte säga emot varandra.

## Det som brister

### Skala

**S1. En omgång mängdades till sitt första blad.** *(åtgärdat)* Varje sida lästes, ritades ut på överlagren —
och slängdes sedan. `quantities.json` var första sidans. En femtiobladig handling gav alltså mängden för
bottenvåningen och kallade det huset. Nu skrivs `document-quantities.json`: rader per blad, samma beteckning
summerad över de blad den står på, och en summa för omgången. På en trebladig provhandling (referensbladen A, C
och E i en fil) 278,28 m mot 211,65 m som första bladet ensamt gav, med `KV1-X31-16` följd över blad 0 och 1.

**S2. Hela handlingen byggdes i minnet innan något lästes.** *(åtgärdat)* Mätt på en femtiobladig omgång:
105 s extraktion, 1,1 miljoner paths, **1956 MB** toppminne — innan en enda meter mätts. Det är inte en sida som
är dyr, det är fyrtionio sidor som sparas till sen. Efter omläggningen: samma 1,1 miljoner paths, en sida i
taget, **352 MB** och 99 s. Sidorna läses nu på begäran och lämnas tillbaka när läsningen är klar med dem;
överlagren ritas blad för blad i stället för sju gånger över hela handlingen.

**S3. Beteckningslistan tvingade fram en andra läsning.** *(åtgärdat)* Listan hittades per blad; stod den längre
bak fick de tidigare bladen läsas om mot den. Nu letas listan upp först, och de läsningar sökandet redan betalat
för återanvänds.

**S4. Sidorna läses strikt i följd, på en arbetstråd.** `worker_threads = 1`, budget 1800 s. Sidor är oberoende
av varandra så snart vokabulären är känd — de är pinsamt parallella. *(inte gjort; se lista)*

*Sidotal från omläggningen:* referensbladen läses nu på ungefär halva tiden (A 82 → 40 s, C 25 → 18 s,
D 41 → 23 s, E 35 → 22 s) med oförändrat resultat, mest för att determinismkontrollen slutade kopiera hela
handlingen och för att den halva av läsningen som sökandet efter beteckningslistan redan betalat för
återanvänds.

**S5. Tvåpassstrukturen läser om samma sida upp till tre gånger.** `run_pass` bygger geometriindex och grafer på
nytt varje gång, och valet mellan passen avgörs av ihopkopplade tumregler (`collapsed`, `halved`, `take1`) som
inte skrivs ned någonstans. Korrekt, men inte inspekterbart. *(inte gjort)*

**S6. Ingenting mellanlagras.** Text-återuppbyggnaden är 62 % av en sidas analystid (5,5 s av 8,9 s på
referensblad A) och görs om vid varje omläsning. `prepare_page` gör den nu till ett värde som går att räkna en
gång och läsa två — men det finns ingen cache mellan körningar.

### Träffsäkerhet

**T1. Enpenneblad.** Den största kvarvarande felklassen. Där exporten saknar lager och allt är samma
streckbredd hamnar rör, väggar, skraffering och text i samma familj och samma graf: 36 % av nodernas grad är
> 2, längsta sammanhängande sträcka 1,86 m, och identiteten dör vid första korsning. Korpusmätning: median 31 %
av beteckningarna nådde ett rör, 34 blad under 10 %. *(inte gjort — se lista, punkt 3)*

**T2. Buntar är geometriskt symmetriska.** På ett blad med parallella kall- och varmvattenledningar kan
geometrin bevisligen inte säga vilken som är vilken: byt KV1↔VV1 överallt och alla villkor håller fortfarande.
Enda riktiga svaret är projektets egen penna→system-vana, vilken finns (kräver 3 samstämmiga blad).

**T3. Korsningar avslutar ägandet.** `_components` stannar vid grad > 2, så en T-avstickare delar sträckan i
delar som var och en behöver sin egen etikett. På glest etiketterade blad tappas meter som en människa
självklart hade fört vidare.

**T4. Skalan är per blad och kunde hamna i CONFLICT** *(åtgärdat)* utan att omgivande blad hjälpte till. Nu:
där två eller fler blad i handlingen fastställt samma skala är det handlingens skala, och ett blad vars egen
stämpel avgjorde ingenting läses om med den — märkt `FROM_THE_SET`, aldrig som om bladet självt sagt det. Blad
med olika skala i samma fil (planer och detaljer) lånar ingenting ut: då finns ingen enig omgång att luta sig
mot. Prov: referensblad D, vars stämpel står i CONFLICT, i en handling med två eniga blad tar handlingens skala
och ett blad läses om.

**T5. Ingen sida-till-sida-fortsättning.** Rör som fortsätter på nästa blad räknas dubbelt eller inte alls.

**T6. Läsningen kontrollerar inte sig själv mot bladet.** Ingenting jämför uppmätta meter med hur mycket bläck
de accepterade rörfamiljerna faktiskt ritar. Ett blad som ritar 400 m och mäter 4 m ser i rapporten ut precis
som ett blad som ritar 4 m.

**T7. En anteckningsruta lästes som beteckningslista.** *(åtgärdat)* "Lista" hittades på 94 % av korpusens sidor
— fler än det finns listor.

### Struktur

**K1. `pipeline.py` är 1500 rader** och blandar orkestrering med algoritmer (buntlösning, stigardetektering,
identitetsbyggnad). `prepare_page` är ett första snitt; resten står kvar.

**K2. Varför ett pass vann skrevs inte ned.** *(åtgärdat)* Läsningen skriver nu vilka läsningar av bladet den
prövade — obegränsad, med ledarpennorna insläppta, med skrivpennorna undantagna — hur många av bladets egna
rörnamn var och en placerade, och vilken som behölls.

## Listan, rangordnad

| # | Åtgärd | Vinst | Status |
|---|--------|-------|--------|
| 1 | Mängda hela handlingen, inte första bladet: per blad-rader och en summa för omgången | träffsäkerhet (allt annat mättes inte alls) | **klart** |
| 2 | Strömmande läsning: sidor byggs på begäran, används och släpps; överlagren ritas blad för blad | skala: O(ett blad) i stället för O(handlingen) | **klart** |
| 3 | Beteckningslistan läses en gång för omgången, och en anteckningsruta är inte en lista | träffsäkerhet på alla stilar | **klart** |
| 4 | `prepare_page`: den halva som inte beror på några val blir ett värde | skala + testbarhet | **klart** |
| 5 | Determinismkontrollen kopierar bara bladet den provar | skala (kopierade hela handlingen tre gånger) | **klart** |
| 6 | Täckningskontroll: uppmätta meter mot ritat rörbläck, per blad | ärlighet: ett oläst blad säger det själv | pågår |
| 7 | Visa omgången i appen: bladväljare, rader per blad, summa | träffsäkerhet blir synlig | pågår |
| 8 | Skalan får luta sig mot syskonbladen i samma handling | räddar blad med otydlig stämpel | **klart** |
| 9 | Skilj rörgeometri från byggnadsgeometri innan grafen byggs, på blad utan lager | den största kvarvarande felklassen | nästa (ett försök mätt och förkastat, se nedan) |
| 10 | Parallell sidläsning, begränsad av kärnor och minne | skala: ~4× på en omgång | nästa |
| 11 | Skriv ned varför ett pass vann, som artefakt | inspekterbarhet | **klart** |
| 12 | Sida-till-sida-fortsättningar | dubbelräkning och tappade sträckor | senare |

Kvar av listan är tre poster, och de är kvar av tre olika skäl. **#9** (rör mot byggnad på blad utan lager) är
forskning: ett försök är mätt och förkastat, och nästa måste skilja rör från byggnad innan familjerna bedöms.
**#10** (parallell sidläsning) är bygge med verklig risk — minne per process och en stor läsning att skicka
tillbaka — och vinsten syns bara på handlingar med många blad. **#12** kräver att man först kan säga att två
sträckor på olika blad är samma rör, vilket ingen del av systemet gör i dag.


## Mätt och förkastat

Det som mäts sämre åker ut, hur rimligt det än låter. Det står här för att nästa försök ska börja i
mätningen och inte i resonemanget igen.

**Bokstavsstreck ur rörgrafen.** På ett blad utan lager, med en enda penna, ligger strecken som läsningen redan
läst som text kvar i rörfamiljen och i grafen byggd av den: på ett sådant blad 10 252 av 47 065 primitiver, en
femtedel, där varje bokstav är en knut av tiondelspunktssegment som möts i noder med hög grad — precis där
etiketterna sitter, alltså på sträckorna. Att ta bort dem ser självklart rätt ut, och läsningen vet redan exakt
vilka sökvägar det är: den håller dem redan borta från vad en hänvisningslinje får landa på.

Mätt föll referensgrindet: ägda meter 386,05 → 377,31, **falska meter 2,53 → 7,05**, missade 9,06 → 17,79.
Blad A ensamt gick från 0,05 till 4,69 falska meter. Och på de fem enpennebladen sjönk de uppmätta metrarna
från 5,33 till 1,42, alltså sämre också där.

Slutsatsen är inte att bokstäver är rör. Den är att ägandet och storleksgränserna i dag vilar på den geometrin
på sätt som ett trubbigt borttagande river: bokstavsstrecken fungerar som gränser och som bryggor över luckor.
Ett riktigt försök måste därför skilja rör från byggnad *innan* familjerna bedöms — och visa att gränserna
håller utan dem — inte plocka bort strecken ur en färdig graf.

**Ett etikettblock med flera koder tar hela sträckan var.** Det överlägset vanligaste skälet till att en
beteckning står kvar som *påpekad men onämnd* är `multi_row_label_shares_one_run`: ett block med flera koder som
når en enda ritad linje. Över korpusen är det 1 178 av knappt 1 340 sådana fall, och de bär 665 m mot 4 407 m
bekräftade — ungefär 13 % mer rör som bladen skriver ut och läsningen avstår från.

Resonemanget för att ta dem ser starkt ut: rör som delar stråk ritas som en linje, för i planskala skulle de
ligga ovanpå varandra, och mängden är då *en längd per kod* — inte en längd delad mellan dem. Att dela var
aldrig alternativet; att avstå var det.

Mätt föll det. Regeln lades in i två former. Den strikta — bara där lagren inte namnger någon av koderna —
utlöses inte alls på A, C, D eller E, så referensgrindet säger ingenting om den. Den lösare — där lagren inte
avgör *någon* rad, vilket är fallet på blad A — gav **17,46 falska meter på blad A och noll ägda meter tillbaka**
(hela setet: falska 2,53 → 19,94). Facit har alltså inte de metrarna: där lagret redan namnger en av koderna i
blocket är den koden den som går där, och de andra raderna säger något annat.

Kvar står alltså: geometrin under ett sådant block är riktigt utpekad, och att avstå från att namnge den är
riktigt. Ett nytt försök måste börja i vad *facit* gör med ett flerradigt block, inte i vad konventionen säger.

## Vad korpuset täcker

Stilbiblioteket är inte en samling ritningar utan en samling **verktygskedjor**: vad som skiljer ett blad från
ett annat är inte byggnaden, det är vilket program som ritade det och vilken skrivare som gjorde PDF:en. Två
kontor som båda använder AutoCAD ger nästan samma fil; samma kontor som byter från pdfplot till Bluebeam ger
en fil läsningen knappt känner igen.

| # | kontor | kedja |
|---|---|---|
| 01 | — | AutoCAD · pdfplot 14–16 · Ghostscript 9.21 |
| 02 | Sweco | AutoCAD MEP 2020 · pdfplot 15 |
| 03 | Sweco | AutoCAD 2023 · pdfplot 16 · hårfina streck |
| 04 | VVS Konsulterna | Revit · Bluebeam Brewery 5.0 |
| 05 | Bengt Dahlgren | Ghostscript 9.21 |
| 06 | PO Andersson | Ghostscript 9.21 |
| 07 | Arildssons Rör | Ghostscript 9.21 |
| 08 | PQR Malmö | Bluebeam Revu · Ghostscript 9.21 |
| 09 | Rejlers | Bluebeam Revu · Ghostscript 9.21 |
| 10 | Kjell Petersson | Bluebeam Revu · Ghostscript 9.21 |
| 11 | Sweco | Bluebeam Brewery 5.0 · uniform streckbredd |

Det som betyder mest för läsningen är två saker som syns direkt i tabellen. **Lagernamn** överlever ur AutoCAD
via pdfplot och försvinner genom Ghostscript och Bluebeam — och ett blad utan lagernamn är det svåra fallet,
eftersom rör och byggnad då ritas med samma penna. **Uniform streckbredd** (11) tar bort det sista som skiljer
en rörlinje från en väggkontur.

Mätningarna ska därför alltid redovisas per kedja och inte som ett medelvärde över korpuset: ett medelvärde
döljer att de lagerbärande bladen läses nästan helt och de lagerlösa knappt alls.
