"""M2.2 brief item 2 — adjacency pairing metric is Euclidean (persona-review
defect: box-proximity overcounts by sqrt(2) vs the cascade's point_seg_dist).

Two entities meeting at a diagonal offset (d, d) with d = sqrt(2)*eps/2 are
adjacent under the box metric (|d| <= eps per axis) but NOT under Euclidean
(hypot(d, d) = eps boundary, held strictly outside in fp). The cascade must
not count such a pair as a remaining attached neighbor.
"""
import math

from geometry.adjacency import build_adjacency
from geometry.entities import Pt, Seg, Side
from rules.engine import place_corner

EPS = 1e-3


def seg(eid, a, b):
    return Seg(eid, Pt(*a), Pt(*b))


def test_adjacency_box_overcount_diagonal_now_non_adjacent():
    # brief's exact offset: both components d = sqrt(2)*eps/2 — hypot(d, d)
    # lands at the eps boundary (1.0000000000000002e-3 in double arithmetic),
    # strictly outside; box metric admits it (per-axis |d| <= eps).
    d = math.sqrt(2.0) * EPS / 2.0
    prims = [
        seg("e1", (0.0, 0.0), (10.0, 0.0)),
        seg("e2", (10.0 + d, d), (20.0, d)),
    ]
    adj = build_adjacency(prims, EPS)
    assert "e2" not in adj.get("e1", frozenset())

    # robust interior-diagonal case: both offsets (0.75*eps, 0.75*eps) —
    # hypot = 1.06*eps > eps clearly; box admits (both |dx|,|dy| <= eps)
    t = 0.75 * EPS
    prims = [
        seg("e1", (0.0, 0.0), (10.0, 0.0)),
        seg("e2", (10.0 + t, t), (20.0, t)),
    ]
    adj = build_adjacency(prims, EPS)
    assert "e2" not in adj.get("e1", frozenset())


def test_adjacency_euclidean_and_box_agree_on_axis_and_45deg():
    # on-axis offset exactly eps/2: adjacent under BOTH metrics
    prims = [
        seg("e1", (0.0, 0.0), (10.0, 0.0)),
        seg("e2", (10.0 + EPS / 2.0, 0.0), (20.0, 0.0)),
    ]
    adj = build_adjacency(prims, EPS)
    assert "e2" in adj.get("e1", frozenset())
    # 45-deg offset with hypot < eps (d = eps/2 each): adjacent under both
    d = EPS / 2.0 / math.sqrt(2.0)
    prims = [
        seg("e1", (0.0, 0.0), (10.0, 0.0)),
        seg("e2", (10.0 + d, d), (20.0, d)),
    ]
    adj = build_adjacency(prims, EPS)
    assert "e2" in adj.get("e1", frozenset())


def test_cascade_no_longer_counts_diagonal_attachment():
    # E1 (horizontal) x E2 (vertical) 90-deg corner at the origin; dogbone
    # circle center (0.7071, -0.7071), r=1. E2's removed portion runs
    # (0, 5) -> (0, -1.4142): TEAM's near endpoint (0, 0.1) lies ON it
    # (cascade candidate). TEAM's FAR endpoint contacts the protected fold
    # SURV diagonally at offset (0.75*eps, 0.75*eps) — box-adjacent (a
    # "remaining attached neighbor" pre-fix, TEAM survives), Euclidean-NOT
    # (post-fix TEAM dangles -> deleted + flagged).
    t = 0.75 * EPS
    prims = [
        seg("E1", (0.0, 0.0), (10.0, 0.0)),
        seg("E2", (0.0, 5.0), (0.0, -10.0)),
        seg("TEAM", (0.0, 0.1), (-2.0, 0.1)),
        seg("SURV", (-2.0 + t, 0.1 + t), (-2.0 + t, 2.0)),  # fold: protected
    ]
    res = place_corner(
        prims, "E1", "E2", Side(+1), 1.0, {"SURV"}, [], side_flip=+1
    )
    assert res.ok, res.refusals
    assert "SURV" not in res.deletions  # protected fold
    assert "TEAM" in res.deletions  # dangles once diagonal contact no longer counts
    flags = {f.eid: f for f in res.flags}
    assert flags["TEAM"].reason == "CASCADE_DANGLING"