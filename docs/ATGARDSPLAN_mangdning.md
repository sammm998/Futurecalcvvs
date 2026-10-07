# Åtgärdsplan: mängdning av rör från VS-ritningar

Till: Claude Code
Underlag: 6 ritningar (Allöskolan, Kristianstad) där systemets resultat jämförts mot manuellt facit
(Bluebeam-markeringar och mängdexport). Bifogat skript: `facit_compare.py`.

---

## 0. Läs detta först – hur du ska arbeta

1. **Bygg regressionstestet innan du ändrar något.** Lägg in de sex ritningsparen som testfall och kör
   `facit_compare.py` på alla. Spara utfallet som baslinje (tabellen i avsnitt 1). Varje ändring ska
   visa förbättring på totalen *och* får inte försämra någon ritning med mer än 0,5 m per beteckning.
2. **Inga ritningsspecifika lösningar.** Inga koordinater, ritningsnummer, beteckningsnamn eller
   "om DN35 och VS1 så …"-specialfall i koden. Varje regel ska formuleras utifrån ritningskonvention
   (hur en VS-konstruktör ritar), och gälla för alla system (KV, VV, VVC, VS, VP, S, D).
3. **Håll ut två ritningar.** Utveckla mot 0023, 0122, 0114, 0024. Verifiera sedan *utan vidare
   justering* på 0121 och 0033. Om de håll-ut-ritningarna inte förbättras är regeln överanpassad.
4. **Hellre flagga än gissa.** När bevisen är motstridiga: lägg sträckan i "behöver granskas" med
   orsak, i stället för att välja en beteckning tyst. En flaggad meter är bättre än en felaktig.
5. **Gör felen synliga.** Avsnitt 6 (diagnostik) är en förutsättning för att kunna verifiera resten –
   börja gärna där.

---

## 1. Baslinje (nuvarande resultat mot facit)

| Ritning | Typ | Horisontellt | Totalt inkl. stigare | Andel facit-meter med fel beteckning |
|---|---|---|---|---|
| W-50-1-A-0023 | Spill under platta | −0,9 % | **+17,7 %** | 16 % |
| W-50-1-A-0033 | Spill under platta | −2,1 % | −1,1 % | <1 % |
| W-50-1-A-0024 | Spill under platta | −0,5 % | −3,0 % | <1 % |
| W-50-1-A-0122 | Plan, alla system | −4,3 % | **−11,3 %** | ~19 % |
| W-50-1-A-0114 | Plan, alla system | −2,6 % | **−10,3 %** | ~8 % |
| W-50-1-A-0121 | Plan, alla system | −3,2 % | −6,3 % | ~16 % |

Totalt i facit: ~960 m horisontellt, ~400 m vertikalt.

**Det som redan fungerar och inte får förstöras:**
- Geometri, skala och täckning: >99 % av facits rör är markerade av systemet.
- Skrafferat område exkluderas på samma sätt som i facit.
- S-system under bottenplatta: inom ±0,5 m per beteckning (0033, 0024).

**Felen fördelar sig så här (ungefärlig påverkan):**

| # | Problem | Påverkan | Ritningar |
|---|---|---|---|
| A | Fel DN/beteckning sprids längs topologin (parallella par, T-rör) | ~120 m felklassat | 0023, 0122, 0114, 0121 |
| B | Stigare kopplas till fel rör (X7 i stället för X31) | ~65 m | 0122, 0114 |
| C | Fel stigarhöjd (allt 1 m eller allt 2,8 m) | ~50 m | 0122, 0114, 0121 |
| D | Stigarräkning: etikett i stället för symbol, skrafferat, symbolvarianter | ~15 m | 0023, 0024, 0121 |
| E | Material/system: K5 (koppar) läses som X31/X7 | ~8 m | 0114 |
| F | Mätgränser: entreprenadgräns, ritningskant | ~6 m | 0024, 0114 |
| G | Overlay: färger återanvänds mellan beteckningar | gör QA omöjlig | alla |

---

## 2. Problem A – beteckning/DN sprids till fel rör (störst)

### Vad som händer
| Ritning | Facit | Systemet sa | Meter | Var |
|---|---|---|---|---|
| 0023 | S1-P2-75 | S1-P2-110 | 5,8 | Diagonal sträcka från golvbrunn till anslutning; etikett "S1-P2-75" pekar *på* sträckan, 110 kommer in från förgreningen |
| 0122 | VS1-S13-35/W | VS1-S13-12/W (40,6) och -22/W (6,7) | 47 | Framlednings-/returpar längs ytterväggar och fönstervägg |
| 0121 | VS1-S13-42/W | VS1-S13-12/W (17,8) och -35/W (2,6) | 20 | Parallellt par längs vänster vägg, förbi radiatoranslutningar |
| 0114 | VVC1-X7-32/W | KV1-X7-40/W | 5,6 | Rörbunt med 3 parallella ledningar vid A300 |
| 0114/0122/0121 | VV1/KV1 X7-16, X7-20, X7-40, X31-16 | annan dimension inom samma system | 2–7 per ritning | Täta områden vid tappställen/WC |

### Trolig grundorsak
Etiketter fästs vid närmaste rör och sprids sedan genom nätet (flood-fill över anslutningar).
När ett huvudrör (35/42) har många grenar till radiatorer (12) "vinner" 12 genom antal eller
genom att spridas tillbaka in i huvudröret via T-rören. I rörbuntar fästs ledarens ände på
grannröret, eftersom det ligger inom toleransen.

### Hur det ska lösas (generella regler)

**A1. Dela nätet i "sträckor" innan beteckningar tilldelas.**
En sträcka = rörgeometri mellan två noder, där nod = T-rör/förgrening, ändpunkt, symbol
(stigare, golvbrunn, ventil, radiator) eller dimensionsbyte (ändrad linjetyp/tjocklek). Beteckningar
tilldelas *sträckor*, inte enskilda segment och inte hela sammanhängande nät.

**A2. Spridning genom T-rör är riktad.**
- Genom en nod med exakt två anslutna sträckor (böj, ingen förgrening) får beteckningen spridas fritt.
- Genom ett T-rör får beteckningen bara spridas *rakt igenom* (kollinjärt, vinkel < ~20°) –
  aldrig in i avgreningen.
- En avgrening får bara egen beteckning från egen evidens (ledare som träffar den).
- Spridning stoppas där en annan direkt ledare-evidens finns.
- Konventionsregel som sanity check: DN i avgrening ≤ DN i huvudledning. För spillvatten (S, D)
  minskar DN aldrig nedströms. Bryts detta → flagga, välj inte tyst.

**A3. Direkt evidens slår spridd evidens, alltid.**
Prioritet: (1) ledarens pil/tick-ände ligger *på* sträckan (vinkelrätt avstånd < 1,5 pt, mätt mot
centrumlinjen) > (2) ledarens ände närmare denna sträcka än någon annan med marginal > 2× >
(3) spridd beteckning via A2. Om (1)/(2) är tvetydigt (två rör inom toleransen) → använd A4,
annars flagga.

**A4. Ledare som korsar flera rör (rörbuntar och par).**
På dessa ritningar korsar en ledare ofta flera parallella rör med ett *snedstreck (tick)* på varje
rör, och beteckningarna står staplade i samma ordning i etikettblocket (se t.ex.
"KV1-X7-40/W / VV1-X7-40/W / VVC1-X7-32/W"). Implementera:
- Hitta alla korsningar mellan ledaren och rör, sorterade längs ledaren från etiketten och ut.
- Matcha korsning *i* mot etikettrad *i* (antal korsningar == antal rader; annars flagga).
- Ticks/korsningar vinner över "närmaste rör".

**A5. Parallella par och buntar har en gemensam identitet.**
Detektera grupper av sträckor som går parallellt (samma riktning ±5°, inbördes avstånd < ~15 pt,
överlapp > 60 %). Inom en bunt har varje rör sin egen beteckning, men beteckningen följer röret
längs hela bunten. Ett rör i bunten får inte byta beteckning mitt i bunten utan en nod (A1).
För VS-par (framledning/retur): båda rören har normalt samma DN. Om ena röret i paret är 35/42 över
en lång sträcka och det andra fått 12 → flagga eller använd parets DN.

**A6. Rimlighetsregler som flaggar (inte ändrar).**
- En radiatorgren (VS DN12) är en kort stump som slutar vid en radiator/ventil. En sträcka märkt
  med minsta DN som är > ~5 m och förbinder två större DN → flagga "misstänkt spridd beteckning".
- En beteckning vars totala längd ökar > 50 % genom spridning jämfört med direkt evidens → flagga.

### Verifiering
`facit_compare.py` → avsnittet "Facit-sträckor: vad systemet kallade dem". Målet är att
VS1-S13-35 (0122) och VS1-S13-42 (0121) går från 34 % respektive 30 % rätt till > 95 %, och
S1-P2-75 (0023) från 45 % till > 95 %, utan att någon annan beteckning tappar.

---

## 3. Problem B – stigare kopplas till fel rör (X31 eller X7)

### Vad som händer
| Ritning | X31-stigare system/facit | X7-stigare system/facit |
|---|---|---|
| 0122 | KV 0/5, VV 0/3 | KV 5/2, VV 3/2 (för många) |
| 0114 | KV 2/15, VV 2/9 | 6/0 |
| 0121 | KV 1/1, VV 0/1 | VV1-X7-20: 2/0 |

Facit sätter stigaren på **X31-ledningen (PEX-kopplingsledning) vid tappstället**, där den går upp
från golvet till blandaren eller toaletten. Systemet hittar antingen inte stigaren eller ger den
till X7-ledningen (fördelningsledningen) som ansluter i samma punkt.

### Hur det ska lösas
- **B1.** En stigarsymbol tillhör den sträcka som har en *ändpunkt* i symbolen (sträckan börjar
  eller slutar där). Om flera sträckor möts i symbolen: välj den som *slutar* där (terminal) framför
  den som passerar igenom. Om flera slutar där: välj den med minst DN, eftersom kopplingsledningen
  är grenen ut till tappstället.
- **B2.** Använd ritningens tabell "KOPPLINGSLEDNINGAR" (ANSL / KV / VV / S, t.ex. B 16(15), TS 16(12))
  och komponentförkortningarna vid tappställena (BL, TS, UB, VK, DB …). Varje tappställe med KV/VV
  ska normalt ha en X31-stigare per medium. Använd detta som **kontroll**: antal X31-stigare ≈ antal
  tappställen × medier enligt tabellen. Avviker det → flagga.
- **B3.** En X7-ledning (fördelning) ska normalt inte få stigare på en planritning om den inte
  uttryckligen har en stigarsymbol med egen etikett. Om systemet ger X7 en stigare i samma punkt som
  en X31 slutar → det är fel enligt B1.

---

## 4. Problem C och D – stigarhöjd och stigarräkning

### C. Höjd per stigartyp
Facit använder två typer för VS1:
- `VS1-S13-12 VERTIKAL` = **2,8 m** (våningshöjd). 0122: 20 st, 0121: 6 st, 0114: 2 st.
- `VS1-S13-12 VERTIKAL genom bjälklag 1m` = **1,0 m**. 0122: 16 st, 0121: 8 st, 0114: 8 st.

Systemet sätter i dag **alla** VS1-stigare till 1 m och **alla** övriga till 2,8 m.
Jag har inte kunnat fastställa säkert vilket ritningstecken som skiljer typerna. Ta fram regeln
själv, så här:
1. Extrahera facits Polygon-annotationer med `/Subj` som innehåller "VERTIKAL" respektive
   "genom bjälklag" (se `read_facit_geometry` i skriptet). Rita ut beskärningar runt varje punkt.
2. Jämför vad som skiljer dem: symboltyp (cirkel, cirkel med kryss, dubbelring, pil upp/ned),
   etikettext ("UPP", "NED", "FR/TILL PLAN 2"), om röret fortsätter till ett annat plan eller går
   till en radiator under/över bjälklaget, och vilket lager linjen ligger på.
3. Implementera regeln som **tabellstyrd konfiguration** (symbol- eller kontexttyp → höjd), inte
   som hårdkodade värden. Gör våningshöjden till en parameter (2,8 m här).
4. Rapportera antal per typ i mängdfilen (t.ex. "Stigare våningshöjd" och "Stigare genom bjälklag"),
   så att en kalkylator kan justera höjden i efterhand.

### D. Räkna stigare rätt
- **D1. Räkna symboler, inte etiketter.** 0023: 110 hade 1 symbol men 2 etiketter, och systemet
  använde 2. Etiketter används bara för att *beteckna* en symbol, aldrig för att räkna.
- **D2. Exkludera stigare i skrafferat område** (samma regel som för längd). 0023: 4 extra
  75-stigare på pålbalken.
- **D3. Känn igen alla stigarsymboler**, även **öppen cirkel utan kryss** i en rörände
  (0024: en DN160-stigare missad). Bygg en symbolkatalog från ritningens förklaringar och
  testdata: cirkel med kryss, dubbelring, öppen cirkel i ände, cirkel med pil.
- **D4. Stigare utan rörkoppling** (S2-P5-110 på 0121: 2 i facit, 0 hos systemet) ska rapporteras
  som "stigare utan sträcka" med etikettens beteckning, i stället för att tappas.

---

## 5. Problem E och F – material och mätgränser

**E. Material ska komma från etiketten, inte från grannrör.** På 0114 ligger KV1-K5-15 och VV1-K5-15
(koppar, vägghängt i schakt) bredvid X31-/X7-ledningar. Systemet gav dem X31/X7. Materialkoden
(K5, X7, X31, S13, P2, P5 …) är en del av beteckningen och får aldrig ärvas genom spridning (A2)
från ett rör med annan materialkod. Om en sträcka saknar egen evidens och grannarna har olika
material → flagga.

**F1. Entreprenadgräns.** På 0024 fortsätter DN160 0,78 m förbi "ENTREPRENADGRÄNS RE/ME".
Läs in gränslinjer (text "ENTREPRENADGRÄNS" plus tillhörande linje eller streckprickad linje) och klipp
mängden vid gränsen. Redovisa det avklippta separat.

**F2. Rör till ritningskant eller matchlinje.** På 0114 är 4,7 m VP1/VS1 DN42 som går upp mot
ritningskanten helt omarkerade, inte ens som skrafferat. Rör som slutar vid ritningsramen ska
mätas fram till ramen och flaggas "fortsätter på annan ritning". De får inte tappas.

**F3. Skrafferad gräns.** Mät fram till kanten av det skrafferade området, inte till närmaste nod
före kanten. Det gäller små diffar på 0033 och 0024.

---

## 6. Problem G – diagnostik som måste finnas

- **G1. Unik färg per beteckning i overlayn.** I dag delar t.ex. KV1-X31-16 och KV1-X7-20/W samma
  färg, och S2-P5-75, VS1-S13-12/W och VVC1-X7-32/W samma färg. Det gör det omöjligt att granska
  ritningen visuellt eller automatiskt. Generera paletten så att ingen färg upprepas. Om antalet
  beteckningar är större än antalet tydliga färger: variera även streckmönster eller tjocklek, och
  skriv beteckningen som liten text längs varje sträcka.
- **G2. Exportera segment → beteckning som JSON** (geometri i PDF-koordinater, beteckning, DN,
  evidens: "direkt ledare" / "tick" / "spridd från sträcka X" / "flaggad"). Då kan
  `facit_compare.py` jämföra exakt i stället för via färger. Utöka skriptet att läsa den när den finns.
- **G3. Evidens per sträcka i rapporten:** hur många meter som är direkt evidens jämfört med spridd.
  En hög andel spridd evidens på en beteckning är den bästa varningssignalen för problem A.

---

## 7. Arbetsordning

1. **G1 och G2** (diagnostik). Ingen mängdändring, men gör resten mätbart.
2. **A1 till A5** (topologi och tilldelning). Störst effekt, ~120 m.
3. **B1 till B3** (stigare på rätt rör).
4. **C** (stigarhöjd per typ). Ta först fram regeln enligt metoden i avsnitt 4.
5. **D1 till D4, E, F1 till F3.**

Efter varje steg: kör alla sex ritningar och uppdatera baslinjetabellen.

## 8. Acceptanskriterier

- Horisontell längd per ritning inom ±3 %. Varje beteckning med facit > 5 m inom ±10 %.
- Andel facit-meter med rätt beteckning ≥ 95 % per ritning (avsnittet "vad systemet kallade dem").
- Antal stigare per beteckning inom ±1 mot facit. Total vertikal längd per ritning inom ±10 %.
- Håll-ut-ritningarna (0121, 0033) ska klara samma krav utan att regler justerats för dem.
- Ingen ritning får bli sämre än baslinjen på någon beteckning med mer än 0,5 m.

## 9. Kör jämförelsen

```bash
python3 facit_compare.py \
  --facit-pdf W-50-1-A-0122.pdf --facit-xlsx W-50-1-A-0122.xlsx \
  --our-xlsx mangder_11.xlsx --our-pdf markerad_11.pdf \
  --out jamforelse/ --name W-50-1-A-0122
```

Skriptet skriver `<namn>_jamforelse.md`, med mängder per beteckning och vad systemet kallade varje
facit-sträcka, samt `<namn>_jamforelse.png` (grönt = rätt, rött = fel beteckning, orange = osäkert
p.g.a. delad färg, svart = saknas, blått = extra, lila rutor = facits stigare).

Några saker att känna till om skriptet:
- Jämförelsenyckeln tar bort "/W" och facits tillägg ("Vertikal", "wallmounted"). Därför jämförs
  VS1-S13-12 och VS1-S13-12/W som en post.
- Legenden i overlayn matchas mot raderna i mangder-filen som har längd > 0 eller skrafferat > 0,
  följt av "skrafferat". Om antalet inte stämmer avbryter skriptet.
- Facit kan ha egna namn. På 0122 kallar facit ett rör S2-P5-50 som är märkt **S2-G3-50** på
  ritningen, och där läste systemet rätt. Kontrollera ritningstexten innan du "rättar" sådant.
