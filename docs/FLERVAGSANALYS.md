# Flervägsanalys och granskning

En läsning kan ha fel på ett sätt den inte kan se. En ledarlinje som landar på fel linje namnger fel ledning,
och ingenting inuti den läsningen säger emot. Därför läses ritningen om längs vägar som använder andra bevis,
och svaren ställs bredvid varandra. Där två vägar namnger samma geometri på samma sätt är läsningen bekräftad.
Där de namnger den olika blir ledningen tvetydig och lämnar mängden. Där bara en väg nådde fram sägs det rent ut
i stället för att gömmas inne i en siffra.

Detta körs på varje sida efter den första läsningen, inne i motorn — inga externa anrop, inget som kan svara
olika två gånger. Resultatet ligger i `route-crosscheck.json` och `reading-review.json`, och i API:t under
`crosscheck` och `reading_review`.

## Vägarna

| väg | bevis | oberoende |
|---|---|---|
| `pointing` | etikettens egen ledarlinje, följd till den geometri den rör eller den symbol den slutar i | ja |
| `writing` | etiketten skriven längs ledningen — parallell, bredvid, täckande, och ensam på den | ja |
| `closure` | en identitet som fortsätter genom en förgrening, eller över ett lager som namnger ett system | nej — det är den första läsningen buren vidare |

`closure` räknas separat just därför att den inte är en andra läsning. Meter som bara nåtts den vägen redovisas
som `closure_only_m`, så att skillnaden mellan *vad ritningen sa* och *vad vi slöt oss till* alltid syns.

## Reglerna mellan vägarna

- En väg får **lägga till** en ledning som de andra missade.
- En väg får **motsäga** en ledning — då blir den tvetydig, inte mätt.
- En väg får **aldrig döpa om** en ledning en annan väg bekräftat. Gör den det är läsningarna inte längre
  oberoende, och då är korsvalideringen värdelös.

## Vad som prövades och förkastades

**`reach` — en ledare som pekar men stannar strax före ledningen.** Mätt på facitritningarna: den plockar fel
linje ur ett parallellt knippe, eftersom "vilken ledning" när spetsen inte rör något avgörs av avstånd allena —
det enda den här motorn aldrig får göra. En sådan ledare rapporteras i stället som oplacerad, med sitt skäl.

**`writing` utan tröskel.** På ritning A namngav den en enda ledning och namngav den fel (`S3-R8-75` skriven
bredvid en DN110-ledning), vilket flyttade 3,8 m till tvetydigt och fördubblade felet. En ritning som namnger
genom att skriva längs ledningarna gör det för många etiketter, inte för en. Vägen används därför bara när minst
tre ledningar namnges så och de utgör minst 15 % av sidans röretiketter.

## Granskningen

Två svep efter varje läsning, som svarar på frågan "vad missades och varför":

- **Ledningar som ingen väg namngav** — samlade till hela stråk med längd och koordinat, så att en läsare kan
  hitta dem på pappret.
- **Röretiketter som ingen väg placerade** — med skälet från fästningen och antalet tecken igenkännaren inte
  kunde läsa.

Plus täckning: `named_m`, `ambiguous_m`, `unnamed_m`, `coverage_pct`, och fördelningen `corroborated_m` /
`one_reading_m` / `closure_only_m` / `in_conflict_m`.

Exempel från stilbiblioteket (samma dag, samma kod):

| sida | täckning | namngivet | oplacerade etiketter, vanligaste skäl |
|---|---|---|---|
| facit A | 100 % | 190,2 m | 11 av 125 — 7 utan ledare |
| Plan 09 Del 42 | 55 % | 14,4 m | 17 av 31 — 14 utan ledare |
| Hus A s.5 (utan lager) | 16 % | 74,9 m | 77 av 105 — 39 ledarspetsar rör ingen rörgeometri, 28 staplade etiketter utan lagerstöd |
| Badskon 1 s.1 | 37 % | 137,9 m | 171 av 231 — 79 ledarspetsar rör inget, 58 staplade |

## Vad de här siffrorna pekar på härnäst

Granskningen namnger arbetsordningen själv. De två skälen som dominerar över alla stilar är:

1. `leader_endpoint_touches_no_pipe_geometry` — ledaren pekar men spetsen rör inget. Får inte lösas med
   närhet (se `reach` ovan); måste lösas med struktur: symbolen spetsen står i, gapet i en streckad linje,
   eller ledningsänden vid markören.
2. `multi_row_no_compatible_layer_group` — en staplad etikett med flera rader mot ett knippe parallella
   ledningar, där lagernamnen inte skiljer raderna åt. Ordningskonventionen finns (på arket vars lager *kan*
   skilja dem ligger 8 av 9 staplar i samma ordning som ledningarna korsas) men riktningen är inte konstant
   (7 nära-först, 1 fjärran-först), så att tilldela på den konventionen byter identitet mellan system på var
   åttonde. Lämnas oavgjord tills en bättre grund finns.
