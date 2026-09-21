# Label grammars observed in practice

Empirical survey of pipe-label conventions across nine Swedish VVS design
offices (Vinnergi, Sweco, PD Andersson, PQR, Rejlers, VVS Konsulterna, Bengt
Dahlgren, Sweco Systems, Bengt Dahlgren industrial) on real bygghandlingar and
relationshandlingar, 2018–2026. This is what the caveat "praxis differs per
consultant" means concretely.

## The invariant, and everything that varies

Every office writes the label as dash-separated positions. Two things never
move: **position 1 is the system (plus a running number), and the last numeric
position is the dimension.** Everything between — how many fields, whether
material is a letter code, a number, or absent, whether insulation is a suffix
— is defined per project in the sheet's FÖRKLARINGAR.

Observed variants, all meaning "a pipe of system X, dimension Y":

| Form | Example | Office pattern |
|---|---|---|
| `SYS-DIM` | `KV-22` | textbook short form |
| `SYSn-MAT-DIM` | `VS1-S13-12` | alphanumeric material (S13, X31, P2) |
| `SYSn-MAT-DIM/ISOL` | `VS1-S13-12/W` | insulation letter suffix |
| `SYSnn-MAT-DIM-ISOLmm` | `VV01-X7-25-F60` | insulation type + thickness in mm |
| `SYSnn-MAT-DIM-ISOL-YTB` | `KV01-E2-54-K2-A` | five positions, ytbeklädnad last |
| `SYSnnn-MM-DIM` | `VS111-55-16`, `S101-52-75` | two-digit numeric material codes |
| `SYSn-MM-DIM/SER/YTB` | `VS2-13-89/S1A/A` | insulation series + cladding after slash |
| `SYSnn-DIM` | `KV11-25` | material folded into the running number (11 = ALU-PEX, 12 = rör-i-rör, 13 = koppar) |
| digits packed in the number | `VS212-28` | positional digits: VS + subsystem 2 + material 1 + insulation 2 |
| four-digit numbers | `VV0175-32` | löpnummer encodes the stam/shaft |

Practical consequences:

- **Tokenize by dashes; do not pattern-match one grammar.** First token =
  system + number, last plain-number token = dimension, middle tokens =
  material/quality, slash or trailing suffix = insulation/cladding.
- **The same string means different things on different projects.** `S13` is a
  material code (thin-wall steel) on one project and a system+number
  (spillvatten 13) on another. Only the sheet's legend disambiguates.
- The legend itself is drawn as a positional key (`POS 1 AVSER SYSTEM … POS 5
  AVSER DIMENSION` or an exploded sample label). One project stated it
  outright: *"FULLSTÄNDIG RITNINGSBETECKNING FINNS PÅ RITNING V50.1-0001"* —
  the full legend lives on a dedicated drawing, and sheets carry excerpts.

## What the running number means — observed readings

All of these are real, sometimes several at once on one project:

| Reading | Example |
|---|---|
| material variant | `KV11` ALU-PEX vs `KV12` rör-i-rör vs `KV13` koppar |
| subsystem by temperature | `VS1` 55/30°C, `VS2` radiatorer, `VS3` ventilation, `VS4` golvvärme, `VS5` markvärme |
| usage/location | `KV 1` allmänt, `2` kök/café, `3` lab |
| water treatment | `KV01` tappkallvatten, `KV02` kombiugnar (softened); `KVM` avhärdat |
| wastewater material | hospital: `S1` gjutjärn, `S2` PEH, `S4` CU |
| wastewater location | `S1` i mark, `S2` inomhus, `S3` storkök |
| acoustic class | `S12` ljuddämpande |
| stam/shaft number | `VV0175` = VV, stam 01, 75 |

Suffixes seen: `L` = luftningsledning (`SA01L`), `SF` = spillvatten till
fettavskiljare, `ST`/`STT` = stigar-/tömningsledning, `SS` = spillvattenstam.

## Project-defined system codes beyond the standard table

Legends freely invent systems the SIS table does not have. Observed: `RAD1`
/`RAD2` (radiator/luftvärme circuits as systems), `FJV` fjärrvärme, `TL`
tryckluft, `VA1` värmeåtervinning badvatten, `RP1–RP3` rörpost (pneumatic
tube), `TR` tomrör, and in hospitals a full medical-gas family: `L1`
andningsluft, `L3` instrumentluft, `G2` oxygen, `G3` lustgas, `G6` gasutlopp,
`G75` koldioxid. Treat the system table as open, seeded by the standard.

## Components and equipment

Component codes follow `CODE + löpnummer [- size]`, and one office documents
the internal structure explicitly: `AV201-50` = beteckning AV, kategori 2,
typ/fabrikat 01, storlek 50. Quantity multipliers prefix the code (`2xAV1-22`,
`4xBL141`), and `+` chains components on one leader (`RV61-10+RV62-15`).

Heaters are annotated by **product name + duty triplet** — power, flow, valve
preset — in any of several unit styles:

```
Novello 22-310   247 W/0,0040 l/s/Kv=0,06
P22-226          600 W, 34 l/h  KV=0,17
RK LB 22-608     Kv=0,076  q=24 l/h  420 W
LSK-200x242x1000-M  14 l/h  kv=0.05
RV63-20          614 l/h  10 kPa
```

Radiator *connection types* get their own code series (`RAD1`–`RAD5`, "vid
fönster med bröstning" etc.) with a detail-drawing reference. Valve preset
values appear as `Förinställningsvärde SV88-XX/X,XXX` (dimension / Kv / flow).

## Recurring drawing tables

Real sheets carry small tables that are quantities in their own right:

- **SCHAKTTABELL / STAMTABELL** — per shaft or riser: dimensions of each system
  on each floor. A matrix, one row per plan, one column per system.
- **KOPPLINGSLEDNINGAR** — default connection dimensions per fixture type,
  applied wherever no label is drawn. Column sets vary (KV/VV/S, plus RAD, plus
  medical gases in hospitals).
- **AVLOPPSANSLUTNINGAR** — default waste connections (WC 110, tvättställ 75–50…).
- per-plan **UK konvektor** mounting heights; per-plan KB/KV/VS dimension tables.

Multi-system stacks also appear inline: a row of system codes over a row of
dimensions (`KV VVC VV KB2 KB2 D3` over `54 22 42 76 76 75`), one column per pipe.

Full-designation stacks are the other multi-row form: one complete designation
per row in a single label block (`VS1-S13-12/W` over `VS1-S13-35/W`;
`KV1-X7-40/W` / `VV1-X7-40/W` / `VVC1-X7-25/W` over a shared `CL 3400 ÖFG`).
Each row is a separate installation — a repeated system code with a different
dimension is two runs, not a duplicate — and a bottom `CL`/`cl`/`VG` row is a
level applying to all rows above it, not a designation. The split form (system
code over an underlined bare dimension) clusters at the start and end of a run;
the boxed form with a level row is the mid-run norm.

## Narrative rules that live as sheet notes

Slope and installation requirements appear as free text, not symbols:
horizontal spillvatten min 1% fall (Ø110), 1.5% (Ø75), 2% to fettavskiljare
(another office: 15‰ / 30‰ for samlingsledningar); vertical-to-horizontal
transitions with `2x45°` bends; *Säker Vatteninstallation 2021* invoked as an
installation standard; `VV/VVC SAMISOLERAS` (co-insulated); asterisk
conventions like `CL xxxx*` = same dimension as the branch, insulation F50;
`c/c 3000` support spacing; fixpoints and expansion sleeves per stam.

## Demolition and scope boundaries

Ombyggnad sets add a vocabulary of their own, declared per sheet:

- `X` marks on a line = **ledning som rivs** (to be demolished); a dashed
  rectangle = **ARBETSOMRÅDE** (work-area boundary); `TS DEM`, `DEM` suffixes.
- Demolition sheets are separate drawings, suffixed `-D` (e.g. `R1402-D`,
  DEMONTERING in the title block).
- `PR` = proppning (capped), `INK` = inkoppling, `ANSL` = anslutning — the
  new/existing boundary.
- **`PB` = ingår i prefab badrum, `PWC` = prefab WC**: pipework inside prefab
  units is factory scope, not site takeoff. Same logic as `IL(BE)` — the
  parenthesised contractor code moves an item to another contract.

## Line-style legends are also per-project

The standard four-style table (see `data/line_types.json`) holds in spirit, but
sheets define their own wording and may shift the reference plane, e.g. one
office's FÖRESKRIFTER: heldragen = ovan golv, streckad = i golvbjälklag,
streckprickad = under tak, dubbelprickad = i takbjälklag. Read the sheet's own
key before assigning elevations.

## Drawing numbers and title blocks in the wild

Observed numbering styles for the *same kind* of VVS plan: `V-50-1-A0122`,
`W-50-1-110A1`, `W--50-1-0101113`, `V50.1-0843`, `V-50-1-1091`, `W-50-1-0121`,
`R1402-D` (plan+del+revision letter, discipline in a separate box), and full
KKS-style plant codes (`R9UHA10-CLB001-001`) on industrial jobs. Discipline
appears as `V`, `W`, or `VS`. Separators vary (`-`, `--`, `.`); parse
defensively and prefer the title-block fields over the filename.

Statuses seen beyond the standard list: GODKÄND (approval stamp on a
relationshandling), municipal registration stamps (`Dnr SBN … Ankom …`) added
by the building authority along the sheet edge.

---

# Second survey pass: 21 additional sheets, deeper findings

Verified against a second batch of sheets from the same nine offices (plans,
one section, hospital new-works, industrial, residential relationshandlingar).

## Stroke notation: verified, with traps

The over/underline notation for slab penetration is now **confirmed on three
offices**, in all four states, including stacked dimensions where each figure
carries its own stroke (`S2-P5 / 110̲ / 1̄60` — 110 rises only, 160 drops only).
Two things an implementer must know:

- **The shelf-line trap.** Offices that write labels on leader shelves put a
  thin horizontal line under *every* text row — system row and dimension row
  alike. The slab stroke is the *extra, visibly heavier and shorter* bar
  hugging just the dimension figure. A naive underline detector classifies
  every label on the sheet as "rises only". Boxed (framed) labels never carry
  strokes; strokes live on the shelf-style labels at risers.
- **Some offices do not use it at all.** One (industrial/E.ON) writes explicit
  levels instead — `CL+17.650` centreline levels on pressure pipes, `VG+11.435`
  inverts along gravity runs — and encodes nothing in strokes. Absence of
  strokes is a convention, not missing data; check which regime the sheet uses.
- In one office's KOPPLINGSLEDNINGAR default table every dimension figure
  carries both strokes (contained within the storey) — the notation reaches
  into legend tables, not just the plan.

## Parentheses carry scope semantics

Three distinct parenthesis conventions, all on real sheets:

- **`( )` around a code = befintligt.** Hospital legend states it outright:
  `( ) AVSER BEFINTLIGT`. So `(S1)`, `(KV-15)`, `(RB28)` are existing
  installations — context for the work, never new quantity. This is the
  ombyggnad counterpart of `BEF`.
- **`(PB)` / `(PWC)` suffix = inside a prefab bathroom/WC.** `S-STAM (PB)`,
  `KOPPLINGSSKÅP (PB)`, `ANSL. PWC` — the element is factory scope. Extends the
  bare PB/PWC markers already recorded.
- **`(L)` after a dimension = avloppsluftare** (legend-defined), and the
  luftning marker also appears as a **letter fused to the dimension figure**:
  `110L`, `110V`, `100V` under a normal system row. Parsers must accept a
  trailing L/V on the dimension token. Material codes get L-variants too:
  `S11L`, `S12L`, `S13L` (vent-line variant of the same pipe material).

## Component numbers encode the served system

The hospital legend defines it formally: the digits after a valve code select
the system family — `AV1` tappvatten, `AV2` värme, `AV41` andningsluft, `AV51/
AV52` oxygen, `AV53` lustgas, `AV8` köldbärare; same for `SV42/SV48/SV81/SV82/
SV88` and pressure-independent `SVM2/SVM48`. Other offices show the same idea
as praxis: `x2xx` codes on tappvatten and `x6xx` on VS stations (`AV201-15` vs
`SV601-32`), `FS2xx` tap-water vs `FS6xx` heating manifold cabinets — which is
also how a legend that defines `FSxxx` twice (both "fördelarskåp, VS" and
"fördelarskåp, tappvatten") gets resolved: by the instance's first digit.

Preset-value annotation formats are legend-defined per family:
`SV88-XX/X,XX` = dim / Kv-värde – flöde l/h; `SVM2-XX/X,XX` = dim – flöde l/h –
inj.värde. Also seen: `RV21-10/74 l/h`, `q= 0.0206 l/s / Kv= 0.24` boxed pairs,
and duty lines in l/s where other offices use l/h.

## Heater product families — the worst collision class

Every office annotates radiators/convectors as `FAMILY+type-size` plus a duty
line, and the family codes freely collide with system and fixture codes:

| Family seen | Office | Collides with |
|---|---|---|
| `RAD101-10-400x2300` (+ `HHHxLLLL` geometry) | Vinnergi | RAD-as-system, RAD-as-connection-type |
| `KON22-286-3000`, `KON34-…` | Rejlers | — |
| `H10-600-2000` (hygienradiator), `TP11-411 V4` | Rejlers | — |
| `M10-418/0,09` | Sweco hospital | — |
| `P22-226`, `LSK-200x242x1000-M` | Wästbygg, BD | P2x material codes |
| `I40H 30-610 kv=0.05` | Sweco Hyllie | — |
| **`KV11-612` 505 W, 29 l/h** | Wästbygg | **`KV11` cold-water pipe label!** |
| **`VK 11-3012` Kv=0,04 q=13 l/h 230 W** | PD Andersson | **`VK` = vattenklosett!** |

Disambiguation that works: a heater label carries a duty line (`W`, `l/h` or
`l/s`, `Kv`) and its "dimension" is implausible as DN (612, 3012, 2300…).
Treat any `CODE-nnn[-…]` with a W/flow/Kv line as equipment, not pipe.

## The running number can encode ROUTING

One legend (Sweco Systems förskola) selects the material digit by where the
pipe runs, within one system: synliga ledningar `KV31/VV31`; i vägg, golv och
ovan fast undertak `KV21/VV21`; ovan demonterbart undertak `KV12/VV12`. So the
digit answers "how is it routed/serviceable", not "what system". Add this to
the open set of number readings — and note the same office pairs it with
`ANSL1-4-DB`-style **connection-type codes**: `ANSL1-2-DM` (diskmaskin, vatten
och avlopp), `ANSL1-2-KOK`, `ANSL1-2-TM`, `ANSL1-SKB` (skötbord) — a numbered
taxonomy of fixture connections, a fourth reading of ANSL.

## Insulation tokens, systematically

- `-F` = mineralull, `-W` = mineralull diffusionstät, digits = thickness in mm
  (`F50…F80`, `W40`). Usage is systematic where defined: cold water gets `W`
  (condensation-tight), heating/hot water gets `F`.
- `VV01 & VVC01 SAMISOLERAS` — the circulation pipe carries no insulation token
  because it shares the VV insulation.
- The slash suffix can pack insulation *and* cladding: `/W` vs `/WC`
  (mineralull + mönsterpräglad alu-plåt). Split the suffix per letter against
  the legend's ISOLERING and YTBEKLÄDNAD lists.
- Sheets use tokens their own legend never defines (`W40`/`F60` undefined on
  the E.ON sheets; `K2` appears as the *sample's* insulation token while being
  a *material* token in real labels) — position in the chain, not vocabulary,
  is what disambiguates.
- District heating: `FJV01-E4-90-7SF140` — post-dimension token plausibly the
  preinsulated-pipe casing series (single observation, unverified); plain
  `FJV01-E4-90` coexists on the same run.

## Cross-sheet ownership of quantities

Notes on real sheets move whole quantity groups to sibling drawings:

- *"KOPPLINGSLEDNINGAR I GOLV MELLAN FÖRDELARSKÅP OCH STORKÖKSUTRUSTNING ÄR
  REDOVISADE PÅ RITNINGAR: V-52-1-A0122…"* — in-floor connection runs live on
  the **undergrupp 52** sheet family for the same plan/del; risers to the floor
  above live on the plan-2 sheets. A takeoff reading only the 50-series plan
  silently drops both groups.
- Overview sheets (`RÖRSYSTEM` at 1:100) coexist with del-sheets at 1:50;
  match lines carry the neighbour sheet's number (`KONNEKTION DEL A1/DEL A2`).
- The legend may live on a dedicated drawing; legend blocks may be keyed by
  BSAB element codes (`53.BB SPILLVATTENSYSTEM`, `PN RÖRLEDNINGAR`) — usable
  for typing legend sections mechanically.

## Section drawings (kategori -2)

On a sektion the pipes are drawn **double-line, with rounded elbows and almost
no labels**: risers as parallel-line bundles, per-storey `FG +x.xx` datums,
`EI60` compartment lines along every slab *and* vertical shaft wall. Sections
resolve the geometry the plan's stroke notation implies; quantities and system
attribution still come from the plans.

## Default tables, extended

Beyond KOPPLINGSLEDNINGAR/AVLOPPSANSLUTNINGAR variants (including a lead line
that names a full default label: *"FÖLJANDE GÄLLER OM EJ ANNAT ANGES:
RAD1-X31-16, KV1/VV1-X31-16"*, and parenthesised `16(15)`/`16(12)` cells whose
meaning no sheet defines), two new table classes:

- **Room-type → product set**: `WC: VK1, TS1 / RWC: VK2, TS2 / DUSCH: BL1, B1 /
  STÄD: UB1, B2 / PENTRY: BL2, ANSL DB, ANSL DM` — fixtures per room label,
  applied wherever rooms are tagged but fixtures unlabelled.
- **Per-plan support/riser tables**: stam-to-first-support distances per floor
  and system, `UK konvektor` mounting heights per floor band.

Recurring free-text micro-notes that carry quantity meaning: `AVSLUTAS PÅ
SLING 2,5m` (connection ends in a coiled spare loop of stated length), `DRAS
SKÄRVFRITT`, `SIDODRAS I SOCKEL`, `Radiatorer ansluts med VS013-12 om ej annat
anges` (a default *label* for radiator tails), `2xANSL`, `POS 8` position refs,
`STORLEK ÄNDRAD F-115-1300x150 B75` (trench drain resize), `GR1…GR5` golvrännor.

## Vocabulary additions (legend-verbatim, various offices)

`S4` kondensavlopp (as spillvatten subsystem) · `SF01` fettavskiljare system ·
`DO01` dagvatten · `SA/SP` spillvatten allmän/process · fall per system code
(`S01 Fall min: 1%`, `SF01 Fall min: 2%`) · `FLK` fläktluftkylare · `FLV`
fläktluftvärmare · `FRD` fördelare · `LR` luftridåvärmare · `PS` pumpstation ·
`RL` renslucka/rensrör med lock · `VMM` värmemängdsmätare · `VVB`
varmvattenberedare · `VFD` vattenfördelarskåp · `UTS1` ventiluttag för
stigarledning · `SPT1` spilltratt · `TR1-3` tråg (typ LK Secure) · `MV1`
magnetventil · `RD1` reduceringsventil · `SHG` shuntgrupp (SIS: SG) · `ALxxx`
avluftare · `VLOxxx`/`VLxxx` vattenlås · `K5` förkromade kopparrör (exposed
fixture tails) · `KVM` avhärdat · hierarchical control tags (`1764-A-5601-EXP1`
= objekt–byggnad–aggregat–component) · title-block field row decoding the
number (`OBJEKTSNUMMER | BYGGNAD | PLAN | DEL | UNDERGRUPP | DISCIPLIN`) ·
consultant matrix where the X-marked row's letter need not equal the DISCIPLIN
box (L-row marked, discipline W, number prefix V — all on one sheet).
