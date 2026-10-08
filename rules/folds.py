"""Fold extend/trim engine — CONTRACTS §3 fold stage (headless; geometry only).

SPEC §11.6 deterministic rule. Idempotent by construction (ADR-004):
an endpoint already on a dogbone relief arc (dist == r within eps) is the
nearest valid candidate to itself, so a second resolve produces no Trim.

Trim semantics per ADR-024(c) / CONTRACTS §1: ``Trim.old`` / ``Trim.new``
= ``(Pt, Pt)`` endpoint pairs (Seg per ADR-015(d)). ONE Trim per fold eid
whose supporting line crosses any dogbone relief arc; BOTH endpoints
resolve independently.

Per-endpoint resolution (§11.6 "trim at first circle entry from the KEPT
side"; the kept side = the side of the endpoint being resolved):
  - candidates = line-circle intersections across all dogbones, restricted
    to points ON the dogbone's relief ARC span (the fold meets the relief
    arc, not the far side of the circle).
  - the KEPT portion for endpoint p is the portion on p's side of the cut
    = ``p -> cand`` (NOT ``cand -> other`` — that's the discarded side for
    a both-sides crossing). Reject candidates whose kept portion's OPEN
    interior hits the disk (§11.4 post-condition).
  - pick the nearest surviving candidate to p.
  - reach cap (EXTEND case only — endpoint strictly outside the circle):
    if the nearest candidate is beyond ``FOLD_REACH_FACTOR * WINDOW_FACTOR
    * 2 * r`` of the endpoint, leave unchanged (out-of-reach warning
    surfaced via ``out_of_reach_warnings``). TRIM (endpoint inside) has no
    reach cap.
"""
from __future__ import annotations

from geometry import geomops as go
from geometry.entities import Dogbone, Entity, Pt, Seg, Trim
from geometry.tolerances import EPS_COINCIDE
from rules.engine import WINDOW_FACTOR

# ADR-024(c): extend reach cap = 2 * WINDOW_FACTOR * 2 * r (= 16 * r).
FOLD_REACH_FACTOR: float = 2.0


def _seg_seg_dist(a: Pt, b: Pt, c: Pt, d: Pt, eps: float) -> float:
    """Minimum distance between segment a-b and segment c-d. Handles
    collinear overlap (distance 0) and crossing (distance 0) correctly;
    falls back to the min of the four endpoint-to-segment distances."""
    # crossing (non-parallel supporting lines, intersection within both)
    ip = go.line_intersection(a, b, c, d, eps)
    if ip is not None:
        ta = _proj(ip, a, go.unit(go.sub(b, a)) if (go.sub(b, a)[0] or go.sub(b, a)[1]) else (1.0, 0.0))
        # parameterize: is ip within [a,b] and within [c,d]?
        # simpler: point_seg_dist from ip to each segment == 0 means inside
        if (go.point_seg_dist(ip, a, b) <= eps and go.point_seg_dist(ip, c, d) <= eps):
            return 0.0
    # collinear overlap: parallel, same line, projections overlap
    if go.point_line_dist(c, a, b) <= eps and go.point_line_dist(d, a, b) <= eps:
        u = go.unit(go.sub(b, a)) if (go.sub(b, a)[0] or go.sub(b, a)[1]) else (1.0, 0.0)
        pa, pb = _proj(a, a, u), _proj(b, a, u)
        pc, pd = _proj(c, a, u), _proj(d, a, u)
        lo1, hi1 = min(pa, pb), max(pa, pb)
        lo2, hi2 = min(pc, pd), max(pc, pd)
        if lo2 <= hi1 + eps and lo1 <= hi2 + eps:
            return 0.0  # projections overlap on the same line
    return min(
        go.point_seg_dist(a, c, d),
        go.point_seg_dist(b, c, d),
        go.point_seg_dist(c, a, b),
        go.point_seg_dist(d, a, b),
    )


def validate_fold_against_contours(
    fold: Seg, primitives: list[Entity], eps: float = EPS_COINCIDE
) -> list[str]:
    """SPEC §11.3 case 5: distance from the fold SEGMENT to every contour
    LINE/ARC edge must exceed eps; one warning string per violating edge.
    Wording matches ``dxf_io/load._fold_contour_warnings`` so the two
    surfaces agree. Never auto-undesignates (SPEC §4.5)."""
    out: list[str] = []
    for e in primitives:
        if not isinstance(e, Seg) or e.eid == fold.eid:
            continue
        if _seg_seg_dist(fold.a, fold.b, e.a, e.b, eps) <= eps:
            out.append(
                f"fold {fold.eid} runs within {eps} mm of contour edge {e.eid}"
            )
    return out


def _proj(p: Pt, a: Pt, d: tuple[float, float]) -> float:
    return (p.x - a.x) * d[0] + (p.y - a.y) * d[1]


def _resolve_endpoint(
    p: Pt,
    q: Pt,
    fold_a: Pt,
    fold_dir: tuple[float, float],
    dogbones: list[Dogbone],
    eps: float,
) -> tuple[Pt | None, Dogbone | None, str | None]:
    """Return (new_pt | None, dogbone | None, warn | None) for one endpoint.

    new_pt is None when the endpoint is idempotent (already on a relief arc)
    or has no valid candidate. ``warn`` is set only for the out-of-reach
    extend case (the caller surfaces it).

    Kept portion for endpoint p = ``p -> cand`` (p's side of the cut). For a
    both-sides crossing this is the near side; the far endpoint resolves
    symmetrically to its own near entry."""
    proj_p = _proj(p, fold_a, fold_dir)
    proj_q = _proj(q, fold_a, fold_dir)
    best: tuple[float, Dogbone, Pt] | None = None
    for db in dogbones:
        xs = go.line_circle_intersections(fold_a, Pt(fold_a.x + fold_dir[0], fold_a.y + fold_dir[1]), db.center, db.r)
        if len(xs) < 2:
            continue
        p_in = go.dist(p, db.center) < db.r - eps  # strictly inside (not on-arc)
        for cand in xs:
            ang = go.pt_angle_deg(db.center, cand)
            if not go.span_contains(db.arc.start_deg, db.arc.end_deg, ang, eps):
                continue
            proj_cand = _proj(cand, fold_a, fold_dir)
            # No-flip guard: reject candidates on the FAR side of q (the other
            # endpoint). A fold entirely on one side of the circle must not
            # extend the FAR endpoint through the near endpoint to reach the
            # circle — that would reverse the fold's extent. Only the NEAR
            # endpoint (the one closer to the circle) may extend/trim.
            if proj_p <= proj_q and proj_cand > proj_q + eps:
                continue
            if proj_p >= proj_q and proj_cand < proj_q - eps:
                continue
            # KEPT portion: for an OUTSIDE endpoint, the kept side is p's side
            # of the cut = p -> cand. For an INSIDE endpoint, the kept side is
            # towards the other (outside) endpoint = cand -> q. The §11.4 post-
            # condition applies to the kept portion either way.
            if p_in:
                if go.seg_interior_hits_disk(cand, q, db.center, db.r, eps):
                    continue
            else:
                if go.seg_interior_hits_disk(p, cand, db.center, db.r, eps):
                    continue
            d = go.dist(p, cand)
            if best is None or d < best[0]:
                best = (d, db, cand)
    if best is None:
        return None, None, None
    d, db, cand = best
    if d <= eps:
        return None, None, None
    reach = FOLD_REACH_FACTOR * WINDOW_FACTOR * 2.0 * db.r
    if go.dist(p, db.center) > db.r + eps and d > reach + eps:
        return (
            None,
            None,
            f"fold endpoint out of reach (extend cap = {reach:.3f} mm); left unchanged",
        )
    return cand, db, None


def resolve_folds(
    primitives: list[Entity],
    dogbones: list[Dogbone],
    fold_eids: set[str],
    eps: float = EPS_COINCIDE,
) -> list[Trim]:
    """SPEC §11.6 deterministic fold extend/trim. One Trim per fold eid
    whose supporting line crosses any dogbone relief arc; both endpoints
    resolve independently. Idempotent: an endpoint already on a relief arc
    is the nearest valid candidate to itself -> no Trim on second call."""
    if not fold_eids or not dogbones:
        return []
    by_eid = {e.eid: e for e in primitives if isinstance(e, Seg)}
    out: list[Trim] = []
    for eid in sorted(fold_eids):
        fold = by_eid.get(eid)
        if fold is None:
            continue
        d = go.sub(fold.b, fold.a)
        n = go.unit(d) if (d[0] or d[1]) else None
        if n is None:
            continue
        new_a, _dba, _wa = _resolve_endpoint(fold.a, fold.b, fold.a, n, dogbones, eps)
        new_b, _dbb, _wb = _resolve_endpoint(fold.b, fold.a, fold.a, n, dogbones, eps)
        if new_a is None and new_b is None:
            continue
        out.append(
            Trim(
                eid=eid,
                old=(fold.a, fold.b),
                new=(new_a if new_a is not None else fold.a,
                     new_b if new_b is not None else fold.b),
            )
        )
    return out


def out_of_reach_warnings(
    primitives: list[Entity],
    dogbones: list[Dogbone],
    fold_eids: set[str],
    eps: float = EPS_COINCIDE,
) -> list[str]:
    """Per-fold out-of-reach warnings (the export stage surfaces these in
    ``ExportResult.warnings``; ``resolve_folds`` returns Trims only)."""
    if not fold_eids or not dogbones:
        return []
    by_eid = {e.eid: e for e in primitives if isinstance(e, Seg)}
    out: list[str] = []
    for eid in sorted(fold_eids):
        fold = by_eid.get(eid)
        if fold is None:
            continue
        d = go.sub(fold.b, fold.a)
        n = go.unit(d) if (d[0] or d[1]) else None
        if n is None:
            continue
        for p, q, label in (
            (fold.a, fold.b, f"fold {eid} endpoint a"),
            (fold.b, fold.a, f"fold {eid} endpoint b"),
        ):
            _new, _db, warn = _resolve_endpoint(p, q, fold.a, n, dogbones, eps)
            if warn is not None:
                out.append(f"{label}: {warn}")
    return out