# Pixel-distance geometry verification

Measured 2026-09-07 on saved Dimension and LLM results for real sheet
**W-50-1-A-0011**. This is not the cited production dataset. No inference was
rerun, no paid model call was made, and saved drawing results were not changed.

| Method | Pipes before / after | Full-trace points | Previous simplifier | New points | Reduction from full trace | Largest discarded deviation | Largest absolute per-pipe length change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dimension | 140 / 140 | 1,817 | 889 | 474 | 73.9% | 0.991293082 px | 0.097643231% |
| LLM | 108 / 108 | 1,785 | 797 | 377 | 78.9% | 0.991293082 px | 0.098636132% |

Lengths are measured from response-canvas coordinates, summing each undirected
edge once. All percentages use the full unsimplified pipe as the denominator.

| Method | Total before (px) | Total after (px) | Total change |
| --- | --- | --- | --- |
| Dimension | 24,198.249437502 | 24,188.028581750 | −0.042237997% |
| LLM | 24,198.249437502 | 24,187.981562090 | −0.042432307% |

The per-pipe limit is enforced independently; aggregate results cannot hide a
pipe exceeding its budget. See [geometry-measurements.csv](geometry-measurements.csv)
for **all 248 per-pipe measurements**, including method, run ID, pipe ID, point
counts, original and final lengths, signed change in pixels and percent,
maximum discarded deviation, and IDs of retained sub-pixel vertices by reason.

Nine sub-pixel vertices in Dimension and eleven in LLM remain because removing
them would violate their individual pipe's length budget. No remaining sub-pixel
vertices in these two results were blocked by topology, accumulated deviation,
or reversal. Other inputs may retain such protected points.

## Supplied rounded corner

The seven-point example becomes exactly these three original points:

```text
1026.56,449.20 → 1013.60,462.64 → 1013.24,549.16
```

- Maximum discarded-point deviation: **0.353006653 px**.
- Length: **105.274918506 → 105.191453282 px**.
- Signed length change: **−0.079283105%**.

## Invariants checked

The 1.0 px tolerance applies after mapping to the requested `coordinateSpace`.
Every discarded original vertex is checked against its **final replacement
segment**, not just its neighbours at the moment of removal. The largest
reported deviation is that final measurement. Every retained coordinate and ID
comes from the original graph; there is no interpolation, rounding or resampling.

The audit independently reconstructs each replacement edge's original chain,
checks that every original edge is represented exactly once, and verifies:

- Original endpoints, explicit junctions and retained vertex degrees survive.
- No pipe is split, no branch is lost, and no crossing is merged by coordinates.
- All original points stay within 1.0 px of their final segment.
- Each pipe's absolute length change is strictly below 0.1% of its full trace.
- Pipe count, IDs, label ownership, and connected result-schema validity remain.
- Both `includeScaleAndLengths` values return identical geometry; requested
  `length.px` equals the length of that simplified geometry.

Sub-pixel direction changes are intentionally removable, unlike the previous
angular test. Significant bends are protected by the final 1.0 px bound.
Original-chain projections must remain monotonic, preventing reversal shortcuts.
When greedy removal stalls, two-vertex windows reconsider original corner
candidates, allowing a better original fillet vertex to be retained.

## Reproduction

```sh
python -m detection_v2.measure_geometry \
  debug/W-50-1-A-0011/.assignment-results/flow.json \
  debug/W-50-1-A-0011/.assignment-results/astra.json
python -m pytest -q detection_v2
```

Drawing inputs remain local. Source run IDs:
Dimension `61f8826e8361b7e8284d5a9e`, LLM `3476168078342fac759efb09`.
The audit emits full per-pipe JSON. Runtime response logs include aggregate
point counts, pixel lengths, maximum per-pipe length change and maximum discarded
deviation, identified by request runId and assignment method.
