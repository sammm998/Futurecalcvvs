# From drawing to quantity: what actually counts

The other files in this skill say what the marks on a sheet *mean*. This one says
which of them become a **number in a quantity schedule** — a different question,
and the one where a correct reading still produces a wrong takeoff.

Every rule here is a decision someone has to make deliberately. The failure mode
is never an error message; it is a plausible total that is quietly 8% off because
a convention was assumed instead of established.

## Scale: the printed figure is not enough

Swedish sheets state scale twice, for two paper sizes: `SKALA A1 (A3) 1:50
(1:100)`. Which one applies depends on the sheet you actually have, and a PDF
does not tell you which print it represents. Taking the first number on faith is
the most common way to be wrong by exactly a factor of two.

The sheet gives you three independent ways to establish scale geometrically, and
they cost minutes:

- the **scale bar** (`0 1 2 3 4 5 m`), drawn at the bottom of most sheets
- the **structural grid** — bubbles like `A100`/`A200`, `B1`–`B7`, `210`/`320`,
  whose centre-to-centre spacing is stated or obtainable from the K drawings
- any **dimensioned length** printed on the plan

Verify against at least one, and treat a deviation above roughly half a percent
as a stop condition rather than a rounding artefact — at that size the cause is
usually a wrong assumption, not measurement noise.

## Scope categories: measure them apart, then choose

A tender quantity is normally **new work only**, but a sheet carries at least
five categories at once, and the skill's own markers identify them:

| Category | How the sheet says it |
|---|---|
| New | absence of any other marker |
| Existing | `BEF`, or a whole code in parentheses — `(S1)`, `(KV-15)` |
| Demolition | repeated `X` marks along the line; `-D` / DEMONTERING sheets; `TS DEM` |
| Out of scope by area | outside the dashed **ARBETSOMRÅDE** rectangle |
| Another contract | `IL(BE)`, `PB` / `PWC` prefab units, `(L)` supplier-fitted items |

Measure each separately rather than filtering early. Two reasons: the estimator
often needs the demolition figure as its own line, and a category you silently
dropped is impossible to audit afterwards — whereas a category you measured and
excluded is one subtraction away from being reconsidered.

## The wall rule: decide it, and price the decision

Where a pipe crosses a wall, does the crossing count?

There is no universal answer, because it depends on how the pipework is
installed and how the estimator prices it:

- **Surface-mounted / exposed runs** — measure straight through. The penetration
  is real pipe, it is installed, and someone is paid for it.
- **Embedded or concealed systems** — many estimators cut the measurement at the
  wall face, because the in-wall portion is priced with the wall build-up or the
  prefab element rather than with the pipe.

Whichever rule the project uses, **measure the pipe-in-wall overlap anyway and
report it as a separate figure.** That number is what the decision is worth. If
it is 1% of the total, the argument is not worth having; if it is 12%, the rule
must be agreed with the estimator before delivery rather than after.

Wall zones are identifiable on the sheet from the architect's hatching — the
regular diagonal family that fills wall bodies — which is also why hatched bands
should be recognised rather than treated as noise.

## Symbols are counted, not measured

Valves, floor gullies, rensanordningar, risers, radiators and equipment sit in
the middle of pipe runs and frequently share the pipe's own drawing layer. Their
geometry is short and pipe-like, so a length-based measurement absorbs them
silently.

They belong in the quantity as **pieces**: `12 × AV601-32`, not `0.4 m`. Two
consequences: subtract symbol geometry from length measurements, and produce a
piece count alongside the metres — the piece count is a deliverable in its own
right, and `references/symbols.md` identifies what each symbol is.

## Areas of the sheet that are not the building

Pipe-shaped geometry appears in several places that are not the installation:

- the **FÖRKLARINGAR / RITNINGSBETECKNINGAR legend**, where every symbol and a
  sample label are drawn
- the **title block** and the **ORIENTERINGSPLAN** locator figure
- **detail boxes** such as `PRINCIPSEKTION-RÖR I BOTTENPLATTAN`, which contain a
  fully drawn miniature pipe arrangement
- the neighbouring **DEL** beyond a match line, often drawn and hatched back

None of it is quantity. Establish these zones from the sheet's own structure —
the legend strip's position, the match line, the hatch band — rather than from
fixed coordinates, because the layout moves between offices. Labels that fall
inside these zones are equally unusable as anchors: the legend's sample label
`VS11-S13-42-F100` is a specimen, not a pipe.

## What is measurable, and what is an estimate

These are not the same claim, and mixing them without saying so is the single
most damaging thing a takeoff can do:

- **Length per system** is a *measured* value once the geometry is attributed —
  the attribution comes from the sheet's own structure and is verifiable.
- **Length per dimension and material** depends on label-to-segment anchoring
  (see "Which segment a label belongs to" in SKILL.md). Until that anchoring has
  been checked against a hand-measured sheet on the current project, the split is
  an *estimate*, however precise the numbers look.

Until anchoring is validated, deliver the designation side as an inventory —
which codes appear and how many times — explicitly flagged as unvalidated,
rather than as metres per dimension. An honest inventory is usable; a confident
wrong split is worse than nothing, because it gets priced.

## Verification is visual, and it is the human's job

The reviewable artefact is an **overlay of the measured geometry, in colour, on
top of the original sheet**. The review rule is symmetric and needs no
explanation to an estimator:

- an original line with no colour on it → **missed**
- colour with no original line under it → **measured something that is not pipe**

This is what a person checks. Reading the code does not tell you whether the
hatch detector caught a wall family it should not have; looking at the overlay
does, in seconds.

## Figures worth reporting beside the total

Each of these turns an invisible assumption into a number someone can argue with:

- **pipe-in-wall overlap** — what the wall rule is worth
- **share of length attributable to symbols** — how much the piece/length split moves the total
- **number of label blocks that could not be read**, and how many pipes ended up
  with no label at all
- **length per scope category** — new, existing, demolition, other contract

## Working with the estimator's tools

Estimators mark up in **Bluebeam**, which is where the source drawing sets in
this domain typically come from. Delivering in a form their markups can be
diffed against turns every human correction into an observable signal about where
the method was wrong — and corrections on the anchoring problem in particular are
exactly the ground truth that would let the per-dimension split graduate from
estimate to measured value.

Where a project's conventions have been established once — its legend, its wall
rule, its scope markers — record them as a **project profile** and reuse it
across the sheets of that project. The legend is authoritative per project, not
per sheet, and re-deriving it for every drawing invites inconsistency between
sheets of the same set.
