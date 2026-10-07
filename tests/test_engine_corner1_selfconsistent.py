"""Corner 1 (top, R=1.5875) self-consistent fixture — user decision
2026-10-05: EXCLUDED from after-file replay (the user's arc is a hand-made
tangent-fit relief; zero before-file pairs reproduce it under §11.4 — see
session log 2026-10-05-M2). This fixture replays the REAL before-file corner
(ramps 8A/84 + 5-piece tear pocket, coordinates from the file) through the
engine's own construction and asserts the identity block + pocket cleanup.
"""
from geometry import geomops as go
from geometry.entities import Pt, Seg, Side
from rules.engine import ghost_candidates, place_corner


def corner1_prims():
    # actual before-file entities (handles as in the DXF)
    return [
        Seg("84", Pt(62.2139, 137.0236), Pt(46.9605, 121.7702)),   # +45 deg ramp
        Seg("85", Pt(46.2534, 119.7702), Pt(46.9605, 121.7702)),   # pocket wall E
        Seg("86", Pt(46.2534, 120.5168), Pt(46.2534, 119.7702)),   # pocket east vert
        Seg("87", Pt(44.2534, 120.5168), Pt(46.2534, 120.5168)),   # pocket floor
        Seg("88", Pt(44.2534, 119.7702), Pt(44.2534, 120.5168)),   # pocket west vert
        Seg("89", Pt(43.5463, 121.7702), Pt(44.2534, 119.7702)),   # pocket wall W
        Seg("8A", Pt(43.5463, 121.7702), Pt(28.2929, 137.0236)),   # -45 deg ramp
    ]


def _air_side(prims):
    # the engine's construction puts the center directly above the true apex
    target = Pt(45.2534, 121.6506)
    gcs = ghost_candidates(prims, "8A", "84", 1.5875)
    assert not hasattr(gcs, "reason")
    for s, f, c in gcs:
        if go.dist(c, target) < 1e-4:
            return s, f
    raise AssertionError("air ghost not found")


def test_engine_corner1_true_apex_and_construction():
    prims = corner1_prims()
    side, flip = _air_side(prims)
    res = place_corner(prims, "8A", "84", side, 1.5875, set(), [], side_flip=flip)
    assert res.ok and res.refusals == []
    db = res.dogbone

    # true apex = the ramps' supporting-line intersection (NOT the SAMPLES.md
    # derived circle-bottom (45.2534, 120.5168))
    assert abs(db.apex.x - 45.2534) < 1e-9
    assert abs(db.apex.y - 120.0631) < 1e-9
    # identity 1: |c - apex| = R
    assert abs(go.dist(db.center, db.apex) - 1.5875) < 1e-9
    # 90 deg corner -> 180 deg relief arc through the apex (semicircle)
    assert abs(db.arc.start_deg - 180.0) < 1e-6
    assert abs(go.span_len(db.arc.start_deg, db.arc.end_deg) - 180.0) < 1e-6
    assert db.arc.end_deg in (0.0, 360.0)  # pt_angle normalizes to [0, 360)
    aa = go.pt_angle_deg(db.center, db.apex)
    assert abs(aa - 270.0) < 1e-6  # apex strictly mid-arc
    # rebuilds: the ramps' pocket-facing ends EXTEND to the arc endpoints
    rb = {x.eid: x for x in res.rebuilt}
    assert set(rb) == {"8A", "84"}
    assert abs(rb["8A"].new.x - 43.6659) < 1e-4 and abs(rb["8A"].new.y - 121.6506) < 1e-4
    assert abs(rb["84"].new.x - 46.8409) < 1e-4 and abs(rb["84"].new.y - 121.6506) < 1e-4
    assert abs(rb["8A"].old.y - 121.7702) < 1e-9 and abs(rb["84"].old.y - 121.7702) < 1e-9


def test_engine_corner1_pocket_cleanup_truth_plus_flags():
    prims = corner1_prims()
    side, flip = _air_side(prims)
    # default: pocket floor + verticals have endpoints inside the circle
    # (truth-table delete); the pocket WALLS cross the engine's circle
    # (it cuts 0.4537 deeper than the user's hand-made arc) -> pending
    # chord-crossers, NOT auto-deleted (ADR-016(d): flagged classes never
    # cascade-deleted; ADR-002 amended).
    res = place_corner(prims, "8A", "84", side, 1.5875, set(), [], side_flip=flip)
    assert res.ok
    assert set(res.deletions) == {"86", "87", "88"}
    flags = {f.eid: f for f in res.flags}
    assert set(flags) == {"85", "89"}
    assert all(f.reason == "CHORD_CROSSER" for f in flags.values())
    assert all(f.options == frozenset({"delete", "keep"}) for f in flags.values())
    assert all(f.decision is None for f in flags.values())
    assert res.warnings == []

    # scripted "delete" (the fixture convention mirrors the user's cleaned
    # after-file): the whole pocket goes
    res2 = place_corner(
        prims, "8A", "84", side, 1.5875, set(), [],
        side_flip=flip, flag_decisions={"85": "delete", "89": "delete"},
    )
    assert set(res2.deletions) == {"86", "87", "88", "85", "89"}
    assert {f.eid: f for f in res2.flags}["85"].decision == "delete"

    # scripted "keep" on one wall: it survives, the other goes
    res3 = place_corner(
        prims, "8A", "84", side, 1.5875, set(), [],
        side_flip=flip, flag_decisions={"85": "keep", "89": "delete"},
    )
    assert set(res3.deletions) == {"86", "87", "88", "89"}
    assert "KEPT_CROSSER: kept entity 85 will cross the relief cut" in res3.warnings


def test_engine_corner1_user_arc_not_reproducible_documented():
    # The user's after-file arc (center (45.2534, 122.1043), span 139.21 deg)
    # is tangent to the tear line at (45.2534, 120.5168) and does NOT pass
    # through the true apex — the engine's construction cuts 0.4537 deeper.
    # This test PINS the divergence (user decision 2026-10-05: excluded from
    # replay; M6 maps the user's arc as a residual).
    prims = corner1_prims()
    side, flip = _air_side(prims)
    res = place_corner(prims, "8A", "84", side, 1.5875, set(), [], side_flip=flip)
    db = res.dogbone
    user_center = Pt(45.2534, 122.1043)
    assert go.dist(db.center, user_center) > 0.45  # construction differs
    # the SAMPLES.md "apex" is the user circle's bottom point, not an edge
    # intersection: distance from the true apex is 0.4537
    assert abs(go.dist(Pt(45.2534, 120.5168), db.apex) - 0.4537) < 1e-3
