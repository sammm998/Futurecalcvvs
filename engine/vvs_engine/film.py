"""What each stage of the reading found, small enough to send while it is still running.

The analysis takes a minute or two on a large sheet, and until it finished there was nothing to look at but a
percentage. This records a frame per stage - the boxes the text reader found, the leaders it traced, the runs it
measured - bounded in size so it can be written and polled cheaply. It is a view of the reading, never an input
to it: nothing here is read back by the engine.
"""
from __future__ import annotations

from typing import Any, Callable

# a frame is drawn on a screen, not measured: a few hundred shapes is already more than the eye follows
CAP = 900
NOTES_CAP = 240         # a running account, not a log: past this the reader has stopped reading anyway


def _thin(items: list, cap: int = CAP) -> list:
    """Every nth item, so a frame shows the whole sheet rather than its top-left corner."""
    if len(items) <= cap:
        return list(items)
    step = len(items) / cap
    return [items[int(i * step)] for i in range(cap)]


def _box(b) -> list[float]:
    return [round(float(v), 1) for v in b]


class Film:
    """Collects the frames. `sink(stage, payload)` is called once per stage, in order."""

    def __init__(self, sink: Callable[[str, dict], None] | None):
        self._sink = sink
        self._notes = 0

    def __bool__(self) -> bool:
        return self._sink is not None

    def note(self, stage: str, text: str) -> None:
        """One line of what the reading is working out, while it is still working it out.

        A frame lands when a stage finishes, and the stages that take the longest are the ones with nothing to
        show until they do: a minute of blank paper, then everything at once. These are the sentences in between
        - what the sheet turned out to carry, which pen was taken for pipe and why, which reading of the sheet
        won. Every one of them is a fact the reading already has at that moment and is about to act on; none of
        them is written for the screen, and none is read back.
        """
        self._notes += 1
        if self._notes > NOTES_CAP:
            return
        self.frame("NOTE", {"on": stage, "t": text[:220]})

    def frame(self, stage: str, payload: dict[str, Any]) -> None:
        if self._sink is None:
            return
        try:
            self._sink(stage, payload)
        except Exception:
            # a frame that cannot be written must never interrupt a reading
            pass

    # --- the frames themselves -------------------------------------------------

    def page(self, page) -> None:
        """The sheet as it stands before anything has been decided about it.

        With only a page size to go on the film showed a white rectangle for as long as the text took to rebuild
        - a minute on a dense sheet, with a sweep line crossing empty paper. The drawing is already read at this
        point, so a thinned sample of its own strokes goes with it: the reader sees the sheet arrive, and then
        watches the reading fill it in. It is a sample for drawing on a screen, never a measurement.
        """
        every = _thin(page.paths)
        strokes = []
        for pth in every:
            for sg in pth.segs[:2]:
                strokes.append([round(sg.x0, 1), round(sg.y0, 1), round(sg.x1, 1), round(sg.y1, 1)])
        self.frame("READING_PDF", {"page": {"w": round(float(page.info.width), 1),
                                            "h": round(float(page.info.height), 1)},
                                   "n_paths": len(page.paths), "strokes": strokes[:CAP]})

    def seeing(self, region, words, i: int, n: int) -> None:
        """Where the vision agent is looking right now, and what it read there.

        One frame per tile, so the sheet shows the pass happening rather than a percentage: the box being read,
        and the words found in it. It is a view of a check, never an input to a measurement.
        """
        self.frame("SEEING", {"region": [round(float(v), 1) for v in region],
                              "words": [{"t": w[:18], "b": _box(b)} for w, b, _c in words[:60]],
                              "i": i, "n": n})

    def text(self, rows) -> None:
        self.frame("RECONSTRUCTING_TEXT",
                   {"rows": [_box(r.bbox) for r in _thin(rows)], "n": len(rows)})

    def designations(self, designations) -> None:
        keep = _thin(list(designations), 400)
        self.frame("READING_DESIGNATIONS",
                   {"labels": [{"b": _box(d.bbox), "t": (d.text or "")[:22]} for d in keep], "n": len(designations)})

    def leaders(self, leaders) -> None:
        out = []
        for ld in _thin(list(leaders), 500):
            pts = getattr(ld, "points", None)
            if not pts:
                pts = [(ld.x0, ld.y0), (ld.x1, ld.y1)] if hasattr(ld, "x0") else None
            if pts:
                out.append([[round(float(x), 1), round(float(y), 1)] for x, y in pts])
        self.frame("FINDING_LEADERS", {"leaders": out, "n": len(leaders)})

    def families(self, families, graphs) -> None:
        fams = []
        for fk, rf in list(families.items())[:12]:
            g = graphs.get(fk)
            segs = [] if g is None else _thin([p.seg for p in g.prims.values()], 500)
            fams.append({"key": fk[:60], "width": round(getattr(rf, "width", 0.0), 2),
                         "n": 0 if g is None else len(g.prims),
                         "segs": [[round(s.x0, 1), round(s.y0, 1), round(s.x1, 1), round(s.y1, 1)] for s in segs]})
        self.frame("RESOLVING_PIPE_REPRESENTATION", {"families": fams})

    def pipes(self, pipes) -> None:
        out = []
        for p in _thin(list(pipes), 500):
            for line in (p.points or [])[:4]:
                out.append({"i": p.identity.key.replace("|DN", "-"),
                            "p": [[round(float(x), 1), round(float(y), 1)] for x, y in _thin(list(line), 120)]})
        self.frame("BUILDING_PHYSICAL_PIPES", {"pipes": out, "n": len(pipes)})

    def measured(self, quantities, scale) -> None:
        rows = [{"d": q["designation"], "m": round(q.get("confirmed_total_m") or 0.0, 2)}
                for q in quantities if (q.get("confirmed_total_m") or 0) > 0]
        rows.sort(key=lambda r: -r["m"])
        self.frame("MEASURING", {"quantities": rows[:60], "total_m": round(sum(r["m"] for r in rows), 2),
                                 "scale": {"state": scale.state, "reason": scale.reason}})
