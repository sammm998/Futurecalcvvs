---
name: swedish-vvs-drawings
description: Domain reference for reading Swedish VVS (plumbing/HVAC) construction drawings — systembeteckningar, pipe labels like KV-22 / VS2-40 / S1-110, line types, vertical stroke notation, valve and apparatus symbols, ritningsnummer, contractor and discipline codes. Use whenever building or debugging software that extracts pipes, labels, dimensions or quantities from VVS ritningar (PDF, DWG, IFC), doing mängdavtagning/takeoff, writing a parser or regex for a pipe designation, deciding which segment a label at a junction describes, training or evaluating a model on Swedish construction drawings, or interpreting any Swedish building-document code (BEF, VG, ÖK, FU, RE, V-56-1-124). Also when the user mentions VVS, ritning, beskrivning, rörentreprenad, Bygghandlingar 90, SIS 32260 or AMA, or shows a Swedish drawing and asks what a label means. Consult it before guessing what a two-letter code means — the codes collide across categories and a wrong guess silently corrupts a takeoff.
---

# Swedish VVS drawings

Reference for interpreting Swedish VVS ritningar (VVS = Värme, Ventilation, Sanitet — heating, ventilation, plumbing). Built for one job in particular: writing code that recognises pipes and their labels on a drawing and turns them into structured data.

The machine-readable source of truth lives in `data/*.json` next to this file. **Load the JSON rather than retyping tables into code** — it is versioned, complete, and carries `notes` fields flagging collisions that a hand-copied table will lose. The prose in `references/` explains what the JSON cannot: why a rule exists and how it fails.

## The one thing that will bite you

Swedish drawing practice is *conventional*, not *guaranteed*. SIS 32260 and Bygghandlingar 90 define the tables here, but every consultant (konsult) and client (byggherre) layers their own praxis on top. Complex designation systems normally carry their own legend (särskild förklaring) printed on the drawing.

So the correct architecture for an extractor is: parse against these tables, but treat a table miss as *unknown*, not *invalid*. Surface unrecognised labels for human review instead of dropping them. A pipeline that silently discards what it cannot parse produces a confident, wrong quantity — the worst possible failure mode in a takeoff, because nothing looks broken.

Where a drawing has a legend, the legend wins over these tables. In real sets
this is the normal case, not the exception — every sheet surveyed (nine design
offices, 2018–2026) carries a **FÖRKLARINGAR / RITNINGSBETECKNINGAR** block
defining that project's systems, materials, insulation types and component
codes; one project keeps the full legend on a dedicated drawing and sheets
carry excerpts. Interpret the legend first, then fall back to these tables for
whatever it does not define.

## Pipe label grammar

The label is a chain of dash-separated positions. Across every office surveyed
only two things never move: **the first position is the system designation plus
a running number, and the last plain-number position is the dimension.** How
many fields sit between — and what they mean — is defined per project in the
sheet's legend.

```
KV-22                system, dimension                     (textbook short form)
VS1-S13-12/W         system+nr, material, dim, insulation
VV01-X7-25-F60       system+nr, material, dim, insulation type+thickness
KV01-E2-54-K2-A      system+nr, material, dim, insulation, cladding
VS111-55-16          system+nr, numeric material code, dim
KV11-25              system+nr (material folded into the nr), dim
VS2-13-89/S1A/A      system+nr, material, dim / insulation series / cladding
```

So: **tokenize by dashes rather than matching one pattern.** Take the first
token as system + number, the last plain-number token as the dimension, keep
everything between as unresolved material/quality fields, and treat slash or
trailing suffixes as insulation/cladding. `references/label-grammars.md` has
the full survey with one row per observed form.

Character-set details that survive every variant: `Å Ä Ö` are legal in system
codes (`Å` alone is steam, `ÅV` recovery), and `VVCi` ends in a lowercase `i`.
Folding Swedish characters to ASCII corrupts real designations. The dimension
figure itself may carry a trailing `L` or `V` (`110L`, `100V` = luftning /
vent line) — accept it and flag the pipe as a vent.

**The label is often split across lines.** `S1-P2` with `75` beneath it is one
label, and multi-system stacks put a row of system codes over a row of
dimensions, one column per pipe. Group text by leader point and reading order
before parsing, or stacked labels parse as systems with no dimension.

**A quantity multiplier may prefix the whole code**: `5xVV1-X31-16`,
`2xKV1-31-16` mean five, two parallel pipes drawn as one line — a tappvatten
bundle to a row of fixtures. The `Nx` is not decoration: it is the number of
pipes, and a parser that strips it to `VV1-X31-16` files one fifth of the
length. Keep it as a count on the designation.

`scripts/parse_pipe_label.py` implements the tokenizer.

### What a label physically looks like

The unit on the sheet is not a designation but a **label block**: a leader
line landing on the pipe(s), carrying a shelf or box of stacked text rows.
Read the block top to bottom and classify each row:

- **Designation rows** — one full designation per row, one row per
  installation. A block may hold one, two, or more:

  ```
  VS1-S13-12/W        two rows, same system, two dimensions →
  VS1-S13-35/W        two separate runs; VS is line_count 2, so four pipes

  KV1-X7-40/W
  VV1-X7-40/W         three rows, three systems →
  VVC1-X7-25/W        three separate installations on one leader
  CL 3400 ÖFG
  ```

  Every row is its own installation to extract, even when the system code
  repeats — two `VS1` rows with different dimensions are two runs, not a
  correction or a duplicate. The block shares one leader, so each row still
  needs its own segment resolution (see stacked labels under association).

- **A level row** — `CL 3400 ÖFG`, `cl 2300 öfg` (case varies per office),
  `VG 2300 ÖFG`, or absolute `CL+17.650`/`VG+11.435`. Always the bottom row,
  never a designation, and it applies to every designation row above it.
  Filter it out of label parsing, keep it as an attribute of the block —
  and remember only VG carries flow direction (see below).

- **Wall-mounted fixture connections** — short `R1` stubs (`KV1-R1-15`,
  `VV1-R1-12`, often as a split form `KV1-R1` over `15` with the stroke
  notation) carrying a very low mounting height, `CL 160 ÖFG` / `CL 200 ÖFG`,
  are the connections to wall-mounted taps and cisterns. One expert takeoff
  (W-50-1-A-0111) keeps them as a separate item from the same code on the
  distribution run — `KV1-R1-15` at CL 200 is "wall-mounted", the same code
  at CL 2900 is not. Carry the CL through; it is what separates the two.
  Observed on one style so far — confirm on another office before relying
  on the threshold.

- **Chained components** — `+CODE` appended to a designation
  (`S017-110+RA1` = spillvatten Ø110 with a rensanordning) marks a component
  sitting in that run: a piece to count, not part of the pipe designation.

Where a block sits also carries information. The full boxed form with a level
row is the mid-run norm. The **split form** — system code above a short
heavy-underlined dimension (`VS1-S13` over `12`) — appears mostly at the
start and end of a run, where the dimension's stroke notation does the work
of the level row; expect it at risers, connections and run ends rather than
mid-run, and join the two rows before parsing.

One trap in dense title areas: labels can overlap background text from other
layers (scale stamps, sheet names, grid references, often printed light
grey). Text weight/colour and membership in the leader's shelf group decide
what belongs to the block — proximity alone does not.

### What a joining point physically looks like

Every stretch of pipe starts and ends at a **joining point**; a label describes
the stretch between two of them. Work on the vectors — the sheets are vector
PDFs and every mark below is a distinct path with its own weight. Measured on
a sheet with a 100%-verified stretch segmentation (88 same-system stretch
boundaries); check the numbers on a new office before trusting them.

- **Leader tick — the mid-run joining point (66 of 88).** The thin leader
  (0.48 pt) from the label block ends ON the pipe centreline, and a short
  diagonal stroke of the same weight — one `l` path ≈5.8 pt long (4.1 × 4.1),
  at 45° to the page axes — is centred on that end and crosses the pipe. The
  tick's midpoint is the joining point. Vector test: single-line path,
  length 4.5–7.5 pt, width ≤ 1 pt, midpoint within 1 pt of pipe ink, and a
  line ≥ 8 pt ending at the midpoint. A rendered detector trained on these
  finds most of them; the vector test finds them exactly.
- **Connection circle (anslutningspunkt) — the run-end joining point.** An
  open circle Ø ≈2.8 pt (0.72 pt stroke, four `c` items) sitting on the END
  of a pipe line. It marks where a stretch begins or ends at a fixture, a
  wall connection or a take-off. Two circles side by side are two stretches
  meeting. A larger grey ring drawn around a circle is a symbol of its own;
  the black circle inside is still the point. Not every circle carries a
  label. Vector test: a closed round path — ≥ 2 `c` items, ≤ 1 `l`, Ø 2–4 pt,
  short side ≥ 0.9 × long side — whose centre lies within 1.5 pt of pipe
  ink, with a leader vertex within its radius + 0.6 pt. The leader ends ON
  the circle far more often than at its centre (10 of 157 circles on the
  reference sheet had a leader end at the centre), and the circle's own path
  starts on the rim — so never chain a circle as line ink, or the leader's
  free end disappears into it.
- **Bare leader end.** The leader touches the pipe with no tick and no
  circle. Still a joining point: the leader's free end IS the mark. Vector
  test: an endpoint of a thin path (width below the thinnest pipe family,
  total length ≥ 8 pt) within 1 pt of pipe ink, outside every label box, and
  farther than 3 pt from any tick or circle already found. 44 of these on
  the reference sheet — roughly one joining point in four.
- **Tee with nothing drawn.** Where a branch leaves a main, the branch's
  stretch begins at the tee even when no mark sits there. The label on the
  branch (its tick further along) names it; the main keeps its own label
  straight past the junction. Vector test: the endpoint of a heavy (pipe
  weight) path lands on the INTERIOR of another heavy path, not on its
  endpoint. About 5 of 88 boundaries on the reference sheet. The tee is a
  boundary for the BRANCH only: the main is not cut there — it is one
  stretch from its own joining point to the next, whatever leaves it on the
  way — and for showing or counting, one pipe is the main together with its
  branches. An extractor that splits the main at every tee produces stretch
  boundaries with no label and no mark, which the expert reads as errors
  (2026-09-03).

Every test above says "pipe ink" or "thin": that is relative to the sheet's
own weights, never absolute. The **vector anatomy** of the reference office,
to check a new office against before trusting any threshold:

| ink | weight | colour | drawn as |
|---|---|---|---|
| pipe, two families | 2.04 pt, 1.44 pt | black | straight `l` paths; a DASHED run is many short paths, each with the solid dash attribute — the pattern lives in the gaps between collinear paths, not in any attribute; CAD exports double-draw many strokes (there and back), keep one copy |
| leader, tick | 0.48 pt | black | `l` paths; a forked leader is one polyline |
| circle, lettering | 0.72 pt | black | circle = closed `c` path; letters = short `l`/`c` paths inside the label box |
| architecture, grid | 0.36–1.44 pt | grey (≈0.73) | never pipe, never leader |

Anything thinner than the thinnest pipe family is annotation ink; the
families themselves are learned from the widest stroke under the joining
points, so the joining points must be found first.

Three things about the LEADER itself that an extractor gets wrong before it
ever reaches the mark (each one lost every tappvatten label on the reference
sheet until fixed):

- **A forked leader is one path.** `2xKV2-X31-16` is drawn as a single
  polyline from the shelf through the centre of the first circle to the
  centre of the second — one path, two pipes. Every vertex of the path is
  a landing point, not only its far end.
- **Two leaders share a mark.** Neighbouring labels routinely land on the
  same circle. Chained by endpoint proximity, the two lines become one chain
  with two label ends and no free pipe end. A mark is where a line STOPS:
  break the chain there between different paths, never inside one path.
- **Lettering is line ink.** On sheets that draw text as strokes, glyphs
  come at leader weight and sit inside the label box; chained in, they weld
  the leaders of neighbouring labels into one. Skip strokes that lie within
  a label box before chaining.

**Proximity does not establish system connectivity.** A ring or leader landing
belonging to one identified system must not attract an adjacent incompatible
system's pipe, even when its centre is the closest candidate. Check the pipe's
actual endpoint/contact with the symbol, its own leader and system evidence
before snapping; crossing the ring's centre is not sufficient. In the
2026-09-07 review of W-50-1-A-0124, a V1 run was incorrectly diverted to an S2
ring. Local replay corrected the three related geometry assertions. This is
evidence from one drawing style, not a universal interpretation of layer names:
resolve tokens such as V1/V2 from the project's legend or documented CAD mapping;
do not equate V1 with KV or V2 with VV by spelling alone. Missing system metadata
means unknown, not proof of compatibility or incompatibility.

What is **not** a joining point, and litters the same neighbourhoods:

- **Coupling arcs `((`** — two `c` items, not closed, aspect ≈ 0.5, by far
  the commonest small mark on the sheet (thousands). Never a boundary.
- **A crossing.** Where a dashed pipe crosses another, BOTH lines are
  broken. Two ends meeting at a right angle with each run continuing
  straight beyond the contact are a crossing, not an elbow — the elbow rule
  (≤ 90°, one pipe) applies only when neither run continues past the corner.
- **Parallel neighbours in a bundle.** Pipes 2–4 pt apart drawn side by
  side: one ending beside another is not a branch landing on a main (a
  branch meets its main at an angle, ≥ 30°), and two parallel ends touching
  are not a continuation unless the tips are collinear.
- **A component in the run.** A valve, a battery or a fitting symbol
  breaks the drawn line for 9–14 pt. The run may continue unchanged behind
  it — or the designation may change there: on one dense tappvatten sheet
  (W-50-1-A-0111) every one of the eleven wrongly merged pairs was two
  differently designated pipes meeting at a valve symbol. Treat the symbol
  as a possible boundary, not as proof of continuation; the designations on
  either side decide.
- **A wall band.** Pipes are not drawn inside hatched wall regions, so a
  run crossing a wall is two pieces with a 10–40 pt gap. Bridge that gap
  only STRAIGHT ON: a run never turns inside a wall, and where several
  parallel drops enter a wall side by side, a corner across the band picks
  whichever neighbour happens to end nearest (twelve fused pairs on one
  dense sheet, W-50-1-A-0124, until this was enforced).
- **Dash pattern is line type is elevation** (see below): a dashed piece and
  a solid piece are never one stretch, whatever the geometry says. Read the
  pattern from the gaps between collinear pipe paths — the PDF attribute
  says "solid" on every dash.

### Which systems come in pairs, and which never do

Circulating circuits are always two pipes: framledning out, returrör back. They
never appear alone, so a lone labelled run of one of these systems means its
partner is somewhere on the sheet — unlabelled, or off the extraction.

`line_count: 2` in `data/system_designations.json` marks them: **VP, VS, KB, KM,
ÅV, FV, FK**, plus the legend spellings **KP, VÅV, FJV, FJK**. Everything else
is `line_count: 1`. Read `line_count` from the JSON per label; do not hardcode a
list that will drift.

Two pipes does not mean two labels, and that difference is the single most
expensive mistake available in this domain — heating pipework off by a factor of
two in either direction. What decides it is how the sheet draws the pair, not the
system code:

- **Both pipes drawn** — the normal case on planritningar. Two parallel runs of
  the same line type, a few hundred millimetres apart, and **only one of them
  carries the label**. Copy that label onto its unlabelled twin and measure both
  lines. Do not also double the length: the twin is already in the geometry, and
  doubling counts it twice.
- **One line for the pair** — single-line schematics, stigarscheman, principle
  diagrams. The label is written once and covers both pipes, so the drawn length
  doubles.

Ask the geometry which case you are in: if a parallel unlabelled run of the same
line type shadows the labelled one, the pair is drawn. That test is cheap and it
is the only honest way to choose — the label itself cannot tell you.

Note that two labelled pairs often run side by side, which is easy to mistake for
one pair. Two labels stacked on their own leaders, taken from a plan:

```
VP1-S13-42/W        primary circuit, DN42     → labelled line + unlabelled twin
CL 3400 ÖFG
VS1-S13-35/W        secondary circuit, DN35   → labelled line + unlabelled twin
CL 3400 ÖFG
```

Four pipes, two labels. VP1 and VS1 are different systems (primary and secondary
heating water), each of which is itself a pair — they are not each other's
partner, which their different dimensions confirm. The shared `S13` material and
`/W` insulation and the identical `CL 3400 ÖFG` centre-line level are what a pair
of labels from the same package looks like; they are not evidence of pairing.

**Systems that always carry their own label: KV, VV, VVC, S, D.** Tappvatten,
spillvatten, dagvatten. Every drawn pipe is labelled individually, so never infer
a twin for them — an inferred partner here is an invented pipe. VV and VVC are the
trap: they travel together and look like a supply/return pair, but they are two
systems with two labels and usually two different dimensions. S and D run side by
side to the same brunn and are likewise separate. Conversely, an unlabelled run
of one of these systems is a miss to surface, not a partner to fill in.

### What the index digit means

The running number is defined by the drawing's legend, not by any standard, and
the surveyed projects genuinely disagree. Observed readings: material variant
(`KV11` ALU-PEX vs `KV12` rör-i-rör), subsystem by temperature (`VS1` 55/30°C …
`VS5` markvärme), usage (`KV 2` = kök/café, `3` = lab), water treatment (`KV02`
softened), wastewater material or location or acoustic class (`S1` gjutjärn *or*
i mark; `S12` ljuddämpande), even the stam number (`VV0175`). The full table is
in `references/label-grammars.md`.

Even the well-attested prior fails across offices: `VS1` radiators/`VS2`
luftvärme on some projects, but `VS11` ventilation/`VS21` radiators/`VS31`
golvvärme on others — the digits swap roles. One legend even selects the digit
by ROUTING: synliga `KV31`, i vägg/golv `KV21`, ovan demonterbart undertak
`KV12`, all one system. So: carry the number through your data model
**unresolved** and resolve it against the sheet's own legend. Systems themselves are an open set — legends freely add `RAD1`, `FJV`,
`TL`, medical gases (`G2`, `L1`, `G75`), rörpost — so treat the standard table
as a seed, not a whitelist.

### What the label may or may not tell you

Rörmaterial, fogmetod and isolering come from the VVS-beskrivning **when the
short label form is used**. When the extended form is used, material and
insulation are in the label and the beskrivning defines what the codes mean.

Either way the beskrivning is required before anything is priceable, and the
join should be explicit in your schema so its absence is visible rather than
defaulted to a guess. Fogmetod is never in the label.

## Which segment a label belongs to

Parsing the label is the easy half. The harder half is deciding which pipe it
describes. Leaders land near junctions, and the two segments meeting there
usually differ in dimension — so choosing the wrong one files a length under the
wrong DN *and* removes it from the right one. The sheet still looks fine; two
quantities are simply wrong.

The whole resolution rests on one idea — call it **the reading rule**:

> **A drawing is read from outside the room inward. A label is placed at the
> BEGINNING of a run, at the point where the pipe enters, so it describes the
> segment that comes AFTER it in that direction — never the one before it.**

Establish the direction and the ambiguity disappears. Everything below is a way
of establishing it, and the numbering below is the RESOLUTION ORDER, not a
ranking of importance: rules 1 and 2 are proxies that happen to be printed on
the sheet, and rule 3 is the reading rule applied directly. Rule 3 comes last
not because it is weaker but because it is what remains once no proxy is
available — so use the most explicit signal the sheet offers, and fall through
in this order.

### 1. Invert level — gravity systems only, and decisive where present

Sewer runs (`S`, plus the office variants `SA`, `SP`, `SF`) fall from higher to
lower because gravity moves the water, and the drawing states this outright as
`VG+1.91` invert levels along the run — a printed number, not an inference. But
be careful which way that number points you. The water leaves the room: it runs
OUTWARD, towards the lower invert. Reading runs INWARD. So on a gravity system
**the reading direction is uphill, against the flow: the label at the lower
invert describes the segment climbing away from it, towards the higher VG.**
Getting this backwards shifts every label on the run one segment the wrong way
while the sheet still looks perfectly plausible — verified against a hand-made
ground truth of one sheet (W-50-1-A-0011), where reversing this single rule
took a rule-based extractor from 44.7% to 59.6% correct codes. For gravity
systems prefer this signal over every other.

**The take-off walk, as the quantity surveyor does it** (expert procedure,
2026-09-02; the drawing below is from W-50-1-A-0011):

1. **Start at the lowest point of the run** — the designation whose level
   (VG, or CL where the block carries that instead) is the lowest. Example:
   `S3-R8-160 | VG+1.46`. That designation's dimension is the initial
   dimension: 160.
2. **Walk in the direction the level rises**, uphill. At every designation
   met on the way, compare its dimension with the current one.
3. **Same dimension** (`S3-R8-160 | VG+1.48`, then `S3-R8-160 | VG+1.50`):
   nothing changes for the quantity. The length continues under 160 up to
   the next designation. The designation is still a joining point — a new
   stretch starts there — it just carries the same dimension forward.
4. **Smaller dimension** (`S3-R8-110 | VG+1.51`): a dimension change. The
   length measured under the previous dimension ENDS here, and the next
   length starts here under the new one, 110, until the next change.
5. Repeat at every designation until the whole run is measured. A branch
   that leaves the run with its own designation (`S3-R8-75 | VG+1.56`)
   starts its own walk from that designation, with its own dimension.

Two things this makes explicit that the reading rule alone only implies:
the run has exactly ONE starting point, the lowest level, and it is found by
comparing levels across the whole run before assigning anything; and a
designation always closes the length before it and opens the length after
it — a label never describes what lies below it on the run. Between two
consecutive designations there is one dimension, the one printed at the
lower of the two.

Do not mistake mounting heights for invert levels. `CL 3400 ÖFG` and `CL+17.650`
are centre-line heights of pressure pipes — they say how high a pipe hangs, not
which way anything flows, and carry no direction information at all. Only VG on a
gravity run indicates fall.

### 2. Dimension — the general case

Pipework tapers as it branches out toward fixtures, so between two candidate
segments the **larger dimension is upstream and the smaller is downstream: the
label belongs to the smaller one.** Both numbers are already in hand from the
neighbouring labels or the sheet's defaults table, which makes this the cheapest
signal to apply and the one that resolves most junctions on pressure systems.

### 3. Position relative to the room boundary — the reading rule itself

This is not a separate heuristic: it is the reading rule with nothing in front
of it. When neither invert level nor dimension separates the candidates, the
segment **further from the point of entry** is downstream and takes the label.

The point of entry is visible on the sheet, not inferred: the pipe comes in
through a wall, from the edge of the drawing, or from a riser. So of the two
candidates at a labelled joining point, the one whose far end disappears into
a wall band, runs off the sheet, or ends at a riser is the side the pipe came
FROM, and the label describes the other one (expert rule, 2026-09-03).

One trap on the way to this decision: doubting the label itself. A split
form (`S1-P2` over an underlined `110`), a designation with no dimension, a
row the grammar could not fully parse — these are all labels, and their
leaders are real joining points. Reject a block only when no row carries a
recognised system. Dropping partial forms as "invalid" raised one
benchmark score (fewer labels to misplace) while the expert read every one
of them as a label — the drawing lost joining points, not noise.

### Specification, designation identity and scope

**Identical specifications do not identify the same designation.** Two separate
`S3-R8-160` marks can describe different stretches. Preserve both the parsed
specification and its source: drawing/revision, label block, original row index,
and leader landing. In a multi-row block, propagate the selected row, not just
the block ID; filtering an unreadable row must not renumber the remaining rows.
Compare specification correctness and source-designation ownership separately.
This distinction was material in the 2026-09-10 review of W-50-1-A-0232.

**A geometry fragment is not necessarily a designation scope.** PDF paths or
extractor graph edges may split one physical run into several pieces. One
designation may cover consecutive fragments along a supported continuous route,
until another applicable designation or a confirmed specification boundary is
reached. Equal text at the next designation does not erase that boundary or
transfer ownership to the earlier mark. Conversely, a software-created endpoint
alone does not prove that a new designation is needed.

Use the reading direction to select the side of a genuine designation boundary;
do not automatically assign both sides. Later feedback and implementation contain
proposed continuation through a designation's own mark, but those exceptions
need source-drawing and topology confirmation before becoming general rules.
A circulating pair remains a separate case: the same designation can describe
two parallel pipes when the pairing is supported by the drawing.

**A branch designation does not automatically describe its main.** Resolve it
onto the branch and its supported continuation. Do not propagate it backwards
onto an unlabelled main merely because that main is connected or nearby. A main
may continue through a tee without changing its own designation; an independently
labelled branch has its own scope. If no applicable designation or explicit
project default describes the main, leave its specification unresolved and
surface it for review. This scope distinction is supported by the 2026-09-06/07
feedback work; candidate availability alone did not validate final assignments.

### When the signals disagree or run out

Equal dimensions on both sides with no invert level to break the tie is common —
a straight run labelled mid-length is exactly that case. Handle it the way this
skill handles every other unresolved reading: attach the label to the nearer
segment, mark the association low-confidence, and surface it. A confident wrong
assignment costs more than an honest uncertain one, because only the second ever
gets reviewed.

Two cases need care:

- **Circulating circuits.** For a `line_count: 2` system (VP, VS, KB, KM, ÅV,
  FV, FK, and the legend spellings KP, VÅV, FJV, FJK) the direction argument
  applies to the pair as a unit. Do not try to separate supply from return with
  it — and where the twin is drawn, resolve the label onto the labelled run
  first, then carry it to the parallel twin, so one uncertain reading does not
  become two.
- **Stacked labels at one leader.** Each figure in the stack is its own pipe and
  needs its own resolution; the stack shares a leader point, not a segment.
  But check whether it really shares one: on the reference sheets about half
  the stacks have **one leader per row** (10 of 22 on W-50-1-A-0111), each
  leaving from its own row's shelf and landing on its own pipe. Then every
  row is read by its own leader and nothing is shared. Where one leader
  does serve the whole stack (its line crosses every pipe of the bundle,
  a tick at each crossing), the rows are listed **in the order the pipes
  lie on the sheet: left to right for vertical pipes, top to bottom for
  horizontal ones** — the reading order of the drawing, not the order in
  which the leader reaches them. Measured against the ground truth of four
  sheets: 31 stacks follow it, 5 do not. Ordering the rows from the leader's
  side instead ("nearest pipe first") is a coin toss (14 to 7) and swaps KV
  and VV on a third of the pairs.

`scripts/assign_label.py` implements the resolution order, including the
low-confidence outcome — port it rather than re-deriving the precedence.

## Geometry the drawing encodes implicitly

A planritning is a section at window level (fönsternivå) seen from above.
(Actual sektioner — category `-2` sheets — are the opposite regime: pipes drawn
double-line with rounded elbows and almost no labels; they resolve riser
geometry, while systems and quantities come from the plans.) Elevation is encoded in the *line style*, and vertical runs are encoded in *strokes on the dimension text*. Both are easy to lose in a raster or vector extraction, and losing them means losing all vertical pipe length.

### Line type → elevation (`data/line_types.json`)

| Style | Swedish | Meaning |
|---|---|---|
| Solid | Heldragen | Below window level (in the room) |
| Dashed | Streckad | Below the floor surface |
| Dash-dot | Streckprickad | Above window level, within the storey |
| Dash-double-dot | Dubbelt streckprickad | Above the floor slab — belongs to the storey above |

Dash-double-dot deserves attention: that pipe is **not on this floor**. Counting it into this storey's quantity double-counts it against the drawing for the floor above.

Sheets restate this key in their own words and may shift the reference plane (one office: heldragen = ovan golv, streckad = i golvbjälklag, streckprickad = under tak, dubbelprickad = i takbjälklag). The four-style principle holds; the exact wording is the sheet's.

### Stroke notation → slab penetration (`data/vertical_pipe_notation.json`)

A heavy stroke (grovt streck) above and/or below the dimension figure says which slabs a vertical pipe passes through. The logic inverts from what most people expect — **a stroke means the pipe stops there**:

| Notation | Passes slab above | Passes slab below | Reading |
|---|---|---|---|
| `15` (bare) | yes | yes | Runs straight through the storey |
| `‾15` (overline) | no | yes | Drops down only |
| `15_` (underline) | yes | no | Rises up only |
| `‾15_` (both) | no | no | Riser contained within the storey |

For any automated reader this is genuinely hard: the stroke is a graphic mark next to the text, not part of it. Treat a missing determination as unknown rather than as "bare" — bare is the most permissive reading and silently inflates the quantity.

Field-verified on three offices, in all four states, including stacked figures each carrying their own stroke. Two verified traps: offices that write labels on leader shelves underline *every* text row with a thin shelf line — only the extra, heavier, shorter bar hugging the figure is the notation (a naive underline detector reads every label as "rises only"); and some offices use no strokes at all, writing explicit `CL+`/`VG+` levels instead — absence is a convention, not missing data. Details in `references/label-grammars.md`.

### Stacked dimensions

Where several pipes share a plan position, dimensions are stacked at one leader point, e.g. `S1` over `110` over `110`, or `15 / 20 / 20`. Each figure is a separate segment and **carries its own stroke notation and pairs with its own line type**.

An extractor that treats a leader point as one label per point will merge these. Group text by leader and preserve reading order top to bottom.

## Recognition traps

- **A gap in a line is a crossing, not an end.** Where pipes cross, one line is broken (avbrott på linjen). Segmentation must reconnect across such breaks, or every crossing fragments a run into two pipes and the label association falls apart.
- **Pipes are single lines** on a planritning, not double-line profiles. Width carries no meaning.
- **A pipe bends; it never folds back.** A fitting turns a run by at most 90° — an elbow, and nothing sharper exists in the catalogue. So a corner up to a right angle is ONE pipe and must not be split into two runs: a bend is a fitting like any other, and an elbow is no shorter than an inline coupling, so the gap it leaves in the drawn line deserves the same reach as a straight one. Conversely, two ends meeting more sharply than a right angle are **two pipes that happen to touch** — a hairpin, or a pair running back alongside itself — and joining them merges one quantity into its neighbour. Allow a few degrees of tolerance (95° works) for the drawn angle and for sampling, but not the 135° a genuine fold-back needs. Beware of testing this with undirected axes: two axes can differ by at most 90°, so a hairpin and a right angle look identical unless the comparison uses the DIRECTIONS the pipe runs off in on either side.
- **`BEF` marks existing installation** — scope boundary, not new-build quantity (`data/level_references.json`).
- **Lines with repeated X marks are demolition** (ledning som ska rivas) — a separate quantity, not new installation. Ombyggnad sets go further: dedicated `-D` (DEMONTERING) sheets, and a dashed rectangle marking the ARBETSOMRÅDE — outside it, nothing is in scope.
- **`PB` / `PWC` mark prefab bathroom/WC units** — their internal pipework is factory scope, not site quantity. Same logic as a parenthesised contractor code like `IL(BE)`. Element labels carry it as a suffix: `S-STAM (PB)`, `KOPPLINGSSKÅP (PB)`.
- **Parentheses around a whole code mean existing**: hospital legends state `( ) AVSER BEFINTLIGT`, so `(S1)`, `(KV-15)` are befintligt — context, not new quantity.
- **An underlined dimension reads as a different number.** The heavy stroke
  of the vertical-pipe notation sits right under the figure, and OCR folds it
  into the glyphs: on one sheet every split-form `S3-R8` / `75` with the stroke
  came back as `S3-R8-15` — ten labels, all `75` on the ground truth. The
  misread can pass a generic numeric parser. Treat an implausible dimension
  for the identified system/project as an OCR warning, not a replacement rule:
  `S*-…-15` under a stroke is a reason to inspect the source figure, not permission
  to rewrite it as `75`. The 2026-09-10 review also found `S2-P5-715` and a third
  designation row outside the saved detection box. Re-read the source at a useful
  scale, separate stroke notation from digits, and check the whole label block
  for clipped rows. Preserve raw OCR, source location and original row identity;
  keep the dimension unknown if it cannot be verified. An unreadable designation
  can still mark a scope boundary. Apply the same validation to saved OCR as to
  fresh reads. These examples are confirmed for the reviewed style; plausibility
  thresholds must follow the project's system and material conventions.
- **Heater product labels mimic pipe labels.** `KV11-612` is a convector (505 W) on the same project where `KV11-25` is a cold-water pipe; `VK 11-3012` is a radiator where `VK` also means WC. Anything with a W/flow/Kv duty line or an implausible dimension is equipment, not pipe.
- **Quantities move between sheets.** Notes like "kopplingsledningar i golv … redovisade på ritningar V-52-1-…" put whole pipe groups on a sibling undergrupp's sheets; match lines (KONNEKTION) continue runs onto the neighbour sheet.
- **Unlabelled pipe is not undimensioned.** Sheets carry default tables (KOPPLINGSLEDNINGAR, AVLOPPSANSLUTNINGAR) giving connection dimensions per fixture type, and SCHAKTTABELL/STAMTABELL matrices giving riser dimensions per floor. A takeoff that only reads labels drops all of it.
- **Wall crossings are a decision, not a detail.** Surface-mounted runs are measured through the wall; concealed systems are often cut at the wall face because the in-wall length is priced elsewhere. Nothing on the sheet states which rule applies, so it has to be agreed — and the overlap measured either way, because that figure is what the decision is worth.
- **Symbols are counted, not measured.** Valves, gullies, rensanordningar and equipment sit inside pipe runs and their geometry is short and pipe-like, so a length measurement absorbs them. They belong in the quantity as pieces.
- **Parts of the sheet are not the building.** The legend, title block, orienteringsplan and detail boxes such as `PRINCIPSEKTION-RÖR I BOTTENPLATTAN` all contain drawn pipework, and the neighbouring DEL beyond a match line is often drawn back. A legend's sample label is a specimen, not a pipe.
- **The printed scale is stated twice** (`SKALA A1 (A3) 1:50 (1:100)`) and a file does not say which print it is. Verify against the scale bar, the structural grid spacing or a dimensioned length before trusting any length.
- **Codes collide across categories.** See below.
- **Revision clouds mark changed regions.** Drawings are versioned by ändringsbeteckning (A, B, C…) in the title block; a KFU or Ändrings-PM means affected quantities must be re-measured. Version your extraction by revision, not by filename.

## Colliding codes

The same two letters mean different things in different categories. Context — is this label on a pipe, on a fixture, in the title block? — is what disambiguates. Never resolve a bare code without knowing its category.

| Code | Meaning A | Meaning B |
|---|---|---|
| **DB** | Diskbänk (kitchen sink) | Dagvattenbrunn (stormwater gully) |
| **TB** | Tillsynsbrunn (inspection chamber) | Kylbaffel med tilluft (chilled beam w/ supply air) |
| **SL** | Säkerhetsledning (safety line, a *system*) | Slutapparat (ventilation terminal unit) |
| **V** | Vätska (liquid, a *system*) | VVS-projektör (discipline, in a drawing number) |
| **G** | Gas (a *system*) | Geotekniker (discipline) |
| **K** | Kondensat (a *system*) | Byggnadskonstruktör (discipline) |
| **L** | Luft (a *system*) | Landskapsarkitekt (discipline) |
| **KP** | Kompensator (expansion joint symbol) | Alternative designation for köldbärare |

V, G, K and L are the practical hazard: they are single letters that are both system designations and discipline codes. Position resolves them — a discipline code is the first field of a ritningsnummer in the title block, a system designation sits on a pipe followed by `-<dimension>`.

`scripts/lookup_code.py` returns every meaning of a code across all categories, so ambiguity is visible instead of assumed away.

## Bundled tooling

- `scripts/parse_pipe_label.py` — reference implementation: parses a label, resolves the system, returns `line_count`. Import it or port it; the point is that the semantics (Å Ä Ö, `VVCi`, `line_count`) are already correct here.
- `scripts/assign_label.py` — decides which of two candidate segments a label at a junction describes, applying invert level → dimension → entry distance in that order and returning a confidence with the reason.
- `scripts/lookup_code.py` — resolves a code across every category, showing collisions.

Both read `data/*.json` directly, so they stay correct if the knowledge base is updated.

## Where to read further

Load these only when the task touches them — they are detail, not orientation.

| File | Covers |
|---|---|
| `references/system-designations.md` | All 22 systembeteckningar with line counts and index semantics |
| `references/symbols.md` | Valves, apparatus, sanitary fixtures, wells, control devices, sensors and instruments — what each symbol looks like on the drawing |
| `references/drawing-metadata.md` | Ritningsnummer structure, drawing categories, content classification, document status, revision handling |
| `references/document-context.md` | Precedence between ritning, beskrivning and AMA; as-built and DoU requirements; what a complete document set contains |
| `references/takeoff-rules.md` | **What becomes a number.** Scale verification, scope categories measured apart, the wall rule, symbols as pieces, sheet areas that are not the building, measured-vs-estimated, and the verification overlay |
| `references/label-grammars.md` | **The praxis survey.** Label grammars per office, index-meaning table, project-defined systems, component and heater annotation, drawing tables, demolition and prefab markers, numbering styles |

## Precedence, when sources disagree

In an utförandeentreprenad (design-bid-build), **the beskrivning takes precedence over the ritning**. AMA text applies underneath the beskrivning via the pyramidregeln, but the beskrivning wins over AMA too.

For an automated pipeline this is a design constraint, not a footnote: when drawing-derived data conflicts with the beskrivning, the beskrivning is authoritative — and the conflict is worth surfacing rather than resolving silently, because a genuine contradiction between the two usually means someone made a mistake that a human needs to see.

## Evidence scope for feedback-derived rules

The September 6–10, 2026 feedback refinements above distinguish specification
from designation ownership, geometry fragments from description scope, branch
from main, system-compatible contacts, and OCR warnings from verified readings.
They come from recorded Pipe Studio expert reviews of W-50-1-A-0011, 0111, 0124,
0131 and 0232. They are extraction guidance grounded in those examples, not new
Swedish standards or proof of cross-office validity. The September 10 review
reported positive evidence only for style-1; its comparison was diagnostic
because the original feedback snapshot lacked a source PDF hash.

When extending these rules, record the drawing/style, source example, what was
actually confirmed (text, geometry, candidates or final ownership), and remaining
exceptions. Treat proposed through-mark continuation as awaiting case validation;
do not turn implementation behavior or repeated feedback records into independent
domain evidence. A project legend remains authoritative for its conventions.

## Provenance

`data/*.json` is a knowledge base built from a Swedish VVS trade handbook
chapter on *ritningar och beskrivningar*, cross-referenced to SIS 32260,
SS 32266, Bygghandlingar 90, AMA VVS & Kyla 19, CoClass and BIP. Swedish codes
and terms are preserved verbatim; English glosses are added.

`references/*.md` is generated from that JSON by
`scripts/build_references.py` — edit the JSON and re-run the script rather than
editing a reference file, or the two will drift.
