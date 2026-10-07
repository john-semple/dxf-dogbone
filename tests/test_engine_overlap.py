"""Dogbone overlap — SPEC §11.2/§11.7: strict with EPS_COINCIDE, tangent
circles allowed; refused second dogbone lists the reason in refusals."""
from geometry.entities import Pt, Seg, Side
from rules.engine import place_corner


def _corner_a_prims():
    return [
        Seg("e1", Pt(0.0, 0.0), Pt(0.0, -10.0)),
        Seg("e2", Pt(0.0, 0.0), Pt(3.0, 0.0)),  # short: no overlap with corner B's e4
    ]


def _corner_b_prims(dx):
    # corner B sits one R-span east; its e4 starts at x=3.175+dx (gap to
    # e2's end at 3.0 keeps the runs separate — overlapping collinear
    # segments are a degenerate fixture the first-wins pick would reject)
    return _corner_a_prims() + [
        Seg("e3", Pt(3.175 + dx, 5.0), Pt(3.175 + dx, -10.0)),
        Seg("e4", Pt(3.175 + dx, 0.0), Pt(13.175 + dx, 0.0)),
    ]


def test_engine_overlap_tangent_circles_allowed():
    res_a = place_corner(_corner_a_prims(), "e1", "e2", Side(+1), 1.5875, set(), [], side_flip=+1)
    assert res_a.ok
    # centers exactly 2R apart (tangent) -> allowed
    res_b = place_corner(
        _corner_b_prims(0.0), "e3", "e4", Side(+1), 1.5875, set(), [res_a.dogbone],
        side_flip=+1,
    )
    assert res_b.ok
    assert res_b.refusals == []


def test_engine_overlap_strict_refusal_exact_string():
    res_a = place_corner(_corner_a_prims(), "e1", "e2", Side(+1), 1.5875, set(), [], side_flip=+1)
    assert res_a.ok
    # 0.01 closer than tangent -> strict overlap refusal
    res_b = place_corner(
        _corner_b_prims(-0.01), "e3", "e4", Side(+1), 1.5875, set(), [res_a.dogbone],
        side_flip=+1,
    )
    assert not res_b.ok
    assert res_b.refusals == [
        "OVERLAP: dogbone circle overlaps existing dogbone db-e1+e2 "
        "(strict with EPS_COINCIDE; tangent circles are allowed)"
    ]
