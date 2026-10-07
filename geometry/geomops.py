"""Pure 2D construction math — stdlib-only, tolerance-explicit (CONTRACTS §2 TOL policy).

All predicates take explicit eps parameters (SPEC §11.2; AGENTS.md invariant 2:
no raw ``==`` on coordinates). No ezdxf/tkinter/numpy (ADR-006/008).
"""
from __future__ import annotations

import math

from geometry.entities import Arc, Pt, Seg


def _xy(p) -> tuple[float, float]:
    """Normalize Pt | tuple to a plain (x, y) tuple."""
    if isinstance(p, Pt):
        return p.x, p.y
    return p[0], p[1]


def unit(v: tuple[float, float]) -> tuple[float, float]:
    n = math.hypot(v[0], v[1])
    if n <= 0.0:
        raise ValueError("zero-length direction vector")
    return v[0] / n, v[1] / n


def sub(a, b) -> tuple[float, float]:
    ax, ay = _xy(a)
    bx, by = _xy(b)
    return ax - bx, ay - by


def add(a, b) -> tuple[float, float]:
    ax, ay = _xy(a)
    bx, by = _xy(b)
    return ax + bx, ay + by


def dist(a, b) -> float:
    ax, ay = _xy(a)
    bx, by = _xy(b)
    return math.hypot(ax - bx, ay - by)


def line_intersection(a, b, c, d, eps: float) -> Pt | None:
    """Supporting-line intersection of line(a,b) x line(c,d); None if parallel/collinear."""
    ax, ay = _xy(a)
    cx, cy = _xy(c)
    d1 = sub(b, a)
    d2 = sub(d, c)
    cr = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(cr) <= eps * max(1.0, math.hypot(d1[0], d1[1]), math.hypot(d2[0], d2[1])):
        return None
    t = ((cx - ax) * d2[1] - (cy - ay) * d2[0]) / cr
    return Pt(ax + t * d1[0], ay + t * d1[1])


def point_line_dist(p, a, b) -> float:
    """Distance from p to the INFINITE line through a,b."""
    px, py = _xy(p)
    d = sub(b, a)
    n = math.hypot(d[0], d[1])
    if n <= 0.0:
        return dist(p, a)
    ax, ay = _xy(a)
    return abs(d[1] * (px - ax) - d[0] * (py - ay)) / n


def point_seg_dist(p, a, b) -> float:
    """Distance from p to the segment a-b (perpendicular; interior projection allowed)."""
    px, py = _xy(p)
    ax, ay = _xy(a)
    bx, by = _xy(b)
    dx, dy = bx - ax, by - ay
    n2 = dx * dx + dy * dy
    if n2 <= 0.0:
        return dist(p, a)
    t = ((px - ax) * dx + (py - ay) * dy) / n2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def line_circle_intersections(a, b, c, r: float) -> list[Pt]:
    """Intersections of infinite line(a,b) with circle(c,r): 0, 1 (tangent), or 2 points."""
    ax, ay = _xy(a)
    cx, cy = _xy(c)
    d = sub(b, a)
    ex, ey = ax - cx, ay - cy
    A = d[0] * d[0] + d[1] * d[1]
    if A <= 0.0:
        return []
    B = 2.0 * (ex * d[0] + ey * d[1])
    C = ex * ex + ey * ey - r * r
    disc = B * B - 4.0 * A * C
    if disc < 0.0:
        return []
    sq = math.sqrt(disc)
    if sq <= 0.0:
        t = -B / (2.0 * A)
        return [Pt(ax + t * d[0], ay + t * d[1])]
    return [
        Pt(ax + t * d[0], ay + t * d[1])
        for t in ((-B + sq) / (2.0 * A), (-B - sq) / (2.0 * A))
    ]


def seg_interior_hits_disk(a, b, c, r: float, eps: float) -> bool:
    """True if the OPEN interior of segment a-b contains a point strictly
    inside disk(c, r-eps) (endpoints on the circle do not count; an endpoint
    strictly inside does, by continuity). Analytic via the quadratic's roots."""
    ax, ay = _xy(a)
    cx, cy = _xy(c)
    bx, by = _xy(b)
    dx, dy = bx - ax, by - ay
    A = dx * dx + dy * dy
    if A <= 0.0:
        return False
    ex, ey = ax - cx, ay - cy
    rr = r - eps
    B = 2.0 * (ex * dx + ey * dy)
    C = ex * ex + ey * ey - rr * rr
    disc = B * B - 4.0 * A * C
    if disc <= 0.0:
        return False  # f >= 0 everywhere (touches at most at one point)
    sq = math.sqrt(disc)
    t1 = (-B - sq) / (2.0 * A)
    t2 = (-B + sq) / (2.0 * A)
    lo = max(0.0, t1)
    hi = min(1.0, t2)
    return lo < hi  # nonempty open interval of t in (0,1) with f(t) < 0


def seg_min_center_dist(a, b, c) -> float:
    """Min distance from c to the segment a-b (point-to-segment)."""
    return point_seg_dist(c, a, b)


def in_disk(p, c, r: float, eps: float) -> bool:
    """Endpoint-in-circle test (SPEC 11.5 row 2: on-circle within eps counts as inside)."""
    return dist(p, c) <= r + eps


def pt_angle_deg(c, p) -> float:
    """CCW angle of p seen from c, normalized to [0, 360)."""
    cx, cy = _xy(c)
    px, py = _xy(p)
    a = math.degrees(math.atan2(py - cy, px - cx))
    return a % 360.0


def span_contains(start_deg: float, end_deg: float, angle_deg: float, eps: float) -> bool:
    """True if angle_deg lies within the CCW arc span start->end. A full
    circle (start->start+360, e.g. 0->360) contains everything; a degenerate
    point span (start == end) contains only near-boundary angles."""
    sweep = (end_deg - start_deg) % 360.0
    if sweep <= eps and abs(end_deg - start_deg) > eps:
        return True  # full circle (e.g. 0 -> 360)
    s = start_deg % 360.0
    e = end_deg % 360.0
    a = angle_deg % 360.0
    if s <= e:
        inside = s <= a <= e
    else:
        inside = a >= s or a <= e
    if inside:
        return True
    for b in (s, e):
        d = abs(((a - b + 180.0) % 360.0) - 180.0)
        if d <= eps:
            return True
    return False


def span_len(start_deg: float, end_deg: float) -> float:
    """CCW sweep length from start to end, in degrees."""
    return (end_deg - start_deg) % 360.0


def two_circle_intersections(c1, r1: float, c2, r2: float, eps: float) -> list[Pt]:
    """Circle x circle intersection points (0, 1 tangent, 2)."""
    c1x, c1y = _xy(c1)
    c2x, c2y = _xy(c2)
    d = dist((c1x, c1y), (c2x, c2y))
    if d <= eps or d > r1 + r2 + eps or d < abs(r1 - r2) - eps:
        return []
    a = (d * d + r1 * r1 - r2 * r2) / (2.0 * d)
    h2 = r1 * r1 - a * a
    if h2 < -eps:
        return []
    h = math.sqrt(max(h2, 0.0))
    ux, uy = (c2x - c1x) / d, (c2y - c1y) / d
    mx, my = c1x + a * ux, c1y + a * uy
    if h <= eps * max(1.0, r1):
        return [Pt(mx, my)]
    return [Pt(mx + h * uy, my - h * ux), Pt(mx - h * uy, my + h * ux)]


def arc_endpoints(arc: Arc) -> tuple[Pt, Pt]:
    """Start/end points of the CCW arc (start_deg -> end_deg)."""
    return (
        Pt(arc.center.x + arc.r * math.cos(math.radians(arc.start_deg)),
           arc.center.y + arc.r * math.sin(math.radians(arc.start_deg))),
        Pt(arc.center.x + arc.r * math.cos(math.radians(arc.end_deg)),
           arc.center.y + arc.r * math.sin(math.radians(arc.end_deg))),
    )


def arc_min_center_dist(arc: Arc, c) -> float:
    """Min distance from c to the arc's point set."""
    cx, cy = _xy(c)
    dx0, dy0 = cx - arc.center.x, cy - arc.center.y
    dn = math.hypot(dx0, dy0)
    if dn <= 0.0:
        return arc.r
    closest_angle = math.degrees(math.atan2(dy0, dx0)) % 360.0
    if span_contains(arc.start_deg, arc.end_deg, closest_angle, 1e-9):
        return abs(dn - arc.r)
    p0, p1 = arc_endpoints(arc)
    return min(dist(p0, c), dist(p1, c))


def arc_disk_inside_interval(arc: Arc, c, r: float, eps: float) -> list[tuple[float, float]]:
    """CCW angle intervals of the arc strictly inside disk(c,r) (analytic; may be [] / one
    interval; degenerate crossings collapse)."""
    cx, cy = _xy(c)
    pts = two_circle_intersections(arc.center, arc.r, (cx, cy), r, eps)
    if not pts:
        # concentric / disjoint circles: arc is fully inside or fully outside
        mid = (arc.start_deg + (span_len(arc.start_deg, arc.end_deg)) / 2.0) % 360.0
        mpt = Pt(arc.center.x + arc.r * math.cos(math.radians(mid)),
                 arc.center.y + arc.r * math.sin(math.radians(mid)))
        if dist(mpt, (cx, cy)) < r - eps:
            return [(arc.start_deg, arc.end_deg)]
        return []
    angles = sorted(pt_angle_deg(arc.center, p) for p in pts)
    # candidate inside intervals: between consecutive crossing angles
    bounds = [a for a in angles if span_contains(arc.start_deg, arc.end_deg, a, eps)]
    if not bounds:
        return []
    if len(bounds) == 1:
        # tangent touch or one crossing at an end: treat as boundary case -> no interval
        return []
    intervals: list[tuple[float, float]] = []
    # walk CCW through the span from each crossing to the next; keep those inside
    for i in range(len(bounds)):
        a0 = bounds[i]
        a1 = bounds[(i + 1) % len(bounds)]
        mid = (a0 + span_len(a0, a1) / 2.0) % 360.0
        mpt = Pt(arc.center.x + arc.r * math.cos(math.radians(mid)),
                 arc.center.y + arc.r * math.sin(math.radians(mid)))
        if dist(mpt, (cx, cy)) < r - eps:
            intervals.append((a0, a1))
    return intervals


def bisector_unit(
    u1: tuple[float, float], u2: tuple[float, float], sign: int
) -> tuple[float, float] | None:
    """ADR-015(g): +1 -> unit(u1+u2), -1 -> unit(u1-u2); None if degenerate."""
    v = (u1[0] + sign * u2[0], u1[1] + sign * u2[1])
    n = math.hypot(v[0], v[1])
    if n <= 0.0:
        return None
    return v[0] / n, v[1] / n


def angle_between_unit_dirs(u1: tuple[float, float], u2: tuple[float, float]) -> float:
    """Angle between direction vectors in [0, 180] degrees."""
    d = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
    return math.degrees(math.acos(d))
