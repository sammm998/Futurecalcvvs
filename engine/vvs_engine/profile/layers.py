"""CAD / vector structural family statistics (per layer, per style). Purely descriptive."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..pdf.extract import RawPage, RawPath


def style_key(p: RawPath) -> str:
    return f"{p.kind}|w{p.width:.2f}|c{p.color if p.color else '-'}"


def layer_tokens(layer: str) -> list[str]:
    """Split a layer name into structural tokens (separators: | - _ space $ . ,)."""
    return [t for t in re.split(r"[|\-_ $.,]+", layer) if t]


@dataclass
class LayerStats:
    layer: str
    layer_id: int
    n_paths: int = 0
    n_segments: int = 0
    total_length: float = 0.0
    kinds: Counter = field(default_factory=Counter)
    widths: Counter = field(default_factory=Counter)
    colors: Counter = field(default_factory=Counter)
    styles: Counter = field(default_factory=Counter)
    n_curves: int = 0
    small_paths: int = 0        # bbox diagonal < 12 pt
    tiny_paths: int = 0         # bbox diagonal < 3 pt
    long_paths: int = 0         # bbox diagonal > 60 pt
    single_seg_paths: int = 0
    seg_len_hist: Counter = field(default_factory=Counter)
    tokens: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer, "n_paths": self.n_paths, "n_segments": self.n_segments,
            "total_length_pt": round(self.total_length, 1), "kinds": dict(self.kinds),
            "widths": {k: v for k, v in sorted(self.widths.items())}, "colors": {str(k): v for k, v in self.colors.most_common(6)},
            "styles": {k: v for k, v in self.styles.most_common(8)}, "n_curves": self.n_curves,
            "small_paths": self.small_paths, "tiny_paths": self.tiny_paths, "long_paths": self.long_paths,
            "single_segment_paths": self.single_seg_paths, "tokens": self.tokens,
        }


def compute_layer_stats(page: RawPage) -> dict[str, LayerStats]:
    stats: dict[str, LayerStats] = {}
    for p in page.paths:
        st = stats.get(p.layer)
        if st is None:
            st = LayerStats(layer=p.layer, layer_id=p.layer_id, tokens=layer_tokens(p.layer))
            stats[p.layer] = st
        st.n_paths += 1
        st.n_segments += len(p.segs)
        L = p.length
        st.total_length += L
        st.kinds[p.kind] += 1
        st.widths[f"{p.width:.2f}"] += 1
        st.colors[str(p.color)] += 1
        st.styles[style_key(p)] += 1
        st.n_curves += p.n_curves
        diag = math.hypot(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1])
        if diag < 12:
            st.small_paths += 1
        if diag < 3:
            st.tiny_paths += 1
        if diag > 60:
            st.long_paths += 1
        if len(p.segs) == 1:
            st.single_seg_paths += 1
        for s in p.segs:
            l = s.length
            b = "0" if l < 1 else ("1-3" if l < 3 else ("3-8" if l < 8 else ("8-20" if l < 20 else ("20-60" if l < 60 else "60+"))))
            st.seg_len_hist[b] += 1
    return stats


def width_classes(page: RawPage) -> list[float]:
    """Distinct stroke widths sorted ascending (drawing-derived)."""
    ws = sorted({round(p.width, 2) for p in page.paths if p.kind != "f"})
    return ws
