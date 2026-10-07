"""DXF Dogbone - viewer + corner workflow entry point.

Launch via run.bat. Optional argv[1]: DXF path to open at startup.
M1: load + render + pan/zoom. M3: corner workflow (click two edges ->
ghosts -> side pick -> red deletion preview -> confirm).
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from dxf_io import LoadRefused, load
from model.model import Model
from model.state import ModelState
from ui.canvas_view import Viewer
from ui.workflow import WorkflowUI


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("DXF Dogbone")
        root.geometry("1200x800")

        self.model: Model | None = None

        menubar = tk.Menu(root)
        file_menu = tk.Menu(menubar, tearoff=0)
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
        # overwrite workflow toasts.
        btns = tk.Frame(root)
        btns.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(btns, textvariable=self.mouse_var, anchor="w",
                 relief=tk.SUNKEN, bd=1, width=46).pack(fill=tk.Y,
                                                       side=tk.LEFT)
        self.confirm_btn = tk.Button(
            btns, text="Confirm", state=tk.DISABLED,
            command=self.on_confirm)
        self.confirm_btn.pack(side=tk.RIGHT, padx=4, pady=3)
        tk.Label(btns, textvariable=self.summary_var, anchor="w",
                 relief=tk.SUNKEN, bd=1).pack(fill=tk.X, side=tk.LEFT,
                                              expand=True)
        tk.Label(root, textvariable=self.status_var, anchor="w",
                 relief=tk.SUNKEN, bd=1).pack(fill=tk.X, side=tk.BOTTOM)
        self.viewer = Viewer(root, on_status=self.mouse_var.set)
        self.viewer.canvas.pack(fill=tk.BOTH, expand=True)
        self.workflow: WorkflowUI | None = None

    def _ensure_workflow(self) -> None:
        if self.workflow is None and self.model is not None:
            self.workflow = WorkflowUI(
                self.viewer, self.model, self.root,
                on_status=self.status_var.set,
                on_state=self._update_confirm)  # every state change refreshes
            self._update_confirm()

    def on_confirm(self) -> None:
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
