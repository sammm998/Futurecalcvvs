"""The drawing as a model the agent can ask questions of.

The reading has already happened. This loads what it wrote - pipes, topology, anchors, designations, the legend,
the geometry it declined - and holds it in one place with the lookups an agent needs. Nothing here measures
anything: every number comes from the artifacts the measuring pipeline produced, so an answer given through the
agent and an answer read off the takeoff table cannot disagree.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from functools import cached_property
from typing import Any


def _load(root: str, name: str, default: Any = None) -> Any:
    path = os.path.join(root, name)
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class DrawingModel:
    """Everything one analysed drawing is, as the reading left it.

    A drawing is often a whole set - twenty-six sheets in one file - and the reading writes each sheet down
    under sheets/<page>/ as it reads it. The agent is asked about the drawing, not about its cover page, so
    everything that is a list of things found on a sheet is gathered across every sheet here. Reading only the
    root is how the agent comes to answer "no pipes were found" about a set it measured four hundred metres on.

    The ids carry their page already, so gathering cannot collide: a label is `des|<page>|…`, an attachment
    `anc|<page>|…`. Readings made before the sheets were kept apart have only the root, and it is used as the
    single sheet it is.
    """

    def __init__(self, result_dir: str, page: int | None = None):
        self.root = result_dir
        # när ett blad pekas ut svarar modellen om det bladet; annars om hela handlingen
        self.page = page

    @cached_property
    def sheets(self) -> list[tuple[int, str]]:
        """Each sheet of this reading as (page, directory), or the root as the one sheet it holds."""
        d = os.path.join(self.root, "sheets")
        if os.path.isdir(d):
            found = [(int(n), os.path.join(d, n)) for n in os.listdir(d) if n.isdigit()]
            if found:
                found.sort()
                return [x for x in found if self.page is None or x[0] == self.page] or found
        return [(0, self.root)]

    def _gather(self, name: str, key: str) -> list[dict]:
        out: list[dict] = []
        for pg, d in self.sheets:
            for row in (_load(d, name, {}) or {}).get(key) or []:
                if isinstance(row, dict):
                    row.setdefault("page", pg)
                out.append(row)
        return out

    # ---- the artifacts, read once ------------------------------------------------
    @cached_property
    def quantities(self) -> dict:
        """The takeoff. For a set it is the set's - a designation drawn on four sheets is one row.

        The scale belongs to a sheet, not to a set, so the one carried here is the first settled one; a sheet's
        own is in `sheet_scales`. Nothing is measured here: both files were written by the reading.
        """
        doc = _load(self.root, "document-quantities.json") if self.page is None else None
        own = _load(self.root, "quantities.json", {"rows": [], "scale": {}, "totals": {}})
        if self.page is not None and self.sheets:
            own = _load(self.sheets[0][1], "quantities.json", own)
        if doc and (doc.get("rows") or doc.get("totals", {}).get("sheets", 0) > 1):
            scale = own.get("scale") or {}
            if not scale.get("meters_per_pdf_point"):
                for sc in self.sheet_scales.values():
                    if sc.get("meters_per_pdf_point"):
                        scale = sc
                        break
            return {"rows": doc.get("rows") or [], "scale": scale, "totals": doc.get("totals") or {},
                    "sheets": doc.get("sheets") or []}
        return own

    @cached_property
    def sheet_scales(self) -> dict[int, dict]:
        """What each sheet is drawn in. A set is not one scale, and a metre is not comparable across two."""
        return {pg: (_load(d, "quantities.json", {}) or {}).get("scale") or {} for pg, d in self.sheets}

    @cached_property
    def pipes(self) -> list[dict]:
        return self._gather("physical-pipes.json", "physical_pipes")

    @cached_property
    def anchors(self) -> list[dict]:
        return self._gather("pipe-code-anchors.json", "anchors")

    @cached_property
    def designations(self) -> list[dict]:
        return self._gather("vector-designations.json", "designations")

    @cached_property
    def legend(self) -> dict:
        return _load(self.root, "drawing-legend.json", {"entries": []})

    @cached_property
    def topology(self) -> list[dict]:
        return self._gather("pipe-topology.json", "families")

    @cached_property
    def declined(self) -> dict:
        """Ink the reading looked at and decided was not pipe, gathered over the sheets it was declined on."""
        out: dict = {"families": [], "unconsidered": [], "drawn_twice": {}, "totals": {}}
        for pg, d in self.sheets:
            one = _load(d, "declined-geometry.json", {}) or {}
            for k in ("families", "unconsidered"):
                for row in one.get(k) or []:
                    if isinstance(row, dict):
                        row.setdefault("page", pg)
                    out[k].append(row)
            for k, v in (one.get("drawn_twice") or {}).items():
                out["drawn_twice"][f"{pg}:{k}"] = v
            for k, v in (one.get("totals") or {}).items():
                if isinstance(v, (int, float)):
                    out["totals"][k] = round(out["totals"].get(k, 0) + v, 3)
        return out

    @cached_property
    def issues(self) -> list[dict]:
        return self._gather("unresolved-issues.json", "issues")

    @cached_property
    def review(self) -> dict:
        return _load(self.root, "review-findings.json", {"findings": [], "agents": []})

    @cached_property
    def profile(self) -> dict:
        return _load(self.root, "drawing-profile.json", {})

    @cached_property
    def reconciliation(self) -> dict:
        return _load(self.root, "reconciliation.json", {})

    # ---- lookups -----------------------------------------------------------------
    @property
    def scale(self) -> dict:
        return self.quantities.get("scale") or {}

    @property
    def meters_per_pt(self) -> float | None:
        return self.scale.get("meters_per_pdf_point")

    @cached_property
    def pipe_by_id(self) -> dict[str, dict]:
        return {p["physical_pipe_id"]: p for p in self.pipes}

    @cached_property
    def anchor_by_id(self) -> dict[str, dict]:
        return {a["anchor_id"]: a for a in self.anchors}

    @cached_property
    def designation_by_id(self) -> dict[str, dict]:
        return {d["did"]: d for d in self.designations}

    @cached_property
    def systems(self) -> list[str]:
        return sorted({e["code"].upper() for e in self.legend.get("entries", []) if e.get("role") == "system"})

    @cached_property
    def components(self) -> list[str]:
        return sorted({e["code"].upper() for e in self.legend.get("entries", []) if e.get("role") == "component"})

    def bbox_of_pipe(self, p: dict) -> list[float]:
        xs: list[float] = []
        ys: list[float] = []
        for line in p.get("geometry") or []:
            for x, y in line:
                xs.append(x); ys.append(y)
        return [min(xs), min(ys), max(xs), max(ys)] if xs else [0.0, 0.0, 0.0, 0.0]

    # ---- the pipe graph ----------------------------------------------------------
    @cached_property
    def _prim_owner(self) -> dict[tuple[str, int], str]:
        """Which physical pipe owns each primitive of each family."""
        out: dict[tuple[str, int], str] = {}
        for p in self.pipes:
            fam = p.get("representation_family") or ""
            for n in p.get("source_segments") or []:
                pass
        # source_segments carry path ids, not prim ids; the topology's nodes carry prim ids, so the join is done
        # through the graph nodes the pipe lists
        for p in self.pipes:
            fam = p.get("representation_family") or ""
            for nid in p.get("graph_nodes") or []:
                out[(fam, int(nid))] = p["physical_pipe_id"]
        return out

    @cached_property
    def adjacency(self) -> dict[str, set[str]]:
        """Physical pipes that meet at a shared graph node.

        Two runs of different size or system that touch at a node are neighbours: that node is exactly where the
        drawing changes something, and it is what a question like "what does this connect to" means.
        """
        by_node: dict[tuple[str, int], set[str]] = defaultdict(set)
        for p in self.pipes:
            fam = p.get("representation_family") or ""
            for nid in p.get("graph_nodes") or []:
                by_node[(fam, int(nid))].add(p["physical_pipe_id"])
        adj: dict[str, set[str]] = defaultdict(set)
        for _, ids in by_node.items():
            for a in ids:
                for b in ids:
                    if a != b:
                        adj[a].add(b)
        return adj

    def connected(self, pipe_id: str) -> list[str]:
        """Every pipe reachable from this one through shared nodes, in a stable order."""
        seen = {pipe_id}
        stack = [pipe_id]
        while stack:
            cur = stack.pop()
            for nb in self.adjacency.get(cur, ()):  # type: ignore[arg-type]
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return sorted(seen)

    def path_between(self, a: str, b: str) -> list[str]:
        """Fewest runs from a to b through shared nodes; empty when they are not connected."""
        if a == b:
            return [a]
        prev: dict[str, str] = {a: ""}
        queue = [a]
        while queue:
            nxt: list[str] = []
            for cur in queue:
                for nb in sorted(self.adjacency.get(cur, ())):  # type: ignore[arg-type]
                    if nb in prev:
                        continue
                    prev[nb] = cur
                    if nb == b:
                        out = [b]
                        while out[-1] != a:
                            out.append(prev[out[-1]])
                        return list(reversed(out))
                    nxt.append(nb)
            queue = nxt
        return []

    @cached_property
    def nodes_by_family(self) -> dict[str, dict[int, dict]]:
        return {f["family"]: {int(n["id"]): n for n in f.get("nodes") or []} for f in self.topology}

    def free_ends(self) -> list[dict]:
        """Ends of runs that meet nothing else in their own family.

        The topology already counted how many primitives meet at each node, so a node of degree one is an end the
        drawing draws and stops at: a connection to another system, a drain, a riser, a continuation onto another
        sheet - or a break in the reading. Which of those it is, the drawing has to say; that it is an end, the
        graph says.
        """
        out = []
        for p in self.pipes:
            fam = p.get("representation_family") or ""
            nodes = self.nodes_by_family.get(fam, {})
            for nid in p.get("graph_nodes") or []:
                n = nodes.get(int(nid))
                if n is not None and int(n.get("degree", 0)) <= 1:
                    out.append({"pipe_id": p["physical_pipe_id"], "designation": p.get("designation"),
                                "dn": p.get("dn"), "page": p.get("page", 0),
                                "point": [round(n["x"], 1), round(n["y"], 1)]})
        out.sort(key=lambda d: (d["pipe_id"], d["point"]))
        return out

    @cached_property
    def frontiers(self) -> list[dict]:
        """Where every run stops, and why - gathered over the sheets the runs are drawn on."""
        return self._gather("pipe-extent-frontiers.json", "frontiers")

    @cached_property
    def frontiers_by_pipe(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = defaultdict(list)
        for f in self.frontiers:
            out[str(f.get("pipe"))].append(f)
        return dict(out)

    def size_frontiers(self) -> list[dict]:
        """Nodes where the drawing changes what the pipe is: a size, a system or a material boundary."""
        by_node: dict[tuple[str, int], list[dict]] = defaultdict(list)
        for p in self.pipes:
            fam = p.get("representation_family") or ""
            for nid in p.get("graph_nodes") or []:
                by_node[(fam, int(nid))].append(p)
        out = []
        for (fam, nid), ps in sorted(by_node.items()):
            ids = {p.get("identity") for p in ps}
            if len(ids) < 2:
                continue
            n = self.nodes_by_family.get(fam, {}).get(nid)
            if n is None:
                continue
            out.append({"point": [round(n["x"], 1), round(n["y"], 1)],
                        "page": ps[0].get("page", 0),
                        "between": sorted({p.get("designation") or "" for p in ps}),
                        "pipe_ids": sorted(p["physical_pipe_id"] for p in ps)})
        return out
