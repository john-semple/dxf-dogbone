"""WORKED-EXAMPLE binding trace — identity block 1-5 (M2 golden fixtures).

Entities mirror the actual before-file storage (handles B8/63/B9/BA; the
WE's "tab-top run" row 3 does not exist in the file — the tab mouth is open;
logged in the M2 session log). Default replay R=1.5875 and golden replay
R=3.175 vs the user's after-file values (SAMPLES.md) within 0.001.
"""
import math

from geometry import geomops as go
from geometry.entities import Pt, Seg, Side
from rules.engine import place_corner


def we_prims():
    return [
        Seg("B8", Pt(45.0, 51.5118), Pt(45.0, -95.0)),          # tab right edge
        Seg("63", Pt(124.7552, 51.5168), Pt(44.2484, 51.5168)),  # body bottom edge
        Seg("B9", Pt(44.2484, 51.5118), Pt(45.0, 51.5118)),     # horizontal tear stub
        Seg("BA", Pt(44.2484, 51.5118), Pt(44.2484, 51.5168)),  # vertical tear stub
    ]


def we_prims_mirror():
    return [
        Seg("B6", Pt(-45.0, -95.0), Pt(-45.0, 51.5118)),
        Seg("B3", Pt(-124.7552, 51.5168), Pt(-44.2484, 51.5168)),
        Seg("B5", Pt(-44.2484, 51.5118), Pt(-45.0, 51.5118)),
        Seg("B4", Pt(-44.2484, 51.5168), Pt(-44.2484, 51.5118)),
    ]


def _arc_point(db, deg):
    return Pt(
        db.center.x + db.r * math.cos(math.radians(deg)),
        db.center.y + db.r * math.sin(math.radians(deg)),
    )


def test_engine_we_default_r_identity_block():
    res = place_corner(
        we_prims(), "B8", "63", Side(-1), 1.5875, set(), [],
        side_flip=+1, flag_decisions={"BA": "delete"},
    )
    assert res.ok
    assert res.refusals == []
    db = res.dogbone

    # identity 1: |c - apex| = R (EPS_CONSTRUCTION)
    assert abs(go.dist(db.center, db.apex) - 1.5875) < 1e-9
    assert abs(db.apex.x - 45.0) < 1e-9 and abs(db.apex.y - 51.5168) < 1e-9

    # acceptance: c = (46.1225, 50.3943); p1 = (45.0, 49.2717) @225;
    #              p2 = (47.2451, 51.5168) @45
    assert abs(db.center.x - 46.122532) < 1e-6
    assert abs(db.center.y - 50.394268) < 1e-6
    rb = {x.eid: x for x in res.rebuilt}
    assert set(rb) == {"B8", "63"}
    assert go.dist(rb["B8"].old, Pt(45.0, 51.5118)) < 1e-9
    assert abs(rb["B8"].new.x - 45.0) < 1e-9
    assert abs(rb["B8"].new.y - 49.271736) < 1e-6
    assert go.dist(rb["63"].old, Pt(44.2484, 51.5168)) < 1e-9
    assert abs(rb["63"].new.x - 47.245064) < 1e-6
    assert abs(rb["63"].new.y - 51.5168) < 1e-9

    # identity 2: p1/p2 unique non-apex intersections (dist = R; apex != them)
    for p in (rb["B8"].new, rb["63"].new):
        assert abs(go.dist(p, db.center) - 1.5875) < 1e-6
        assert go.dist(p, db.apex) > 1.0

    # identity 3: arc endpoints == rebuilt endpoints; apex strictly mid-arc
    assert abs(db.arc.start_deg - 45.0) < 1e-6
    assert abs(db.arc.end_deg - 225.0) < 1e-6
    aa = go.pt_angle_deg(db.center, db.apex)
    assert abs(aa - 135.0) < 1e-6
    assert go.span_contains(db.arc.start_deg, db.arc.end_deg, aa, 1e-9)
    assert go.dist(_arc_point(db, db.arc.start_deg), rb["63"].new) < 1e-6
    assert go.dist(_arc_point(db, db.arc.end_deg), rb["B8"].new) < 1e-6

    # identity 4: kept main-edge interiors do not intersect the circle
    assert not go.seg_interior_hits_disk(rb["B8"].new, Pt(45.0, -95.0), db.center, db.r, 1e-3)
    assert not go.seg_interior_hits_disk(Pt(124.7552, 51.5168), rb["63"].new, db.center, db.r, 1e-3)

    # identity 5: truth table + scripted cascade decision (WE Step 5)
    assert res.deletions == ["B9", "BA"]
    flags = {f.eid: f for f in res.flags}
    assert set(flags) == {"BA"}
    assert flags["BA"].reason == "CASCADE_DANGLING"
    assert flags["BA"].options == frozenset({"delete", "keep"})
    assert flags["BA"].decision == "delete"  # scripted per WE identity #5


def test_engine_we_default_r_cascade_defaults_and_keep_path():
    # default (no scripted decision): cascade still deletes, flag pending
    res = place_corner(we_prims(), "B8", "63", Side(-1), 1.5875, set(), [], side_flip=+1)
    assert res.deletions == ["B9", "BA"]
    flags = {f.eid: f for f in res.flags}
    assert flags["BA"].decision is None

    # scripted "keep": the dangling stub survives
    res2 = place_corner(
        we_prims(), "B8", "63", Side(-1), 1.5875, set(), [],
        side_flip=+1, flag_decisions={"BA": "keep"},
    )
    assert res2.deletions == ["B9"]
    flags2 = {f.eid: f for f in res2.flags}
    assert flags2["BA"].decision == "keep"


def test_engine_we_golden_replay_matches_after_file():
    # R=3.175 golden: c=(47.2451, 49.2717); p1=(45.0, 47.0267);
    # p2=(49.4901, 51.5168); arc 45->225 — within 0.001 of SAMPLES.md
    res = place_corner(
        we_prims(), "B8", "63", Side(-1), 3.175, set(), [],
        side_flip=+1, flag_decisions={"BA": "delete"},
    )
    assert res.ok
    db = res.dogbone
    assert abs(db.center.x - 47.245064) < 1e-6
    assert abs(db.center.y - 49.271736) < 1e-6
    rb = {x.eid: x for x in res.rebuilt}
    # after-file cross-checks (SAMPLES.md): (45.0, 47.0267) / (49.4901, 51.5168)
    assert abs(rb["B8"].new.x - 45.0) < 1e-9 and abs(rb["B8"].new.y - 47.0267) < 0.001
    assert abs(rb["63"].new.x - 49.4901) < 0.001 and abs(rb["63"].new.y - 51.5168) < 1e-9
    assert abs(db.arc.start_deg - 45.0) < 1e-6
    assert abs(db.arc.end_deg - 225.0) < 1e-6
    # golden truth table mirrors the default (B9 endpoint-in; BA cascade)
    assert res.deletions == ["B9", "BA"]


def test_engine_we_mirror_golden_corner3():
    # SAMPLES.md corner 3: c=(-47.2451, 49.2717), rebuilt (-45.0, 47.0267) /
    # (-49.4901, 51.5168), arc span 315->135. The air side is found via
    # ghost_candidates (ADR-015(m): sign/flip depend on stored directions).
    from rules.engine import ghost_candidates

    prims = we_prims_mirror()
    target = Pt(-47.245064, 49.271736)
    gcs = ghost_candidates(prims, "B6", "B3", 3.175)
    assert not hasattr(gcs, "reason")  # not a Refusal
    side, flip = None, None
    for s, f, c in gcs:
        if go.dist(c, target) < 1e-6:
            side, flip = s, f
            break
    assert side is not None, "golden ghost not found"

    res = place_corner(
        prims, "B6", "B3", side, 3.175, set(), [],
        side_flip=flip, flag_decisions={"B4": "delete"},
    )
    assert res.ok
    db = res.dogbone
    assert abs(db.center.x - (-47.245064)) < 1e-6
    assert abs(db.center.y - 49.271736) < 1e-6
    rb = {x.eid: x for x in res.rebuilt}
    assert set(rb) == {"B6", "B3"}
    assert abs(rb["B6"].new.x - (-45.0)) < 1e-9 and abs(rb["B6"].new.y - 47.0267) < 0.001
    assert abs(rb["B3"].new.x - (-49.4901)) < 0.001 and abs(rb["B3"].new.y - 51.5168) < 1e-9
    assert abs(db.arc.start_deg - 315.0) < 1e-6
    assert abs(db.arc.end_deg - 135.0) < 1e-6
    # mirror truth table: B5 endpoint-in; B4 cascade-dangles
    assert res.deletions == ["B5", "B4"]
    flags = {f.eid: f for f in res.flags}
    assert set(flags) == {"B4"} and flags["B4"].reason == "CASCADE_DANGLING"


def test_engine_we_endpoint_uniqueness_both_alternatives():
    # §11.4 post-condition: for each edge BOTH alternatives are computed and
    # exactly one passes the kept-interior test (pinned via the rebuild choice:
    # moving the WRONG endpoint would leave kept interiors inside the disk).
    prims = we_prims()
    res = place_corner(prims, "B8", "63", Side(-1), 1.5875, set(), [], side_flip=+1)
    assert res.ok
    db = res.dogbone
    rb = {x.eid: x for x in res.rebuilt}
    # edge 1 (B8): the moved endpoint is the TOP one (51.5118), not (45, -95)
    assert abs(rb["B8"].old.y - 51.5118) < 1e-9
    # edge 2 (63): the moved endpoint is the EAST one (44.2484), not (124.7552)
    assert abs(rb["63"].old.x - 44.2484) < 1e-9
    # the counterfactual kept segments WOULD hit the disk
    assert go.seg_interior_hits_disk(
        Pt(45.0, 51.5118), rb["B8"].new, db.center, db.r, 1e-3
    )
    assert go.seg_interior_hits_disk(
        Pt(44.2484, 51.5168), rb["63"].new, db.center, db.r, 1e-3
    )
