"""ADR-032 — fold first-hit on throat wall; throat-vs-protected overlap."""
from __future__ import annotations

import math

from geometry import geomops as go
from geometry.entities import Arc, Dogbone, Pt, Refusal, Seg, Side
from geometry.tolerances import EPS_COINCIDE
from rules.engine import ghost_candidates, place_corner
from rules.folds import resolve_folds
from tests.test_rules_entry_widen_geometry import R, _acute_notch


def test_rules_entry_widen_fold_first_hit_on_throat_wall():
    from tests.test_rules_entry_widen_geometry import _place_air

    prims, _apex = _acute_notch(40.0)
    res = _place_air(prims)
    assert res.ok and res.dogbone is not None and res.dogbone.throat is not None
    db = res.dogbone
    # vertical fold crossing the upper throat wall (walls // +x at y = 50±R)
    th = max(db.throat, key=lambda s: s.a.y)
    mid_x = 0.5 * (th.a.x + th.b.x)
    fold = Seg(
        "fold",
        Pt(mid_x, th.a.y + 10.0),
        Pt(mid_x, th.a.y - 10.0),
    )
    prims2 = list(prims) + [fold]
    trims = resolve_folds(prims2, [db], {"fold"}, EPS_COINCIDE)
    assert len(trims) == 1
    new_a, new_b = trims[0].new
    hit = new_a if abs(new_a.y - th.a.y) < 1e-4 else new_b
    assert abs(hit.y - th.a.y) < 1e-4
    assert abs(hit.x - mid_x) < 1e-4
    assert go.point_seg_dist(hit, th.a, th.b) <= EPS_COINCIDE


def test_rules_entry_widen_throat_overlap_refuses():
    """Planned throat crossing another dogbone's arc → THROAT_OVERLAP refuse."""
    prims, apex = _acute_notch(40.0)
    gcs = ghost_candidates(prims, "e1", "e2", R)
    assert not isinstance(gcs, Refusal)
    picks = [(s, f, c) for s, f, c in gcs if c.x > apex.x]
    side, flip, center = picks[0]

    alpha = math.radians(18.43494882)
    q_depth = R / math.tan(alpha)
    wall_x = 90.0 + 0.5 * (R + q_depth)
    wall_y = 50.0 + R
    on_wall = Dogbone(
        db_id="db-block",
        apex=Pt(wall_x, wall_y + 1.0),
        center=Pt(wall_x, wall_y),
        r=0.4,
        side=Side(1),
        edge1_eid="bx",
        edge2_eid="by",
        arc=Arc("block-arc", Pt(wall_x, wall_y), 0.4, 0.0, 360.0),
    )
    assert go.dist(center, on_wall.center) >= R + 0.4 - EPS_COINCIDE
    res = place_corner(
        prims, "e1", "e2", side, R, set(), [on_wall], side_flip=flip
    )
    assert not res.ok
    assert any(r.startswith("THROAT_OVERLAP:") for r in res.refusals)
