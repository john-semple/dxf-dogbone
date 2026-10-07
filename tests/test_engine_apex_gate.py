"""rules.engine apex gate — SPEC §11.4 v3 point-to-SEGMENT gate (M2).

T-junction gate fixture is mandatory (§11.4 v3 fix, §11.9): interior apex
passes at 0; overshoot past an end allowed if <= K*R.
"""
from geometry import geomops as go
from geometry.entities import Pt, Seg, Side
from rules.engine import K_OVERSHOOT, apex_proximity_ok, place_corner

B8 = Seg("B8", Pt(45.0, 51.5118), Pt(45.0, -95.0))
E63 = Seg("63", Pt(124.7552, 51.5168), Pt(44.2484, 51.5168))
APEX = Pt(45.0, 51.5168)


def test_engine_gate_worked_example_distances():
    # WORKED-EXAMPLE Step 1: 0.0050 overshoot / 0.0 interior -> pass
    assert apex_proximity_ok(APEX, B8, E63, K_OVERSHOOT, 1.5875)
    d1 = go.point_seg_dist(APEX, B8.a, B8.b)
    d2 = go.point_seg_dist(APEX, E63.a, E63.b)
    assert abs(d1 - 0.0050) < 1e-9
    assert abs(d2 - 0.0) < 1e-9


def test_engine_gate_t_cap_interior_apex_passes_at_zero():
    # T-cap: apex strictly interior to both segments (crossing edges)
    e1 = Seg("e1", Pt(0, 0), Pt(0, -10))
    e2 = Seg("e2", Pt(-5, 0), Pt(10, 0))
    assert apex_proximity_ok(Pt(0, 0), e1, e2, K_OVERSHOOT, 1.5875)


def test_engine_gate_overshoot_over_limit_fails():
    short = Seg("B8s", Pt(45.0, 43.5168), Pt(45.0, -95.0))  # 8.0 overshoot
    assert not apex_proximity_ok(APEX, short, E63, K_OVERSHOOT, 1.5875)


def test_engine_place_corner_apex_gate_refusal_exact_string():
    short = Seg("B8s", Pt(45.0, 43.5168), Pt(45.0, -95.0))
    res = place_corner(
        [short, E63], "B8s", "63", Side(1), 1.5875, set(), []
    )
    assert not res.ok
    assert res.refusals == [
        "APEX_GATE: apex lies 8.0000 from edge B8s and 0.0000 from edge 63; "
        "limit K*R = 7.9375"
    ]


def test_engine_place_corner_same_edge_refusal():
    res = place_corner([B8, E63], "B8", "B8", Side(1), 1.5875, set(), [])
    assert not res.ok
    assert res.refusals == ["SAME_EDGE: both picks reference the same edge"]


def test_engine_place_corner_unknown_edge_refusal():
    res = place_corner([B8, E63], "nope", "63", Side(1), 1.5875, set(), [])
    assert not res.ok
    assert res.refusals == ["UNKNOWN_EDGE: nope is not resolvable in primitives"]
