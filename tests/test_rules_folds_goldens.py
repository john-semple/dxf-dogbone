"""rules/folds.py — WORKED-EXAMPLE Step 6 goldens + idempotency + validation.

Binding numbers (WE Step 6, print-precision note):
  R=1.5875 circle at (46.12253, 50.39427), arc [45,225]:
    fold y=51.2634 from the LEFT → kept-side endpoint (44.7941, 51.2634) ±0.001.
  R=3.175 golden replay circle at (47.24506, 49.27174):
    crossings x = 49.71757 / 44.77237 (±0.001).

ISSUE-012(d): the SAMPLES.md (44.3930/46.1138) trim goldens were measured on
the USER's hand-made arc; M5 re-derives them against the ENGINE corner-1 arc
(center (45.2534, 121.6506), span 180→0). The engine arc crossings at
y=120.7702 are x = 43.9324 / 46.5744 (±0.001).
"""
import math

from geometry import geomops as go
from geometry.entities import Arc, Dogbone, Pt, Seg, Side
from rules.folds import (
    FOLD_REACH_FACTOR,
    out_of_reach_warnings,
    resolve_folds,
    validate_fold_against_contours,
)
from rules.engine import WINDOW_FACTOR, ghost_candidates, place_corner


def _arc_db(center, r, span=(45.0, 225.0)):
    arc = Arc(eid="arc1", center=center, r=r, start_deg=span[0], end_deg=span[1])
    return Dogbone(
        db_id="db1",
        apex=Pt(45.0, 51.5168),
        center=center,
        r=r,
        side=Side(-1),
        edge1_eid="e1",
        edge2_eid="e2",
        arc=arc,
    )


# ---------------------------------------------------------------------------
# WORKED-EXAMPLE Step 6 goldens
# ---------------------------------------------------------------------------


def test_rules_folds_we_step6_default_r_extend_golden():
    """WE Step 6: fold y=51.2634 from the LEFT → kept-side endpoint
    (44.7941, 51.2634) ±0.001."""
    db = _arc_db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    trims = resolve_folds([fold], [db], {"F1"})
    assert len(trims) == 1
    t = trims[0]
    assert t.eid == "F1"
    assert t.old == (Pt(40.0, 51.2634), Pt(0.0, 51.2634))
    new_a, new_b = t.new
    # the near endpoint (a=40, closer to the circle) extends to the arc
    assert abs(new_a.x - 44.7941) < 0.001 and abs(new_a.y - 51.2634) < 1e-9
    # the far endpoint (b=0) is unchanged
    assert new_b == Pt(0.0, 51.2634)
    # the extended endpoint lies ON the relief arc (dist to center == r)
    assert abs(go.dist(new_a, db.center) - db.r) < 1e-6
    # ... and ON the arc span (angle within [45, 225])
    ang = go.pt_angle_deg(db.center, new_a)
    assert go.span_contains(db.arc.start_deg, db.arc.end_deg, ang, 1e-6)


def test_rules_folds_we_step6_golden_replay_r3175_crossings():
    """WE Step 6 golden replay R=3.175: crossings x = 49.71757 / 44.77237
    (±0.001). The fold from the LEFT extends to the LEFT entry (44.77237)."""
    db = _arc_db(Pt(47.24506, 49.27174), 3.175)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    trims = resolve_folds([fold], [db], {"F1"})
    assert len(trims) == 1
    new_a, _new_b = trims[0].new
    assert abs(new_a.x - 44.77237) < 0.001 and abs(new_a.y - 51.2634) < 1e-9
    assert abs(go.dist(new_a, db.center) - db.r) < 1e-6


def test_rules_folds_we_step6_both_sides_trim_full_circle_arc():
    """Both-sides crossing with a full-circle arc: each endpoint trims to
    its NEAR entry. Fold 40→50; left entry 44.7941, right entry 47.4510."""
    db = _arc_db(Pt(46.12253, 50.39427), 1.5875, span=(0.0, 360.0))
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(50.0, 51.2634))
    trims = resolve_folds([fold], [db], {"F1"})
    assert len(trims) == 1
    new_a, new_b = trims[0].new
    # a=40 (left) trims to the left entry (44.7941) — its near side
    assert abs(new_a.x - 44.7941) < 0.001
    # b=50 (right) trims to the right entry (47.4510) — its near side
    assert abs(new_b.x - 47.4510) < 0.001
    # both lie on the circle
    assert abs(go.dist(new_a, db.center) - db.r) < 1e-6
    assert abs(go.dist(new_b, db.center) - db.r) < 1e-6
    # the kept fold interior (44.7941 → 47.4510) now SPANS the circle — the
    # gap between the two arc entries is the dogbone relief, by design


# ---------------------------------------------------------------------------
# Idempotency (ADR-004 / SPEC §11.6)
# ---------------------------------------------------------------------------


def test_rules_folds_idempotency_double_resolve_noop():
    """SPEC §11.6: double-resolve = no-op. After applying the first Trim,
    a second resolve returns no Trims for the already-resolved fold."""
    db = _arc_db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    t1 = resolve_folds([fold], [db], {"F1"})
    assert len(t1) == 1
    # apply the trim: the near endpoint is now ON the arc
    new_a, _ = t1[0].new
    fold_resolved = Seg(eid="F1", a=new_a, b=Pt(0.0, 51.2634))
    t2 = resolve_folds([fold_resolved], [db], {"F1"})
    assert t2 == []


def test_rules_folds_idempotency_both_endpoints_on_arc():
    """Both endpoints already on the arc → no Trim (idempotency fixture per
    ADR-024(c): 'both already on-arc within eps → no Trim')."""
    db = _arc_db(Pt(46.12253, 50.39427), 1.5875, span=(0.0, 360.0))
    # construct both endpoints ON the circle at the two entries
    left = Pt(44.7941, 51.2634)
    right = Pt(47.4510, 51.2634)
    fold = Seg(eid="F1", a=left, b=right)
    assert resolve_folds([fold], [db], {"F1"}) == []


# ---------------------------------------------------------------------------
# Validation warnings (SPEC §11.3 case 5)
# ---------------------------------------------------------------------------


def test_rules_folds_validate_warning_within_eps_of_contour():
    """Fold collinear with / within eps of a contour edge → warning string
    present (wording matches dxf_io/load._fold_contour_warnings)."""
    fold = Seg(eid="F1", a=Pt(0.0, 50.0), b=Pt(100.0, 50.0))
    contour = Seg(eid="C1", a=Pt(40.0, 50.0), b=Pt(60.0, 50.0))  # collinear overlap
    warns = validate_fold_against_contours(fold, [contour], eps=1e-3)
    assert len(warns) >= 1
    assert any(
        "fold F1 runs within 0.001 mm of contour edge C1" in w for w in warns
    )


def test_rules_folds_validate_no_warning_for_clear_fold():
    """A fold clear of all contour edges → no warnings."""
    fold = Seg(eid="F1", a=Pt(0.0, 50.0), b=Pt(100.0, 50.0))
    contour = Seg(eid="C1", a=Pt(40.0, 60.0), b=Pt(60.0, 60.0))  # 10 mm away
    assert validate_fold_against_contours(fold, [contour], eps=1e-3) == []


def test_rules_folds_validate_ignores_non_seg_entities():
    """Only LINE/Seg contour edges trigger the check (arcs/circles/text
    are not contour edges for §11.3 case 5 per the load stub's shape)."""
    from geometry.entities import Circ, TextEnt

    fold = Seg(eid="F1", a=Pt(0.0, 50.0), b=Pt(100.0, 50.0))
    others = [Circ(eid="C1", center=Pt(50, 50), r=5), TextEnt(eid="T1", p=Pt(50, 50), text="x")]
    assert validate_fold_against_contours(fold, others, eps=1e-3) == []


# ---------------------------------------------------------------------------
# Out-of-reach (SPEC §11.6: max 2× deletion window → unchanged + warn)
# ---------------------------------------------------------------------------


def test_rules_folds_out_of_reach_extend_warns_and_leaves_unchanged():
    """Extend candidate beyond the reach cap → no Trim + out-of-reach
    warning. reach = FOLD_REACH_FACTOR * WINDOW_FACTOR * 2 * r."""
    r = 1.5875
    db = _arc_db(Pt(46.12253, 50.39427), r)
    reach = FOLD_REACH_FACTOR * WINDOW_FACTOR * 2.0 * r  # = 16 * r ≈ 25.4
    # place the fold's near endpoint well beyond reach from the circle
    # circle left entry ≈ 44.79; an endpoint at x = 44.79 - reach - 5 is beyond cap
    far_x = 44.7941 - reach - 5.0
    fold = Seg(eid="F1", a=Pt(far_x, 51.2634), b=Pt(far_x - 50.0, 51.2634))
    trims = resolve_folds([fold], [db], {"F1"})
    assert trims == []  # unchanged
    warns = out_of_reach_warnings([fold], [db], {"F1"})
    assert len(warns) >= 1
    assert "out of reach" in warns[0]


def test_rules_folds_out_of_reach_trim_has_no_cap():
    """TRIM (endpoint inside the circle) has no reach cap — the endpoint
    is pulled to the arc entry regardless of distance (the fold already
    crosses the relief; it must be cleaned up)."""
    r = 1.5875
    db = _arc_db(Pt(46.12253, 50.39427), r, span=(0.0, 360.0))
    # endpoint a=46.5 is INSIDE the circle (dist to center < r); the other
    # endpoint b=1000 is far right. a trims to the right entry (47.4510).
    fold = Seg(eid="F1", a=Pt(46.5, 51.2634), b=Pt(1000.0, 51.2634))
    trims = resolve_folds([fold], [db], {"F1"})
    assert len(trims) == 1
    new_a, new_b = trims[0].new
    # a (inside) trims to the right entry on its side (towards b)
    assert abs(go.dist(new_a, db.center) - r) < 1e-6
    assert new_a.x > db.center.x  # right entry (towards b=1000)
    # b is unchanged (no candidate on its side within reach is relevant —
    # the fold from 47.45 to 1000 has a clean kept interior)
    assert new_b == Pt(1000.0, 51.2634)


# ---------------------------------------------------------------------------
# No-circle case
# ---------------------------------------------------------------------------


def test_rules_folds_no_dogbones_no_trims():
    """Zero dogbones → zero Trims, no warnings."""
    fold = Seg(eid="F1", a=Pt(0.0, 50.0), b=Pt(100.0, 50.0))
    assert resolve_folds([fold], [], {"F1"}) == []
    assert out_of_reach_warnings([fold], [], {"F1"}) == []


def test_rules_folds_no_fold_eids_no_trims():
    """Zero designated folds → zero Trims."""
    db = _arc_db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    assert resolve_folds([fold], [db], set()) == []


def test_rules_folds_fold_not_in_primitives_no_trims():
    """A fold eid not present in primitives → no Trim (defensive)."""
    db = _arc_db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    assert resolve_folds([fold], [db], {"NONEXISTENT"}) == []


def test_rules_folds_no_line_circle_intersection_no_trims():
    """Fold line doesn't cross the circle → no Trim."""
    db = _arc_db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(0.0, 80.0), b=Pt(100.0, 80.0))  # y=80, far above
    assert resolve_folds([fold], [db], {"F1"}) == []


# ---------------------------------------------------------------------------
# ISSUE-012(d): corner-1 trim goldens re-derived against the ENGINE arc
# ---------------------------------------------------------------------------


def _corner1_engine_db():
    """Place the engine's corner-1 dogbone and return its Dogbone."""
    prims = [
        Seg("84", Pt(62.2139, 137.0236), Pt(46.9605, 121.7702)),
        Seg("85", Pt(46.2534, 119.7702), Pt(46.9605, 121.7702)),
        Seg("86", Pt(46.2534, 120.5168), Pt(46.2534, 119.7702)),
        Seg("87", Pt(44.2534, 120.5168), Pt(46.2534, 120.5168)),
        Seg("88", Pt(44.2534, 119.7702), Pt(44.2534, 120.5168)),
        Seg("89", Pt(43.5463, 121.7702), Pt(44.2534, 119.7702)),
        Seg("8A", Pt(43.5463, 121.7702), Pt(28.2929, 137.0236)),
    ]
    target = Pt(45.2534, 121.6506)
    gcs = ghost_candidates(prims, "8A", "84", 1.5875)
    assert not hasattr(gcs, "reason")
    for s, f, c in gcs:
        if go.dist(c, target) < 1e-4:
            side, flip = s, f
            break
    res = place_corner(prims, "8A", "84", side, 1.5875, set(), [], side_flip=flip)
    assert res.ok
    return res.dogbone


def test_rules_folds_corner1_engine_arc_trim_golden():
    """ISSUE-012(d): the SAMPLES.md (44.3930/46.1138) trims were measured
    on the USER's hand-made arc (center (45.2534, 122.1043)); M5 re-derives
    them against the ENGINE arc (center (45.2534, 121.6506), span 180→0).
    Fold y=120.7702 crossings against the engine arc:
      x = 43.9324 / 46.5744 (±0.001)."""
    db = _corner1_engine_db()
    assert abs(db.center.x - 45.2534) < 1e-4 and abs(db.center.y - 121.6506) < 1e-4
    # right-side fold portion: (46.607, 120.7702) extending rightward to
    # (184.4066, 120.7702) — the near endpoint (46.607) is just outside the
    # engine arc's right entry; it extends to (46.5744, 120.7702).
    fold = Seg(eid="FR", a=Pt(46.607, 120.7702), b=Pt(184.4066, 120.7702))
    trims = resolve_folds([fold], [db], {"FR"})
    assert len(trims) == 1
    new_a, _new_b = trims[0].new
    assert abs(new_a.x - 46.5744) < 0.001 and abs(new_a.y - 120.7702) < 1e-9
    assert abs(go.dist(new_a, db.center) - db.r) < 1e-6
    # left-side fold portion: (-46.607, 120.7702) extending leftward — the
    # engine arc is only on the right side (x≈45); the left fold portion
    # has no crossing → no Trim.
    fold_l = Seg(eid="FL", a=Pt(-46.607, 120.7702), b=Pt(-184.4066, 120.7702))
    assert resolve_folds([fold_l], [db], {"FL"}) == []