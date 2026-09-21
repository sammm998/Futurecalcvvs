"""Input classification per page: clean vector, scanned (raster) or mixed.

Decided from the PDF content itself: stroke paths and text characters versus embedded images and their coverage
of the page. Only a page with usable vector content is analysed; a scanned or image-only page is skipped and
reported, because the engine reads the drawing's own geometry rather than guessing at pixels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InputClass:
    mode: str                 # 'vector' | 'raster' | 'mixed' | 'empty'
    n_paths: int
    n_chars: int
    n_images: int
    image_coverage: float     # share of the page area covered by images (0..1)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "n_paths": self.n_paths, "n_chars": self.n_chars, "n_images": self.n_images,
                "image_coverage": round(self.image_coverage, 3), "reasons": self.reasons}


def classify_page(page, drawings=None) -> InputClass:
    """`page` is a PyMuPDF page."""
    if drawings is None:
        drawings = page.get_drawings()
    n_paths = sum(1 for d in drawings if d.get("type") in ("s", "fs", "f") and d.get("items"))
    n_chars = len(page.get_text("text").replace("\n", "").replace(" ", ""))
    area = max(page.rect.width * page.rect.height, 1.0)
    cov = 0.0
    n_images = 0
    for info in page.get_image_info():
        n_images += 1
        b = info.get("bbox")
        if b:
            x0, y0, x1, y1 = b
            cov += max(0.0, min(x1, page.rect.x1) - max(x0, page.rect.x0)) * max(0.0, min(y1, page.rect.y1) - max(y0, page.rect.y0)) / area
    cov = min(cov, 1.0)
    reasons = []
    if n_paths >= 200 or (n_paths >= 50 and n_chars >= 50):
        mode = "vector"
        reasons.append(f"{n_paths} vector paths, {n_chars} text characters")
        if cov >= 0.5:
            mode = "mixed"
            reasons.append(f"embedded image covers {cov:.0%} of the page")
    elif cov >= 0.5 and n_images >= 1:
        mode = "raster"
        reasons.append(f"embedded image covers {cov:.0%} of the page, only {n_paths} vector paths and {n_chars} text characters")
    elif n_paths == 0 and n_chars == 0 and n_images == 0:
        mode = "empty"
        reasons.append("no drawings, text or images")
    elif n_images >= 1 and n_paths < 50:
        mode = "raster"
        reasons.append(f"image page ({cov:.0%} coverage) with {n_paths} vector paths")
    else:
        mode = "vector"
        reasons.append(f"{n_paths} vector paths, {n_chars} text characters, no dominant image")
    return InputClass(mode=mode, n_paths=n_paths, n_chars=n_chars, n_images=n_images, image_coverage=cov, reasons=reasons)
