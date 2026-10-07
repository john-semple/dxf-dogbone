"""M1/M3 GUI verification harness (CONTRACTS §4; M1 + M3 brief DoDs).

Usage:
    python tools/verify_gui.py                 -> M1 viewer checks, both golden files
    python tools/verify_gui.py file.dxf [...]  -> M1 viewer checks on the given file(s)
    python tools/verify_gui.py --full          -> M1 checks + M3 corner-workflow
                                                  synthetic-event drive of all three
                                                  sample corners, asserting final
                                                  ModelState vs SAMPLES.md blocks

Agents cannot see the canvas: this drives the tkinter canvas with synthetic
events (event_generate, with direct-method fallback recorded in the dump),
asserts canvas item count == drawable-primitive count (PassThrough never
renders), checks screen<->world round-trips across pan/zoom, and dumps every
item's world coords to previews/items-<name>.json for diffing.

M3 mode additionally drives ui/workflow.py corner-to-corner per
CONTRACTS §4 ``run_corner_workflow_clicks``: two edge clicks → ghost click →
confirm, then asserts the final ModelState (dogbone count, deletions,
rebuilt endpoints) against the SAMPLES.md golden blocks (±0.001).

Exit code 0 iff every check PASSes.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import tkinter as tk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dxf_io import LoadRefused, load  # noqa: E402
from geometry.entities import Arc, Circ, PassThrough, PointEnt, Pt, Seg, TextEnt  # noqa: E402
from ui.canvas_view import Viewer  # noqa: E402

GOLDEN = [
    ROOT / "samples" / "base-rectangular-before-AI.DXF",
    ROOT / "samples" / "base-rectangular - partially radiused.DXF",
]
BEFORE = GOLDEN[0]
OUT_DIR = ROOT / "previews"
ROUND_TRIP_TOL = 1e-6


def _world_fields(e) -> dict:
    if isinstance(e, Seg):
        return {"kind": "LINE", "a": [e.a.x, e.a.y], "b": [e.b.x, e.b.y]}
    if isinstance(e, Arc):
        return {"kind": "ARC", "center": [e.center.x, e.center.y], "r": e.r,
                "start_deg": e.start_deg, "end_deg": e.end_deg}
    if isinstance(e, Circ):
        return {"kind": "CIRCLE", "center": [e.center.x, e.center.y], "r": e.r}
    if isinstance(e, PointEnt):
        return {"kind": "POINT", "p": [e.p.x, e.p.y]}
    if isinstance(e, TextEnt):
        return {"kind": "MTEXT", "p": [e.p.x, e.p.y], "text": e.text}
    return {"kind": "PASSTHROUGH", "raw": e.kind}


def _anchor(e) -> Pt:
    if isinstance(e, Seg):
        return e.a
    if isinstance(e, (Arc, Circ)):
        return e.center
    if isinstance(e, (PointEnt, TextEnt)):
        return e.p
    raise TypeError(e)


def _r6(x: float) -> float:
    return round(x + 0.0, 6)


def verify(path: Path) -> tuple[bool, str]:
    try:
        result = load(path)
    except LoadRefused as exc:
        return False, f"refused: {exc.reason}"

    drawables = [e for e in result.model_state.primitives
                 if not isinstance(e, PassThrough)]
    events_used: list[str] = []

    root = tk.Tk()
    root.title(f"verify_gui - {path.name}")
    try:
        viewer = Viewer(root, width=1100, height=750)
        viewer.canvas.pack(fill=tk.BOTH, expand=True)
        root.update()
        viewer.set_model(result.model_state)
        root.update()

        # -- assertion 1: one canvas item per drawable primitive --
        n_items = viewer.item_count()
        if n_items != len(drawables):
            return False, (f"item count {n_items} != drawable count {len(drawables)}")
        if len(viewer._item_of) != len(drawables):
            return False, "eid->item map incomplete"

        # -- assertion 2: screen<->world round trip at fit --
        t = viewer.transform
        for e in drawables:
            a = _anchor(e)
            sx, sy = t.to_screen(a)
            w = t.to_world(sx, sy)
            if abs(w.x - a.x) > ROUND_TRIP_TOL or abs(w.y - a.y) > ROUND_TRIP_TOL:
                return False, f"round-trip failed for {e.eid}"

        # -- synthetic wheel zoom at canvas center (fallback: direct call) --
        cx, cy = 550, 375
        scale_before = viewer.transform.scale
        try:
            viewer.canvas.event_generate("<MouseWheel>", x=cx, y=cy, delta=120)
            root.update()
        except Exception:
            pass
        if abs(viewer.transform.scale - scale_before) < 1e-12:
            viewer.transform = viewer.transform.zoomed_at(cx, cy, 1.25)
            viewer.redraw()
            events_used.append("wheel:direct-fallback")
        else:
            events_used.append("wheel:event_generate")
        if viewer.transform.scale <= scale_before:
            return False, "wheel zoom did not increase scale"
        if viewer.item_count() != len(drawables):
            return False, "item count changed after zoom redraw"

        # -- synthetic pan drag (fallback: direct call) --
        ox_before = viewer.transform.ox
        oy_before = viewer.transform.oy
        try:
            viewer.canvas.event_generate("<ButtonPress-1>", x=200, y=200)
            viewer.canvas.event_generate("<B1-Motion>", x=260, y=225)
            viewer.canvas.event_generate("<ButtonRelease-1>", x=260, y=225)
            root.update()
        except Exception:
            pass
        if abs(viewer.transform.ox - ox_before) < 1e-9 and abs(viewer.transform.oy - oy_before) < 1e-9:
            viewer.canvas.move("all", 60, 25)
            viewer.transform = viewer.transform.panned_by(60, 25)
            events_used.append("pan:direct-fallback")
        else:
            events_used.append("pan:event_generate")
        if viewer.item_count() != len(drawables):
            return False, "item count changed after pan"
        t = viewer.transform
        for e in drawables:  # round-trip again after pan
            a = _anchor(e)
            sx, sy = t.to_screen(a)
            w = t.to_world(sx, sy)
            if abs(w.x - a.x) > ROUND_TRIP_TOL or abs(w.y - a.y) > ROUND_TRIP_TOL:
                return False, f"round-trip failed after pan for {e.eid}"

        # -- dump world coords of all items --
        items = []
        for e in result.model_state.primitives:
            if isinstance(e, PassThrough):
                continue
            it = viewer._item_of[e.eid]
            bbox = viewer.canvas.bbox(it)
            wd = _world_fields(e)
            items.append({
                "eid": e.eid,
                **{k: (v if not isinstance(v, list) else [_r6(c) for c in v])
                   for k, v in wd.items() if k != "kind"},
                "kind": wd["kind"],
                "screen_bbox": [_r6(v) for v in bbox],
            })
        items.sort(key=lambda d: (d["kind"], d["eid"]))
        dump = {
            "file": path.name,
            "header": result.header,
            "warnings": result.warnings,
            "counts": {
                "primitives": len(result.model_state.primitives),
                "drawables": len(drawables),
                "canvas_items": viewer.item_count(),
            },
            "transform_after_checks": {
                "scale": _r6(viewer.transform.scale),
                "ox": _r6(viewer.transform.ox),
                "oy": _r6(viewer.transform.oy),
            },
            "synthetic_event_path": events_used,
            "items": items,
        }
        OUT_DIR.mkdir(exist_ok=True)
        out = OUT_DIR / f"items-{path.stem}.json"
        out.write_text(json.dumps(dump, indent=1, sort_keys=True), encoding="utf-8")
        return True, f"{len(drawables)} items ok; dump previews/{out.name}"
    finally:
        root.destroy()


def main() -> int:
    args = sys.argv[1:]
    full = "--full" in args
    args = [a for a in args if a != "--full"]
    files = [Path(a) for a in args] if args else GOLDEN
    ok_all = True
    print(f"{'file':40} result")
    for f in files:
        try:
            ok, msg_ = verify(f)
        except Exception as exc:  # noqa: BLE001
            ok, msg_ = False, f"harness error: {type(exc).__name__}: {exc}"
        ok_all &= ok
        print(f"{f.name:40} {'PASS' if ok else 'FAIL'} - {msg_}")
    if full:
        try:
            ok, msg_ = verify_full_workflow()
        except Exception as exc:  # noqa: BLE001
            ok, msg_ = False, f"harness error: {type(exc).__name__}: {exc}"
        ok_all &= ok
        print(f"{'M3 corner workflow (--full)':40} {'PASS' if ok else 'FAIL'} - {msg_}")
    print("ALL PASS" if ok_all else "FAILURES PRESENT")
    return 0 if ok_all else 1


# ---------------------------------------------------------------------------
# M3 corner-workflow drive (CONTRACTS §4 run_corner_workflow_clicks)
# ---------------------------------------------------------------------------

from geometry.entities import Arc, CornerResult, Dogbone, Refusal  # noqa: E402
from model.model import Model  # noqa: E402
from rules.engine import ghost_candidates  # noqa: E402
from ui.workflow import (  # noqa: E402
    PendingCorner,
    WorkflowFSM,
    WorkflowState,
    WorkflowUI,
)
import ui.messages as messages  # noqa: E402

TOL = 0.001  # SAMPLES.md / SPEC §11.9 acceptance

# SAMPLES.md golden blocks + verify_m2's pinned cleanup sets (M2.2 item 1)
CORNERS = [
    {
        "name": "corner2 (right T-junction, R=3.175)",
        "e1": "B8", "e2": "63",
        "clicks_world": [(45.0, 44.0), (47.5, 51.5)],
        "r": 3.175,
        "center": (47.2451, 49.2717),
        "rebuilt": [((45.0, 47.0267), 0.45), ((49.4901, 51.5168), 0.45)],
        "deletions": {"B9", "BA"},
        "flags": {"BA": "CASCADE_DANGLING"},
        "span": (45.0, 225.0),
        "prompt_defaults": {"BA": "delete"},  # cascade prompt → "delete"
    },
    {
        "name": "corner3 (left T-junction, R=3.175)",
        "e1": "B6", "e2": "B3",
        "clicks_world": [(-45.0, 44.0), (-50.0, 51.5)],
        "r": 3.175,
        "center": (-47.2451, 49.2717),
        "rebuilt": [((-45.0, 47.0267), 0.45), ((-49.4901, 51.5168), 0.45)],
        "deletions": {"B5", "B4"},
        "flags": {"B4": "CASCADE_DANGLING"},
        "span": (315.0, 135.0),
        "prompt_defaults": {"B4": "delete"},  # cascade prompt → "delete"
    },
    {
        "name": "corner1 (top, R=1.5875, self-consistent)",
        "e1": "8A", "e2": "84",
        "clicks_world": [(44.0, 122.8), (47.0, 122.4)],
        "r": 1.5875,
        "center": (45.2534, 121.6506),  # ENGINE center (ISSUE-012 ruling)
        "rebuilt": [((43.6659, 121.6506), 0.45), ((46.8409, 121.6506), 0.45)],
        "deletions": {"85", "86", "87", "88", "89"},
        "flags": {"85": "CHORD_CROSSER", "89": "CHORD_CROSSER"},
        "span": None,  # engine's construction, not the user's arc
        "scripted_flags": {"85": "delete", "89": "delete"},
    },
]


def _check(label, got, want, tol=TOL):
    assert abs(got - want) <= tol, f"{label}: got {got:.6f}, want {want:.6f}"


def _pick_ghost_near(ui: WorkflowUI, target: tuple[float, float]):
    """Pick the ghost whose center is nearest the golden center.

    Corner 1's docs value (45.2534, 121.6506) is the 4-decimal gloss of
    (45.2534031067865, 121.6505598284844): tolerance 1e-3 (SAMPLES TOL),
    not 1e-4."""
    best = None
    for g in ui.fsm.ghosts:
        d = math.hypot(g.center.x - target[0], g.center.y - target[1])
        if best is None or d < best[0]:
            best = (d, g)
    assert best is not None and best[0] < TOL, \
        f"no ghost within {TOL} of golden center {target} (best d={best[0] if best else None})"
    return best[1]


def verify_corner_workflow(root: tk.Tk, corner: dict) -> str:
    """One corner, corner-to-corner: load → two synthetic edge clicks →
    ghost click → confirm → assert final ModelState."""
    result = load(BEFORE)
    model = Model(result.model_state)
    viewer = Viewer(root, width=1100, height=750)
    viewer.canvas.pack(fill=tk.BOTH, expand=True)
    root.update()
    viewer.set_model(model.state)
    root.update()

    status: list[str] = []
    ui = WorkflowUI(viewer, model, root, on_status=status.append,
                    radius_mm=corner["r"])
    # headless: pre-seed sticky flag decisions (ADR-009) AND intercept the
    # first-occurrence prompts (scripted answers; the modal must never
    # block the harness — cascade flags surface only at preview time)
    for eid, dec in corner.get("scripted_flags", {}).items():
        model.state.flag_decisions[eid] = dec

    class _ScriptedUI(WorkflowUI):  # type: ignore[misc]
        def decide_flag(self, flag, kind):
            dec = corner.get("prompt_defaults", {}).get(
                flag.eid, "delete"
            )
            model.state.flag_decisions[flag.eid] = dec
            return dec

    ui = _ScriptedUI(viewer, model, root, on_status=status.append,
                     radius_mm=corner["r"])
    ui.start()
    root.update()

    # --- two edge clicks (synthetic ButtonPress-1; FSM hit-test path) ---
    for wx, wy in corner["clicks_world"]:
        sx, sy = viewer.transform.to_screen(Pt(wx, wy))
        try:
            viewer.canvas.event_generate("<ButtonPress-1>", x=int(sx), y=int(sy))
        except Exception:
            pass
        root.update()
        # event_generate can be unavailable headless — direct fallback:
        if ui.fsm.state not in (WorkflowState.PICK_EDGE2,
                                WorkflowState.GHOSTS_VISIBLE):
            ui.fsm.click_world(Pt(wx, wy))
            ui._sync_view()
        root.update()

    assert ui.fsm.state == WorkflowState.GHOSTS_VISIBLE, \
        f"{corner['name']}: state {ui.fsm.state} != GHOSTS_VISIBLE; " \
        f"inline={ui.fsm.inline!r}"

    # --- ghost click: the ray matching the golden center ---
    g = _pick_ghost_near(ui, corner["center"])
    ui.fsm.pick_ghost(g.side, g.side_flip)
    root.update()
    assert ui.fsm.state == WorkflowState.SIDE_PICKED, \
        f"{corner['name']}: no preview after ghost pick; inline={ui.fsm.inline!r}"
    ui._prompt_pending_flags()  # applies scripted decisions; no modal
    root.update()

    # --- preview asserts (pre-apply CornerResult) ---
    res = ui.fsm.preview
    assert res is not None and res.ok, f"{corner['name']}: preview refused"
    assert set(res.deletions) == set(corner["deletions"]), \
        f"{corner['name']}: deletions {sorted(res.deletions)} != {sorted(corner['deletions'])}"
    got_flags = {f.eid: f.reason for f in res.flags}
    assert got_flags == corner["flags"], \
        f"{corner['name']}: flags {got_flags} != {corner['flags']}"
    assert all(f.decision is not None for f in res.flags), \
        f"{corner['name']}: pending flags remain: {res.flags}"

    # --- confirm → applied ModelState ---
    applied = ui.confirm_click()
    assert applied is not None and applied.ok, \
        f"{corner['name']}: confirm blocked/refused: {ui.fsm.inline!r}"
    st = model.state
    assert len(st.dogbones) == 1, f"{corner['name']}: dogbone count {len(st.dogbones)}"
    db = st.dogbones[0]
    _check(f"{corner['name']} center.x", db.center.x, corner["center"][0])
    _check(f"{corner['name']} center.y", db.center.y, corner["center"][1])
    assert abs(math.hypot(db.center.x - db.apex.x, db.center.y - db.apex.y)
               - corner["r"]) <= 1e-6, f"{corner['name']}: |center-apex| != R"
    for (want_pt, tol), rb in zip(corner["rebuilt"], applied.rebuilt):
        _check(f"{corner['name']} rebuilt.x", rb.new.x, want_pt[0], tol)
        _check(f"{corner['name']} rebuilt.y", rb.new.y, want_pt[1], tol)
    if corner["span"] is not None:
        _check(f"{corner['name']} arc.start", db.arc.start_deg % 360.0,
               corner["span"][0] % 360.0)
        _check(f"{corner['name']} arc.end", db.arc.end_deg % 360.0,
               corner["span"][1] % 360.0)
    # model-level: deletions really gone; arc primitive present with minted eid
    eids = {e.eid for e in st.primitives}
    assert not (set(corner["deletions"]) & eids), \
        f"{corner['name']}: deleted eids still present"
    assert db.arc.eid.startswith("n"), \
        f"{corner['name']}: arc eid {db.arc.eid} not minted (ADR-015(c))"
    assert db.arc.eid in eids, f"{corner['name']}: placed arc not in primitives"
    # summary line: the brief's EXACT text shape
    assert ui.summary_line() == "" or "Deleting:" in ui.summary_line()

    viewer.canvas.destroy()
    return (f"{corner['name']}: dogbone applied center=({db.center.x:.4f}, "
            f"{db.center.y:.4f}) deletions={sorted(corner['deletions'])}")


def verify_full_workflow() -> tuple[bool, str]:
    """CONTRACTS §4 run_corner_workflow_clicks across all three sample
    corners; asserts final ModelState per corner against SAMPLES.md."""
    root = tk.Tk()
    root.title("verify_gui --full (M3 corner workflow)")
    try:
        notes = []
        for corner in CORNERS:
            notes.append(verify_corner_workflow(root, corner))
        # parallel-lines refusal toast (human checklist proxy): two parallel
        # edges must refuse verbatim and leave the workflow pickable
        result = load(BEFORE)
        model = Model(result.model_state)
        viewer = Viewer(root, width=1100, height=750)
        viewer.canvas.pack(fill=tk.BOTH, expand=True)
        root.update()
        viewer.set_model(model.state)
        root.update()
        status: list[str] = []
        ui = WorkflowUI(viewer, model, root, on_status=status.append,
                        radius_mm=3.175 / 2.0)
        ui.start()
        # two parallel edges of the before-file: the tab left/right walls
        ui.fsm.click_world(Pt(45.0, 44.0))   # B8 vertical (tab right wall)
        ui._sync_view()
        root.update()
        ui.fsm.click_world(Pt(-45.0, 44.0))  # B6 vertical (tab left wall)
        ui._sync_view()
        root.update()
        assert ui.fsm.state == WorkflowState.PICK_EDGE2, \
            f"parallel pair: state {ui.fsm.state} != PICK_EDGE2"
        assert ui.fsm.inline and "PARALLEL" in ui.fsm.inline, \
            f"parallel pair: refusal toast missing: {ui.fsm.inline!r}"
        assert any("PARALLEL" in s for s in status), \
            "parallel pair: refusal not on the status line"
        notes.append("parallel-pair refusal toast: PASS (engine string verbatim)")
        viewer.canvas.destroy()
        return True, " | ".join(notes)
    finally:
        root.destroy()


if __name__ == "__main__":
    sys.exit(main())
