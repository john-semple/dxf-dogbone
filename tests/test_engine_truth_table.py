"""SPEC §11.5 stray/deletion truth table rows (M2; ADR-009/012/013).

Synthetic 90 deg corner: e1 vertical, e2 horizontal, Side(+1)/flip+1 places
the circle at (1.122532, -1.122532), R = 1.5875 (window = 12.7 mm).
"""
import math

from geometry import geomops as go
from geometry.entities import Arc, Circ, Dogbone, PointEnt, Pt, Seg, Side, TextEnt
from model.model import Model
from model.state import ModelState
from rules.engine import (
    DELETE_MAX_MM,
    arc_crosses_circle,
    fold_circle_intersections,
    place_corner,
)

C_CENTER = Pt(1.122532, -1.122532)
R = 1.5875


def base_prims(extra):
    prims = [
        Seg("e1", Pt(0.0, 0.0), Pt(0.0, -10.0)),
        Seg("e2", Pt(0.0, 0.0), Pt(10.0, 0.0)),
    ]
    prims.extend(extra)
    return prims


def place(prims, **kw):
    return place_corner(
        prims, "e1", "e2", Side(+1), R, kw.pop("folds", set()), kw.pop("dbs", []),
        side_flip=+1, **kw,
    )


def test_engine_truth_table_line_endpoint_in_and_on_circle():
    # At or under DELETE_MAX_MM the whole line is still deleted, including
    # an end that merely lies on the circle (§11.5 row 2, ADR-030).
    epin = Seg("epin", Pt(1.622532, -1.122532), Pt(3.622532, -1.122532))  # len 2
    onc = Seg("oncirc", Pt(1.122532, 0.464968), Pt(1.122532, 1.464968))  # len 1, on circle
    assert go.dist(epin.a, epin.b) <= DELETE_MAX_MM
    assert go.dist(onc.a, onc.b) <= DELETE_MAX_MM
    res = place(base_prims([epin, onc]))
    assert res.ok
    assert "epin" in res.deletions and "oncirc" in res.deletions
    assert not any(f.eid in ("epin", "oncirc") for f in res.flags)


def test_engine_truth_table_long_line_one_end_in_trims_to_circle():
    # Longer than the cap, one end inside: trim that end, keep the rest.
    far = Pt(1.622532 + DELETE_MAX_MM + 0.5, -1.122532)
    long = Seg("long", Pt(1.622532, -1.122532), far)
    assert go.dist(long.a, long.b) > DELETE_MAX_MM
    # Exactly the cap still deletes.
    capped = Seg("capped", Pt(1.622532, -2.122532), Pt(1.622532 + DELETE_MAX_MM, -2.122532))
    assert abs(go.dist(capped.a, capped.b) - DELETE_MAX_MM) < 1e-9
    # Both ends inside, and longer than the cap: the whole segment is in the cut.
    both = Seg("both", Pt(1.122532 - 1.55, -1.122532), Pt(1.122532 + 1.55, -1.122532))
    assert go.dist(both.a, both.b) > DELETE_MAX_MM
    res = place(base_prims([long, capped, both]))
    assert res.ok
    assert "long" not in res.deletions
    assert "capped" in res.deletions and "both" in res.deletions
    assert not any(f.eid == "long" for f in res.flags)
    assert len(res.trims) == 1
    trim = res.trims[0]
    assert trim.eid == "long" and trim.old == (long.a, long.b)
    assert trim.new[1] == far
    assert abs(go.dist(trim.new[0], C_CENTER) - R) < 1e-6
    assert go.dist(trim.new[0], long.a) > 1e-3


def test_engine_truth_table_long_line_on_circle_left_unchanged():
    # End already on the circle, body running away: nothing to cut.
    onc = Seg("oncirc", Pt(1.122532, 0.464968), Pt(6.0, 0.464968))
    assert go.dist(onc.a, onc.b) > DELETE_MAX_MM
    res = place(base_prims([onc]))
    assert res.ok
    assert "oncirc" not in res.deletions
    assert not any(t.eid == "oncirc" for t in res.trims)
    assert not any(f.eid == "oncirc" for f in res.flags)


def test_engine_truth_table_long_line_touching_edge_is_not_cascade_deleted():
    # The inside end lies on the vertical edge, inside the portion that
    # rebuild cuts away. Cascade must not delete the line after the trim.
    long = Seg("long", Pt(0.0, -0.5), Pt(10.0, -0.5))
    res = place(base_prims([long]))
    assert res.ok
    assert "long" not in res.deletions
    assert not any(f.eid == "long" for f in res.flags)
    assert len(res.trims) == 1 and res.trims[0].eid == "long"
    assert res.trims[0].new[1] == long.b
    assert abs(go.dist(res.trims[0].new[0], C_CENTER) - R) < 1e-6


def test_engine_truth_table_long_line_trim_applies():
    far = Pt(1.622532 + DELETE_MAX_MM + 0.5, -1.122532)
    long = Seg("long", Pt(1.622532, -1.122532), far)
    prims = base_prims([long])
    res = place(prims)
    model = Model(ModelState(primitives=list(prims)))
    model.apply_corner(res)
    got = next(e for e in model.state.primitives if isinstance(e, Seg) and e.eid == "long")
    assert got.b == far
    assert abs(go.dist(got.a, C_CENTER) - R) < 1e-6


def test_engine_truth_table_tangent_stray_no_op():
    tangent = Seg("tangent", Pt(-4.0, 0.464968), Pt(6.0, 0.464968))  # touches at top
    res = place(base_prims([tangent]))
    assert res.ok
    assert "tangent" not in res.deletions
    assert not any(f.eid == "tangent" for f in res.flags)


def test_engine_truth_table_chord_crosser_flagged_pending_delete_keep():
    chord = Seg("chord", Pt(-4.0, -1.122532), Pt(6.0, -1.122532))  # through center
    # pending: flag only
    res = place(base_prims([chord]))
    assert res.ok and "chord" not in res.deletions
    fl = {f.eid: f for f in res.flags}["chord"]
    assert fl.reason == "CHORD_CROSSER" and fl.options == frozenset({"delete", "keep"})
    assert fl.decision is None
    # scripted delete
    res2 = place(base_prims([chord]), flag_decisions={"chord": "delete"})
    assert "chord" in res2.deletions
    assert {f.eid: f for f in res2.flags}["chord"].decision == "delete"
    # scripted keep: survives, decision recorded
    res3 = place(base_prims([chord]), flag_decisions={"chord": "keep"})
    assert "chord" not in res3.deletions
    assert {f.eid: f for f in res3.flags}["chord"].decision == "keep"


def test_engine_truth_table_point_delete_only_when_inside():
    pin = PointEnt("pin", Pt(1.0, -1.0))       # dist 0.173 < R
    pout = PointEnt("pout", Pt(5.0, -5.0))     # in window, outside circle
    res = place(base_prims([pin, pout]))
    assert res.ok
    assert "pin" in res.deletions and "pout" not in res.deletions
    assert not any(f.eid in ("pin", "pout") for f in res.flags)


def test_engine_truth_table_arc_endpoint_in_delete_flagged():
    aep = Arc("aep", Pt(2.0, -1.122532), 0.8, 90.0, 270.0)  # endpoints dist 1.186 < R
    res = place(base_prims([aep]))
    assert res.ok
    assert "aep" in res.deletions
    fl = {f.eid: f for f in res.flags}["aep"]
    assert fl.reason == "ARC_ENDPOINT_IN"
    assert fl.options == frozenset({"delete", "keep"})
    assert fl.decision is None
    # scripted keep overrides the table's delete
    res2 = place(base_prims([aep]), flag_decisions={"aep": "keep"})
    assert "aep" not in res2.deletions
    assert {f.eid: f for f in res2.flags}["aep"].decision == "keep"


def test_engine_truth_table_arc_chord_crosser_trim_option():
    # arc dips into the disk near 180 deg; both endpoints outside
    achord = Arc("achord", Pt(2.9, -1.1225), 1.4, 115.0, 245.0)
    res = place(base_prims([achord]))
    assert res.ok and "achord" not in res.deletions
    fl = {f.eid: f for f in res.flags}["achord"]
    assert fl.reason == "CHORD_CROSSER"
    assert fl.options == frozenset({"delete", "keep", "trim"})  # ADR-013
    # scripted trim -> Trim to the kept-side sub-arc (midpoint farther from apex)
    res2 = place(base_prims([achord]), flag_decisions={"achord": "trim"})
    assert len(res2.trims) == 1
    t = res2.trims[0]
    assert t.eid == "achord"
    assert t.old == (115.0, 245.0)
    assert abs(t.new[0] - 238.48) < 0.05 and abs(t.new[1] - 245.0) < 1e-9
    assert "achord" not in res2.deletions
    # scripted delete
    res3 = place(base_prims([achord]), flag_decisions={"achord": "delete"})
    assert "achord" in res3.deletions


def test_engine_truth_table_circle_and_mtext_always_flagged():
    hole = Circ("hole", Pt(2.0, -2.0), 0.5)
    note = TextEnt("mtext", Pt(3.0, -3.0), "NOTES")
    res = place(base_prims([hole, note]))
    assert res.ok
    fl = {f.eid: f for f in res.flags}
    assert fl["hole"].reason == "CIRCLE_IN_WINDOW"
    assert fl["hole"].options == frozenset({"delete", "keep"})
    assert fl["mtext"].reason == "MTEXT_IN_WINDOW"
    assert "hole" not in res.deletions and "mtext" not in res.deletions
    # scripted delete honored for both
    res2 = place(base_prims([hole, note]), flag_decisions={"hole": "delete", "mtext": "delete"})
    assert "hole" in res2.deletions and "mtext" in res2.deletions


def test_engine_truth_table_protected_fold_exempt_and_fold_stub():
    fold = Seg("fold", Pt(-5.0, -1.122532), Pt(5.0, -1.122532))  # crosses the circle
    res = place(base_prims([fold]), folds={"fold"})
    assert res.ok
    assert "fold" not in res.deletions
    assert not any(f.eid == "fold" for f in res.flags)
    fold_trims = [t for t in res.trims if t.eid == "fold"]
    assert len(fold_trims) == 1
    moved = [
        new for new, old in zip(fold_trims[0].new, fold_trims[0].old) if new != old
    ]
    assert moved
    for end in moved:
        assert abs(go.dist(end, C_CENTER) - R) < 1e-4
    # §2 fold stub: intersection points computed for preview only
    xs = fold_circle_intersections(base_prims([fold]), {"fold"}, C_CENTER, R)
    assert len(xs["fold"]) == 2
    got = sorted(p.x for p in xs["fold"])
    assert abs(got[0] - (-0.464968)) < 1e-4 and abs(got[1] - 2.710032) < 1e-4


def test_engine_truth_table_protected_arc_crossing_refuses():
    # overlap fires first for real dogbones; a crafted record with a far
    # center but a crossing placed-arc exercises the §11.5 protected row.
    arc = Arc("pax", Pt(2.5, -1.1225), 1.0, 0.0, 360.0)
    db = Dogbone(
        db_id="db-EXIST",
        apex=Pt(50.0, -50.0),
        center=Pt(50.0, -50.0),
        r=R,
        side=Side(1),
        edge1_eid="far1",
        edge2_eid="far2",
        arc=arc,
    )
    res = place(base_prims([]), dbs=[db])
    assert not res.ok
    assert res.refusals == [
        "PROTECTED_ARC: placed arc pax crosses the dogbone circle"
    ]


def test_engine_arc_crosses_circle_helper():
    crossing = Arc("a", Pt(2.5, -1.1225), 1.0, 0.0, 360.0)
    assert arc_crosses_circle(crossing, C_CENTER, R, 1e-3)
    # tangent circle: single touch does not count
    tangent = Arc("t", Pt(3.710032, -1.122532), 1.0, 0.0, 360.0)  # d == r1 + r2
    assert not arc_crosses_circle(tangent, C_CENTER, R, 1e-3)
    # concentric: no crossing points
    conc = Arc("c", C_CENTER, 2.0, 0.0, 360.0)
    assert not arc_crosses_circle(conc, C_CENTER, R, 1e-3)
