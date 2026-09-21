# Rörmängdningen: fem fel, och vad de kostade

Det här är redovisningen av åtgärdsomgången för rör, dimensioner, längder och stigare. Varje fel återskapades
av ett prov innan det rättades, och varje prov ligger kvar i `engine/tests/`. Inga beteckningar, koordinater
eller förväntade summor finns i motorn; facit och referensmarkeringar ligger utanför den och läses aldrig av
produktionskoden (kontamineringsspärren går PASS i varje körning).

## De fem felen

| # | Felet | Provet |
|---|-------|--------|
| 1 | En vågrät etikett blev stigare: `_risers_from_dn_rows` tappade vilka etiketter som var dess egna när identiteterna kompletterades och plockade upp hela bladets | `test_a_horizontal_label_is_not_a_riser.py` |
| 2 | En förbindelse mellan två dimensioner avgjordes av primitivnumreringen: samma ritning gav DN20 eller DN40 beroende på ritordning, båda som CONFIRMED | `test_a_connector_between_two_sizes_stays_ambiguous.py` |
| 3 | Två rör bredvid varandra blev ett: dubbellinjeprovet räknade hela segment vars mittpunkt låg nära (segmenteringsberoende) och den andra kanten lämnade ifrån sig alla sina meter, också där den gick sin egen väg | `test_two_pipes_side_by_side_are_two_pipes.py` |
| 4 | Ett lagernamn räckte över ett mellanrum: en familj med enigt lagernamn gav sitt namn åt allt i familjen, hur långt bort det än låg | `test_a_layer_name_does_not_reach_across_a_gap.py` |
| 5 | Skalstockens enhet tappades: `5000 mm` lästes som fem tusen meter och stocken förkastades; en gradering räknades dessutom i skillnaden mellan etiketternas tal i stället för i papperspunkter, så stockens egen ritade längd användes aldrig när den var skriven i mm eller cm | `test_the_scale_bar_keeps_its_unit.py` |

Därutöver två saker som hör till samma doktrin:

* **Förklaringslistan avgör vad som är en rörbeteckning.** Rumsnummer (`C 2004`) har samma form som en
  beteckning och blev rör med meter och stigare. En kod bladets egen lista aldrig nämner är ingen beteckning på
  det bladet. Regeln gäller bara en egen lista som känner bladet och stänger bara ute koder listan inte nämner
  alls. `test_the_legend_decides_what_names_a_pipe.py`
* **Meter mätta under en skala bladet inte avgjort är ett förslag.** Säger stämpel och skalstock emot varandra
  mäts bladet fortfarande - stocken är det bättre vittnet - men raden heter `SCALE_UNSETTLED`, inte
  `CONFIRMED`, och handlingens sammanställning räknar dem för sig (`m_under_an_unsettled_scale`). En lånad
  skala (`FROM_THE_SET`) namnger de blad den kommer från och märks `SCALE_FROM_THE_SET`.
  `test_an_unsettled_scale_is_not_a_confirmed_metre.py`

## Före/efter över hela referensomgången (33 blad, 6 245 m facit)

| | före | efter |
|---|---|---|
| Ägda meter | 4 993,0 | 4 953,0 |
| Täckning | 79,95 % | 79,31 % |
| Falska meter | 1 703,9 | 1 702,6 |
| Falskhet | 27,28 % | 27,26 % |
| Rätt beteckningar | 270 av 365 | 267 av 365 |
| Påhittade beteckningar | 80 | 76 |
| Meter utanför facits system | 180,6 | 161,1 |

**Rättningarna kostade 40 meter täckning.** Det är avsiktligt och det ska sägas rakt ut: det som togs bort var
meter som stämde med facit av fel skäl - en förbindelse som gissade rätt dimension, ett lagernamn som råkade
peka på rätt rör, en andra kant som lämnade ifrån sig hela sin längd fast bara en del låg bredvid. Doktrinen är
att AMBIGUOUS är ett giltigt svar och fel säkerhet inte är det, och då blir det här priset det rätta priset.
Fyra färre påhittade beteckningar och 19,5 meter mindre utanför facits system är det som kom tillbaka.

### Per ritning (de blad som rörde sig)

| ritning | facit | ägt före | ägt efter | diff | falskt före | falskt efter | diff |
|---|---|---|---|---|---|---|---|
| A | 213,7 | 211,2 | 183,0 | −28,2 | 1,5 | 2,3 | +0,8 |
| V-50-1-A0411 | 196,2 | 156,3 | 168,5 | **+12,2** | 41,0 | 41,0 | ±0 |
| V-50-1-A0421 | 129,9 | 117,6 | 111,1 | −6,6 | 138,8 | 140,0 | +1,2 |
| V-50-1-A0423 | 156,6 | 75,1 | 70,0 | −5,1 | 72,4 | 77,2 | +4,9 |
| V-50-1-B0122 | 517,2 | 323,7 | 319,6 | −4,2 | 109,4 | 110,5 | +1,1 |
| D | 112,9 | 108,0 | 104,0 | −4,0 | 4,4 | 4,3 | −0,0 |
| V-50-1-A0422 | 175,2 | 136,0 | 136,0 | ±0 | 87,2 | 80,9 | **−6,3** |
| V-50-1-A0122 | 321,1 | 315,5 | 315,9 | +0,4 | 182,8 | 180,9 | −1,9 |

Sheet A är den inskannade: nästan hela förlusten ligger där, och den är dubbellinjeprovets. Det som försvann
var meter som en andra kant lämnade ifrån sig fast den gick sin egen väg efter halva sträckan.

### Per system

| system | facit | ägt före | ägt efter | diff | falskt efter |
|---|---|---|---|---|---|
| VS | 2 504,6 | 1 974,0 | 1 974,0 | ±0 | 528,8 |
| KV | 1 327,2 | 1 189,1 | 1 182,9 | −6,2 | 452,9 |
| VV | 1 052,4 | 814,2 | 808,2 | −6,0 | 312,5 |
| S | 805,3 | 599,0 | 574,8 | −24,2 | 200,1 |
| VVC | 269,5 | 202,7 | 202,7 | ±0 | 113,0 |
| VP | 189,1 | 165,5 | 165,5 | ±0 | 61,7 |
| SF | 73,9 | 31,6 | 32,0 | +0,4 | 33,6 |
| FJV | 21,2 | 15,1 | 11,1 | −4,0 | 0,0 |

### Per dimension (de som rörde sig)

| DN | facit | ägt före | ägt efter | diff | falskt före | falskt efter | diff |
|---|---|---|---|---|---|---|---|
| 110 | 475,7 | 345,1 | 331,5 | −13,6 | 58,2 | 45,8 | **−12,4** |
| 16 | 1 677,6 | 1 502,3 | 1 490,1 | −12,2 | 448,1 | 448,1 | ±0 |
| 160 | 293,0 | 200,7 | 191,6 | −9,1 | 19,9 | 19,9 | ±0 |
| 75 | 105,8 | 87,2 | 86,1 | −1,1 | 89,1 | 102,6 | +13,5 |
| utan dimension | 22,6 | 15,5 | 11,5 | −4,0 | 69,6 | 67,6 | −2,0 |

DN 75 blev sämre: 13,5 meter som förut hamnade i en annan rad ligger nu i 75. Det är dubbellinjeprovets
avigsida på ett blad där två 75-rör går bredvid varandra en bit och sedan skiljs åt, och det är inte rättat.

## V-50-1-A0312 mot Bluebeam-facit (STEG 4)

| beteckning | facit | före | efter |
|---|---|---|---|
| KV01-X31-16 | 55,9 | 51,7 | 51,7 |
| KV01-X7-25-W40 | 2,2 | 5,3 | 5,3 |
| S01-P3-160 | – | 7,8 | 7,8 |
| S01-P5-110 | 10,3 | 14,0 | 13,0 |
| S01-P5-160 | 12,3 | 0,8 | 0,8 |
| VS11-S13-35-F60 | 14,1 | 7,2 | 7,2 |
| VS21-S13-15-F50 | 81,2 | 106,7 | 106,7 |
| VS21-S13-22-F60 | 45,9 | 10,4 | 10,4 |
| VV01-X31-16 | 28,6 | 24,1 | 24,1 |
| summa | 262,6 | 233,9 | 232,9 |

De fem rättningarna rör inte det här bladet, och det ska sägas: **A0312 är inte löst.** Vad mätningen visar:

* VS2x-lagret har 112,7 m ritat bläck. Av det äger `VS21-S13-15-F50` 74,9 m, `VS21-S13-22-F60` 7,4 m och
  30,0 m ägs av ingen och redovisas som onämnt.
* Rören är streckade och varje rör bryggar ungefär 29 % gap - jämnt över alla rör, vilket är streckmönstret och
  inte en överbryggning.
* De två lodräta stråken i kolumnen x≈630-645 går genom hela planen. Deras fulla utsträckning är ≈45,8 m, vilket
  är precis facits 45,9 m för `VS21-S13-22-F60`. Läsningen når bara den del som ligger mellan de två etiketter
  som pekar på dem (10,4 m); resten stannar onämnd därför att kedjan inte får korsa dimensionsgränsen mot
  15-F50 utan att ritningen säger det.
* `S01-P3-160` (7,8 m) mot facits `S01-P5-160` (12,3 m) är samma rör läst med fel siffra. Samma blad läser
  `1:S0` i stämpeln på ritning D - femman är den här omgångens svaga tecken.

Vad som återstår är alltså inte en gissning som ska tas bort utan två saker som ska läsas: siffran 5 i den här
stilen, och dimensionsgränsen mellan 22 och 15 (etiketternas `CL`-höjd skiljer dem åt - `CL 3600` mot
`CL 4000`). Ingetdera är rättat här, och ingen intern kontroll som säger VALID ändrar på det.

## Så körs jämförelsen om

Motorn körs över omgången utan att facit finns i processen, och poängsättningen är ett eget steg efteråt:

    python <scratchpad>/gate_run.py <ut>.json      # läser bara ritningarna
    python <scratchpad>/rescore.py <ut>.json       # jämför mot facit
    python <scratchpad>/fore_efter.py              # före/efter per ritning, system och dimension
