"""Collinear run re-derivation and the single promotion chain walk.

ADR-015(k): model may import geometry, never rules (SPEC §11.1), so run
re-derivation lives here. ADR-016(f): this is the SINGLE chain-walk
implementation — rules/filters.py delegates its promotion walk to
``chain_run`` (the filters/runs twins diverged once; never again).

ADR-016(f) eid rule: re-promotion of a registered composite KEEPS the
composite's own eid (never prefixes, never mints a second id — ADR-012(c)'s
intent; supersedes M1's promoted-promoted-* prefixing).
"""
from __future__ import annotations

import math

from geometry.entities import Entity, Pt, Seg
from geometry.tolerances import EPS_COINCIDE

_DOT_SAME = 0.999


def _member_ids(s: Seg) -> tuple[str, ...]:
    return s.members if s.members else (s.eid,)


def _unit(vx: float, vy: float) -> tuple[float, float] | None:
    n = math.hypot(vx, vy)
    if n <= 0.0:
        return None
    return vx / n, vy / n


def chain_run(
    primitives: list[Entity],
    clicked: Seg,
    eps_coincide: float = EPS_COINCIDE,
    pick_eid: str = "",
) -> tuple[Seg, tuple[str, ...]] | None:
    """Promotion walk from a clicked Seg: extend along collinear neighbors in
    BOTH directions to fixed point (endpoint gap <= eps_coincide; direction
    dot >= 0.999 same / <= -0.999 reversed). The extent is SYMMETRIC over both
    projections of every member (the round-2 divergence fix).

    Returns ``(promoted Seg, entity_eids)`` where ``entity_eids`` are the
    run's entity-level eids present in primitives (plain members and/or
    registered composites) in anchor order. The Seg's ``members`` are the
    flattened member eids (ADR-012(c)); its ``eid`` is
    ``promoted-<first entity eid>``, or the composite's OWN eid when the
    first entity is itself a composite (ADR-016(f) keep-seed-eid).
    """
    d = _unit(clicked.b.x - clicked.a.x, clicked.b.y - clicked.a.y)
    if d is None:  # degenerate seed: no direction, no run
        return (
            Seg(
                eid=f"promoted-{clicked.eid}",
                a=clicked.a,
                b=clicked.b,
                members=_member_ids(clicked),
                pick_eid=pick_eid,
            ),
            (clicked.eid,),
        )
    dx, dy = d
    ax, ay = clicked.a.x, clicked.a.y

    def proj(p: Pt) -> float:
        return (p.x - ax) * dx + (p.y - ay) * dy

    def lateral(p: Pt) -> float:
        return (p.x - ax) * dy - (p.y - ay) * dx

    pool = [e for e in primitives if isinstance(e, Seg)]
    members: dict[str, tuple[float, float, float, float]] = {
        clicked.eid: (proj(clicked.a), proj(clicked.b), lateral(clicked.a), lateral(clicked.b))
    }

    def _joinable(s: Seg, end_pt: Pt) -> bool:
        u = _unit(s.b.x - s.a.x, s.b.y - s.a.y)
        if u is None:
            return False
        dot = u[0] * dx + u[1] * dy
        if abs(dot) < _DOT_SAME:
            return False
        if not (
            math.hypot(s.a.x - end_pt.x, s.a.y - end_pt.y) <= eps_coincide
            or math.hypot(s.b.x - end_pt.x, s.b.y - end_pt.y) <= eps_coincide
        ):
            return False
        return abs(lateral(s.a)) <= eps_coincide and abs(lateral(s.b)) <= eps_coincide

    grew = True
    while grew:
        grew = False
        lo = min(min(v[0], v[1]) for v in members.values())
        hi = max(max(v[0], v[1]) for v in members.values())
        lo_pt = Pt(ax + lo * dx, ay + lo * dy)
        hi_pt = Pt(ax + hi * dx, ay + hi * dy)
        for s in pool:
            if s.eid in members:
                continue
            if _joinable(s, lo_pt) or _joinable(s, hi_pt):
                members[s.eid] = (proj(s.a), proj(s.b), lateral(s.a), lateral(s.b))
                grew = True

    by_eid = {s.eid: s for s in pool}

    lo = min(min(v[0], v[1]) for v in members.values())
    hi = max(max(v[0], v[1]) for v in members.values())

    # dominant-axis snap tolerance: scale-aware (mm world), EPS_CONSTRUCTION-
    # sized relative to the run length — exact axes snap exactly (0 offset),
    # real oblique runs are never snapped (see docstring).
    eps_snap = eps_coincide * 1e-6 * max(1.0, abs(hi - lo))

    # ADR-016(f) + M2.2 item 4: the CANONICAL direction governs the member
    # ORDER and the run EID. It is derived from the run's EXTENT vector
    # (world-ordered: hi_pt - lo_pt along the walk), snapped to the DOMINANT
    # axis — a near-vertical alternating-micro-drift run keeps ONE canonical
    # direction whichever member is clicked (the mathematician's two-ids
    # defect: the old rule keyed off the CLICKED seed's direction sign).
    # Exact-axis behavior is preserved: vertical runs canonicalize along
    # sign(dy) (up = top-first, down = bottom-first), horizontal along
    # sign(dx). Near-tie |dx| ~ |dy| within eps_snap -> +x.
    ex = hi * dx
    ey = hi * dy
    s: float
    if abs(ex) > abs(ey) + eps_snap:
        s = 1.0 if ex > 0.0 else -1.0
    elif abs(ey) > abs(ex) + eps_snap:
        s = 1.0 if ey > 0.0 else -1.0
    else:
        s = 1.0

    def cproj(v: tuple[float, float, float, float]) -> tuple[float, float]:
        # member projections re-expressed along the canonical direction:
        # flipping the direction negates AND swaps the span's min/max
        lo0, hi0 = min(v[0], v[1]), max(v[0], v[1])
        if s > 0.0:
            return lo0, hi0
        return -hi0, -lo0

    ordered: list[str] = sorted(members, key=lambda e: (cproj(members[e])[0], e))
    flat: list[str] = []
    for eid in ordered:
        for m in _member_ids(by_eid[eid]):
            if m not in flat:
                flat.append(m)

    first = by_eid[ordered[0]]
    run_eid = ordered[0] if first.members else f"promoted-{ordered[0]}"
    return (
        Seg(
            eid=run_eid,
            a=Pt(ax + lo * dx, ay + lo * dy),
            b=Pt(ax + hi * dx, ay + hi * dy),
            members=tuple(flat),
            pick_eid=pick_eid,
        ),
        tuple(ordered),
    )


def collinear_run_through(
    primitives: list[Entity], seed_eid: str, eps_coincide: float = EPS_COINCIDE
) -> Seg | None:
    """Promoted-style composite Seg of the collinear run containing the seed
    member (ADR-015(k) convenience wrapper; the model calls ``chain_run``
    directly when it also needs entity eids)."""
    seed = next(
        (e for e in primitives if isinstance(e, Seg) and e.eid == seed_eid), None
    )
    if seed is None:
        return None
    result = chain_run(primitives, seed, eps_coincide)
    if result is None:
        return None
    return result[0]
