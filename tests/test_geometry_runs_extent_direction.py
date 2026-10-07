"""M2.2 brief item 4 — chain_run canonical direction from the run extent,
snapped to the dominant axis (mathematician's alternating-drift defect).

Two near-vertical members with OPPOSITE micro-drift: each clicked seed's
direction has a different dx SIGN (unit(5e-6, 5) vs unit(-5e-6, 5)), so the
old rule s = "+1 if dx>0 or (dx==0 and dy>0)" minted DIFFERENT canonical
directions — two run eids (promoted-m1 vs promoted-m2) for ONE line.

Fix: s keys off the DOMINANT axis component of the run's extent direction:
|dy| clearly dominant -> sign(dy); |dx| clearly dominant -> sign(dx);
near-tie (|dx| ~ |dy| within EPS_CONSTRUCTION) -> +x preference. Exact-axis
behavior is preserved (vertical-down runs stay bottom-first; the M2.1
promoted-m2 pin must keep passing). Residual (logged): drift at exactly 45deg
can still flip dominance — out of the probed defect class.
"""
import math

import pytest

from geometry.entities import Pt, Seg
from geometry.runs import chain_run
from rules.filters import promoted_edge_at

EPS_C = 1e-9


def seg(eid, a, b):
    return Seg(eid, Pt(*a), Pt(*b))


def drift_prims():
    # alternating micro-drift: m1 drifts +x going up, m2 drifts back to x=0
    return [
        seg("m1", (0.0, 0.0), (5e-6, 5.0)),
        seg("m2", (5e-6, 5.0), (0.0, 10.0)),
    ]


def test_runs_drift_pair_mints_one_eid_from_both_clicks():
    prims = drift_prims()
    r1 = chain_run(prims, prims[0])  # click m1 (dx = +1e-6)
    r2 = chain_run(prims, prims[1])  # click m2 (dx = -1e-6)
    assert r1 is not None and r2 is not None
    run1, ent1 = r1
    run2, ent2 = r2
    assert run1.eid == run2.eid, "alternating-drift run minted two eids"
    assert run1.members == run2.members
    assert ent1 == ent2


def test_runs_drift_pair_vertical_extent_preserved():
    prims = drift_prims()
    run, _ent = chain_run(prims, prims[0])
    # extent is symmetric regardless of canonicalization
    assert abs(run.a.y - 0.0) < 1e-9
    assert abs(run.b.y - 10.0) < 1e-9


def test_runs_exact_vertical_down_stays_bottom_first():
    # M2.1 pin (test_model_apply_corner_microsegmented_run_and_repromotion):
    # vertical-DOWN stored runs canonicalize bottom-up -> promoted-m2.
    prims = [
        seg("m1", (0.0, 0.0), (0.0, -5.0)),
        seg("m2", (0.0, -5.0), (0.0, -10.0)),
    ]
    run, ent = chain_run(prims, prims[0])
    assert run.eid == "promoted-m2"
    assert run.members == ("m2", "m1")


def test_runs_exact_vertical_up_stays_top_first():
    prims = [
        seg("m1", (0.0, 0.0), (0.0, 5.0)),
        seg("m2", (0.0, 5.0), (0.0, 10.0)),
    ]
    run, _ent = chain_run(prims, prims[0])
    assert run.eid == "promoted-m1"
    run2, _ent2 = chain_run(prims, prims[1])
    assert run2.eid == "promoted-m1"


def test_runs_exact_horizontal_unchanged():
    prims = [seg("A", (0.0, 0.0), (10.0, 0.0)), seg("B", (10.0, 0.0), (20.0, 0.0))]
    run, _ent = chain_run(prims, prims[0])
    assert run.eid == "promoted-A" and run.members == ("A", "B")


# --- twin-sync corpus addition (brief: "add it to the twin-sync corpus") ---


@pytest.mark.parametrize("click_y", [1.0, 6.0])
def test_runs_twin_sync_drift_pair(click_y):
    # promoted_edge_at (pick by proximity + chain walk) and the runs walk
    # must agree on the drift pair from clicks on BOTH members.
    prims = drift_prims()
    picked = promoted_edge_at(prims, Pt(2.5e-6, click_y), eps_pick=0.5)
    assert picked is not None
    seed = prims[0] if click_y < 5.0 else prims[1]
    direct = chain_run(prims, seed)
    assert direct is not None
    assert picked.eid == direct[0].eid
    assert picked.members == direct[0].members
    # and the canonical eid is the same whichever member was picked
    other = chain_run(prims, prims[1] if seed is prims[0] else prims[0])
    assert other is not None
    assert other[0].eid == picked.eid