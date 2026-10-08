"""Manual trim-to-closest — CONTRACTS §2 ``trim_to_closest`` (ADR-025).

Headless pure engine (ADR-006): imports geometry ONLY — never tkinter,
never ezdxf. The UI picks the line (promoted_edge_at), converts screen to
world, and calls in; the engine resolves the run, finds the moving
endpoint's closest supporting-geometry intersection, and proposes one
Trim (extend-when-short, trim-when-past) — or, for a run with zero
EXTERNAL attachments, deletion of the whole run (the stray rule: "if
the line is connected to nothing the whole thing should be deleted").

Pinned refusal strings (ADR-025(a); toast carries them verbatim):
  "UNKNOWN_EDGE: <eid> is not resolvable in primitives"
  "NO_TARGET: no supporting-geometry intersection found"

Semantics locked by the user's spec answers (2026-10-07):
  * moving endpoint = run-extent endpoint nearest the click;
  * closest = min world distance from the moving endpoint's PRE-move
    position over candidate target intersections; supporting geometry
    counts (LINE supporting line, ARC/CIRCLE supporting circle, POINT
    location) — the target need not reach;
  * whole promoted run is the subject; run's own members are never
    candidates; folds fully allowed both ways;
  * no attachment cascade (manual fix = explicit; neighbors untouched).
"""
from __future__ import annotations

import math

from geometry import geomops as go
from geometry.adjacency import attachment_points, build_adjacency
from geometry.entities import (
    Arc,
    Circ,
    EditResult,
    Entity,
    PointEnt,
    Pt,
    Seg,
    Trim,
)
from geometry.runs import chain_run
from geometry.tolerances import EPS_COINCIDE, EPS_CONSTRUCTION

REFUSAL_UNKNOWN = "UNKNOWN_EDGE: {eid} is not resolvable in primitives"
REFUSAL_NO_TARGET = "NO_TARGET: no supporting-geometry intersection found"


def _refused(reason: str) -> EditResult:
    return EditResult(ok=False, reason=reason, deletions=[], trims=[])


def _member_ids(s: Seg) -> set[str]:
    return set(s.members) if s.members else {s.eid}


def _resolve_run(
    primitives: list[Entity], eid: str, eps_coincide: float
) -> tuple[Seg, tuple[str, ...]] | None:
    """Resolve eid (plain member or promoted-* composite) to the promoted
    run + entity-level eids, the resolve_edge way (ADR-016(f) single walk;
    at most one prefix unroll)."""
    seed_eid = eid
    seed = None
    stripped = False
    while True:
        seed = next(
            (e for e in primitives if isinstance(e, Seg) and e.eid == seed_eid),
            None,
        )
        if seed is not None:
            break
        if not stripped and seed_eid.startswith("promoted-"):
            seed_eid = seed_eid[len("promoted-"):]
            stripped = True
        else:
            break
    if seed is None:
        return None
    chained = chain_run(primitives, seed, eps_coincide)
    if chained is None:
        return None
    run, ent_eids = chained
    members = run.members if run.members else (run.eid,)
    seed_member = seed.members[0] if seed.members else seed.eid
    if seed_member not in members and seed.eid not in members:
        return None
    return run, ent_eids


def _external_attachments(
    primitives: list[Entity],
    run: Seg,
    ent_eids: tuple[str, ...],
    eps_coincide: float,
) -> set[str]:
    """eids NOT part of the run that share an attachment point with any
    run endpoint (build_adjacency minus the run's own entities)."""
    adj = build_adjacency(primitives, eps_coincide)
    own = set(ent_eids) | _member_ids(run)
    own.add(run.eid)
    attached: set[str] = set()
    for eid in (*ent_eids, run.eid):
        attached |= adj.get(eid, frozenset())
    return attached - own


def _closest_on_line(run: Seg, target: Seg) -> Pt | None:
    """Deprecated helper kept out of the pipeline (unused); see the inline
    candidate loop. Left as documentation of the perpendicular-foot rule."""
    raise NotImplementedError


def trim_to_closest(
    primitives: list[Entity],
    p_world: Pt,
    eid: str,
    eps_construction: float = EPS_CONSTRUCTION,
    eps_coincide: float = EPS_COINCIDE,
) -> EditResult:
    """CONTRACTS §2 / ADR-025: propose the manual trim/extend/stray-delete
    for the run under ``eid`` given the click ``p_world``."""
    resolved = _resolve_run(primitives, eid, eps_coincide)
    if resolved is None:
        return _refused(REFUSAL_UNKNOWN.format(eid=eid))
    run, ent_eids = resolved

    # -- stray rule: zero EXTERNAL attachments => delete the whole run --
    if not _external_attachments(primitives, run, ent_eids, eps_coincide):
        return EditResult(
            ok=True,
            reason=None,
            deletions=list(ent_eids) or [run.eid],
            trims=[],
        )

    # -- which extent endpoint moves: the one nearest the click --
    d_a = go.dist(p_world, run.a)
    d_b = go.dist(p_world, run.b)
    moving_end = "a" if d_a <= d_b else "b"
    moving_pt = run.a if moving_end == "a" else run.b
    other_pt = run.b if moving_end == "a" else run.a

    # run direction along the moving->other axis (for the flip guard)
    rx = other_pt.x - moving_pt.x
    ry = other_pt.y - moving_pt.y
    run_len = math.hypot(rx, ry)
    if run_len <= eps_construction:
        return _refused(REFUSAL_NO_TARGET)  # degenerate run: nothing to trim
    ux, uy = rx / run_len, ry / run_len

    def _valid(cand: Pt) -> bool:
        """A candidate must project onto the moving->other axis BELOW the
        far endpoint (proj < run_len): snapping the moving endpoint PAST
        the other endpoint would collapse/flip the run. EXTENSION
        (proj < 0, candidate beyond the moving end away from the run)
        is allowed — user answer 2: falls-short EXTENDS. A candidate AT
        the other endpoint (proj ~ run_len) is invalid."""
        proj = (cand.x - moving_pt.x) * ux + (cand.y - moving_pt.y) * uy
        return proj < run_len - eps_construction

    own = set(ent_eids) | _member_ids(run)
    own.add(run.eid)

    best: tuple[float, Pt] | None = None

    def _consider(cand: Pt) -> None:
        nonlocal best
        if go.dist(cand, moving_pt) <= eps_construction:
            return  # no-op move (already there)
        if not _valid(cand):
            return
        d = go.dist(moving_pt, cand)
        if best is None or d < best[0]:
            best = (d, cand)

    for e in primitives:
        if e.eid in own:
            continue
        if isinstance(e, Seg):
            vx, vy = e.b.x - e.a.x, e.b.y - e.a.y
            L2 = vx * vx + vy * vy
            if L2 <= 0.0:
                _consider(e.a)
            else:
                wx, wy = moving_pt.x - e.a.x, moving_pt.y - e.a.y
                t = (wx * vx + wy * vy) / L2
                _consider(Pt(e.a.x + t * vx, e.a.y + t * vy))
        elif isinstance(e, Arc):
            # supporting circle, arc-span-filtered. Candidate selection:
            # 1. the RADIAL projection of the moving endpoint onto the
            #    supporting circle, when its angle lies in the arc's span;
            # 2. otherwise, the NEAREST spanned TRUE crossing of the run's
            #    supporting line with the circle (reach path — the arc
            #    actually crosses the run/extension there).
            dn = math.hypot(moving_pt.x - e.center.x, moving_pt.y - e.center.y)
            if dn <= eps_construction:
                continue
            ux2 = (moving_pt.x - e.center.x) / dn
            uy2 = (moving_pt.y - e.center.y) / dn
            radial = Pt(e.center.x + e.r * ux2, e.center.y + e.r * uy2)
            ang = go.pt_angle_deg(e.center, radial)
            if go.span_contains(e.start_deg, e.end_deg, ang, eps_construction):
                _consider(radial)
                continue
            # reach path: the arc is a candidate only when the moving
            # endpoint can reach a SPANNED crossing WITHOUT passing
            # through unspanned circle. Rule: the FIRST crossing along
            # the ray FROM the moving endpoint must itself be spanned
            # (the entry is on the arc). If that entry is unspanned,
            # every farther spanned crossing lies past unspanned circle
            # (a disk-crossing snap) — refused.
            crossings = sorted(
                go.line_circle_intersections(
                    moving_pt, other_pt, e.center, e.r),
                key=lambda p: -((p.x - moving_pt.x) * ux
                                + (p.y - moving_pt.y) * uy),
            )
            for p in crossings:
                proj = ((p.x - moving_pt.x) * ux
                        + (p.y - moving_pt.y) * uy)
                if proj > run_len + eps_construction:
                    continue  # past the OTHER endpoint: unreached
                if go.span_contains(e.start_deg, e.end_deg,
                                    go.pt_angle_deg(e.center, p),
                                    eps_construction):
                    _consider(p)  # entry (or sole crossing) is spanned
                break  # the FIRST crossing decides; later ones cross the disk
        elif isinstance(e, Circ):
            dn = math.hypot(moving_pt.x - e.center.x, moving_pt.y - e.center.y)
            if dn <= eps_construction:
                continue
            ux2 = (moving_pt.x - e.center.x) / dn
            uy2 = (moving_pt.y - e.center.y) / dn
            _consider(Pt(e.center.x + e.r * ux2, e.center.y + e.r * uy2))
        elif isinstance(e, PointEnt):
            _consider(e.p)

    if best is None:
        return _refused(REFUSAL_NO_TARGET)

    new_pt = best[1]
    old_a, old_b = run.a, run.b
    if moving_end == "a":
        new_a, new_b = new_pt, old_b
    else:
        new_a, new_b = old_a, new_pt
    return EditResult(
        ok=True,
        reason=None,
        deletions=[],
        trims=[Trim(eid=run.eid, old=(old_a, old_b), new=(new_a, new_b))],
    )