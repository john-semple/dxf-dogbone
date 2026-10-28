"""ADR-032 / M-ENTRY — parallel-throat entry widen goldens."""
from __future__ import annotations

import math

from geometry import geomops as go
from geometry.entities import Circ, Pt, Seg, Side
from geometry.tolerances import EPS_COINCIDE
from rules.engine import (
    ENTRY_WIDENED,
    ENTRY_WIDEN_HOST,
    ghost_candidates,
    place_corner,
)


R = 1.5875


def _acute_notch(edge_len: float = 40.0):
    """syn-tight-notch class: air-V ≈ 36.87°, apex (90, 50), air +x.

    Edges along (30,±10) directions, truncated to ``edge_len``.
    """
    apex = Pt(90.0, 50.0)
    # unit dirs for the two flanks (length of (30,10) = sqrt(1000))
    n = math.sqrt(1000.0)
    d1 = (30.0 / n, -10.0 / n)
    d2 = (30.0 / n, 10.0 / n)
    e1 = Seg(
        "e1",
        apex,
        Pt(apex.x + edge_len * d1[0], apex.y + edge_len * d1[1]),
    )
    e2 = Seg(
        "e2",
        apex,
        Pt(apex.x + edge_len * d2[0], apex.y + edge_len * d2[1]),
    )
    return [e1, e2], apex


def _place_air(prims, r=R):
    from geometry.entities import Refusal

    gcs = ghost_candidates(prims, "e1", "e2", r)
    assert not isinstance(gcs, Refusal)
    # air side: center has larger x than apex for this fixture
    apex_x = 90.0
    picks = [(s, f, c) for s, f, c in gcs if c.x > apex_x]
    assert picks
    side, flip, _c = picks[0]
    return place_corner(
        prims, "e1", "e2", side, r, set(), [], side_flip=flip
    )


def test_rules_entry_widen_90_stays_classic():
    # unit square corner at origin, air in +/+ quadrant
    prims = [
        Seg("e1", Pt(0.0, 0.0), Pt(40.0, 0.0)),
        Seg("e2", Pt(0.0, 0.0), Pt(0.0, 40.0)),
    ]
    gcs = ghost_candidates(prims, "e1", "e2", R)
    from geometry.entities import Refusal

    assert not isinstance(gcs, Refusal)
    # air bisector toward (+1,+1)
    picks = [(s, f, c) for s, f, c in gcs if c.x > 0 and c.y > 0]
    side, flip, _c = picks[0]
    res = place_corner(
        prims, "e1", "e2", side, R, set(), [], side_flip=flip
    )
    assert res.ok
    assert res.dogbone is not None
    assert res.dogbone.throat is None
    assert ENTRY_WIDENED not in res.warnings
    span = go.span_len(res.dogbone.arc.start_deg, res.dogbone.arc.end_deg)
    assert abs(span - (360.0 - 4.0 * 45.0)) < 1e-6


def test_rules_entry_widen_acute_capsule_goldens():
    prims, apex = _acute_notch(40.0)
    res = _place_air(prims)
    assert res.ok
    db = res.dogbone
    assert db is not None
    assert db.throat is not None
    assert ENTRY_WIDENED in res.warnings

    # same center as classic
    assert abs(go.dist(db.center, apex) - R) < 1e-9
    assert abs(db.center.x - (90.0 + R)) < 1e-6
    assert abs(db.center.y - 50.0) < 1e-6

    t1, t2 = db.throat[0].b, db.throat[1].b
    q1, q2 = db.throat[0].a, db.throat[1].a
    assert abs(go.dist(t1, t2) - 2.0 * R) < 1e-6
    # walls // bisector (+x)
    for th in db.throat:
        d = go.sub(th.b, th.a)
        # direction should be parallel to û = (1,0): |dy| ~ 0 relative
        assert abs(d[1]) < 1e-6
    # undercut semicircle (180°) through apex; air-far point not on span
    span = go.span_len(db.arc.start_deg, db.arc.end_deg)
    assert abs(span - 180.0) < 1e-3
    aa = go.pt_angle_deg(db.center, apex)
    assert go.span_contains(db.arc.start_deg, db.arc.end_deg, aa, 1e-3)
    u = go.unit(go.sub(db.center, apex))
    far = Pt(db.center.x + R * u[0], db.center.y + R * u[1])
    assert not go.span_contains(
        db.arc.start_deg, db.arc.end_deg, go.pt_angle_deg(db.center, far), 1e-3
    )
    # rebuilt to q, not classic p
    rb = {x.eid: x for x in res.rebuilt}
    assert go.dist(rb["e1"].new, q1) < EPS_COINCIDE or go.dist(rb["e1"].new, q2) < EPS_COINCIDE
    assert go.dist(rb["e2"].new, q1) < EPS_COINCIDE or go.dist(rb["e2"].new, q2) < EPS_COINCIDE
    # mouth trigger: classic mouth < Ø
    # half_side ≈ 18.435°; mouth = 2R sin(2α) for central gap 4α
    alpha = math.radians(18.43494882)
    mouth = 2.0 * R * math.sin(2.0 * alpha)
    assert mouth < 2.0 * R - EPS_COINCIDE


def test_rules_entry_widen_not_hostable_falls_back_classic():
    # Classic p sits at ~2R cos(α) ≈ 3.01; widen q at R/sin(α) ≈ 5.02.
    # Edge length 4 hosts classic but not the throat junction.
    prims, _apex = _acute_notch(edge_len=4.0)
    res = _place_air(prims)
    assert res.ok
    assert res.dogbone is not None
    assert res.dogbone.throat is None
    assert ENTRY_WIDEN_HOST in res.warnings
    assert ENTRY_WIDENED not in res.warnings
    span = go.span_len(res.dogbone.arc.start_deg, res.dogbone.arc.end_deg)
    assert abs(span - 180.0) > 1.0  # classic long arc, not semicircle


def test_rules_entry_widen_batch_mixed_mouth_per_candidate():
    """Wide 90° and acute notch both queued independently (per-candidate gate)."""
    square = [
        Seg("s1", Pt(0.0, 0.0), Pt(40.0, 0.0)),
        Seg("s2", Pt(0.0, 0.0), Pt(0.0, 40.0)),
    ]
    acute, _ = _acute_notch(40.0)
    # rename acute eids to avoid clash in a shared primitive list (separate places)
    gcs = ghost_candidates(square, "s1", "s2", R)
    from geometry.entities import Refusal

    assert not isinstance(gcs, Refusal)
    picks = [(s, f, c) for s, f, c in gcs if c.x > 0 and c.y > 0]
    side, flip, _ = picks[0]
    res90 = place_corner(
        square, "s1", "s2", side, R, set(), [], side_flip=flip
    )
    res_ac = _place_air(acute)
    assert res90.ok and res_ac.ok
    assert res90.dogbone.throat is None
    assert res_ac.dogbone.throat is not None


def test_rules_entry_widen_circle_throat_slab_flagged_disk_miss_not():
    """ISSUE-026 + ADR-032: CIRCLE overlapping throat slab only is flagged;
    a nearby hole clear of the capsule is not."""
    prims, apex = _acute_notch(40.0)
    alpha = math.radians(18.43494882)
    q_depth = R / math.tan(alpha)
    # On bisector past the disk, still inside the throat slab u∈[R, q_depth].
    u_slab = q_depth - 0.2
    hole_r = 0.3
    throat_hole = Circ(
        "throat_hole",
        Pt(apex.x + u_slab, apex.y),
        hole_r,
    )
    assert not go.disks_overlap_beyond_tangency(
        throat_hole.center, hole_r, Pt(apex.x + R, apex.y), R, EPS_COINCIDE
    )
    assert go.circle_hits_capsule(
        throat_hole.center, hole_r, apex, Pt(apex.x + R, apex.y), R,
        (1.0, 0.0), q_depth, EPS_COINCIDE,
    )
    near = Circ("near_hole", Pt(apex.x + 20.0, apex.y + 20.0), 1.0)
    res = _place_air(prims + [throat_hole, near])
    assert res.ok and res.dogbone is not None and res.dogbone.throat is not None
    flagged = {f.eid: f.reason for f in res.flags}
    assert flagged.get("throat_hole") == "CIRCLE_IN_WINDOW"
    assert "near_hole" not in flagged
