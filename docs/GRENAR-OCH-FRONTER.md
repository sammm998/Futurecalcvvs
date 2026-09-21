# Grenar som kräver bevis, en flödesbudget per stråk, och fronter på varje rör

Datum 2026-09-11. Före: gate52 (commit a24ed19). Efter: gate53 (samma 33 blad, samma indata, körd blint och
poängsatt efteråt; `results/2026-09-11-topologi/gate53*.json`, `hashmanifest-gate53.json`).

## Vad som ändrades

1. **En råkontakt är ingen anslutning.** En onämnd linje som möter ett etiketterat stråk i en T fick stråkets
   namn så snart korsningen bara hade ett namn att ge. Nu måste grenen sluta i något som säger att den är ett
   rör - en ritad komponent, bladets kant, en annan pennas fortsättning eller bläck, eller ett stråk som redan
   bär samma namn. Slutar den i tomma luften blir den **tvetydig med korsningens namn som kandidat**: metrarna
   redovisas, som en fråga, inte som ett svar. Huvudstråket förblir ett rör genom korsningen.
2. **Flödesbudgeten är stråkets egen.** Hur långt ett namn får rinna förbi sina etiketter (2 gånger det
   etiketterna avgränsar) vägdes över hela pennan: ett stråk som vandrat in i ett väggnät tog de flödade
   metrarna av varje annat stråk på samma penna. Nu vägs varje sammanhängande stråk mot sina egna etiketter.
3. **Inget rör slutar tyst.** Varje kant på varje fysiskt rör får ett skäl (femton skäl i tre klasser:
   riktig gräns / förlust / öppet), i `pipe-extent-frontiers.json`, `frontier-overlay.pdf`, på varje rör i
   `physical-pipes.json`, i granskningsvyn (lagret "Var rören slutar" och varför-panelen). Summan av det oägda
   bortom fronterna är ett mått på underpropagering som följs utan referens.

## Vad det kostade och gav, blint mätt

| | gate52 | gate53 | Δ |
|---|---:|---:|---:|
| Täckning (ägda m / referens 6 245 m) | 79,31 % | 77,88 % | −1,43 pp (−89,4 m) |
| Falskt ägande (m utöver referens / referens) | 27,26 % | 25,71 % | −1,55 pp (−96,8 m) |
| Bekräftade meter, alla system | 6 816,7 | 6 623,8 | −192,9 |
| Tvetydiga meter, alla system | 182,9 | 309,4 | +126,5 |
| Beteckningar rätt / påhittade | 267 / 76 | 267 / 76 | 0 |
| Utsträckning FULL / PARTIAL / OVER / MISSED / WRONG (namn vikta) | 59 / 85 / 127 / 70 / 64 | 57 / 91 / 123 / 70 / 64 | |

Läsningen: 97 m som referensen inte har försvann ur de säkra mängderna, och 89 m som referensen har flyttade
från säkert till tvetydigt. Ingen beteckning kom till eller föll bort. Det är precis bytet doktrinen kräver -
fel säkerhet mot en fråga - och det redovisas som ett byte, inte som en vinst. (Skillnaden mellan −192,9
bekräftade och +126,5 tvetydiga är bryggade gap: tvetydiga meter räknar bara ritat bläck.)

Per blad (17 av 33 ändrades) finns i `gate53-rescore.json`. Största rörelserna:

| Blad | Δ ägt | Δ falskt | Vad som hände |
|---|---:|---:|---|
| V-50-1-A0412 | −30,2 | −8,0 | S1-P5-110: 36,4 → 11,9 m (ref 48,5) - grenar till fixturer utan ritad komponent blev frågor |
| V-50-1-A0123 | −5,3 | −18,5 | ett stråk in i byggnadsgeometri på rörpennan togs tillbaka |
| V-50-1-A0422 | −5,5 | −17,7 | samma |
| V-50-1-A0411 | −6,0 | −14,2 | samma |
| V-50-1-A0122 | −3,9 | −13,6 | samma |
| V-50-1-A0321 | 0 | +2,2 | S1-P5-160 2,6 → 4,8 m: ett namn referensen inte har (felläst siffra, samma svaghet som A0312); budgeten per stråk släppte en bit den gamla familjebudgeten höll |

## Beslut

**ACCEPT**, under uppdragets villkor: ändringen tar bort falskt ägande utan att en enda beteckning kommer
till eller faller bort, och det den kostar i täckning ligger kvar på bladet som tvetydigt med rätt kandidat -
det en person kan bekräfta med ett klick. Det som inte får glömmas: grenar till fixturer som saknar ritad
komponent på bladet (A0412) är nu frågor. Nästa bevis att lägga till är fixturer på arkitektens lager där
de finns som annan penna (redan `ENDS_AT_OTHER_INK`), och stigarsymboler som bevis vid grenens ände.

## Fronterna över korpusen (gate53)

3 908 fronter på 33 blad, 0 tysta rör. SYMBOL 1 892, VERTICAL 643, BROKEN_CONTINUITY 384,
AMBIGUOUS_JUNCTION 229, REAL_DN_BOUNDARY 224, FREE_END 157. Oägt bortom fronterna: 77,6 m - det är vad
samma penna fortsätter med utan namn, och det förklarar bara en liten del av de 1 380 m referensen har som
läsningen saknar. Resten ligger tidigare i kedjan: 98 av 365 beteckningar läses inte alls (siffran 5, `1:S0`),
och 384 brutna fortsättningar där bryggningen inte slöt gapet. Det är där nästa arbete sitter.

## Prov

`test_a_branch_needs_evidence_to_take_a_name.py` (sex prov), `test_boundary_rules.py` (grenprovet omskrivet),
`test_a_crossing_is_not_a_connection.py` (grenarna slutar i en apparat), `test_no_pipe_ends_silently.py`
(nio prov). 415 prov gröna.
