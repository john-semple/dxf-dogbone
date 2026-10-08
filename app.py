"""DXF Dogbone - viewer + corner workflow entry point.

Launch via run.bat. Optional argv[1]: DXF path to open at startup.
M1: load + render + pan/zoom. M3: corner workflow (click two edges ->
ghosts -> side pick -> red deletion preview -> confirm).
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from dxf_io import LoadRefused, load
from model.model import Model
from model.snapshots import SnapshotStack
from model.state import ModelState
from ui.apply_panel import ApplyAllWorkflowUI, ToolPanel
from ui.canvas_view import Viewer
from ui.fold_panel import FoldPanel
from ui.trim_panel import TrimPanel
from ui.theme import COLORS as THEME, apply as theme_apply
import ui.messages as msg


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        theme_apply(root)
        root.title("DXF Dogbone")
        root.geometry("1200x800")

        self.model: Model | None = None

        menubar = tk.Menu(root, bg=THEME["menu_bg"], fg=THEME["menu_fg"],
                          activebackground=THEME["menu_active_bg"],
                          activeforeground=THEME["menu_active_fg"])
        file_menu = tk.Menu(menubar, tearoff=0, bg=THEME["menu_bg"],
                            fg=THEME["menu_fg"],
                            activebackground=THEME["menu_active_bg"],
                            activeforeground=THEME["menu_active_fg"])
        file_menu.add_command(label="Open DXF...", command=self.open_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
        root.config(menu=menubar)

        self.status_var = tk.StringVar(value="Open a DXF (File > Open DXF...)")
        self.mouse_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="")
        # pack order matters: the message bars are packed FIRST so the
        # expanding canvas cannot squeeze them to zero height (checklist
        # defect: bottom bars packed after the canvas were invisible at
        # 1200x800). Status line = workflow messages; mouse readout (x/y
        # /zoom/entities) gets its own label so motion events cannot
        # overwrite workflow toasts. UI-UPGRADE: slim ttk status bar —
        # Status.TLabel + ttk.Separator, no sunkent-bar chrome.
        btns = ttk.Frame(root, style="Status.TFrame")
        btns.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(btns, textvariable=self.mouse_var,
                  style="Status.TLabel", width=46).pack(
            fill=tk.Y, side=tk.LEFT)
        self.confirm_btn = ttk.Button(
            btns, text="Confirm", style="Accent.TButton", state=tk.DISABLED,
            command=self.on_confirm)
        self.confirm_btn.pack(side=tk.RIGHT, padx=8, pady=4)
        ttk.Label(btns, textvariable=self.summary_var,
                  style="Status.TLabel").pack(fill=tk.X, side=tk.LEFT,
                                              expand=True)
        ttk.Separator(root).pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(root, textvariable=self.status_var,
                  style="Status.TLabel").pack(fill=tk.X, side=tk.BOTTOM)
        # M4: left tool panel (diameter + quick sizes + Apply All /
        # Undo / Revert) packs BEFORE the canvas so the expanding
        # canvas cannot squeeze it.
        # M5b: a left-side container holds the tool panel AND the fold
        # panel stacked vertically, both packed BEFORE the canvas.
        left = ttk.Frame(root, style="TFrame")
        left.pack(fill=tk.Y, side=tk.LEFT, padx=(0, 6), pady=6)
        self.panel = ToolPanel(root, on_apply_all=self.on_apply_all,
                               on_undo=self.on_undo,
                               on_revert=self.on_revert,
                               on_radius_change=self.on_radius_change)
        self.panel.pack(in_=left, fill=tk.Y, side=tk.TOP)
        self.viewer = Viewer(root, on_status=self.mouse_var.set)
        self.fold_panel = FoldPanel(
            root, self.viewer, self.model,
            on_status=self.status_var.set)
        self.fold_panel.pack(in_=left, fill=tk.Y, side=tk.TOP)
        # ADR-025: manual trim panel (stack is created with the workflow;
        # the panel gets it at _ensure_workflow time)
        self.trim_panel = TrimPanel(
            root, self.viewer, self.model,
            on_status=self.status_var.set)
        self.trim_panel.pack(in_=left, fill=tk.Y, side=tk.TOP)
        self.viewer.canvas.pack(fill=tk.BOTH, expand=True)
        self.workflow: ApplyAllWorkflowUI | None = None
        # T key toggles trim mode (ADR-025(d)); needs keyboard focus on
        # the canvas — bound on the root so it works whenever the app
        # has focus. Fold mode takes precedence visually; toggling trim
        # while fold mode is ON is refused with a status hint.
        root.bind("<t>", self._toggle_trim_mode)
        root.bind("<T>", self._toggle_trim_mode)

    def _toggle_trim_mode(self, _ev=None) -> None:
        from ui.fold_panel import FoldMode
        if self.fold_panel is not None and self.fold_panel.fsm.mode == FoldMode.ON:
            self.status_var.set("Exit fold mode first (Esc), then T for trim.")
            return
        self.trim_panel.toggle_mode()
        self._update_confirm()

    def _ensure_workflow(self) -> None:
        if self.workflow is None and self.model is not None:
            stack = SnapshotStack(self.model)
            self.workflow = ApplyAllWorkflowUI(
                self.viewer, self.model, self.root,
                stack=stack,
                on_status=self.status_var.set,
                on_state=self._update_confirm,
                panel=self.panel)
            # ADR-025: the trim panel mutates through the same stack
            self.trim_panel.model = self.model
            self.trim_panel.stack = stack
            self._update_confirm()

    def on_apply_all(self) -> None:
        """M4: Apply All drives the batch (snapshot -> re-place each
        pending live -> apply in click order; skips toasted)."""
        if self.workflow is None:
            return
        applied, skips = self.workflow.apply_all()
        self._update_confirm()
        if applied:
            self.summary_var.set("")

    def on_undo(self) -> None:
        if self.workflow is None:
            return
        self.workflow.undo()
        self._update_confirm()
        if self.fold_panel is not None:
            self.fold_panel.on_model_change()
        # ADR-025: a pending trim preview is stale after undo — drop it
        if self.trim_panel is not None:
            self.trim_panel.fsm._clear_pick()
            self.trim_panel._clear_overlays()

    def on_revert(self) -> None:
        if self.workflow is None or self.model is None:
            return
        if not messagebox.askyesno(msg.REVERT_TITLE, msg.REVERT_CONFIRM):
            return
        self.workflow.revert_to_original()
        self._update_confirm()
        if self.fold_panel is not None:
            self.fold_panel.on_model_change()
        if self.trim_panel is not None:
            self.trim_panel.fsm._clear_pick()
            self.trim_panel._clear_overlays()

    def on_radius_change(self) -> None:
        if self.workflow is not None:
            self.workflow.on_radius_change()
            self._update_confirm()

    def on_confirm(self) -> None:
        """M3's Confirm = enqueue on M4 (SPEC 5: single Apply All)."""
        if self.workflow is None:
            return
        res = self.workflow.confirm_click()
        self._update_confirm()
        if res is None:
            s = self.workflow.summary_line()
            if s:
                self.summary_var.set(s)

    def _update_confirm(self) -> None:
        from ui.workflow import WorkflowState
        if self.workflow is None:
            self.confirm_btn.config(state=tk.DISABLED)
            self.summary_var.set("")
            return
        st = self.workflow.fsm.state
        self.confirm_btn.config(
            state=tk.NORMAL if st == WorkflowState.SIDE_PICKED else tk.DISABLED
        )
        s = self.workflow.summary_line()
        self.summary_var.set(s if st == WorkflowState.SIDE_PICKED else "")

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open DXF",
            filetypes=[("DXF files", "*.dxf *.DXF"), ("All files", "*.*")],
        )
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        try:
            result = load(path)
        except LoadRefused as exc:
            messagebox.showerror("Load refused", exc.reason)
            return
        self.model = Model(result.model_state)
        self.viewer.set_model(result.model_state)
        self.root.title(f"DXF Dogbone - {path.name}")
        self._ensure_workflow()
        # ADR-025: exiting trim mode on load drops stale bindings/pick
        if self.trim_panel.fsm.mode.name == "ON":
            self.trim_panel.toggle_mode()
        # M5b: fire auto-preselect ONCE per load on the existing panel.
        if self.fold_panel is not None:
            self.fold_panel.unbind_canvas()
            self.fold_panel.model = self.model
            self.fold_panel.on_load(result.layer_of)
        if self.workflow is not None:
            self.workflow.start()
            self._update_confirm()
        if result.warnings:
            messagebox.showwarning(
                "Loaded with warnings",
                "\n".join(result.warnings),
            )
        self.status_var.set(
            f"{path.name}: {len(result.model_state.primitives)} entities loaded"
        )


def main() -> int:
    root = tk.Tk()
    app = App(root)
    if len(sys.argv) > 1:
        app.open_path(Path(sys.argv[1]))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
