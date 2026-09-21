"""Object models for the review application.

Every editable entity is a small dataclass that round-trips to plain JSON.
Adding a new entity type (valves, walls, symbols, dimensions) means adding a
dataclass here plus a collection on Document - nothing else in the backend
needs to know about it.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

AUTO = "auto"
MANUAL = "manual"
UNKNOWN = "Unknown"

SCHEMA_VERSION = 2

# the detector's own floor: everything above it is kept with its score
DEFAULT_THRESHOLDS = {"label": 0.05, "join": 0.05}


def clean_thresholds(d):
    out = dict(DEFAULT_THRESHOLDS)
    for k in out:
        try:
            v = float((d or {}).get(k, out[k]))
        except (TypeError, ValueError):
            continue
        if 0.0 <= v <= 1.0:
            out[k] = v
    return out


def _f2(v):
    return round(float(v), 2)


@dataclass
class Pipe:
    id: str
    polygon: List[List[float]]          # closed ring, page points
    type: str = UNKNOWN
    source: str = AUTO                  # auto | manual  (class assignment)
    origin: str = AUTO                  # auto | manual  (geometry origin)
    deleted: bool = False
    area: float = 0.0
    joins: List[str] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "Pipe":
        return Pipe(
            id=d["id"],
            polygon=[[_f2(x), _f2(y)] for x, y in d["polygon"]],
            type=d.get("type", UNKNOWN),
            source=d.get("source", AUTO),
            origin=d.get("origin", AUTO),
            deleted=bool(d.get("deleted", False)),
            area=float(d.get("area", 0.0)),
            joins=list(d.get("joins", [])),
        )


@dataclass
class LabelBox:
    id: str
    code: str
    rect: List[float]                   # [x0, y0, x1, y1]
    conf: float = -1.0                  # OCR confidence 0-100, -1 unknown
    source: str = AUTO
    deleted: bool = False
    block: Optional[List[float]] = None  # enclosing stack bbox, if any
    # What was read inside the box when it did not parse as a code (ML
    # detector), shown so the user can correct it instead of retyping.
    text: str = ""
    # The ML detector's box score 0-1; -1 when the label did not come from it.
    score: float = -1.0
    # Installation elevation stated on the drawing next to the code, metres.
    # Sewer runs (system S) are gravity-driven and read higher -> lower, so
    # this decides which stretch a sewer label describes before diameter or
    # position do.  Not read by OCR yet; set by hand in the review UI.
    elevation: Optional[float] = None
    # The note this label took from the LAST label on the connection line it
    # shares ("CL 3200"): one ladder line serves a stack of labels and the
    # note that applies to all of them is written once, at the end.  "" when
    # everything in `code` is the label's own.
    inherited: str = ""

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "LabelBox":
        e = d.get("elevation")
        try:
            e = float(e) if e not in (None, "") else None
        except (TypeError, ValueError):
            e = None
        return LabelBox(
            id=d["id"],
            code=d.get("code", ""),
            rect=[_f2(v) for v in d["rect"]],
            conf=float(d.get("conf", -1.0)),
            source=d.get("source", AUTO),
            deleted=bool(d.get("deleted", False)),
            block=d.get("block"),
            text=str(d.get("text", "") or ""),
            score=float(d.get("score", -1.0)),
            elevation=e,
            inherited=str(d.get("inherited", "") or ""),
        )


DEFAULT_JOIN_RADIUS = 6.0
MIN_JOIN_RADIUS = 1.5
MAX_JOIN_RADIUS = 60.0


@dataclass
class JoinPoint:
    id: str
    point: List[float]                  # [x, y] page points
    # capture radius in page points: every pipe within it, on the side this
    # joining point claims, receives its class.  User-resizable.
    radius: float = DEFAULT_JOIN_RADIUS
    code: str = ""                      # resolved code (from label, or manual)
    labelId: Optional[str] = None
    pipeId: Optional[str] = None        # nearest claimed pipe
    pipeIds: List[str] = field(default_factory=list)   # every claimed pipe
    anchor: Optional[List[float]] = None  # leader-side end, for drawing
    source: str = AUTO
    # Who decided WHICH LABEL this joining point belongs to.  MANUAL means the
    # user pointed it at that label with the Link tool, and the automatic
    # resolver must leave it alone; AUTO means it may be re-resolved from the
    # connection line that actually reaches it.
    labelSource: str = AUTO
    deleted: bool = False
    # ML detection score 0-100 when this point came from the detector, -1
    # when it did not (drawn circles and hand-placed joining points)
    conf: float = -1.0

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "JoinPoint":
        r = float(d.get("radius", DEFAULT_JOIN_RADIUS))
        return JoinPoint(
            id=d["id"],
            point=[_f2(d["point"][0]), _f2(d["point"][1])],
            radius=round(max(MIN_JOIN_RADIUS, min(MAX_JOIN_RADIUS, r)), 2),
            code=d.get("code", ""),
            labelId=d.get("labelId"),
            pipeId=d.get("pipeId"),
            pipeIds=list(d.get("pipeIds", [])),
            anchor=d.get("anchor"),
            source=d.get("source", AUTO),
            labelSource=d.get("labelSource", AUTO),
            deleted=bool(d.get("deleted", False)),
            conf=float(d.get("conf", -1.0)),
        )


@dataclass
class LeaderLine:
    """The thin line a label uses to point at a pipe.

    It is highlighted in the workspace but is NEVER merged into a pipe
    polygon - it is annotation, not pipe geometry.
    """
    id: str
    labelId: Optional[str] = None
    joinId: Optional[str] = None
    path: List[List[List[float]]] = field(default_factory=list)  # [[[x,y],[x,y]], ...]
    code: str = ""
    source: str = AUTO
    deleted: bool = False
    # True when `path` is the line traced from the drawing.  False marks a
    # connection the drawing has no line for, so the UI can hint at it instead
    # of pretending the drawing shows one.
    drawn: bool = True

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "LeaderLine":
        return LeaderLine(
            id=d["id"],
            labelId=d.get("labelId"),
            joinId=d.get("joinId"),
            path=[[[_f2(a[0]), _f2(a[1])], [_f2(b[0]), _f2(b[1])]]
                  for a, b in d.get("path", [])],
            code=d.get("code", ""),
            source=d.get("source", AUTO),
            deleted=bool(d.get("deleted", False)),
            drawn=bool(d.get("drawn", True)),
        )


@dataclass
class Document:
    stem: str
    pdf_path: str
    page: List[float]                   # [width, height] in points
    scale: float                        # background raster px per point
    pipes: List[Pipe] = field(default_factory=list)
    # the reviewed segmentation (one polygon per connected pipe).  `pipes`
    # holds it during steps 1-3; classification splits it at joining points
    # and replaces `pipes` with the split pieces, keeping this as the source.
    base_pipes: List[Pipe] = field(default_factory=list)
    labels: List[LabelBox] = field(default_factory=list)
    joins: List[JoinPoint] = field(default_factory=list)
    leaders: List[LeaderLine] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    wall: List[List[List[float]]] = field(default_factory=list)  # wall rings
    # Every thin connection line traced from the drawing, as raw geometry —
    # including the ones no label was matched to.  `leaders` holds only the
    # matched ones, so this is what lets a joining point be resolved against
    # the line that physically reaches it.  Paths only; the label each one
    # touches is resolved against the CURRENT labels, so lines the user adds
    # or edits labels for are picked up.
    line_pool: List[List[List[List[float]]]] = field(default_factory=list)
    dirty_edits: int = 0                # edits since the last assignment run
    # True while `pipes` holds a CLASSIFIED result (the segmentation split at
    # joining points).  Classification must never run on an already-classified
    # set, or every run would split the previous pieces again and stack new
    # polygons on the old ones.
    classified: bool = False
    saved: bool = True
    # What the ML joining points revealed about the drawing: pipe families
    # (width + dash pattern + colour), connection-line weights, glyph weight
    # (pipe_signature.Signature.to_json()).  {} for a pre-signature session;
    # informational — recomputed on every re-process.
    signature: Dict[str, Any] = field(default_factory=dict)
    # Detector confidence the user settled on, scores 0-1 per class: labels
    # and joining points below it are hidden in the UI and ignored by
    # classification, without being deleted — the detector runs at a low
    # floor and the user slides these before or after the results are shown.
    # Hand-placed objects carry no score and are never filtered.
    thresholds: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS))

    # -- lookups ---------------------------------------------------------- #
    def pipe(self, pid) -> Optional[Pipe]:
        return next((p for p in self.pipes if p.id == pid), None)

    def label(self, lid) -> Optional[LabelBox]:
        return next((l for l in self.labels if l.id == lid), None)

    def join(self, jid) -> Optional[JoinPoint]:
        return next((j for j in self.joins if j.id == jid), None)

    def leader(self, lid) -> Optional[LeaderLine]:
        return next((x for x in self.leaders if x.id == lid), None)

    def label_visible(self, lab) -> bool:
        """Above the user's label threshold (hand-made labels always are)."""
        thr = clean_thresholds(self.thresholds)["label"]
        return lab.score < 0 or lab.score >= thr - 1e-9

    def join_visible(self, j) -> bool:
        """Above the user's joining-point threshold (hand-placed always)."""
        thr = clean_thresholds(self.thresholds)["join"]
        return j.conf < 0 or j.conf >= thr * 100.0 - 1e-6

    def active_leaders(self):
        return [x for x in self.leaders if not x.deleted]

    def active_pipes(self):
        return [p for p in self.pipes if not p.deleted]

    def active_labels(self):
        return [l for l in self.labels if not l.deleted]

    def active_joins(self):
        return [j for j in self.joins if not j.deleted]

    def all_classes(self) -> List[str]:
        found = {p.type for p in self.pipes if p.type and p.type != UNKNOWN}
        found |= {l.code for l in self.labels if l.code}
        found |= {j.code for j in self.joins if j.code}
        return sorted(found | set(self.classes))

    # -- serialisation ----------------------------------------------------- #
    def to_json(self) -> Dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "stem": self.stem,
            "pdf_path": self.pdf_path,
            "page": self.page,
            "scale": self.scale,
            "pipes": [p.to_json() for p in self.pipes],
            "base_pipes": [p.to_json() for p in self.base_pipes],
            "labels": [l.to_json() for l in self.labels],
            "joins": [j.to_json() for j in self.joins],
            "leaders": [x.to_json() for x in self.leaders],
            "classes": self.all_classes(),
            "wall": self.wall,
            "line_pool": self.line_pool,
            "dirty_edits": self.dirty_edits,
            "classified": self.classified,
            "thresholds": clean_thresholds(self.thresholds),
            "signature": self.signature or {},
        }

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "Document":
        return Document(
            stem=d["stem"],
            pdf_path=d.get("pdf_path", ""),
            page=d.get("page", [0, 0]),
            scale=d.get("scale", 2.0),
            pipes=[Pipe.from_json(x) for x in d.get("pipes", [])],
            base_pipes=[Pipe.from_json(x) for x in d.get("base_pipes", [])],
            labels=[LabelBox.from_json(x) for x in d.get("labels", [])],
            joins=[JoinPoint.from_json(x) for x in d.get("joins", [])],
            leaders=[LeaderLine.from_json(x) for x in d.get("leaders", [])],
            classes=list(d.get("classes", [])),
            wall=d.get("wall", []),
            line_pool=d.get("line_pool", []),
            dirty_edits=int(d.get("dirty_edits", 0)),
            classified=bool(d.get("classified", False)),
            thresholds=clean_thresholds(d.get("thresholds")),
            signature=dict(d.get("signature") or {}),
        )
