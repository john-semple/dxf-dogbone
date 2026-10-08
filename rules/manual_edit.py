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
  * ADR-028: a click between intersections on both sides removes that
    collinear span (deletion, or one on-axis trim of a one-sided stub)
    instead of rotating onto a perpendicular foot.
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
    TextEnt,
    Trim,
)
from geometry.runs import chain_run
from geometry.tolerances import EPS_COINCIDE, EPS_CONSTRUCTION

REFUSAL_UNKNOWN = "UNKNOWN_EDGE: {eid} is not resolvable in primitives"
REFUSAL_NO_TARGET = "NO_TARGET: no supporting-geometry intersection found"
# ADR-028: pinned on a both-sides span deletion so the UI does not reuse
# the stray sentence. The foot path and the stray rule leave warnings empty.
SPAN_DELETE_WARNING = (
    "SPAN_DELETE: the collinear span up to the nearest intersection on each side"
)


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


def _record_stop(stops: list[float], t: float, eps: float) -> None:
    for existing in stops:
        if abs(existing - t) <= eps:
            return
    stops.append(t)


def _on_segment(a: Pt, b: Pt, p: Pt, eps: float) -> bool:
    return go.point_seg_dist(p, a, b) <= eps


def _strict_interior(a: Pt, b: Pt, p: Pt, eps: float) -> bool:
    """True when ``p`` lies on segment a-b and is farther than ``eps`` from
    both endpoints. Endpoint hits are attachment stops, not interior crossings."""
    if not _on_segment(a, b, p, eps):
        return False
    return go.dist(p, a) > eps and go.dist(p, b) > eps


def _span_delete(ent_eids: tuple[str, ...], kill: set[str]) -> EditResult:
    return EditResult(
        ok=True,
        reason=None,
        deletions=[eid for eid in ent_eids if eid in kill],
        trims=[],
        warnings=[SPAN_DELETE_WARNING],
    )


def _span_between_intersections(
    primitives: list[Entity],
    p_world: Pt,
    run: Seg,
    ent_eids: tuple[str, ...],
    eps_construction: float,
    eps_coincide: float,
) -> EditResult | None:
    """ADR-028. The collinear piece is the chain run. Walk both ways from
    the click and stop at the first intersection on each side.

    An intersection is an external attachment at a piece endpoint, or a
    finite crossing through the piece interior. Collinear neighbors joined
    only by an endpoint gap stay in the piece. Returns None when either
    side is open — that click stays on the ADR-025 perpendicular-foot path.
    """
    rx = run.b.x - run.a.x
    ry = run.b.y - run.a.y
    run_len = math.hypot(rx, ry)
    if run_len <= eps_construction:
        return None
    ux, uy = rx / run_len, ry / run_len

    def proj(p: Pt) -> float:
        return (p.x - run.a.x) * ux + (p.y - run.a.y) * uy

    def point_at(t: float) -> Pt:
        return Pt(run.a.x + ux * t, run.a.y + uy * t)

    segs = {e.eid: e for e in primitives if isinstance(e, Seg)}
    members = [segs[eid] for eid in ent_eids if eid in segs]
    if not members:
        return None
    piece = set(ent_eids)

    stops: list[float] = []
    for member in members:
        for end in (member.a, member.b):
            for e in primitives:
                if e.eid in piece:
                    continue
                for ax, ay in attachment_points(e):
                    if math.hypot(end.x - ax, end.y - ay) <= eps_coincide:
                        _record_stop(stops, proj(end), eps_coincide)
                        break

    for e in primitives:
        if e.eid in piece:
            continue
        for member in members:
            if isinstance(e, Seg):
                hit = go.line_intersection(
                    member.a, member.b, e.a, e.b, eps_construction)
                if hit is None:
                    continue
                if _strict_interior(member.a, member.b, hit, eps_coincide) \
                        and _on_segment(e.a, e.b, hit, eps_coincide):
                    _record_stop(stops, proj(hit), eps_coincide)
            elif isinstance(e, (Arc, Circ)):
                for hit in go.line_circle_intersections(
                        member.a, member.b, e.center, e.r):
                    if not _strict_interior(
                            member.a, member.b, hit, eps_coincide):
                        continue
                    if isinstance(e, Arc) and not go.span_contains(
                            e.start_deg, e.end_deg,
                            go.pt_angle_deg(e.center, hit),
                            eps_construction):
                        continue
                    _record_stop(stops, proj(hit), eps_coincide)
            elif isinstance(e, (PointEnt, TextEnt)):
                p = e.p
                if _strict_interior(member.a, member.b, p, eps_coincide):
                    _record_stop(stops, proj(p), eps_coincide)

    t_click = proj(p_world)
    left = [t for t in stops if t < t_click - eps_coincide]
    right = [t for t in stops if t > t_click + eps_coincide]
    if not left or not right:
        return None
    t_lo, t_hi = max(left), min(right)

    overlap: list[Seg] = []
    past_lo: list[Seg] = []
    past_hi: list[Seg] = []
    inside: list[Seg] = []
    for member in members:
        s0, s1 = sorted((proj(member.a), proj(member.b)))
        if not (s1 > t_lo + eps_coincide and s0 < t_hi - eps_coincide):
            continue
        overlap.append(member)
        lo_past = s0 < t_lo - eps_coincide
        hi_past = s1 > t_hi + eps_coincide
        if lo_past and hi_past:
            past_lo.append(member)
            past_hi.append(member)
        elif lo_past:
            past_lo.append(member)
        elif hi_past:
            past_hi.append(member)
        else:
            inside.append(member)

    past_both = [m for m in past_lo if m in past_hi]
    if past_both or (past_lo and past_hi):
        # A window through one segment cannot be cut with one Trim.
        # Delete each such segment whole. Members that merely begin at an
        # intersection and run outward are not in ``overlap``.
        if past_both:
            kill = {m.eid for m in past_both} | {m.eid for m in inside}
        else:
            kill = {m.eid for m in overlap}
        if not kill:
            return None
        return _span_delete(ent_eids, kill)

    if past_lo or past_hi:
        # Surviving stub is on one side only. One on-axis Trim; apply_edit
        # shortens the straddler and drops members wholly in the removed span.
        if past_hi:
            new_a, new_b = point_at(t_hi), run.b
        else:
            new_a, new_b = run.a, point_at(t_lo)
        return EditResult(
            ok=True,
            reason=None,
            deletions=[],
            trims=[Trim(eid=run.eid, old=(run.a, run.b), new=(new_a, new_b))],
        )

    if not inside:
        return None
    return _span_delete(ent_eids, {m.eid for m in inside})


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

    # ADR-028: both sides of the click closed by an intersection. Otherwise
    # fall through to the perpendicular-foot path below.
    spanned = _span_between_intersections(
        primitives, p_world, run, ent_eids, eps_construction, eps_coincide)
    if spanned is not None:
        return spanned

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