"""ui.fold_panel — headless FSM tests (M5b brief DoD).

The FoldFSM is canvas-free by construction: these tests drive (state,
event) transitions with a fake ports object, no tkinter anywhere. Covers:
mode toggle in/out; click toggle in/out; shift-click (identical
semantics); box-select threshold (>=5 px = box, <5 px = click); badge
text on every mutation kind; auto-preselect once-per-load + user-
authoritative-after; Esc exit; mode isolation (corner picks don't fire
while fold mode is ON); validation warnings surfaced for a near-contour
fold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from geometry.entities import Arc, Entity, Pt, Seg
import ui.messages as msg
from ui.fold_panel import (
    BOX_SELECT_PX,
    DEFAULT_FOLD_PATTERNS,
    FoldFSM,
    FoldMode,
    FoldPanel,
)


@dataclass
class FakePorts:
    """Scripted ports: primitives + a pick map + captured set_fold_eids calls."""
    _primitives: list[Entity]
    picks: dict[Pt, str] = field(default_factory=dict)  # world point -> eid
    set_calls: list[set[str]] = field(default_factory=list)
    last_eids: set[str] = field(default_factory=set)

    @property
    def primitives(self) -> list[Entity]:
        return self._primitives

    def pick_fold_line(self, p_world: Pt) -> str | None:
        # nearest pick within a small tolerance
        import math
        best = None
        for e in self._primitives:
            if not isinstance(e, Seg):
                continue
            d = math.hypot(
                min(p_world.x - e.a.x, p_world.x - e.b.x),
                min(p_world.y - e.a.y, p_world.y - e.b.y),
            )
            if best is None or d < best[0]:
                best = (d, e.eid)
        return best[1] if best else None

    def set_fold_eids(self, eids: set[str]) -> None:
        self.set_calls.append(set(eids))
        self.last_eids = set(eids)


def _prims():
    """A small set: 3 straight LINEs + 1 arc (arcs never designated).
    Lines don't share endpoints (so validation warnings are isolated)."""
    return [
        Seg("L1", Pt(0, 0), Pt(100, 0)),    # horizontal, bottom
        Seg("L2", Pt(0, 50), Pt(100, 50)),   # horizontal, mid
        Seg("L3", Pt(50, 100), Pt(50, 200)),  # vertical, far from L1/L2
        Arc("A1", Pt(200, 200), 5, 0, 90),
    ]


# ---------------------------------------------------------------------------
# Mode toggle + Esc exit + mode isolation
# ---------------------------------------------------------------------------


def test_fold_fsm_toggle_mode_on_off():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    assert fsm.mode == FoldMode.OFF
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    assert fsm.mode == FoldMode.ON
    assert msg.FOLD_MODE_ENTER in fsm.status
    assert "Middle-drag" not in fsm.status
    assert "Drag pans" in fsm.status
    assert "right-drag box-selects" in fsm.status
    fsm.exit()
    assert fsm.mode == FoldMode.OFF
    assert fsm._box_start is None  # no partial state


def test_fold_fsm_esc_exits_cleanly():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    fsm._box_start = (10.0, 20.0)  # pending box-select
    fsm.exit()
    assert fsm.mode == FoldMode.OFF
    assert fsm._box_start is None


def test_fold_fsm_mode_isolation_click_ignored_when_off():
    """Clicks while fold mode is OFF must not designate anything."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    # mode is OFF; a click does nothing
    fsm.click_world(Pt(50, 0))
    assert fsm.fold_eids == set()
    assert ports.last_eids == set()


# ---------------------------------------------------------------------------
# Click / shift-click toggle
# ---------------------------------------------------------------------------


def test_fold_fsm_click_toggles_designation_in_and_out():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    # click near L1 (0,0)->(100,0): pick returns nearest Seg
    fsm.click_world(Pt(50, 0))
    assert "L1" in fsm.fold_eids
    # click again toggles it out
    fsm.click_world(Pt(50, 0))
    assert "L1" not in fsm.fold_eids


def test_fold_fsm_shift_click_identical_to_click():
    """SPEC §11.8.4 / brief §1: shift-click toggles too (identical
    semantics, both directions)."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    fsm.click_world(Pt(50, 0), shift=True)
    assert "L1" in fsm.fold_eids
    fsm.click_world(Pt(50, 0), shift=True)
    assert "L1" not in fsm.fold_eids


def test_fold_fsm_click_only_designates_straight_lines():
    """SPEC §4.5: straight LINEs only — arcs/circles/points/text never
    designated. The pick returns the nearest Seg, so an arc is never
    returned."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    # click near the arc — pick_fold_line returns the nearest Seg (L3 is
    # closest to (0,100)), never the arc
    fsm.click_world(Pt(0, 100))
    assert "A1" not in fsm.fold_eids


# ---------------------------------------------------------------------------
# Box-select threshold (>=5 px = box, <5 px = click)
# ---------------------------------------------------------------------------


def test_fold_fsm_box_select_toggles_all_lines_in_box():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    # box covering x=[-10, 110], y=[-10, 60] -> catches L1 (y=0), L2 (y=50)
    fsm.box_select(Pt(-10, -10), Pt(110, 60))
    assert fsm.fold_eids == {"L1", "L2"}


def test_fold_fsm_box_select_shift_identical():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    fsm.box_select(Pt(-10, -10), Pt(110, 60), shift=True)
    assert fsm.fold_eids == {"L1", "L2"}


def test_fold_fsm_box_select_toggle_out():
    """Box-selecting an already-designated fold toggles it OUT."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    fsm.box_select(Pt(-10, -10), Pt(110, 10))  # catches L1
    assert fsm.fold_eids == {"L1"}
    fsm.box_select(Pt(-10, -10), Pt(110, 10))  # toggles it out
    assert fsm.fold_eids == set()


# ---------------------------------------------------------------------------
# Badge text on every mutation kind
# ---------------------------------------------------------------------------


def test_fold_fsm_badge_text_format():
    """Brief §1: 'N of M straight lines designated' — count updates on
    EVERY change (click, shift-click, box, load, undo/restore)."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    assert fsm.badge_text == msg.FOLD_BADGE.format(n=0, m=3)
    fsm.click_world(Pt(50, 0))
    assert fsm.badge_text == msg.FOLD_BADGE.format(n=1, m=3)
    fsm.click_world(Pt(50, 50))
    assert fsm.badge_text == msg.FOLD_BADGE.format(n=2, m=3)
    fsm.click_world(Pt(50, 0))  # toggle L1 out
    assert fsm.badge_text == msg.FOLD_BADGE.format(n=1, m=3)


def test_fold_fsm_badge_updates_on_box_select():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    fsm.box_select(Pt(-10, -10), Pt(110, 60))
    assert fsm.badge_text == msg.FOLD_BADGE.format(n=2, m=3)


def test_fold_fsm_badge_updates_on_auto_preselect():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.auto_preselect(ports.primitives, {"L1": "BEND_UP", "L2": "0", "L3": "0"})
    assert fsm.badge_text == msg.FOLD_BADGE.format(n=1, m=3)
    assert "L1" in fsm.fold_eids


# ---------------------------------------------------------------------------
# Auto-preselect: once-per-load + user-authoritative-after
# ---------------------------------------------------------------------------


def test_fold_fsm_auto_preselect_fires_once_per_load():
    """Auto-preselect designates lines on matching layers (case-insensitive
    contains bend|fold|centerline). Calling it again with the SAME layer
    map re-fires (a re-Open re-fires for the new document — the App
    controls the once-per-load rule by calling auto_preselect only after
    set_model on Open, not on undo/restore)."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    layer_of = {"L1": "BEND_UP", "L2": "FOLD_LINES", "L3": "0", "A1": "0"}
    fsm.auto_preselect(ports.primitives, layer_of)
    assert fsm.fold_eids == {"L1", "L2"}


def test_fold_fsm_auto_preselect_case_insensitive():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.auto_preselect(ports.primitives,
                       {"L1": "bend-down", "L2": "CenterLine", "L3": "FOLD"})
    assert fsm.fold_eids == {"L1", "L2", "L3"}


def test_fold_fsm_auto_preselect_user_authoritative_after():
    """After auto-preselect, user toggles are authoritative (a user
    un-designating an auto-picked fold keeps it un-designated)."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.auto_preselect(ports.primitives, {"L1": "BEND_UP", "L2": "0", "L3": "0"})
    assert "L1" in fsm.fold_eids
    fsm.enter()
    fsm.click_world(Pt(50, 0))  # user un-designates L1
    assert "L1" not in fsm.fold_eids


def test_fold_fsm_auto_preselect_custom_patterns():
    """The pattern list is editable; auto-preselect honors custom patterns."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.auto_preselect(ports.primitives, {"L1": "score", "L2": "0", "L3": "0"},
                       patterns=("score",))
    assert fsm.fold_eids == {"L1"}


# ---------------------------------------------------------------------------
# Validation warnings surfaced
# ---------------------------------------------------------------------------


def test_fold_fsm_validation_warning_for_near_contour_fold():
    """SPEC §11.3 case 5: designating a fold that runs within eps of a
    contour edge surfaces a warning string (non-blocking; never auto-
    undesignates)."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    # L1 (0,0)->(100,0); add a contour edge C1 collinear with L1's middle.
    # The pick returns the NEAREST Seg to (50,0) — C1 is closer than L1,
    # so C1 gets designated and the warning surfaces about the L1 contour.
    ports._primitives.append(Seg("C1", Pt(40, 0), Pt(60, 0)))
    fsm.click_world(Pt(50, 0))
    # one of the two collinear lines got designated; the warning fires
    # about the OTHER (the contour edge it runs within eps of)
    designated = next(iter(fsm.fold_eids))
    assert designated in ("L1", "C1")
    other = "L1" if designated == "C1" else "C1"
    assert any(f"fold {designated} runs within" in w
               and f"contour edge {other}" in w
               for w in fsm.warnings)


def test_fold_fsm_no_warning_for_clear_fold():
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.set_primitives(ports.primitives)
    fsm.enter()
    fsm.click_world(Pt(50, 0))  # L1, no contour nearby
    assert "L1" in fsm.fold_eids
    assert fsm.warnings == []


# ---------------------------------------------------------------------------
# set_primitives / model change (undo/restore)
# ---------------------------------------------------------------------------


def test_fold_fsm_set_primitives_drops_stale_eids():
    """On a model change (undo past a pre-pick), fold_eids no longer in
    primitives are dropped (fold_eids travel in snapshots — restore may
    have changed the set)."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.fold_eids = {"L1", "L2", "GONE"}
    # model change: GONE is no longer present
    fsm.set_primitives([Seg("L1", Pt(0, 0), Pt(100, 0)),
                        Seg("L2", Pt(0, 50), Pt(100, 50))])
    assert "GONE" not in fsm.fold_eids
    assert fsm.fold_eids == {"L1", "L2"}
    assert fsm.straight_count == 2


def test_fold_fsm_set_primitives_does_not_refire_preselect():
    """set_primitives refreshes the count + drops stale eids but does NOT
    re-fire auto-preselect (the once-per-load rule)."""
    ports = FakePorts(_prims())
    fsm = FoldFSM(ports=ports)
    fsm.auto_preselect(ports.primitives, {"L1": "BEND_UP", "L2": "0", "L3": "0"})
    assert fsm.fold_eids == {"L1"}
    # user un-designates L1
    fsm.fold_eids.discard("L1")
    # a model change must NOT re-pick L1
    fsm.set_primitives(ports.primitives)
    assert "L1" not in fsm.fold_eids


# ---------------------------------------------------------------------------
# BOX_SELECT_PX constant
# ---------------------------------------------------------------------------


def test_fold_panel_box_select_px_constant_is_5():
    """CONTRACTS §3 note / SPEC §11.8.4: drag >= 5 px = box select."""
    assert BOX_SELECT_PX == 5.0


def test_fold_panel_default_patterns():
    """ISSUE-003 defaults: bend, fold, centerline. The entry keeps that
    text under the bend-import label."""
    import tkinter as tk

    import pytest

    assert DEFAULT_FOLD_PATTERNS == ("bend", "fold", "centerline")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    try:
        panel = FoldPanel(root, None, None)
        assert panel.pattern_label.cget("text") == "Bend import keywords"
        assert panel.pattern_label.cget("text") == msg.FOLD_PATTERN_LABEL
        assert panel.pattern_entry.get() == "bend, fold, centerline"
        assert panel.pattern_hint.cget("text") == msg.FOLD_PATTERN_HINT
        assert panel.layer_heading.cget("text") == "Layers with straight lines"
        assert panel.layer_hint.cget("text") == msg.FOLD_LAYER_HINT
        assert panel.layer_heading.winfo_manager() == ""
    finally:
        root.destroy()