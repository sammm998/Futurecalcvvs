# Known limitations (state at the open-world gate)

> Nuläget - grindens siffror, vad som inte görs och varför - står i [`SYSTEMET.md`](SYSTEMET.md) §11-12.
> Det här dokumentet beskriver begränsningarna som de såg ut vid den öppna grinden och gäller i sak fortfarande.

* **Vertical quantities**: the drawing carries no floor height, so the engine never invents vertical metres. It
  counts risers per designation (closed riser marks a label points at, marks of the same riser-mark family at the
  end of or on a pipe, count prefixes such as `5x` for marker stacks) and reports `riser_count`; the application
  turns risers into vertical metres only with a floor height the user enters (Excel/CSV export accept
  `floor_height`). Elevation pairs (VG/CL) on one pipe still give measured vertical metres. Riser counts follow the
  drawn marks: tiny end circles without a label (fixture connection points) are not risers; a label pointing at a
  connection mark still counts it. On drawing A this gives 55 risers against 54 in the reference takeoff, with
  per-system differences (KV2/VV1 7 vs 5 counted from the labelled end marks, S3-R8-75 28 vs 35 where seven riser
  marks sit on short unowned stubs).
* **Hatched areas** (regularly spaced parallel strokes: wall sections, existing parts) are discovered per drawing;
  pipe length inside them is measured but excluded from the horizontal quantity and reported as
  `in_hatched_area_m` ("varav i skrafferat område"), since takeoffs normally do not count pipe in walls.
* **DN transitions** are placed only at drawn evidence: the tick mark at a leader end on the pipe. Between two labels
  of different DN the geometry belongs to the label whose tick is not the boundary; when both (or neither) carry a
  tick and no dead end decides, the run is AMBIGUOUS_DN_BOUNDARY. A tick in the middle of a branch that continues
  past it (DN change or plain pointer, undecidable) makes the part between junction and tick AMBIGUOUS.
  Reducer symbols are not recognised as proof of a transition point.
* **Label-vs-takeoff convention on dead-end stubs**: a stub labelled DN75 with its tick right after the junction is
  owned as DN75 from that tick (label evidence). A human takeoff may count the stub as the main DN up to the last
  tick before the riser; the engine does not guess and reports the label's reading.
* **Unlabeled branches** at junctions stay AMBIGUOUS_BRANCH with candidate identities; only collinear straight-through
  runs, agreeing anchors, and the junction's own DN up to a drawn tick continue ownership through junctions.
* **Bundle labels** (one leader crossing N pipes with N stacked rows) are resolved through drawing-local layer-name
  tokens (exact, wildcard, or abbreviated tail such as KV2 -> V2), a unique parallel-line count bijection, or the row
  whose own underline the leader starts from; a bundle with two rows of the same system and different DN on the same
  layer stays ambiguous. Runs interrupted by symbol groups (stacked valve/coupling circles) are not bridged through
  the symbols: the geometry beyond the symbol group stays UNNAMED unless it carries its own label.
* **Count prefixes** ("5xKV2-X31") are read and recorded as the label's multiplier; quantities count the pipes actually
  drawn and attached (parallel lines), never the multiplier times one line.
* **Stroke-font recognition** relies on generic reference alphabets (Hershey simplex/duplex, Helvetica, Courier,
  Times skeletons). Very small text (< 2.5 pt on the page) and exotic CAD fonts produce unknown glyphs ('?');
  unknown characters are never repaired from expected words. The one exception is a character whose ink is cut
  by a clipping edge of the drawing (a sheet-part boundary that halves a label): the truncated character is
  completed from what this drawing itself writes, and only when one reading dominates the alternatives.
* **Hatched areas** are detected as regularly spaced parallel strokes and pipe inside them is measured but held
  out of the total. The engine cannot tell a wall section from a large area hatch marking an adjacent sheet part,
  so on a sheet that hatches most of its plan (drawing W-50-1-A-0014: 39 m hatched against 48 m outside) the
  operator decides with the "Räkna med skrafferade ytor" checkbox.
* **Open-world drawing D** (ground-heating site plan, 1:400): labels are zone descriptions without DN, placed on
  unlabeled loop pipes; no VVS designation grammar exists, so no pipes are owned. The engine reports UNSUPPORTED
  structure and zero false ownership. Post-freeze, per-glyph O/0 twin substitution lets the vector scale bar
  (0 5 10 20 30 METER) be read (BAR_ONLY, 1:400).
* **Unreadable characters are only partly recoverable.** The OCR-assisted pass fills a '?' only where OCR reads
  the same word and agrees with it character for character. On dense drawings much of the small text is beyond
  OCR too, so unreadable characters remain; the unresolved list now says how many sit inside a designation (which
  costs a takeoff row) and how many sit in legend or note text (which costs nothing).
* **The review agents are deterministic checks, not a language model.** They compare the result against the
  drawing's own evidence and report where to look; they do not reason about intent, and they never edit a
  measurement. The OCR cross-check reads the rendered page only to ask whether a designation exists where the
  vector reading has none - it never contributes a metre.
* **Scanned drawings are not analysed.** Only vector PDFs are read. A scanned or image-only page is classified,
  skipped and reported; a PDF with no vector page is rejected. Measuring a scan means inferring geometry from
  pixels, and on these drawings that produced errors large enough to be misleading, so the engine says no instead.
* **Docker images** could not be built inside the development container (no Docker daemon); the Dockerfiles and
  compose file are provided as written and the backend/frontend were verified with pytest and `npm run build`.
* Multi-page PDFs are analysed page by page; overlays and artifacts are written for page 0 (the first analysed page)
  in the CLI and web application.

## Added after the generality pass over four unseen drawing styles

* **One scale per page, not per drawing region.** A detail box drawn at another scale is measured at the plan's
  scale. Where the page states two ratios and no bar confirms either, the reading refuses rather than picks; where
  a bar disagrees with the text, the bar is used, the state is CONFLICT, and every run measured that way now
  carries the conflict in its reasons rather than reading as confidently measured.
* **Curved dashed runs are not bridged around a bend.** Curves (Bezier, arc, polyline) are read and measured, but
  a break in a dashed *curve* is only closed where the pieces are collinear or meet at a corner.
* **A bundle label listing more codes than the sheet draws lines** is left ambiguous. Elimination settles it only
  when every other run of the bundle is named elsewhere AND the remaining code's own leader touches the remaining
  run; without that positive contact the case stays open rather than being split by a convention.
* **Identity can still be decided by node ordering in one case.** The junction pass stops looking at a run once it
  is confirmed, so an unnamed length between two junctions takes the identity of whichever end was reached first.
  A pass demoting such runs where the far end disagrees was written, measured, and reverted: on the reference set
  it cost correct metres and removed no wrong ones. The defect is real and unfixed.
* **Material written after the dimension would merge two identities.** `identity_from_text` drops short alphabetic
  tokens after the DN token, which is right for an insulation marker (`FJV1-S6-50/W`) and wrong for an office that
  writes the material there (`VS1-20-CU` vs `VS1-20-PEX`). No sheet in the corpus writes it that way, so the change
  cannot be tested and has not been made.
* **Very large pages can exceed the analysis timeout.** Five of 212 pages in the style corpus did not finish inside
  240 s. A page that times out is reported as TIMEOUT; it never produces a partial quantity.

## Labels that never reach their pipe

Counted per label rather than per metre, this is the largest remaining gap. A pipe designation reaches its pipe
on 91 % of the reference drawing, 84 % of drawing D, and between 53 % and 92 % of the unseen styles. What is left
falls into two kinds, and the reading now says which of them each label is:

* **No line starts at the label at all.** Some are legend rows, which have no leader by design. The rest are
  labels the draughtsman placed directly beside the pipe. The engine will not read those: identity comes from a
  designation and its real leader, and "the nearest run" is the rule this whole system exists to avoid. They are
  reported as `missing_leader`, with the reason.
* **A line starts, and its end reaches nothing the reading accepted as pipe.** Where the end lands on a family
  that was declined or never weighed, the declined-geometry layer shows which.

### A rule that was measured and rejected

A leader's arrowhead is drawn up to the **edge** of a pipe, but contact is measured to its centreline, so on a
run drawn with a two-point pen the leader lands about one point away from what the reading indexes. The contact
tolerance caps the pen allowance at half a point, which refuses those. Counting half of each pen instead - which
is what the ink actually does - won attachments on two unseen styles (S1 77 % -> 92 %, S2 68 % -> 71 %) and cost
the reference set 0.40 m: on drawing E it moved 0.34 m across a size boundary from `S1-P2-160` to `S1-P2-75`, and
turned two cases the reading had correctly left unresolved into confident wrong ones. Restricting the widening to
leaders that touch nothing at all did not separate the two: the same leader on drawing E is one of them. Total
absolute error went 15.46 m -> 15.86 m, so the rule was reverted. It is written down here because the geometry
behind it is right and the obstacle is the size-boundary walk, not the tolerance.

## Ink that never becomes pipe

Most of the ink on a plan sheet is not pipe, and the reading has four different relationships to a drawn family:
it measures it, it weighs it and sets it aside, no label's leader ever comes near it, or it sits on a layer the
drawing uses for its own labels and frames. Only the first produces metres. The others used to leave the reading
without a word, which made a declined wall and a missed run look identical on the sheet - both simply grey - so
`declined-geometry.json` now carries all of them with the reason and a bounded sample of the strokes, and the
viewer draws them as *Bortvald geometri*. On the seven drawings in the corpus every stroke that is not a letter or
a leader line lands in one of the four, and a test holds that invariant.

Two limits are worth stating plainly:

* **A family no leader points at can never be measured, however much it looks like pipe.** Identity comes from a
  designation and its real leader; a run with neither has no identity, and inventing one would be exactly the wrong
  certainty. Such a family is reported - and marked when its layer is named the way this drawing names its pipe
  layers, which is the case a reader most wants to look at - but it is never claimed. On the reference drawing that
  is 36.9 m of ink on VVS-named layers, none of it in the hand takeoff.
* **The strokes carried are bounded** (8 000 for weighed-and-declined families, 4 000 for unweighed ones, and no
  single family may take more than 3 000 / 1 500). A building outline can hold tens of thousands of strokes; past
  the budget a family reports its full length and segment count with `segments_truncated` set, so the number is
  complete even when the picture is a sample. The budget is spent on pipe-named layers first, so a vector logo
  cannot crowd out the ink a reader actually wants to look at.
* **Filled shapes are counted, not drawn.** A pipe is a stroked line; a filled room outline or piece of furniture
  is not one however much of the sheet it covers. Their number and length are reported (2 199.75 m on the
  reference drawing) so the sheet adds up, and they are never offered as pipe candidates.

## Where an identity comes from

Three sources, and only three - what an identity *is*, and where it is allowed to go:

1. **the designation the sheet writes** - system, material, dimension, read from the drawing's own glyphs;
2. **the real leader** from that designation to a piece of drawn geometry;
3. **the graph** that geometry forms - chains, junctions, collinear arms.

Neither model-assisted pass is a fourth source, and the difference is worth stating precisely because the whole
takeoff rests on it.

The **second reader** is a tie-breaker between the three, never a source. It is asked only about an anchor the
geometry itself already declared AMBIGUOUS, and the only admissible answers are the families that leader's own
end actually landed on. `verify()` refuses anything else character for character; an answer naming two candidates
stays ambiguous; and `apply_answers` checks again at the point of use that the chosen family is one the anchor
really touched, refusing it at the door otherwise. All it can do is narrow an existing contact set from several
to one. It cannot introduce a designation, a DN, a coordinate, a leader or a metre - there is no code path from
it to any of those. It does not answer "what is this pipe"; the label already said that. It answers "which of the
drawn families did this label's leader mean", among candidates the three sources produced.

The **look at the page** cannot do even that: no `apply()`, no number in a finding, and the only thing it may
produce is the name of a tile from a list the reading drew.

Measured rather than asserted: on the reference drawing the second reader is asked nothing at all, because every
ambiguous anchor there touches exactly one family and there is nothing to choose between. On `S3_25`, the sheet in
the corpus with real multi-family ambiguity, it is asked twice, answers OKLART twice, and settles nothing:
42.399 m with it on and 42.399 m with it off. To date it has moved zero metres on every drawing measured.

## What a language model is and is not allowed to do here

The measurement path is vector geometry and nothing else. Two model-assisted passes exist, both fenced in code:

* **A second reader** (`vvs_engine/semantics/astra.py`) may choose among candidates the drawing itself offers, for a
  case the engine already declared AMBIGUOUS. `verify()` refuses any answer that is not one of those candidates, an
  answer naming two of them stays ambiguous, and a chosen family is checked again at the point of use against the
  geometry that leader actually touched. Without a transport nothing is asked, which is the default: the engine is
  deterministic and needs no network.
* **A look at the rendered page** (`vvs_engine/review/vision.py`) may report what the vector reading seems to have
  missed, and say **where** by naming one of the tiles drawn on the picture it was shown - a rectangle the caller
  drew, never a coordinate the model produced, which is the same fence the second reader works behind. A tile name
  that is not on the list is dropped rather than interpreted.

  What the tile actually contains is then read out of the vectors alone (`vvs_engine/review/region.py`): which
  stroke family the ink belongs to, what the reading made of it (measured, ambiguous, unowned, declined, never
  weighed, annotation, fill), which labels sit there and whether their leaders reached anything, and one sentence
  naming the reason there are no metres. **The eye says where. The vectors say why.** Only the second of those is
  ever an answer, and neither can move a metre: there is no `apply()`, and the account is computed from the
  reading it is explaining.

  Measured on the reference drawing, five findings: one located to a tile that holds 45 m of measured pipe, where
  the vectors contradict the eye outright; two to tiles whose ink is all `NO_LEADER_EVER_CAME_NEAR_IT` - the model
  saw building outline and un-overlaid section detail and was right about both, for the reason the vectors give;
  one to the legend, where every stroke is annotation. A model that can see is still a model that can be wrong,
  which is why the sentence beside its finding is never its own.

## Geometry the drawing drew twice is reported, not subtracted

A run drawn once whole and once in pieces, or two collinear segments sharing part of their length, is one pipe.
The exact-duplicate test at collection catches a segment redrawn end for end; it does not catch these. Measured
over the style library it is a fifth of the drawn length on the sheets that do it and a few tenths of a percent
on the ones that do not, so it is real.

It is nevertheless reported rather than removed, and that is a measured decision. The doubled stubs sit at joins.
Dropping them moves a graph node, and on the reference sheet a size frontier then landed where the drawing makes
no join at all: six metres changed size to save eight tenths of a metre of double count, and the total absolute
error went from 15.46 m to 21.21 m. Clipping the shared length instead of dropping the segment was worse again,
27.35 m, because the cut itself became a node.

So the reading says where the doubled line is - `drawn_twice` in `declined-geometry.json`, with a place and a
length for each - and leaves the measurement alone. Removing it is worth doing only once a size frontier no
longer depends on which stub happens to be present.
