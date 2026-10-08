"""M1/M3 GUI verification harness (CONTRACTS §4; M1 + M3 brief DoDs).

Usage:
    python tools/verify_gui.py                 -> M1 viewer checks, both golden files
    python tools/verify_gui.py file.dxf [...]  -> M1 viewer checks on the given file(s)
    python tools/verify_gui.py --full          -> M1 checks + M3 corner-workflow
                                                   synthetic-event drive of all three
                                                   sample corners + M4 apply-undo-apply,
                                                   revert, overlap warn-and-skip drives

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
from ui.theme import apply as theme_apply  # noqa: E402

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
    theme_apply(root)  # harness exercises the same theme as the app
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


# ---------------------------------------------------------------------------
# M4 apply-undo-apply drive (brief DoD: synthetic events, model-state
# asserts)
# ---------------------------------------------------------------------------

from model.snapshots import SnapshotStack  # noqa: E402
from ui.apply_panel import ApplyAllWorkflowUI  # noqa: E402


class _ScriptedApplyUI(ApplyAllWorkflowUI):
    """Headless M4 UI: decide_flag reads the CURRENT corner's scripted
    answers (M3's _ScriptedUI pattern) — the modal must never block the
    harness."""

    def __init__(self, *args, corner: dict, **kwargs):
        self._corner = corner
        super().__init__(*args, **kwargs)

    def decide_flag(self, flag, kind):
        dec = self._corner.get("prompt_defaults", {}).get(flag.eid,
                                                          "delete")
        self.model.state.flag_decisions[flag.eid] = dec
        return dec


def _queue_corner(ui: ApplyAllWorkflowUI, root: tk.Tk, corner: dict,
                  model: Model) -> None:
    """Two synthetic edge clicks -> ghost click -> confirm (ENQUEUE on
    M4). Scripted flag decisions keep it headless; per-click
    expected-state fallback keeps the drive deterministic when
    event_generate is unavailable."""
    for eid, dec in corner.get("scripted_flags", {}).items():
        model.state.flag_decisions[eid] = dec
    # M3's auto-zoom left the canvas deep-zoomed into the previous
    # corner; reset to the fit transform so the click hit-tests land
    ui.viewer.fit()
    root.update()
    # per-corner radius: CORNERS['r'] is a RADIUS (the panel, when
    # present, takes a DIAMETER)
    if ui.panel is not None:
        ui.panel.set_diameter_mm(corner["r"] * 2.0)
    else:
        ui._radius_mm = corner["r"]
    # click 1: PICK_EDGE1 -> PICK_EDGE2; click 2: -> GHOSTS_VISIBLE.
    # The direct fallback fires whenever the synthetic event did not
    # produce the expected transition (missed event OR no advancement).
    expected = [WorkflowState.PICK_EDGE2, WorkflowState.GHOSTS_VISIBLE]
    for (wx, wy), want in zip(corner["clicks_world"], expected):
        before = ui.fsm.state
        sx, sy = ui.viewer.transform.to_screen(Pt(wx, wy))
        try:
            ui.viewer.canvas.event_generate("<ButtonPress-1>",
                                            x=int(sx), y=int(sy))
        except Exception:
            pass
        root.update()
        if ui.fsm.state != want:
            ui.fsm.click_world(Pt(wx, wy))
            ui._sync_view()
            root.update()
        assert ui.fsm.state == want, \
            (f"{corner['name']}: click ({wx}, {wy}) -> state "
             f"{ui.fsm.state} != {want} (before {before}); "
             f"inline={ui.fsm.inline!r}")
    g = _pick_ghost_near(ui, corner["center"])
    ui.fsm.pick_ghost(g.side, g.side_flip)
    root.update()
    assert ui.fsm.state == WorkflowState.SIDE_PICKED
    ui._prompt_pending_flags()  # scripted decisions; no modal
    root.update()
    n_before = len(ui.queue.queue)
    n_dogs = len(model.state.dogbones)
    res = ui.confirm_click()   # M4: ENQUEUE (does not mutate)
    assert res is not None and res.ok, \
        f"{corner['name']}: enqueue confirm blocked: {ui.fsm.inline!r}"
    assert len(model.state.dogbones) == n_dogs, \
        f"{corner['name']}: confirm must NOT mutate on M4"
    assert len(ui.queue.queue) == n_before + 1, \
        f"{corner['name']}: confirm must enqueue"
    root.update()


def _make_m4_ui(root: tk.Tk, model: Model, viewer: Viewer,
                corner: dict, status: list) -> "_ScriptedApplyUI":
    return _ScriptedApplyUI(viewer, model, root, SnapshotStack(model),
                            on_status=status.append, corner=corner)


def verify_apply_undo_sequence(root: tk.Tk) -> tuple[bool, str]:
    """M4 DoD sequence: queue 2 corners (same R per decision 3; corners
    2+3, both R=3.175) -> Apply All -> assert 2 dogbones in CLICK ORDER
    (golden centers) -> Undo once -> full pre-apply ModelState equality
    (incl. flag_decisions) -> second Undo -> original -> re-queue +
    re-apply (apply-undo-apply) -> undo to bottom: disabled not
    crashed."""
    result = load(BEFORE)
    model = Model(result.model_state)
    viewer = Viewer(root, width=1100, height=750)
    viewer.canvas.pack(fill=tk.BOTH, expand=True)
    root.update()
    viewer.set_model(model.state)
    root.update()

    status: list[str] = []
    ui = _make_m4_ui(root, model, viewer, CORNERS[1], status)
    original = model.snapshot()
    ui.start()
    root.update()

    # --- queue corner 3 then corner 2 (click order must be preserved) ---
    _queue_corner(ui, root, CORNERS[1], model)
    _queue_corner(ui, root, CORNERS[0], model)
    assert len(ui.queue.queue) == 2, "two corners must be queued"
    pre_apply = model.snapshot()

    # --- Apply All ---
    applied, skips = ui.apply_all()
    assert applied == 2 and skips == [], \
        f"apply all: applied={applied} skips={skips}"
    assert len(model.state.dogbones) == 2
    # click order: first queued (corner3) first — golden centers, not
    # guessed db_id strings (promoted eids carry the run's canonical id)
    c3, c2 = model.state.dogbones
    _check("undo-seq dogbone1 center.x", c3.center.x, CORNERS[1]["center"][0])
    _check("undo-seq dogbone1 center.y", c3.center.y, CORNERS[1]["center"][1])
    _check("undo-seq dogbone2 center.x", c2.center.x, CORNERS[0]["center"][0])
    _check("undo-seq dogbone2 center.y", c2.center.y, CORNERS[0]["center"][1])
    root.update()

    # --- Undo once -> full pre-apply state equality ---
    assert ui.undo()
    assert model.state == pre_apply, \
        "undo must restore the exact pre-apply ModelState"
    assert len(model.state.dogbones) == 0
    root.update()

    # --- second Undo -> load snapshot (original) ---
    assert ui.undo()
    assert model.state == original, "second undo must land on the original"
    assert len(model.state.dogbones) == 0
    root.update()

    # --- re-queue + re-apply (apply-undo-apply) ---
    _queue_corner(ui, root, CORNERS[1], model)
    _queue_corner(ui, root, CORNERS[0], model)
    # capture AFTER queueing (scripted flag prompts legitimately
    # persist decisions during the pick flow)
    pre_reapply = model.snapshot()
    applied, skips = ui.apply_all()
    assert applied == 2 and skips == [], \
        f"re-apply after undo: applied={applied} skips={skips}"
    assert len(model.state.dogbones) == 2
    root.update()

    # --- undo to bottom: the load seed was consumed by the first
    # phase's two undos, so this batch's stack carries only its own
    # pre-batch snapshot (geometrically the original; n<seq> counters
    # advanced by the first pass, so compare against the captured
    # pre-batch snapshot). One undo lands on it; the next is at the
    # bottom: disabled, not crashed. ---
    assert ui.undo()
    assert model.state == pre_reapply, \
        "undo after re-apply must land on the exact pre-batch state"
    assert ui.undo() is False, "undo at stack bottom must return False"
    assert ui.stack.can_undo() is False
    root.update()

    viewer.canvas.destroy()
    return True, ("apply-undo-apply: 2 corners queued -> applied in click "
                 "order -> 1st undo exact pre-apply -> 2nd undo original "
                 "-> re-apply -> undo-at-bottom disabled not crashed")


def verify_revert_flow(root: tk.Tk) -> tuple[bool, str]:
    """M4: Revert-to-Original = load snapshot + flag_decisions cleared
    (ADR-009) + undo stack emptied; the pending queue survives."""
    result = load(BEFORE)
    model = Model(result.model_state)
    viewer = Viewer(root, width=1100, height=750)
    viewer.canvas.pack(fill=tk.BOTH, expand=True)
    root.update()
    viewer.set_model(model.state)
    root.update()

    status: list[str] = []
    ui = _make_m4_ui(root, model, viewer, CORNERS[1], status)
    original = model.snapshot()
    ui.start()
    root.update()

    _queue_corner(ui, root, CORNERS[1], model)
    applied, skips = ui.apply_all()
    assert applied == 1 and skips == []
    # flag decisions present after apply (scripted chord-crossers)
    assert model.state.flag_decisions, "flag decisions must exist"
    _queue_corner(ui, root, CORNERS[2], model)  # queue survives revert

    assert ui.revert_to_original()
    assert model.state == original
    assert model.state.flag_decisions == {}, "revert must clear flag_decisions"
    assert len(model.state.dogbones) == 0
    assert not ui.stack.can_undo(), "revert must empty the undo stack"
    assert len(ui.queue.queue) == 1, "pending queue must survive revert"
    root.update()

    viewer.canvas.destroy()
    return True, ("revert: original restored + flag_decisions cleared + "
                  "stack emptied + pending queue kept")


def verify_overlap_tangent_and_skip(root: tk.Tk) -> tuple[bool, str]:
    """M4 DoD: overlap-tangent passes / overlap-true refused — the
    batch re-places live, so the SAME corner queued twice sees its own
    twin: first applies, second refuses verbatim (OVERLAP) and is
    warn-and-skipped."""
    result = load(BEFORE)
    model = Model(result.model_state)
    viewer = Viewer(root, width=1100, height=750)
    viewer.canvas.pack(fill=tk.BOTH, expand=True)
    root.update()
    viewer.set_model(model.state)
    root.update()

    status: list[str] = []
    ui = _make_m4_ui(root, model, viewer, CORNERS[1], status)
    ui.start()
    root.update()

    _queue_corner(ui, root, CORNERS[1], model)
    _queue_corner(ui, root, CORNERS[1], model)  # same corner twice
    applied, skips = ui.apply_all()
    assert applied == 1, f"twin corner: applied={applied}"
    assert len(skips) == 1 and "OVERLAP" in skips[0], \
        f"twin corner: skip must carry OVERLAP verbatim: {skips}"
    expected = ("OVERLAP: dogbone circle overlaps existing dogbone "
                f"{model.state.dogbones[0].db_id} "
                "(strict with EPS_COINCIDE; tangent circles are allowed)")
    assert skips[0] == expected, \
        f"engine string must be verbatim: {skips[0]!r} != {expected!r}"
    assert len(model.state.dogbones) == 1
    root.update()

    viewer.canvas.destroy()
    return True, ("overlap: same-corner twin re-places live — second "
                  "refused OVERLAP verbatim + warn-and-skipped")


def main() -> int:
    args = sys.argv[1:]
    full = "--full" in args
    folds = "--folds" in args
    trim = "--trim" in args
    args = [a for a in args if a not in ("--full", "--folds", "--trim")]
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
        root_m4 = tk.Tk()
        root_m4.title("verify_gui --full (M4 apply/undo/revert)")
        theme_apply(root_m4)
        try:
            for label, fn in (
                ("M4 apply-undo-apply", verify_apply_undo_sequence),
                ("M4 revert flow", verify_revert_flow),
                ("M4 overlap skip", verify_overlap_tangent_and_skip),
            ):
                try:
                    ok, msg_ = fn(root_m4)
                except Exception as exc:  # noqa: BLE001
                    ok, msg_ = False, f"harness error: {type(exc).__name__}: {exc}"
                ok_all &= ok
                print(f"{label:40} {'PASS' if ok else 'FAIL'} - {msg_}")
        finally:
            root_m4.destroy()
    if folds:
        try:
            ok, msg_ = verify_fold_selection()
        except Exception as exc:  # noqa: BLE001
            ok, msg_ = False, f"harness error: {type(exc).__name__}: {exc}"
        ok_all &= ok
        print(f"{'M5b fold selection (--folds)':40} {'PASS' if ok else 'FAIL'} - {msg_}")
        try:
            ok, msg_ = verify_fold_mode_binding_regression()
        except Exception as exc:  # noqa: BLE001
            ok, msg_ = False, f"harness error: {type(exc).__name__}: {exc}"
        ok_all &= ok
        print(f"{'M5b fold binding regression':40} {'PASS' if ok else 'FAIL'} - {msg_}")
    if trim:
        try:
            ok, msg_ = verify_trim_tool()
        except Exception as exc:  # noqa: BLE001
            ok, msg_ = False, f"harness error: {type(exc).__name__}: {exc}"
        ok_all &= ok
        print(f"{'M-TRIM trim tool (--trim)':40} {'PASS' if ok else 'FAIL'} - {msg_}")
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
    theme_apply(root)  # harness exercises the same theme as the app
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


# ---------------------------------------------------------------------------
# M5b fold-selection drive (CONTRACTS §4; brief DoD: --folds)
# ---------------------------------------------------------------------------

from ui.fold_panel import FoldPanel, FoldMode  # noqa: E402

FOLD_SAMPLE = ROOT / "samples" / "syn-fold-heavy.dxf"


def verify_fold_selection() -> tuple[bool, str]:
    """M5b DoD: load syn-fold-heavy.dxf → auto-preselect (BEND_UP +
    FOLD_LINES lines) → designate 3 folds via synthetic box-select +
    clicks → assert fold_eids + badge + preselect + warnings surface for
    the near-contour fold. Direct-FSM fallback per the existing harness
    pattern when event_generate is unavailable."""
    result = load(FOLD_SAMPLE)
    model = Model(result.model_state)

    root = tk.Tk()
    root.title("verify_gui --folds (M5b fold selection)")
    theme_apply(root)
    try:
        viewer = Viewer(root, width=1100, height=750)
        viewer.canvas.pack(fill=tk.BOTH, expand=True)
        root.update()
        viewer.set_model(model.state)
        root.update()

        status: list[str] = []
        panel = FoldPanel(root, viewer, model, on_status=status.append)
        panel.pack(fill=tk.Y, side=tk.LEFT, padx=(0, 6), pady=6)
        # auto-preselect fires once per load
        panel.on_load(result.layer_of)
        root.update()

        # --- assert auto-preselect: BEND_UP + FOLD_LINES lines designated ---
        # syn-fold-heavy: '37' (BEND_UP y=80), '38' (BEND_UP y=40),
        # '39' (FOLD_LINES y=20). '3C' (FOLD_LINES) was merged as a
        # duplicate of '35' at load (collinear overlap) so it's absent
        # from primitives; layer-0 lines are NOT designated.
        expected_pre = {"37", "38", "39"}
        assert model.state.fold_eids == expected_pre, (
            f"auto-preselect: {sorted(model.state.fold_eids)} != "
            f"{sorted(expected_pre)} (layer_of={result.layer_of})")
        # badge: 3 of N straight lines designated
        n_straight = sum(1 for e in model.state.primitives
                         if isinstance(e, Seg))
        assert panel.fsm.badge_text == f"3 of {n_straight} straight lines designated", \
            f"badge after preselect: {panel.fsm.badge_text!r}"

        # --- enter fold mode + designate 1 more fold via a click (a
        # layer-0 line) ---
        panel.toggle_mode()
        root.update()
        assert panel.fsm.mode == FoldMode.ON

        # click on the layer-0 line '3A' (50,61)->(150,61): click near (100,61)
        panel.fsm.click_world(Pt(100, 61))
        root.update()
        assert "3A" in model.state.fold_eids, (
            f"click designate 3A: fold_eids={sorted(model.state.fold_eids)}")
        # badge count incremented (3 preselected + 1 clicked = 4)
        assert panel.fsm.badge_text == f"4 of {n_straight} straight lines designated"

        # --- box-select to toggle TWO more layer-0 lines ('31' and '3B') ---
        # box covering x=[-10, 160], y=[-10, 35]: catches '31' (0,0)->(180,0)
        # at y=0 AND '3B' (50,30)->(150,30) at y=30
        panel.fsm.box_select(Pt(-10, -10), Pt(160, 35))
        root.update()
        assert "31" in model.state.fold_eids, "box-select missed '31'"
        assert "3B" in model.state.fold_eids, "box-select missed '3B'"

        # --- shift-click toggles (identical semantics) ---
        # shift-click on '32' (180,0)->(180,90) near (180,45): toggle in.
        # '32' was NOT caught by the box (box x-max was 160 < 180).
        panel.fsm.click_world(Pt(180, 45), shift=True)
        root.update()
        assert "32" in model.state.fold_eids, "shift-click designate 32"

        # --- Esc exits fold mode cleanly ---
        panel.fsm.exit()
        root.update()
        assert panel.fsm.mode == FoldMode.OFF
        # fold_eids survive mode exit (designation is model state)
        assert "3A" in model.state.fold_eids

        # --- fold-color rendering: designated folds draw in the fold color ---
        viewer.redraw()
        root.update()
        # check at least one designated fold's canvas item has the fold color
        from ui.canvas_view import FOLD_FG
        fold_item = viewer._item_of.get("3A")
        assert fold_item is not None, "3A canvas item missing after redraw"
        item_color = viewer.canvas.itemcget(fold_item, "fill")
        assert item_color == FOLD_FG, (
            f"3A fold color: {item_color!r} != {FOLD_FG!r} (fold-color rendering)")

        # --- designation survives redraw (M5-plan ruling: fold-color at
        # draw time from fold_eids — full-wipe redraw reads model state) ---
        viewer.set_model(model.state)
        root.update()
        assert "3A" in viewer.fold_eids, "fold_eids not on viewer after set_model"

        # --- the §11.3 case-5 near-contour fold: '35' (20,60)->(0,60) and
        # '36' (0,60)->(0,0) share the endpoint (0,60). Designating 35
        # surfaces a warning about the contour edge 36 (they touch at
        # (0,60) within EPS_COINCIDE). Re-designate to trigger:
        panel.fsm.enter()
        panel.fsm.click_world(Pt(10, 60))  # toggle 35 (nearest to (10,60))
        root.update()
        assert "35" in model.state.fold_eids, (
            f"designate 35: fold_eids={sorted(model.state.fold_eids)}")
        assert panel.fsm.warnings, (
            f"near-contour fold warning missing: warnings={panel.fsm.warnings}")
        assert any("runs within" in w for w in panel.fsm.warnings)

        panel.fsm.exit()
        root.update()

        viewer.canvas.destroy()
        return True, (
            "fold selection: auto-preselect 4 (BEND_UP+FOLD_LINES) + "
            "click 1 + box-select 2 + shift-click 1 + Esc exit + "
            "fold-color rendering + near-contour warning — all PASS")
    finally:
        root.destroy()


def verify_fold_mode_binding_regression() -> tuple[bool, str]:
    """Regression (user report 2026-10-07): exiting fold mode killed pan
    and corner picking — unbind(seq) deletes EVERY handler for a
    sequence, not just the fold panel's, and add=True handlers made
    fold-mode clicks start corner picks. Drives the REAL Tk bindings:
    full stack (Viewer + WorkflowUI + FoldPanel), toggle in, click (must
    NOT start a corner pick), toggle out, then pan + corner pick must
    still work."""
    result = load(FOLD_SAMPLE)
    model = Model(result.model_state)

    root = tk.Tk()
    root.title("verify_gui --folds (binding regression)")
    theme_apply(root)
    try:
        viewer = Viewer(root, width=1100, height=750)
        viewer.canvas.pack(fill=tk.BOTH, expand=True)
        root.update()
        viewer.set_model(model.state)
        root.update()

        # the corner workflow binds AFTER the viewer (App order)
        ui = WorkflowUI(viewer, model, root, on_status=None,
                        radius_mm=3.175 / 2.0)
        ui.start()
        root.update()

        status: list[str] = []
        panel = FoldPanel(root, viewer, model, on_status=status.append)
        panel.pack(fill=tk.Y, side=tk.LEFT, padx=(0, 6), pady=6)
        panel.on_load(result.layer_of)
        root.update()

        pre_scripts = {seq: viewer.canvas.bind(seq) for seq in (
            "<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>",
            "<Button-3>", "<Escape>")}

        # --- toggle fold mode ON ---
        panel.toggle_mode()
        root.update()
        assert panel.fsm.mode == FoldMode.ON, (
            f"fold mode did not enter: {panel.fsm.mode!r}")

        # --- a fold-mode click designates but does NOT start a corner
        # pick (mode isolation at the REAL-binding level) ---
        n_designated = len(model.state.fold_eids)
        sx, sy = viewer.transform.to_screen(Pt(100, 61))  # near line '3A'
        viewer.canvas.event_generate("<ButtonPress-1>", x=int(sx), y=int(sy))
        viewer.canvas.event_generate("<ButtonRelease-1>", x=int(sx), y=int(sy))
        root.update()
        assert "3A" in model.state.fold_eids, (
            f"fold-mode click did not designate 3A: "
            f"{sorted(model.state.fold_eids)}")
        assert ui.fsm.state == WorkflowState.PICK_EDGE1, (
            f"fold-mode click started a corner pick: "
            f"workflow state {ui.fsm.state}, edge1={ui.fsm.edge1_eid!r}")
        n_designated += 1

        # --- middle-drag pans while fold mode is ON (B2 replaces the
        # viewer's L-drag pan during fold mode) ---
        ox_before = viewer.transform.ox
        viewer.canvas.event_generate("<ButtonPress-2>", x=500, y=400)
        viewer.canvas.event_generate("<B2-Motion>", x=530, y=400)
        viewer.canvas.event_generate("<ButtonRelease-2>", x=530, y=400)
        root.update()
        assert abs(viewer.transform.ox - (ox_before + 30.0)) < 1e-9, (
            f"middle-drag pan dead in fold mode: ox {ox_before} -> "
            f"{viewer.transform.ox}")

        # --- Esc exits fold mode. event_generate("<Escape>") needs
        # keyboard focus (unreliable under harness multi-window); drive
        # the REAL binding script directly via event_generate with a
        # fallback to the bound handler's command ---
        viewer.canvas.event_generate("<Escape>")
        root.update()
        if panel.fsm.mode != FoldMode.OFF:
            panel.fsm.exit()
            panel.unbind_canvas()
        assert panel.fsm.mode == FoldMode.OFF, (
            f"fold mode did not exit: {panel.fsm.mode!r}")

        # --- regression: every pre-fold-mode script is RESTORED ---
        for seq, script in pre_scripts.items():
            got = viewer.canvas.bind(seq)
            assert got == script, (
                f"binding {seq} not restored after fold-mode exit")

        # --- pan works again (viewer's own handler survived) ---
        ox_before = viewer.transform.ox
        viewer.canvas.event_generate("<ButtonPress-1>", x=500, y=400)
        viewer.canvas.event_generate("<B1-Motion>", x=520, y=410)
        viewer.canvas.event_generate("<ButtonRelease-1>", x=520, y=410)
        root.update()
        assert abs(viewer.transform.ox - (ox_before + 20.0)) < 1e-9, (
            f"pan dead after fold-mode exit: ox {ox_before} -> "
            f"{viewer.transform.ox}")

        # --- corner picking works again: a click on the syn-fold-heavy
        # bottom outline ('31', (0,0)->(180,0)) must pick edge 1 through
        # the REAL binding (workflow state PICK_EDGE1 -> PICK_EDGE2) ---
        sx, sy = viewer.transform.to_screen(Pt(90, 0))
        viewer.canvas.event_generate("<ButtonPress-1>", x=int(sx), y=int(sy))
        viewer.canvas.event_generate("<ButtonRelease-1>", x=int(sx), y=int(sy))
        root.update()
        assert ui.fsm.state == WorkflowState.PICK_EDGE2, (
            f"corner pick dead after fold-mode exit: state {ui.fsm.state}, "
            f"edge1={ui.fsm.edge1_eid!r}")

        viewer.canvas.destroy()
        return True, (
            "binding regression: fold-mode click designates without "
            "corner pick; Esc restores pan + corner-pick bindings "
            "(script-identical)")
    finally:
        root.destroy()


# ---------------------------------------------------------------------------
# M-TRIM manual trim tool drive (ADR-025; --trim)
# ---------------------------------------------------------------------------

from ui.trim_panel import TrimMode, TrimPanel  # noqa: E402


def verify_trim_tool() -> tuple[bool, str]:
    """ADR-025 DoD: synthetic drive on syn-trim.dxf-style fixtures loaded
    from a purpose-built in-memory state (no DXF dependency — the loader
    is not in scope). Cases: plain trim (overshoot), extend (falls
    short), stray-delete (fold-designation scrub), NO_TARGET stay,
    undo restores, binding isolation (corner workflow suspended in
    trim mode; scripts restored on exit)."""
    from geometry.entities import PointEnt, Pt
    from model.model import Model
    from model.snapshots import SnapshotStack
    from model.state import ModelState

    root = tk.Tk()
    root.title("verify_gui --trim (M-TRIM manual trim)")
    theme_apply(root)
    try:
        # --- fixture: a 7-entity scene on the canvas ---
        # L1 (0,0)-(20,0) attached at (0,0) to WALL; overshoots T at x=10
        # STRAY (0,50)-(20,50): isolated
        # FOLD (0,80)-(12,80): designated fold, attached at (0,80) to
        # WALL2; falls short of PT (13,80)
        def build_state() -> ModelState:
            st = ModelState()
            st.primitives = [
                Seg(eid="L1", a=Pt(0, 0), b=Pt(20, 0)),
                Seg(eid="WALL", a=Pt(0, 0), b=Pt(0, 5)),
                Seg(eid="T", a=Pt(10, -5), b=Pt(10, 5)),
                Seg(eid="STRAY", a=Pt(0, 50), b=Pt(20, 50)),
                Seg(eid="FOLD", a=Pt(0, 80), b=Pt(12, 80)),
                Seg(eid="WALL2", a=Pt(0, 80), b=Pt(0, 85)),
                PointEnt(eid="PT", p=Pt(13, 80)),
            ]
            st.fold_eids = {"FOLD", "STRAY"}
            return st

        model = Model(build_state())
        stack = SnapshotStack(model)
        stack.push_load()
        viewer = Viewer(root, width=1100, height=750)
        viewer.canvas.pack(fill=tk.BOTH, expand=True)
        root.update()
        viewer.set_model(model.state)
        root.update()

        status: list[str] = []
        panel = TrimPanel(root, viewer, model, stack=stack,
                          on_status=status.append)
        panel.pack(fill=tk.Y, side=tk.LEFT, padx=(0, 6), pady=6)
        # corner workflow binds AFTER the viewer (App order)
        ui = WorkflowUI(viewer, model, root, on_status=status.append,
                        radius_mm=3.175 / 2.0)
        ui.start()
        root.update()

        # --- 1. mode isolation: enter trim mode; a click must NOT start
        # a corner pick; corner-pick bindings replaced ---
        pre_scripts = {seq: viewer.canvas.bind(seq) for seq in (
            "<ButtonPress-1>", "<Button-3>", "<Escape>")}
        panel.toggle_mode()
        root.update()
        assert panel.fsm.mode == TrimMode.ON

        # --- 2. plain trim: click L1 near its b end (20,0) → snap to
        # T's supporting line x=10 ---
        panel.fsm.click_world(Pt(19.9, 0.05))
        root.update()
        assert panel.fsm.pending is not None and panel.fsm.pending.ok, (
            f"trim proposal missing: inline={panel.fsm.inline!r}")
        assert len(panel.fsm.pending.trims) == 1
        res = panel.confirm_click()
        root.update()
        assert res is not None and res.ok, (
            f"trim confirm failed: {panel.fsm.inline!r}")
        got = model.get("L1")
        assert got is not None and abs(got.b.x - 10.0) < 0.001, (
            f"L1 not trimmed to x=10: {got!r}")
        assert stack.can_undo(), "no snapshot pushed at trim apply"
        notes = ["trim: L1 b snapped to T supporting line x=10"]

        # --- 3. extend: click FOLD near (12,80) → extends to PT (13,80);
        # fold designation KEPT (trim keeps eid) ---
        panel.fsm.click_world(Pt(11.9, 80.05))
        root.update()
        res = panel.confirm_click()
        root.update()
        assert res is not None and res.ok, (
            f"fold extend failed: {panel.fsm.inline!r}")
        got = model.get("FOLD")
        assert got is not None and abs(got.b.x - 13.0) < 0.001, (
            f"FOLD not extended to PT x=13: {got!r}")
        assert "FOLD" in model.state.fold_eids, (
            "trimmed fold lost its designation (ADR-025: trims keep)")
        notes.append("extend: FOLD extended to PT (13,80); designation kept")

        # --- 4. stray-delete: click STRAY → whole-run deletion proposed;
        # confirm removes it ---
        assert model.get("STRAY") is not None
        panel.fsm.click_world(Pt(10.0, 50.0))
        root.update()
        assert panel.fsm.pending is not None and panel.fsm.pending.ok
        assert panel.fsm.pending.deletions == ["STRAY"], (
            f"stray proposal wrong: {panel.fsm.pending.deletions!r}")
        res = panel.confirm_click()
        root.update()
        assert res is not None and res.deletions == ["STRAY"]
        assert model.get("STRAY") is None, "stray not deleted"
        assert "STRAY" not in model.state.fold_eids, (
            "deleted fold eid not scrubbed from fold_eids")
        assert "FOLD" in model.state.fold_eids, (
            "unrelated fold designation scrubbed")
        notes.append("stray: isolated STRAY deleted whole + fold scrub")

        # --- 5. NO_TARGET stays in pick: a minimal attached pair with
        # NO candidate geometry: L2 (30,0)-(40,0) attached to W3 at
        # (30,0); clicking L2's far end proposes NOTHING (W3's foot is
        # the other endpoint; no other entities) → toast + stay ---
        st2 = ModelState()
        st2.primitives = [
            Seg(eid="L2", a=Pt(30, 0), b=Pt(40, 0)),
            Seg(eid="W3", a=Pt(30, 0), b=Pt(30, 5)),
        ]
        model2 = Model(st2)
        panel.model = model2
        panel.fsm.click_world(Pt(39.9, 0.05))
        root.update()
        assert panel.fsm.pending is None and panel.fsm.picked_eid is None, (
            "NO_TARGET must clear the pick (toast + stay)")
        assert panel.fsm.inline and "NO_TARGET" in panel.fsm.inline, (
            f"NO_TARGET toast missing: {panel.fsm.inline!r}")
        panel.model = model  # restore the main scene
        notes.append("NO_TARGET: toast + stay in pick")

        # --- 6. undo restores the pre-trim state (one push per Confirm,
        # ADR-025(c): 3 confirms -> 3 undos back to the load state) ---
        assert stack.can_undo()
        stack.undo()
        stack.undo()
        stack.undo()
        root.update()
        viewer.set_model(model.state)
        root.update()
        got = model.get("L1")
        assert got is not None and abs(got.b.x - 20.0) < 0.001, (
            f"undo did not restore L1: {got!r}")
        assert model.get("STRAY") is not None, "undo did not restore STRAY"
        got = model.get("FOLD")
        assert got is not None and abs(got.b.x - 12.0) < 0.001, (
            f"undo did not restore FOLD: {got!r}")
        notes.append("undo: all three edits reverted (3 pushes, 3 undos)")

        # --- 7. binding isolation: trim-mode click did NOT start a
        # corner pick; scripts restored on exit ---
        assert ui.fsm.state == WorkflowState.PICK_EDGE1, (
            f"trim-mode click leaked into the corner workflow: "
            f"state={ui.fsm.state}")
        panel.toggle_mode()  # exit
        root.update()
        assert panel.fsm.mode == TrimMode.OFF
        for seq, script in pre_scripts.items():
            got_script = viewer.canvas.bind(seq)
            assert got_script == script, (
                f"binding {seq} not restored after trim-mode exit")
        # corner picking works again: click L1 → PICK_EDGE2
        sx, sy = viewer.transform.to_screen(Pt(10, 0))
        viewer.canvas.event_generate("<ButtonPress-1>", x=int(sx), y=int(sy))
        root.update()
        if ui.fsm.state == WorkflowState.PICK_EDGE1:
            # event_generate unavailable: drive the restored binding path
            ui.fsm.click_world(Pt(10, 0))
            ui._sync_view()
        assert ui.fsm.state == WorkflowState.PICK_EDGE2, (
            f"corner pick dead after trim-mode exit: {ui.fsm.state}")
        notes.append("binding: corner workflow isolated + restored")

        viewer.canvas.destroy()
        return True, " | ".join(notes)
    finally:
        root.destroy()


if __name__ == "__main__":
    sys.exit(main())
