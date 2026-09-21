# VVS-lathund: ritningsläsning, analys och mängdning

Det här är beställarens egen standard för hur en svensk VVS-ritning ska läsas och mängdas. Den är inte en
beskrivning av vad motorn gör i dag; den är måttstocken motorn mäts mot. Där koden och lathunden säger olika
saker är det koden som ska ändras, eller lathunden som ska citeras i en regel som förklarar varför.

**Huvudregeln, som går före allt annat i det här dokumentet:** ritningens egen legend, förklaringsruta, slips,
tekniska beskrivning och senaste revision gäller alltid före lathunden. Går en beteckning eller linje inte att
tolka säkert ska den märkas som osäker med skäl — aldrig gissas.

---

## Var motorn står mot lathunden

En ärlig avstämning, punkt för punkt. `✓` betyder byggt och provat, `~` delvis, `✗` inte byggt.

| § | Krav | Läge | Var |
|---|------|------|-----|
| 1 | Läs ritningshuvud, revision, status, skala före geometrin | ✓ | skala i `measure/scale.py`; nummer, revision, status, datum och hus ur namnrutan i `handling.py` |
| 2 | Bryt upp beteckningen i system + material + dimension + isolering | ✓ | `ownership.identity_from_text` |
| 3 D | Streckad linje: mät hela sträckan, inte strecken | ✓ | `representation`, DASH_GAP_MAX |
| 3 I/J | Två eller tre parallella rör är två eller tre mängder | ~ | undersöks |
| 3 K/L | Korsning är inte automatiskt anslutning | ✓ | korsningsregeln i `ownership._resolve_family`: en linje som passerar går in på ena sidan av noden och ut på den andra; en stump kortare än kontakttoleransen bär aldrig ett namn |
| 3 S | Dela mängden vid dimensionsbyte | ✓ | DN-frontier i `ownership` |
| 3 T | Dela mängden vid materialbyte | ✓ | ingår i identitetens stam |
| 3 U/V/W | Befintligt, rivning och nytt skiljs åt | ✗ | **saknas** |
| 4 | Systembeteckningar | ✓ | ur bladets egen lista |
| 5 | Materialbeteckningar | ✓ | ur bladets egen lista |
| 6 | Dimensioner i alla skrivsätt (DN, Ø, d, 22x1,0) | ~ | DN och tal ✓, `22x1,0` ~ |
| 7 | Höjdbeteckningar CL, VG, FG, ÖFG, UK | ✓ | `_elevations` |
| 8 | Avloppsfall ur VG-skillnad | ~ | höjder läses, fall räknas ej |
| 9 | Mängda efter system + material + dimension | ✓ | mängdtabellen |
| 10 | Dela vid varje byte av system/material/dimension/status | ~ | status saknas |
| 11 | Mät centrumlinjen längs vägen | ✓ | summan av primitiver |
| 12 | Streckade rör mäts helt | ✓ | |
| 13 | Vertikala rör: stammar, uppstick, nedstick | ~ | räknas som antal, höjd anges av användaren |
| 14/15 | Fram + retur, KV + VV + VVC är separata rör | ~ | undersöks |
| 16 | Korsning eller anslutning | ✓ | |
| 17 | Fittings mängdas separat | ✗ | **saknas** |
| 18 | Ventiler: typ + dimension + antal | ~ | känns igen som komponenter, räknas ej |
| 19 | Komponenter | ~ | dito |
| 20 | Genomföringar, hylsor, brandtätning | ✗ | **saknas** |
| 21 | Isolering mängdas separat | ~ | koden bärs i identiteten, egen post saknas |
| 22 | Status: nytt, befintligt, rivs, flyttas | ✗ | **saknas** |
| 23 | Överlapp mellan ritningar räknas en gång | ~ | projektanalysen håller husen isär och summerar per hus; överlapp mellan blad i samma hus prövas ej |
| 24 | Dubbel CAD-geometri räknas en gång | ✓ | sammanfallande primitiver slås ihop |
| 25 | Mät inte längd ur ett schema | ~ | skala krävs, schema känns ej igen |
| 26 | Kalibrera mot skalstock | ✓ | `measure/scale.py` |
| 27 | Nettomängd | ✓ | |
| 28 | Kalkylmängd = netto + spill | ✓ | kalkylen i `backend/app/calc.py`: spill i procent, utskrivet per rad |
| 29 | Beställningsmängd = handelslängder | ✗ | **saknas** |
| 31 | Verifierad / härledd / osäker | ✓ | CONFIRMED / flödad / AMBIGUOUS |
| 32 | De vanligaste mängdfelen | ~ | se raderna ovan |
| 36 | Ändra aldrig siffran för att få summan att stämma | ✓ | avstämningen redovisar avvikelsen |

---

## Guldregeln

> Mät inte en linje. Mät ett identifierat rör.

Ett rör är rätt först när ritning, revision, status, system, material, dimension, geometri, höjd och
anslutningar hänger ihop. Varje meter ska gå att peka ut på ritningen.

## Slutregeln

Stämmer inte en totalsumma ska siffrorna inte ändras för att tvinga fram rätt total. Fel ska hittas som en
faktisk rörsträcka som saknas, räknats dubbelt, fått fel system, fel dimension eller fel material.

---

## Linjestilar och vad de kan betyda

Betydelsen bestäms alltid av det aktuella bladets legend. Det här är de visuella huvudtyperna som måste kännas
igen som *former*, innan legenden säger vad de betyder.

| Utseende | Att tänka |
|---|---|
| `────────────` | Heldragen ledning — legenden avgör status och höjd |
| `━━━━━━━━━━━━` | Tjock ledning — ofta huvudstråk eller större vikt, men legenden avgör |
| `- - - - - - -` | Streckad — dold, annan höjd eller rivning beroende på projekt |
| `— · — · — · —` | Punktstreckad — projektspecifik status eller höjd |
| `════════════` | Dubbel linje — stor dimension, mantel eller skyddsrör |
| `──────┬──────` | Förgrening, T-anslutning |
| `──────  ────` med korsande linje | Passerande rör — normalt ingen gren |
| `──────→` | Flöde, fall eller fortsättning beroende på sammanhang |
| `────┐ ↑` / `────┐ ↓` | Uppgående respektive nedgående rör eller stam |
| `KV ─── / VV ─── / VVC ───` | Tre separata rör trots gemensamt stråk |
| `VS-T ─── / VS-R ───` | Fram och retur — två separata mängder |
| `110 ─── 75 ───` | Dimensionsbyte — dela mängdposten |
| `P2 ─── R8 ───` | Materialbyte — dela mängdposten |
| mediarör inuti större linje | Skyddsrör eller förisolerat — kan bli två mängdposter |

---

## Systembeteckningar

Projektets legend gäller alltid. Det här är vad de brukar betyda.

**Tappvatten** KV kallvatten (KV1–KV4 olika behandlingsgrader) · VV varmvatten (VV1–VV3) · VVC
varmvattencirkulation

**Avlopp** S spillvatten (S1, S2, S3 …) · D/DV dagvatten · DR dränvatten · SD kombinerat · SF fettavskiljning ·
SO oljeavskiljning · SP processpill · SI infekterat

**Värme** FV fjärrvärme · VP primär · VS sekundär · VÅ värmeåtervinning

**Kyla** FK fjärrkyla · KP primär köldbärare · KB sekundär köldbärare · KM köldmedium · KY kylmedel · VKÅ
kylåtervinning

**Brand** BR1 sprinkler våtrör · BR2 torrör · BR3 förutlösning · BPL brandpost · STL stigarledning · VDS
vattendimma · GSS gassläck

**Övrigt** ÅY ånga · K kondensat · BEV bevattning · NKV nödkylvatten

## Materialfamiljer

A ABS · C PVC · E PE/PEM · G gjutjärn · K koppar · P PP · R rostfritt · S stål · X PEX · Y projektspecifikt

`P2` betyder inte samma produkt i alla projekt: `P` är familjen, `2` är variantens nummer enligt projektet.

## Höjder

CL centrumlinje · VG vattengång (självfallsavlopp) · FG färdigt golv · ÖFG över färdigt golv · UK underkant ·
ÖK överkant · ANSL anslutning · INK inkoppling på befintligt

Fall räknas som höjdskillnad genom längd: VG +1,100 till VG +1,000 på 10 m är 0,100/10 = 1 % = 10 ‰.
Kontrollera att VG sjunker i flödesriktningen.

## Ventiler

AV avstängning · BV backventil · RV regler/injustering · SV styrventil · SÄV säkerhet · BLV blandning ·
TRV tryckreducering · ALV avluftning. Mängdas som typ + dimension + antal.

## Komponenter

P pump · VVX värmeväxlare · VVB varmvattenberedare · EXP expansionskärl · ACK ackumulatortank · SHG shuntgrupp ·
RAD radiator · KON konvektor · GB/Bxxx golvbrunn · GR golvränna · TS tvättställ · VK wc · UR urinal ·
DB diskbänk · UB utslagsback · BL blandare · VUK vattenutkastare

## De vanligaste mängdfelen

Fel skala · dubbla CAD-linjer · befintligt räknat som nytt · rivning räknat som nytt · returledning glömd ·
VVC glömd · vertikalt rör glömt · uppstick glömt · stam glömd · dimensionsbyte missat · materialbyte missat ·
streckad linje felmätt · symbol misstolkad som rör · hänvisningslinje misstolkad som rör · överlapp mellan
delritningar · samma rör räknat två gånger · skyddsrör glömt · genomföring glömd · isolering glömd ·
komponentanslutning glömd

## Slutkontroll

1. **Geometri** — har varje verkligt rör mätts exakt en gång?
2. **System** — har varje rör rätt system?
3. **Material och dimension** — är alla byten registrerade?
4. **Topologi** — är grenar, stammar och anslutningar logiska?
5. **Dokument** — är legend, revision, detaljer, sektioner och teknisk beskrivning kontrollerade?
