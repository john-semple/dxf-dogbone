"""geometry.geomops — pure math predicates (M2)."""
import math

from geometry import geomops as go
from geometry.entities import Arc, Pt


def test_geomops_line_intersection_and_parallel():
    a = go.line_intersection(Pt(0, 0), Pt(10, 0), Pt(5, -5), Pt(5, 5), 1e-9)
    assert a is not None and abs(a.x - 5.0) < 1e-9 and abs(a.y) < 1e-9
    assert (
        go.line_intersection(Pt(0, 0), Pt(10, 0), Pt(0, 1), Pt(10, 1), 1e-9) is None
    )


def test_geomops_point_distances():
    assert abs(go.point_seg_dist(Pt(5, 3), Pt(0, 0), Pt(10, 0)) - 3.0) < 1e-12
    assert abs(go.point_seg_dist(Pt(15, 0), Pt(0, 0), Pt(10, 0)) - 5.0) < 1e-12
    assert abs(go.point_line_dist(Pt(5, 2), Pt(0, 0), Pt(10, 0)) - 2.0) < 1e-12


def test_geomops_line_circle_intersections():
    pts = go.line_circle_intersections(Pt(0, 0), Pt(10, 0), Pt(3, 0), 2.0)
    assert sorted(round(p.x, 9) for p in pts) == [1.0, 5.0]
    assert len(go.line_circle_intersections(Pt(0, 5), Pt(10, 5), Pt(3, 0), 2.0)) == 0
    assert len(go.line_circle_intersections(Pt(0, 2), Pt(10, 2), Pt(3, 0), 2.0)) == 1


def test_geomops_seg_interior_hits_disk():
    c, r = Pt(0, 0), 2.0
    # kept segment starting on the circle, going away: interior misses
    assert not go.seg_interior_hits_disk(Pt(2, 0), Pt(9, 0), c, r, 1e-3)
    # interior strictly inside the disk
    assert go.seg_interior_hits_disk(Pt(2, 0), Pt(0.5, 0), c, r, 1e-3)
    # endpoint strictly inside counts (continuity)
    assert go.seg_interior_hits_disk(Pt(2, 0), Pt(1.0, 0), c, r, 1e-3)
    # chord crossing (both endpoints outside)
    assert go.seg_interior_hits_disk(Pt(-5, 0.5), Pt(5, 0.5), c, r, 1e-3)
    # fully outside
    assert not go.seg_interior_hits_disk(Pt(5, 0), Pt(9, 0), c, r, 1e-3)


def test_geomops_two_circle_and_span():
    pts = go.two_circle_intersections(Pt(0, 0), 2.0, Pt(3, 0), 2.0, 1e-9)
    assert len(pts) == 2 and abs(pts[0].x - 1.5) < 1e-9
    assert len(go.two_circle_intersections(Pt(0, 0), 2.0, Pt(4, 0), 2.0, 1e-9)) == 1
    assert len(go.two_circle_intersections(Pt(0, 0), 2.0, Pt(9, 0), 2.0, 1e-9)) == 0
    assert go.span_contains(45.0, 225.0, 135.0, 1e-9)
    assert not go.span_contains(45.0, 225.0, 315.0, 1e-9)
    assert abs(go.span_len(315.0, 135.0) - 180.0) < 1e-9
    assert abs(go.span_len(200.3947, 339.6053) - 139.2106) < 1e-3


def test_geomops_arc_helpers():
    arc = Arc("a", Pt(0, 0), 2.0, 90.0, 270.0)  # left half circle
    assert abs(go.arc_min_center_dist(arc, Pt(-5, 0)) - 3.0) < 1e-9
    assert abs(go.arc_min_center_dist(arc, Pt(5, 0)) - math.sqrt(29.0)) < 1e-9
    p0, p1 = go.arc_endpoints(arc)
    assert abs(p0.x) < 1e-9 and abs(p0.y - 2.0) < 1e-9
    assert abs(p1.x) < 1e-9 and abs(p1.y + 2.0) < 1e-9
    # chord-crossing arc vs disk at its left: inside interval near 180 deg
    iv = go.arc_disk_inside_interval(arc, Pt(-2.5, 0), 2.0, 1e-9)
    assert len(iv) == 1
    a0, a1 = iv[0]
    assert abs(a0 - 128.68) < 0.01 and abs(a1 - 231.32) < 0.01
    # disjoint disk: no interval
    assert go.arc_disk_inside_interval(arc, Pt(2.5, 0), 2.0, 1e-9) == []


def test_geomops_bisector_and_angles():
    b = go.bisector_unit((0.0, -1.0), (1.0, 0.0), +1)
    assert abs(b[0] - math.sqrt(0.5)) < 1e-12 and abs(b[1] + math.sqrt(0.5)) < 1e-12
    b2 = go.bisector_unit((0.0, -1.0), (1.0, 0.0), -1)
    assert abs(b2[0] + math.sqrt(0.5)) < 1e-12 and abs(b2[1] + math.sqrt(0.5)) < 1e-12
    assert go.bisector_unit((1.0, 0.0), (-1.0, 0.0), +1) is None  # degenerate
    assert abs(go.angle_between_unit_dirs((1.0, 0.0), (0.0, 1.0)) - 90.0) < 1e-9


def test_geomops_span_contains_full_circle_and_degenerate():
    # ADR-016 round-3 audit: direct full-circle span test
    assert go.span_contains(0.0, 360.0, 180.0, 1e-9)   # full circle contains all
    assert go.span_contains(0.0, 360.0, 0.0, 1e-9)
    assert go.span_contains(45.0, 405.0, 300.0, 1e-9)  # sweep == 360 via wrap
    assert not go.span_contains(45.0, 45.0, 300.0, 1e-9)  # point span: only near 45
    assert go.span_contains(45.0, 45.0, 45.0, 1e-9)
