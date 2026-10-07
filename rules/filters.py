"""Hit-test, EPS_PICK derivation, and edge promotion — CONTRACTS §2 (`promoted_edge_at`) + §5.

Headless and stdlib+geometry only (ADR-006/008). The UI converts screen→world
and calls in; it never computes geometry itself.

ADR-016(f): the promotion chain walk is DELEGATED to geometry/runs.chain_run
(the single implementation — the filters/runs twins diverged once). Pick =
nearest Seg within ``eps_pick`` (point-to-segment; FIRST wins ties,
deterministic). Re-promotion of a registered composite KEEPS the composite's
own eid (ADR-012(c) intent as amended by ADR-016; supersedes the
``promoted-promoted-*`` prefixing). Returned Seg: ``eid`` per chain_run,
``members`` = ordered flattened member eids (ADR-012(c)), ``pick_eid`` = the
clicked member eid.
"""
from __future__ import annotations

import math

from geometry.entities import Entity, Pt, Seg
from geometry.runs import chain_run
from geometry.tolerances import EPS_COINCIDE, PICK_PX


def eps_pick_from_scale(px_per_world: float, pick_px: float = PICK_PX) -> float:
    """EPS_PICK (world units) for a canvas scale of ``px_per_world`` px/mm (SPEC §11.2: world-units ~= 3 screen px)."""
    if px_per_world <= 0.0:
        raise ValueError(f"px_per_world must be positive, got {px_per_world}")
    return pick_px / px_per_world


def _pt_seg_dist(p: Pt, s: Seg) -> float:
    """Perpendicular distance from point p to segment s (interior projection allowed)."""
    vx, vy = s.b.x - s.a.x, s.b.y - s.a.y
    wx, wy = p.x - s.a.x, p.y - s.a.y
    L2 = vx * vx + vy * vy
    if L2 <= 0.0:  # degenerate (zero-length) segment
        return math.hypot(wx, wy)
    t = (wx * vx + wy * vy) / L2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(wx - t * vx, wy - t * vy)


def promoted_edge_at(
    primitives: list[Entity],
    p_world: Pt,
    eps_pick: float,
    eps_coincide: float = EPS_COINCIDE,
) -> Seg | None:
    """Pick + promote the edge under ``p_world``; None when nothing is within ``eps_pick``."""
    # -- pick: nearest Seg within eps_pick (FIRST wins ties, deterministic) --
    clicked: Seg | None = None
    best = math.inf
    for ent in primitives:
        if isinstance(ent, Seg):
            d = _pt_seg_dist(p_world, ent)
            if d <= eps_pick and d < best:
                clicked, best = ent, d
    if clicked is None:
        return None

    # -- promotion: single chain walk (ADR-016(f)) --
    result = chain_run(primitives, clicked, eps_coincide, pick_eid=clicked.eid)
    if result is None:
        return None
    return result[0]
