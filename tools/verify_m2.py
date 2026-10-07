"""M2 corner-local golden gate (CONTRACTS -4; M2 brief item 5).

Per user decision 2026-10-05 (session log 2026-10-05-M2):
  - corners 2/3 (T-junctions, golden R=3.175) replay vs the user's after-file
    values (SAMPLES.md) within 0.001;
  - corner 1 (top, R=1.5875) replays the REAL before-file corner
    self-consistently (the user's arc is a hand-made tangent-fit relief,
    excluded from replay; M6 maps it as a residual).

Consumes dxf_io.load (CONTRACTS -3 API - M1's tested loader; the M2 brief
forbids dxf_io internals, not the API). Golden radii are TEST-ONLY
parameters (SAMPLES.md); the whole-file normalized diff is M6, not here.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dxf_io import load as dxf_load  # noqa: E402
from geometry import geomops as go  # noqa: E402
from geometry.entities import Pt, Refusal  # noqa: E402
from rules.engine import ghost_candidates, place_corner  # noqa: E402

BEFORE = ROOT / "samples" / "base-rectangular-before-AI.DXF"
AFTER = ROOT / "samples" / "base-rectangular - partially radiused.DXF"

TOL = 0.001  # acceptance (SAMPLES.md / SPEC 11.9)

# SAMPLES.md golden blocks (script-printed from the after-file)
C2_GOLD = {
    "center": (47.2451, 49.2717),
    "p_tab": (45.0, 47.0267),     # rebuilt tab-edge endpoint
    "p_body": (49.4901, 51.5168),  # rebuilt body-edge endpoint
    "span": (45.0, 225.0),
    "r": 3.175,
}
C3_GOLD = {
    "center": (-47.2451, 49.2717),
    "p_tab": (-45.0, 47.0267),
    "p_body": (-49.4901, 51.5168),
    "span": (315.0, 135.0),
    "r": 3.175,
}
C1_GOLD = {
    "center": (45.2534, 122.1043),  # user's hand-made arc (excluded; reference only)
    "span": (200.3947, 339.6053),
    "r": 1.5875,
}


def pick_side(prims, e1, e2, r, target):
    gcs = ghost_candidates(prims, e1, e2, r)
    assert not isinstance(gcs, Refusal), gcs.reason if isinstance(gcs, Refusal) else ""
    best = None
    for side, flip, c in gcs:
        d = go.dist(c, Pt(*target))
        if best is None or d < best[0]:
            best = (d, side, flip)
    return best[1], best[2], best[0]


def check(label, got, want, tol=TOL):
    d = abs(got - want)
    assert d <= tol, f"{label}: got {got:.6f}, want {want:.6f} (d={d:.6f} > {tol})"
    return d


def verify_t_junction(name, res, gold, other_body_x):
    assert res.ok, f"{name}: refused: {res.refusals}"
    db = res.dogbone
    check(f"{name} center.x", db.center.x, gold["center"][0])
    check(f"{name} center.y", db.center.y, gold["center"][1])
    assert abs(go.dist(db.center, db.apex) - gold["r"]) < 1e-6
    rb = {x.eid: x for x in res.rebuilt}
    assert len(rb) == 2
    news = [x.new for x in res.rebuilt]
    p_tab = min(news, key=lambda p: abs(p.x - gold["p_tab"][0]) + abs(p.y - gold["p_tab"][1]))
    p_body = max(news, key=lambda p: abs(p.x - gold["p_tab"][0]) + abs(p.y - gold["p_tab"][1]))
    check(f"{name} p_tab.x", p_tab.x, gold["p_tab"][0])
    check(f"{name} p_tab.y", p_tab.y, gold["p_tab"][1])
    check(f"{name} p_body.x", p_body.x, gold["p_body"][0])
    check(f"{name} p_body.y", p_body.y, gold["p_body"][1])
    check(f"{name} span.start", db.arc.start_deg, gold["span"][0])
    # span end may normalize (135.0 == 135.0; 225.0 == 225.0) - compare mod 360
    span_end = db.arc.end_deg % 360.0
    check(f"{name} span.end", span_end, gold["span"][1] % 360.0)
    assert abs(go.span_len(db.arc.start_deg, db.arc.end_deg) - 180.0) < 1e-6
    # apex strictly mid-arc
    aa = go.pt_angle_deg(db.center, db.apex)
    assert go.span_contains(db.arc.start_deg, db.arc.end_deg, aa, 1e-9)
    return db


def main() -> int:
    lines = []

    # pytest pin (M2 brief item 5: assert the pin, don't guess it)
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pins = [l.strip() for l in req.splitlines() if l.strip().startswith("pytest==")]
    assert pins, "requirements.txt: pytest pin missing (M0 brief)"
    lines.append(f"pytest pin: {pins[0]}")

    before = dxf_load(BEFORE)
    after = dxf_load(AFTER)
    prims = before.model_state.primitives
    lines.append(
        f"load: before={len(prims)} entities, after={len(after.model_state.primitives)} entities"
    )

    # after-file golden arcs sanity (SAMPLES.md table)
    arcs = [e for e in after.model_state.primitives if type(e).__name__ == "Arc"]
    assert len(arcs) == 15, f"after-file ARC census: {len(arcs)} != 15"
    for gold in (C1_GOLD, C2_GOLD, C3_GOLD):
        hits = [
            a
            for a in arcs
            if go.dist(a.center, Pt(*gold["center"])) < 1e-3 and abs(a.r - gold["r"]) < 1e-4
        ]
        assert len(hits) == 1, f"golden arc at {gold['center']} not found"
        span = (hits[0].start_deg, hits[0].end_deg)
        assert abs(span[0] - gold["span"][0]) < 1e-3 and abs(span[1] - gold["span"][1]) < 1e-3

    # --- corner 2: right T-junction (tab right edge B8 x body bottom 63) ---
    side, flip, d = pick_side(prims, "B8", "63", C2_GOLD["r"], C2_GOLD["center"])
    assert d < 1e-4, f"corner2: no ghost matches the golden center (d={d:.6f})"
    res2 = place_corner(
        prims, "B8", "63", side, C2_GOLD["r"], set(), [], side_flip=flip
    )
    verify_t_junction("corner2", res2, C2_GOLD, 124.7552)
    # cleanup pin (M2.2 item 1 — the gate-integrity fix): golden-R window
    # occupants are exactly {63, B8, B9, BA}; B9 = LINE endpoint-in-circle
    # (truth-table delete), BA dangles post-rebuild (cascade delete + flag,
    # ADR-016(d)). Exact set, not count — a silently-wrong deletion set can
    # no longer PASS the gate.
    assert set(res2.deletions) == {"B9", "BA"}, f"corner2 deletions: {res2.deletions}"
    fl2 = {f.eid: f for f in res2.flags}
    assert set(fl2) == {"BA"}, f"corner2 flags: {sorted(fl2)}"
    assert fl2["BA"].reason == "CASCADE_DANGLING"
    assert fl2["BA"].options == frozenset({"delete", "keep"})
    assert fl2["BA"].decision is None
    assert res2.warnings == []
    lines.append(
        "corner2 (right T-junction, R=3.175): PASS - center/rebuilt/span vs after-file within 0.001"
        f" [deletions={sorted(res2.deletions)}, flags={sorted(fl2)}]"
    )

    # --- corner 3: left T-junction (mirror) ---
    side, flip, d = pick_side(prims, "B6", "B3", C3_GOLD["r"], C3_GOLD["center"])
    assert d < 1e-4, f"corner3: no ghost matches the golden center (d={d:.6f})"
    res3 = place_corner(
        prims, "B6", "B3", side, C3_GOLD["r"], set(), [], side_flip=flip
    )
    verify_t_junction("corner3", res3, C3_GOLD, -124.7552)
    # cleanup pin: mirror of corner 2 ({B5, B4}; B4 cascade-flagged)
    assert set(res3.deletions) == {"B5", "B4"}, f"corner3 deletions: {res3.deletions}"
    fl3 = {f.eid: f for f in res3.flags}
    assert set(fl3) == {"B4"}, f"corner3 flags: {sorted(fl3)}"
    assert fl3["B4"].reason == "CASCADE_DANGLING"
    assert fl3["B4"].options == frozenset({"delete", "keep"})
    assert fl3["B4"].decision is None
    assert res3.warnings == []
    lines.append(
        "corner3 (left T-junction, R=3.175): PASS - center/rebuilt/span vs after-file within 0.001"
        f" [deletions={sorted(res3.deletions)}, flags={sorted(fl3)}]"
    )

    # --- corner 1: top corner - self-consistent replay (user decision) ---
    # true ramp pair 8A/84; the engine's construction center sits directly
    # above the TRUE apex (45.2534, 120.0631), 0.4537 below the user's arc.
    target = (45.2534, 121.6506)
    side, flip, d = pick_side(prims, "8A", "84", C1_GOLD["r"], target)
    assert d < 1e-4, f"corner1: no ghost matches the engine center (d={d:.6f})"
    res1 = place_corner(
        prims, "8A", "84", side, C1_GOLD["r"], set(), [], side_flip=flip,
        flag_decisions={"85": "delete", "89": "delete"},
    )
    assert res1.ok, f"corner1 refused: {res1.refusals}"
    db1 = res1.dogbone
    # expectations carry the DXF's stored precision vs the 4-decimal docs - TOL
    check("corner1 center.x", db1.center.x, target[0])
    check("corner1 center.y", db1.center.y, target[1])
    assert abs(go.dist(db1.center, db1.apex) - C1_GOLD["r"]) < 1e-9
    check("corner1 apex.y", db1.apex.y, 120.0631)
    assert abs(go.span_len(db1.arc.start_deg, db1.arc.end_deg) - 180.0) < 1e-6
    rb1 = {x.eid: x for x in res1.rebuilt}
    assert set(rb1) == {"8A", "84"}
    for eid, ex in (("8A", 43.6659), ("84", 46.8409)):
        assert abs(rb1[eid].new.x - ex) < 1e-3, f"corner1 rebuild {eid}"
        assert abs(rb1[eid].new.y - 121.6506) < 1e-3
    # pocket cleanup: floor + verticals truth-table deleted; the walls cross
    # the ENGINE circle (deeper than the user's arc) -> pending chord-crossers
    # deleted via the scripted decision (ADR-016(d); mirrors the after-file).
    # M2.2 item 1: exact SET pin + the decided flags stay present per
    # ADR-016(d) (decided flags are never dropped from CornerResult.flags);
    # warnings must be empty under valid scripted decisions.
    assert set(res1.deletions) == {"85", "86", "87", "88", "89"}
    fl1 = {f.eid: f for f in res1.flags}
    assert set(fl1) == {"85", "89"}, f"corner1 flags: {sorted(fl1)}"
    assert all(f.reason == "CHORD_CROSSER" for f in fl1.values())
    assert all(f.decision == "delete" for f in fl1.values())
    assert all(f.options == frozenset({"delete", "keep"}) for f in fl1.values())
    assert res1.warnings == []
    # documented divergence from the user's hand-made arc (>= 0.45 mm)
    div = go.dist(db1.center, Pt(*C1_GOLD["center"]))
    assert div > 0.45, f"corner1: expected divergence from user arc, got {div:.6f}"
    lines.append(
        "corner1 (top, R=1.5875): PASS - self-consistent construction; "
        "tear pocket fully cleaned (85-89); user arc EXCLUDED per 2026-10-05 "
        f"decision (divergence {div:.4f} mm; M6 residual)"
    )

    print("M2 corner-local golden gate")
    for l in lines:
        print("  " + l)
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
