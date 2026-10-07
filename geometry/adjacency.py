"""Endpoint-keyed adjacency map — ADR-012(b) / ADR-015(e).

Pure derived function of the entity list (no ModelState field; "maintained /
traveling in snapshots" is satisfied by derivation — documents are tiny).
rules (cascade) and model (M4 cache) both import it: model may import geometry,
never rules (SPEC §11.1).
"""
from __future__ import annotations

import math

from geometry.entities import Arc, Entity, PointEnt, Seg, TextEnt
from geometry.tolerances import EPS_COINCIDE


def attachment_points(e: Entity) -> list[tuple[float, float]]:
    """Endpoint-like attachment points per entity kind (circles have none)."""
    if isinstance(e, Seg):
        return [(e.a.x, e.a.y), (e.b.x, e.b.y)]
    if isinstance(e, Arc):
        return [
            (e.center.x + e.r * math.cos(math.radians(e.start_deg)),
             e.center.y + e.r * math.sin(math.radians(e.start_deg))),
            (e.center.x + e.r * math.cos(math.radians(e.end_deg)),
             e.center.y + e.r * math.sin(math.radians(e.end_deg))),
        ]
    if isinstance(e, PointEnt):
        return [(e.p.x, e.p.y)]
    if isinstance(e, TextEnt):
        return [(e.p.x, e.p.y)]
    return []



def build_adjacency(
    entities: list[Entity], eps_coincide: float = EPS_COINCIDE
) -> dict[str, frozenset[str]]:
    """eid -> frozenset of other eids sharing an attachment point within eps_coincide."""
    pts: list[tuple[str, tuple[float, float]]] = []
    for e in entities:
        for p in attachment_points(e):
            pts.append((e.eid, p))
    adj: dict[str, set[str]] = {}
    for i, (eid_a, pa) in enumerate(pts):
        for eid_b, pb in pts[i + 1 :]:
            if eid_a == eid_b:
                continue
            if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) <= eps_coincide:
                adj.setdefault(eid_a, set()).add(eid_b)
                adj.setdefault(eid_b, set()).add(eid_a)
    return {k: frozenset(v) for k, v in adj.items()}
