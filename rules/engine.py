"""Corner pipeline — CONTRACTS §2 engine API (headless; geometry imports only).

Pipeline (CONTRACTS §2 order): apex gate -> overlap vs existing dogbones ->
circle construction -> deletion truth table (SPEC §11.5) -> edge rebuild
(ADR-003 ops; §11.4 uniqueness post-condition) -> attachment cascade
(ADR-012(b)) -> fold-vs-circle preview stub (fold extend/trim itself runs at
export, M5/M6).

Conventions per ADR-015: compute_apex returns half of the SMALLER supporting-
line angle; Side selects the bisector CONSTRUCTION (CONTRACTS §1: +1 =
unit(u1+u2) line, -1 = unit(u1-u2) line) and the kwarg side_flip selects the
ray within that line (+1 / -1; ADR-015(m) — a single sign bit cannot address
all four ghost rays, so ghost_candidates enumerates all four as
(Side, flip, center) and place_corner takes the picked pair); db_id default
"db-<edge1>+<edge2>"; placed-arc eid placeholder "arc-pending-<db_id>";
refusal strings pinned per ADR-015(i).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from geometry import geomops as go
from geometry.adjacency import attachment_points, build_adjacency
from geometry.entities import (
    Arc,
    Circ,
    CornerResult,
    Dogbone,
    Entity,
    Flag,
    PassThrough,
    PointEnt,
    Pt,
    Refusal,
    Rebuild,
    Seg,
    Side,
    TextEnt,
    Trim,
)
from geometry.tolerances import EPS_COINCIDE, EPS_CONSTRUCTION
from geometry.runs import chain_run

K_OVERSHOOT = 5.0  # SPEC §11.4: apex within K*R of each edge segment
HALF_ANGLE_MIN_DEG = 15.0  # SPEC §11.4 band (constants, tunable)
HALF_ANGLE_MAX_DEG = 165.0
WINDOW_FACTOR = 4.0  # SPEC §11.5: 4x tool DIAMETER window (prefilter only)


def _refused(*reasons: str) -> CornerResult:
    return CornerResult(
        ok=False,
        dogbone=None,
        deletions=[],
        trims=[],
        rebuilt=[],
        refusals=list(reasons),
        flags=[],
    )


def _dir(seg: Seg) -> tuple[float, float]:
    return go.unit(go.sub(seg.b, seg.a))


# ---------------------------------------------------------------------------
# CONTRACTS §2 API
# ---------------------------------------------------------------------------


def compute_apex(
    seg1: Seg, seg2: Seg, eps_construction: float = EPS_CONSTRUCTION
) -> tuple[Pt, float] | Refusal:
    """Apex = supporting-line intersection; returns (apex, half_angle_deg).

    ADR-015(g): the returned half-angle is half of the SMALLER angle between
    the two supporting lines (side not yet known). Band [15, 165] on it
    refuses near-collinear pairs at BOTH ends.
    """
    apex = go.line_intersection(seg1.a, seg1.b, seg2.a, seg2.b, eps_construction)
    if apex is None:
        return Refusal(
            "PARALLEL: edges are parallel or collinear (no supporting-line intersection)"
        )
    theta = go.angle_between_unit_dirs(_dir(seg1), _dir(seg2))
    half = min(theta, 180.0 - theta) / 2.0
    if half < HALF_ANGLE_MIN_DEG - 1e-9 or half > HALF_ANGLE_MAX_DEG + 1e-9:
        return Refusal(
            f"SHALLOW: corner half-angle {half:.3f} deg outside "
            f"[{HALF_ANGLE_MIN_DEG:.3f}, {HALF_ANGLE_MAX_DEG:.3f}] (near-collinear edges)"
        )
    return apex, half


def apex_proximity_ok(apex: Pt, seg1: Seg, seg2: Seg, k: float, r: float) -> bool:
    """Point-to-SEGMENT gate (SPEC §11.4 v3): interior apex passes at 0
    (T-cap); overshoot past an end allowed if <= k*r."""
    limit = k * r
    return (
        go.point_seg_dist(apex, seg1.a, seg1.b) <= limit
        and go.point_seg_dist(apex, seg2.a, seg2.b) <= limit
    )


def resolve_edge(
    primitives: list[Entity], eid: str, eps_coincide: float = EPS_COINCIDE
) -> tuple[Seg, Seg] | None:
    """Resolve an edge eid (plain member or promoted-* composite, possibly
    nested per ADR-012(c)) to (promoted run Seg, seed Seg). The seed is the
    deepest eid present in primitives (a member pre-apply, a registered
    composite post-apply). M2.2 item 3 (mathematician's X-crossing defect):
    the run is re-derived by walking chain_run FROM THE SEED — never by a
    proximity pick at the seed's midpoint (a first-wins pick could latch a
    non-collinear entity crossing that midpoint and falsely refuse
    UNKNOWN_EDGE)."""
    seed_eid = eid
    seed = None
    stripped = False  # M2.2 item 7: unroll AT MOST ONE prefix level
    while True:
        seed = next(
            (e for e in primitives if isinstance(e, Seg) and e.eid == seed_eid), None
        )
        if seed is not None:
            break
        if not stripped and seed_eid.startswith("promoted-"):
            seed_eid = seed_eid[len("promoted-"):]
            stripped = True
        else:
            break
    if seed is None:
        # M2.2 item 7 (developer's probe): a double-prefixed label is
        # corrupt data (ADR-016(f) abolished nested prefixing) — fail loud
        # instead of silently resolving through it.
        if stripped and eid.startswith("promoted-promoted-"):
            raise ValueError(
                f"corrupt edge eid {eid!r}: nested promoted-promoted-* labels "
                f"are not mintable (ADR-016(f))"
            )
        return None
    result = chain_run(primitives, seed, eps_coincide)
    if result is None:
        return None
    run = result[0]
    members = run.members if run.members else (run.eid,)
    seed_member = seed.members[0] if seed.members else seed.eid
    if seed_member not in members and seed.eid not in members:
        return None
    return run, seed


def ghost_candidates(
    primitives: list[Entity],
    edge1_eid: str,
    edge2_eid: str,
    r: float,
    eps_construction: float = EPS_CONSTRUCTION,
    eps_coincide: float = EPS_COINCIDE,
) -> list[tuple[Side, int, Pt]] | Refusal:
    """The four ghost dogbone centers for a picked edge pair (SPEC §4.2 "two
    ghost previews, one per valid side" — ADR-015(m): the two bisector
    constructions x the two rays of each). Returns (Side, side_flip, center)
    tags; the UI forwards the picked (Side, flip) to place_corner. Refusal
    propagates the apex/band gate (compute_apex) — no ghosts for refused
    pairs."""
    r1 = resolve_edge(primitives, edge1_eid, eps_coincide)
    r2 = resolve_edge(primitives, edge2_eid, eps_coincide)
    if r1 is None or r2 is None:
        missing = edge1_eid if r1 is None else edge2_eid
        return Refusal(f"UNKNOWN_EDGE: {missing} is not resolvable in primitives")
    run1, _seed1 = r1
    run2, _seed2 = r2
    ap = compute_apex(run1, run2, eps_construction)
    if isinstance(ap, Refusal):
        return ap
    apex, _half = ap
    u1, u2 = _dir(run1), _dir(run2)
    out: list[tuple[Side, int, Pt]] = []
    for sign in (+1, -1):
        b = go.bisector_unit(u1, u2, sign)
        if b is None:
            continue
        for flip in (+1, -1):
            out.append(
                (
                    Side(sign),
                    flip,
                    Pt(apex.x + r * flip * b[0], apex.y + r * flip * b[1]),
                )
            )
    if len(out) != 4:
        return Refusal(
            "PARALLEL: edges are parallel or collinear (no supporting-line intersection)"
        )
    return out


def arc_crosses_circle(arc: Arc, c: Pt, r: float, eps: float) -> bool:
    """True if the arc STRICTLY crosses circle(c, r) at two points within its
    span (SPEC §11.5 protected-ARC row; a single tangent touch does not count)."""
    pts = go.two_circle_intersections(arc.center, arc.r, c, r, eps)
    if len(pts) < 2:
        return False
    return all(
        go.span_contains(arc.start_deg, arc.end_deg, go.pt_angle_deg(arc.center, p), eps)
        for p in pts
    )


def fold_circle_intersections(
    primitives: list[Entity],
    fold_eids: set[str],
    center: Pt,
    r: float,
) -> dict[str, list[Pt]]:
    """§2 fold stub: fold-vs-circle intersection points for preview only
    (fold extend/trim executes at export; M5 owns that)."""
    out: dict[str, list[Pt]] = {}
    for eid in sorted(fold_eids):
        ent = next((e for e in primitives if e.eid == eid and isinstance(e, Seg)), None)
        if ent is None:
            continue
        xs = go.line_circle_intersections(ent.a, ent.b, center, r)
        if xs:
            out[eid] = xs
    return out


# ---------------------------------------------------------------------------
# place_corner internals
# ---------------------------------------------------------------------------


def _half_side(b: tuple[float, float], u: tuple[float, float]) -> float:
    theta = go.angle_between_unit_dirs(b, u)
    return min(theta, 180.0 - theta)


def _rebuild_edge(
    label: str,
    run: Seg,
    seed: Seg,
    primitives: list[Entity],
    apex: Pt,
    center: Pt,
    r: float,
    eps_construction: float,
    eps_coincide: float,
) -> Rebuild | Refusal:
    """ADR-003/§11.4 rebuild: the moved endpoint goes to the UNIQUE non-apex
    intersection of the run's supporting line with the dogbone circle. Both
    endpoint alternatives are computed (§11.4 post-condition): exactly one
    passing -> that one (WE case); both passing -> the endpoint nearer the
    apex (ADR-003 "dogbone side"; extension-type rebuilds, ADR-015(l));
    none -> SPAN refusal."""
    xs = go.line_circle_intersections(run.a, run.b, center, r)
    if len(xs) < 2:
        return Refusal(
            f"TANGENT: supporting line of edge {label} is tangent to the dogbone circle"
        )
    p = max(xs, key=lambda q: go.dist(q, apex))  # the non-apex intersection
    keep_a = not go.seg_interior_hits_disk(p, run.b, center, r, eps_coincide)
    keep_b = not go.seg_interior_hits_disk(run.a, p, center, r, eps_coincide)
    if keep_a and keep_b:
        old = run.a if go.dist(run.a, apex) <= go.dist(run.b, apex) else run.b
    elif keep_a:
        old = run.a
    elif keep_b:
        old = run.b
    else:
        return Refusal(
            f"SPAN: edge {label} no longer spans the rebuilt intersection "
            f"(kept interior cannot clear the dogbone circle)"
        )
    owner = _owning_member(primitives, run, seed, old, eps_coincide)
    return Rebuild(eid=owner, old=old, new=p)


def _owning_member(
    primitives: list[Entity], run: Seg, seed: Seg, old: Pt, eps_coincide: float
) -> str:
    """The member (or composite, ADR-012(c)) eid owning the moved extent
    endpoint: the seed first (the clicked/registered entity), then the run's
    flattened members."""
    if go.dist(seed.a, old) <= eps_coincide or go.dist(seed.b, old) <= eps_coincide:
        return seed.eid
    by_eid = {e.eid: e for e in primitives if isinstance(e, Seg)}
    for m in (run.members or (run.eid,)):
        ent = by_eid.get(m)
        if ent is not None:
            if go.dist(ent.a, old) <= eps_coincide or go.dist(ent.b, old) <= eps_coincide:
                return m
    return run.eid


def _shared_point(
    e: Entity, other: Entity, eps_coincide: float
) -> Pt | None:
    """Euclidean pairing metric (M2.2 brief item 2 — same metric as
    geometry/adjacency.build_adjacency, never box-proximity)."""
    for pa in attachment_points(e):
        for pb in attachment_points(other):
            if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) <= eps_coincide:
                return Pt(pa[0], pa[1])
    return None


def _cascade(
    primitives: list[Entity],
    deletions: list[str],
    flags: list[Flag],
    warnings: list[str],
    removed_portions: list[tuple[Pt, Pt]],
    protected: set[str],
    flag_decisions: dict[str, str],
    eps_coincide: float,
    flagged: set[str],
) -> None:
    """ADR-012(b) attachment cascade: truth-table/decision deletions first,
    then transitive fixed-point. A candidate dangles iff it has an
    attachment endpoint in a removed portion AND no remaining attached
    neighbor (contacts at vertices inside removed portions do not count).
    ADR-016(d): eids already flagged by the truth table are SKIPPED (flagged
    classes flow through the flagged flow, never cascade-deleted; one flag
    per eid per result). Default (absent decision) = delete + flag;
    "keep" survives; an INVALID decision is ignored -> pending, never
    auto-deleted (ADR-016(c)), with a warning."""
    adjacency = build_adjacency(primitives, eps_coincide)
    by_eid = {e.eid: e for e in primitives}
    deleted = set(deletions)
    cascade_flagged: set[str] = set()
    options = frozenset({"delete", "keep"})
    changed = True
    while changed:
        changed = False
        for e in primitives:
            if (
                e.eid in deleted
                or e.eid in protected
                or isinstance(e, PassThrough)
                or e.eid in flagged
                or e.eid in cascade_flagged
            ):
                continue
            aps = attachment_points(e)
            attached_in_portion = any(
                go.point_seg_dist(Pt(*p), old, new) <= eps_coincide
                for p in aps
                for (old, new) in removed_portions
            )
            if not attached_in_portion:
                continue
            remaining = False
            for n_eid in adjacency.get(e.eid, ()):
                if n_eid == e.eid or n_eid in deleted:
                    continue
                n_ent = by_eid.get(n_eid)
                if n_ent is None:
                    continue
                shared = _shared_point(e, n_ent, eps_coincide)
                if shared is None:
                    continue
                if any(
                    go.point_seg_dist(shared, old, new) <= eps_coincide
                    for (old, new) in removed_portions
                ):
                    continue  # contact at a removed-portion vertex does not count
                remaining = True
                break
            if not remaining:
                raw = flag_decisions.get(e.eid)
                invalid = raw is not None and raw not in options
                # dangles: flag always (ADR-012(b)); delete only on absent or
                # "delete" — an INVALID decision is pending, never destructive
                # (ADR-016(c)); "keep" survives
                flags.append(
                    Flag(e.eid, "CASCADE_DANGLING", options, None if invalid else raw)
                )
                cascade_flagged.add(e.eid)
                if invalid:
                    warnings.append(
                        f"FLAG_DECISION: ignoring invalid decision '{raw}' for {e.eid} "
                        f"(allowed: {'|'.join(sorted(options))})"
                    )
                elif raw is None or raw == "delete":
                    deleted.add(e.eid)
                    deletions.append(e.eid)
                changed = True


def _arc_chord_trim(
    arc: Arc, apex: Pt, center: Pt, r: float, eps: float
) -> Trim | None:
    """ADR-013/§11.5 ARC chord-crosser trim to the kept-side sub-arc (single
    piece). Kept side = the complement piece whose midpoint is farther from
    the apex; ties -> longer piece; still tied -> first in CCW order.
    Not executable (whole arc inside / weaving) -> None; flag retained."""
    intervals = go.arc_disk_inside_interval(arc, center, r, eps)
    if len(intervals) != 1:
        return None
    a0, a1 = intervals[0]
    S, E = arc.start_deg, arc.end_deg
    eps_deg = 1e-6
    pieces: list[tuple[float, float]] = []
    if go.span_len(S, a0) > eps_deg:
        pieces.append((S, a0))
    if go.span_len(a1, E) > eps_deg:
        pieces.append((a1, E))
    if not pieces:
        return None
    if len(pieces) == 2:

        def piece_key(pc: tuple[float, float]) -> tuple[float, float, float]:
            mid = (pc[0] + go.span_len(pc[0], pc[1]) / 2.0) % 360.0
            mpt = Pt(
                arc.center.x + arc.r * math.cos(math.radians(mid)),
                arc.center.y + arc.r * math.sin(math.radians(mid)),
            )
            return (go.dist(mpt, apex), go.span_len(pc[0], pc[1]), 1.0)

        pieces.sort(key=piece_key, reverse=True)
    ks, ke = pieces[0]
    return Trim(eid=arc.eid, old=(arc.start_deg, arc.end_deg), new=(ks, ke))


def _entity_window_dist(e: Entity, apex: Pt) -> float:
    if isinstance(e, Seg):
        return go.point_seg_dist(apex, e.a, e.b)
    if isinstance(e, Arc):
        return go.arc_min_center_dist(e, apex)
    if isinstance(e, Circ):
        return abs(go.dist(e.center, apex) - e.r)
    if isinstance(e, PointEnt):
        return go.dist(e.p, apex)
    if isinstance(e, TextEnt):
        return go.dist(e.p, apex)
    return float("inf")


# ---------------------------------------------------------------------------
# place_corner (M2.2 item 5: decomposed into _validate_inputs -> _truth_table
# -> _rebuild_and_arc over an internal _Ctx; public API, evaluation order and
# all refusal/warning strings byte-identical)
# ---------------------------------------------------------------------------


@dataclass
class _Ctx:
    """Internal place_corner stage context (NOT part of the CONTRACTS §2
    API): the bound inputs plus the derived state each stage fills in."""

    primitives: list[Entity]
    edge1_eid: str
    edge2_eid: str
    side: Side
    r: float
    fold_eids: set[str]
    dogbones: list[Dogbone]
    eps_construction: float
    eps_coincide: float
    flag_decisions: dict[str, str]
    db_id: str | None
    side_flip: int
    # filled by _validate_inputs:
    run1: Seg | None = None
    seed1: Seg | None = None
    run2: Seg | None = None
    seed2: Seg | None = None
    apex: Pt | None = None
    center: Pt | None = None
    half_side: float = 0.0
    # filled by _truth_table:
    protected: set[str] = field(default_factory=set)
    deletions: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    trims: list[Trim] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    flagged: set[str] = field(default_factory=set)


def _validate_inputs(ctx: _Ctx) -> Refusal | None:
    """Stage 1: radius validation, edge resolution, apex gate, bisector,
    overlap, half-angle band — every refusal that fires before any
    truth-table row is evaluated. Fills ctx; None = proceed."""
    # ADR-016(e): radius validation FIRST (replaces accidental
    # wrong-diagnosis TANGENT/APEX_GATE/SPAN refusals for degenerate radii)
    if ctx.r < ctx.eps_coincide:
        return Refusal(
            f"RADIUS: tool radius must exceed EPS_COINCIDE (got {ctx.r:.6f})"
        )
    if ctx.edge1_eid == ctx.edge2_eid:
        return Refusal("SAME_EDGE: both picks reference the same edge")

    r1 = resolve_edge(ctx.primitives, ctx.edge1_eid, ctx.eps_coincide)
    r2 = resolve_edge(ctx.primitives, ctx.edge2_eid, ctx.eps_coincide)
    if r1 is None or r2 is None:
        missing = ctx.edge1_eid if r1 is None else ctx.edge2_eid
        return Refusal(f"UNKNOWN_EDGE: {missing} is not resolvable in primitives")
    ctx.run1, ctx.seed1 = r1
    ctx.run2, ctx.seed2 = r2

    ap = compute_apex(ctx.run1, ctx.run2, ctx.eps_construction)
    if isinstance(ap, Refusal):
        return ap
    ctx.apex = ap[0]

    d1 = go.point_seg_dist(ctx.apex, ctx.run1.a, ctx.run1.b)
    d2 = go.point_seg_dist(ctx.apex, ctx.run2.a, ctx.run2.b)
    limit = K_OVERSHOOT * ctx.r
    if d1 > limit or d2 > limit:
        return Refusal(
            f"APEX_GATE: apex lies {d1:.4f} from edge {ctx.edge1_eid} and {d2:.4f} from "
            f"edge {ctx.edge2_eid}; limit K*R = {limit:.4f}"
        )

    u1, u2 = _dir(ctx.run1), _dir(ctx.run2)
    b = go.bisector_unit(u1, u2, ctx.side.sign)
    if b is None:
        return Refusal(
            "PARALLEL: edges are parallel or collinear (no supporting-line intersection)"
        )
    b = (ctx.side_flip * b[0], ctx.side_flip * b[1])
    ctx.center = Pt(ctx.apex.x + ctx.r * b[0], ctx.apex.y + ctx.r * b[1])

    for db in ctx.dogbones:
        if go.dist(ctx.center, db.center) < ctx.r + db.r - ctx.eps_coincide:
            return Refusal(
                f"OVERLAP: dogbone circle overlaps existing dogbone {db.db_id} "
                f"(strict with EPS_COINCIDE; tangent circles are allowed)"
            )

    ctx.half_side = _half_side(b, u1)
    half_side2 = _half_side(b, u2)
    if abs(ctx.half_side - half_side2) > 1e-6:
        raise ValueError(
            f"bisector asymmetry: {ctx.half_side:.9f} vs {half_side2:.9f} (internal invariant)"
        )
    if not (HALF_ANGLE_MIN_DEG - 1e-9 <= ctx.half_side <= HALF_ANGLE_MAX_DEG + 1e-9):
        return Refusal(
            f"SHALLOW: corner half-angle {ctx.half_side:.3f} deg outside "
            f"[{HALF_ANGLE_MIN_DEG:.3f}, {HALF_ANGLE_MAX_DEG:.3f}] (near-collinear edges)"
        )
    return None


def _truth_table(ctx: _Ctx) -> Refusal | None:
    """Stage 2: protected set + SPEC §11.5 deletion truth table (rows ->
    deletions/flags/trims/warnings + the flagged set). None = proceed."""
    # protected set (SPEC §11.5: global, monotone — all main edges
    # (applied + pending) + designated folds + placed dogbone arcs).
    # ADR-016(g): applied dogbones' edge eids are resolved AT USE via
    # resolve_edge against current primitives (Dogbone stays immutable).
    protected = ctx.protected
    protected.update(ctx.fold_eids)
    for db in ctx.dogbones:
        protected.add(db.arc.eid)
        for db_edge in (db.edge1_eid, db.edge2_eid):
            protected.add(db_edge)
            rr = resolve_edge(ctx.primitives, db_edge, ctx.eps_coincide)
            if rr is not None:
                db_run, db_seed = rr
                protected.update(db_run.members if db_run.members else (db_run.eid,))
                protected.add(db_run.eid)
                protected.add(db_seed.eid)
    # M2.2 item 5: explicit (run, eid, seed) triples replace the fragile
    # `seed1.eid if run is run1 else seed2.eid` identity comparison
    for run, eid, seed in (
        (ctx.run1, ctx.edge1_eid, ctx.seed1),
        (ctx.run2, ctx.edge2_eid, ctx.seed2),
    ):
        protected.add(eid)
        protected.update(run.members if run.members else (run.eid,))
        protected.add(seed.eid)

    # window = 4x tool DIAMETER disk around the apex; prefilter only
    window = WINDOW_FACTOR * 2.0 * ctx.r
    deletions = ctx.deletions
    flags = ctx.flags
    trims = ctx.trims
    warnings = ctx.warnings
    flagged = ctx.flagged  # ADR-016(d): one flag per eid per result

    _OPTS_DELETE_KEEP = frozenset({"delete", "keep"})

    def _validated(eid: str, options: frozenset) -> tuple[str | None, bool]:
        """ADR-016(c): per-case validation of flag_decisions.
        Returns (decision, invalid): an invalid value is IGNORED (falls back
        to pending, never destructive) and a warning is recorded."""
        raw = ctx.flag_decisions.get(eid)
        if raw is None or raw in options:
            return raw, False
        warnings.append(
            f"FLAG_DECISION: ignoring invalid decision '{raw}' for {eid} "
            f"(allowed: {'|'.join(sorted(options))})"
        )
        return None, True

    def _kept_crosser(eid: str) -> None:
        warnings.append(f"KEPT_CROSSER: kept entity {eid} will cross the relief cut")

    for db in ctx.dogbones:  # protected-ARC row (defensive: overlap fires first)
        if arc_crosses_circle(db.arc, ctx.center, ctx.r, ctx.eps_coincide):
            return Refusal(
                f"PROTECTED_ARC: placed arc {db.arc.eid} crosses the dogbone circle"
            )

    for e in ctx.primitives:
        if (
            isinstance(e, PassThrough)
            or e.eid in protected
            or _entity_window_dist(e, ctx.apex) > window
        ):
            continue
        if isinstance(e, Seg):
            if go.in_disk(e.a, ctx.center, ctx.r, ctx.eps_coincide) or go.in_disk(
                e.b, ctx.center, ctx.r, ctx.eps_coincide
            ):
                deletions.append(e.eid)
            elif go.seg_min_center_dist(e.a, e.b, ctx.center) < ctx.r - ctx.eps_coincide:
                decision, _invalid = _validated(e.eid, _OPTS_DELETE_KEEP)
                flags.append(Flag(e.eid, "CHORD_CROSSER", _OPTS_DELETE_KEEP, decision))
                flagged.add(e.eid)
                if decision == "delete":
                    deletions.append(e.eid)
                elif decision == "keep":
                    _kept_crosser(e.eid)
        elif isinstance(e, Arc):
            p0, p1 = go.arc_endpoints(e)
            if go.in_disk(p0, ctx.center, ctx.r, ctx.eps_coincide) or go.in_disk(
                p1, ctx.center, ctx.r, ctx.eps_coincide
            ):
                decision, invalid = _validated(e.eid, _OPTS_DELETE_KEEP)
                flags.append(Flag(e.eid, "ARC_ENDPOINT_IN", _OPTS_DELETE_KEEP, decision))
                flagged.add(e.eid)
                # table default (absent) deletes; an INVALID value never
                # auto-deletes (ADR-016(c))
                if decision == "delete" or (decision is None and not invalid):
                    deletions.append(e.eid)
                elif decision == "keep":
                    if go.arc_min_center_dist(e, ctx.center) < ctx.r - ctx.eps_coincide:
                        _kept_crosser(e.eid)
            elif go.arc_min_center_dist(e, ctx.center) < ctx.r - ctx.eps_coincide:
                decision, _invalid = _validated(
                    e.eid, frozenset({"delete", "keep", "trim"})
                )
                flags.append(
                    Flag(e.eid, "CHORD_CROSSER", frozenset({"delete", "keep", "trim"}), decision)
                )
                flagged.add(e.eid)
                if decision == "delete":
                    deletions.append(e.eid)
                elif decision == "keep":
                    if go.arc_min_center_dist(e, ctx.center) < ctx.r - ctx.eps_coincide:
                        _kept_crosser(e.eid)
                elif decision == "trim":
                    t = _arc_chord_trim(e, ctx.apex, ctx.center, ctx.r, ctx.eps_coincide)
                    if t is not None:
                        trims.append(t)
        elif isinstance(e, Circ):
            decision, _invalid = _validated(e.eid, _OPTS_DELETE_KEEP)
            flags.append(Flag(e.eid, "CIRCLE_IN_WINDOW", _OPTS_DELETE_KEEP, decision))
            flagged.add(e.eid)
            if decision == "delete":
                deletions.append(e.eid)
            elif (
                decision == "keep"
                and go.dist(ctx.center, e.center) < ctx.r + e.r - ctx.eps_coincide
            ):
                warnings.append(
                    f"KEPT_INTERSECTS: kept CIRCLE {e.eid} intersects the dogbone circle"
                )
        elif isinstance(e, PointEnt):
            if go.in_disk(e.p, ctx.center, ctx.r, ctx.eps_coincide):
                deletions.append(e.eid)
        elif isinstance(e, TextEnt):
            decision, _invalid = _validated(e.eid, _OPTS_DELETE_KEEP)
            flags.append(Flag(e.eid, "MTEXT_IN_WINDOW", _OPTS_DELETE_KEEP, decision))
            flagged.add(e.eid)
            if decision == "delete":
                deletions.append(e.eid)
    return None


def _rebuild_and_arc(ctx: _Ctx) -> CornerResult:
    """Stage 3: edge rebuild (§11.4 uniqueness post-condition), attachment
    cascade (ADR-012(b)), relief-arc span identity, dogbone assembly."""
    # -- edge rebuild (ADR-003 ops; §11.4 uniqueness post-condition) --
    rebuilt: list[Rebuild] = []
    removed_portions: list[tuple[Pt, Pt]] = []
    for label, run, seed in (
        (ctx.edge1_eid, ctx.run1, ctx.seed1),
        (ctx.edge2_eid, ctx.run2, ctx.seed2),
    ):
        rb = _rebuild_edge(
            label, run, seed, ctx.primitives, ctx.apex, ctx.center, ctx.r,
            ctx.eps_construction, ctx.eps_coincide,
        )
        if isinstance(rb, Refusal):
            return _refused(rb.reason)
        rebuilt.append(rb)
        removed_portions.append((rb.old, rb.new))

    # -- attachment cascade (ADR-012(b); ADR-016(c)/(d)) --
    _cascade(
        ctx.primitives, ctx.deletions, ctx.flags, ctx.warnings, removed_portions,
        ctx.protected, ctx.flag_decisions, ctx.eps_coincide, ctx.flagged,
    )

    # -- relief arc (endpoints == rebuilt endpoints; apex strictly mid-arc) --
    p1, p2 = rebuilt[0].new, rebuilt[1].new  # rebuild order == (edge1, edge2)
    a1 = go.pt_angle_deg(ctx.center, p1)
    a2 = go.pt_angle_deg(ctx.center, p2)
    aa = go.pt_angle_deg(ctx.center, ctx.apex)
    if go.span_contains(a2, a1, aa, 1e-9):
        start_deg, end_deg = a2, a1
    elif go.span_contains(a1, a2, aa, 1e-9):
        start_deg, end_deg = a1, a2
    else:
        return _refused("TANGENT: apex not interior to the relief arc (degenerate construction)")
    for bound in (start_deg, end_deg):
        if abs(((aa - bound + 180.0) % 360.0) - 180.0) <= 1e-9:
            return _refused(
                "TANGENT: apex not interior to the relief arc (degenerate construction)"
            )
    span = go.span_len(start_deg, end_deg)
    if abs(span - (360.0 - 4.0 * ctx.half_side)) > 1e-6:
        raise ValueError(
            f"arc span identity violated: {span:.9f} vs {360.0 - 4.0 * ctx.half_side:.9f}"
        )

    db_id = ctx.db_id or f"db-{ctx.edge1_eid}+{ctx.edge2_eid}"
    arc = Arc(
        eid=f"arc-pending-{db_id}",
        center=ctx.center,
        r=ctx.r,
        start_deg=start_deg,
        end_deg=end_deg,
    )
    dogbone = Dogbone(
        db_id=db_id,
        apex=ctx.apex,
        center=ctx.center,
        r=ctx.r,
        side=ctx.side,
        edge1_eid=ctx.edge1_eid,
        edge2_eid=ctx.edge2_eid,
        arc=arc,
    )
    return CornerResult(
        ok=True,
        dogbone=dogbone,
        deletions=ctx.deletions,
        trims=ctx.trims,
        rebuilt=rebuilt,
        refusals=[],
        flags=ctx.flags,
        warnings=ctx.warnings,
    )


def place_corner(
    primitives: list[Entity],
    edge1_eid: str,
    edge2_eid: str,
    side: Side,
    r: float,
    fold_eids: set[str],
    dogbones: list[Dogbone],
    *,
    eps_construction: float = EPS_CONSTRUCTION,
    eps_coincide: float = EPS_COINCIDE,
    flag_decisions: dict[str, str] | None = None,
    db_id: str | None = None,
    side_flip: int = +1,
) -> CornerResult:
    """Full rule pipeline (CONTRACTS §2 order). M2.2 item 5: decomposed
    into _validate_inputs -> _truth_table -> _rebuild_and_arc over an
    internal _Ctx — public behavior and every refusal/warning string
    byte-identical; signature unchanged."""
    ctx = _Ctx(
        primitives=primitives,
        edge1_eid=edge1_eid,
        edge2_eid=edge2_eid,
        side=side,
        r=r,
        fold_eids=fold_eids,
        dogbones=dogbones,
        eps_construction=eps_construction,
        eps_coincide=eps_coincide,
        flag_decisions=dict(flag_decisions) if flag_decisions else {},
        db_id=db_id,
        side_flip=side_flip,
    )
    ref = _validate_inputs(ctx)
    if ref is not None:
        return _refused(ref.reason)
    ref = _truth_table(ctx)
    if ref is not None:
        return _refused(ref.reason)
    return _rebuild_and_arc(ctx)
