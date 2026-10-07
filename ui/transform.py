"""World<->screen transform — single zoom-factor model (SPEC 11.8.6), tkinter-free.

World coords: mm, y up (DXF). Screen coords: canvas pixels, y down.
``scale`` is px per world mm; ``ox``/``oy`` is the screen position of the world
origin. screen = (ox + x*scale, oy - y*scale).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from geometry.entities import Pt

MIN_SCALE = 1e-4  # px per mm
MAX_SCALE = 1e6


@dataclass(frozen=True)
class ViewTransform:
    scale: float  # px per world mm
    ox: float  # screen x of world origin
    oy: float  # screen y of world origin

    def to_screen(self, p: Pt) -> tuple[float, float]:
        return (self.ox + p.x * self.scale, self.oy - p.y * self.scale)

    def to_world(self, sx: float, sy: float) -> Pt:
        return Pt((sx - self.ox) / self.scale, (self.oy - sy) / self.scale)

    def zoomed_at(self, sx: float, sy: float, factor: float) -> "ViewTransform":
        """New transform with ``factor`` applied, keeping the world point under (sx, sy) fixed."""
        if factor <= 0.0:
            raise ValueError(f"zoom factor must be positive, got {factor}")
        new_scale = min(MAX_SCALE, max(MIN_SCALE, self.scale * factor))
        w = self.to_world(sx, sy)
        return ViewTransform(
            scale=new_scale,
            ox=sx - w.x * new_scale,
            oy=sy + w.y * new_scale,
        )

    def panned_by(self, dx: float, dy: float) -> "ViewTransform":
        """New transform after shifting content by (dx, dy) screen px."""
        return replace(self, ox=self.ox + dx, oy=self.oy + dy)
