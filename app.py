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
from ui.collapsible import Sidebar
from ui.fold_panel import FoldPanel
from ui.rounded_button import RoundedButton, quiet_button
from ui.trim_panel import TrimPanel
from ui.theme import COLORS as THEME, apply as theme_apply, font as theme_font
import ui.messages as msg

_TITLE = "DXF Dogbone"
_STARTUP_STATUS = "Add a DXF to get started."
# Windows taskbar groups windows by process. Without an explicit id it
# keeps the python.exe snake even after the window icon is set.
_APP_USER_MODEL_ID = "dxf-dogbone"
_ICON_ICO = Path(__file__).resolve().parent / "assets" / "dxf-dogbone.ico"
_ICON_PNG = Path(__file__).resolve().parent / "assets" / "dxf-dogbone.png"


def _set_windows_app_id() -> None:
    """Call before the first window. Windows otherwise groups us under python.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.HRESULT
        shell32.SetCurrentProcessExplicitAppUserModelID(_APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def _win32_set_icons(root: tk.Tk, ico: str) -> None:
    """Push the .ico onto the title bar and the taskbar button."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = wintypes.LPARAM
    image_icon = 1
    lr_loadfromfile = 0x0010
    wm_seticon = 0x0080
    hwnd = wintypes.HWND(root.winfo_id())
    # Keep the handles alive for the life of the window.
    handles: list[int] = []
    for which, px in ((0, 16), (1, 32)):
        handle = user32.LoadImageW(None, ico, image_icon, px, px, lr_loadfromfile)
        if not handle:
            continue
        handles.append(int(handle))
        user32.SendMessageW(hwnd, wm_seticon, which, handle)
    root._icon_handles = handles  # type: ignore[attr-defined]


def _apply_window_icon(root: tk.Tk) -> tk.PhotoImage | None:
    """Title-bar and taskbar mark. The PhotoImage must stay referenced."""
    if not _ICON_ICO.is_file():
        return None
    ico = str(_ICON_ICO)
    try:
        root.iconbitmap(default=ico)
        root.iconbitmap(ico)
    except tk.TclError:
        pass
    if sys.platform == "win32":
        try:
            _win32_set_icons(root, ico)
        except (AttributeError, OSError, tk.TclError):
            pass
        return None
    if not _ICON_PNG.is_file():
        return None
    try:
        image = tk.PhotoImage(file=_ICON_PNG.as_posix())
    except tk.TclError:
        return None
    root.iconphoto(True, image)
    return image


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        theme_apply(root)
        root.title(_TITLE)
        self._icon_image = _apply_window_icon(root)
        root.geometry("1200x800")

        self.model: Model | None = None
        self.source_path: Path | None = None
        self.header: dict = {}
        self.export_dir: Path | None = None

        self.status_var = tk.StringVar(value=_STARTUP_STATUS)
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
        self.export_btn = RoundedButton(
            btns, text=msg.EXPORT_MENU, command=self.export_dialog)
        self.export_btn.pack(side=tk.RIGHT, padx=8, pady=4)
        ttk.Label(btns, textvariable=self.summary_var,
                  style="Status.TLabel").pack(fill=tk.X, side=tk.LEFT,
                                              expand=True)
        ttk.Separator(root).pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(root, textvariable=self.status_var,
                  style="Status.TLabel").pack(fill=tk.X, side=tk.BOTTOM)
        # Full-width strip above the rail (packed before the sidebar so
        # it spans the window). ✕ clears the session; it is not the
        # window close button and it does not delete the file on disk.
        close_bar = ttk.Frame(root, style="TopBar.TFrame")
        close_bar.pack(fill=tk.X, side=tk.TOP)
        ttk.Separator(root, orient=tk.HORIZONTAL).pack(fill=tk.X, side=tk.TOP)
        # Popup, not root.config(menu=...): the native Windows menubar
        # stays white. The dropdown still uses the dark menu colors.
        self.file_menu = tk.Menu(
            root, tearoff=0, bg=THEME["menu_bg"], fg=THEME["menu_fg"],
            activebackground=THEME["menu_active_bg"],
            activeforeground=THEME["menu_active_fg"])
        self.file_menu.add_command(label="Open DXF...", command=self.open_dialog)
        self.file_menu.add_command(label=msg.EXPORT_MENU, command=self.export_dialog)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=root.destroy)
        self.file_chip = tk.Frame(close_bar, bg=THEME["file_chip"], cursor="hand2")
        self.file_chip.pack(side=tk.LEFT, padx=(8, 0), pady=2)
        self.file_btn = tk.Label(
            self.file_chip, text="File", bg=THEME["file_chip"], fg=THEME["fg"],
            font=theme_font(9), padx=8, pady=2, cursor="hand2",
            highlightthickness=0)
        self.file_btn.pack(side=tk.LEFT)
        for widget in (self.file_chip, self.file_btn):
            widget.bind("<Button-1>", self._post_file_menu)
            widget.bind("<Enter>", lambda _e: self._paint_file_chip(True))
            widget.bind("<Leave>", self._file_chip_hover_off)
        root.bind("<Alt-f>", self._post_file_menu)
        root.bind("<Alt-F>", self._post_file_menu)
        self.close_btn = ttk.Button(
            close_bar, text="✕", style="BarQuiet.TButton",
            command=self.close_dxf)
        self.close_btn.pack(side=tk.RIGHT, padx=8, pady=2)
        # Left rail, packed BEFORE the canvas so the expanding canvas
        # cannot squeeze it. Undo/Redo/Revert stay pinned. Dogbone,
        # Folds, and Trim share one column and scroll only when that
        # column is taller than the rail.
        self.sidebar = Sidebar(root, on_hover=self._sidebar_hover)
        self.sidebar.pack(fill=tk.Y, side=tk.LEFT, pady=(0, 0))
        rail = self.sidebar.body
        self.panel = ToolPanel(rail, on_apply_all=self.on_apply_all,
                               on_undo=self.on_undo,
                               on_redo=self.on_redo,
                               on_revert=self.on_revert,
                               on_radius_change=self.on_radius_change,
                               command_parent=self.sidebar.pin)
        self.panel.commands.pack(fill=tk.X)
        self.panel.dogbone.pack(fill=tk.X, pady=(0, 6))
        self.viewer = Viewer(root, on_status=self.mouse_var.set)
        self.fold_panel = FoldPanel(
            rail, self.viewer, self.model,
            on_status=self.status_var.set)
        self.fold_panel.pack(fill=tk.X, side=tk.TOP)
        # ADR-025: manual trim panel (stack is created with the workflow;
        # the panel gets it at _ensure_workflow time)
        self.trim_panel = TrimPanel(
            rail, self.viewer, self.model,
            on_status=self.status_var.set)
        self.trim_panel.pack(fill=tk.X, side=tk.TOP)
        self.viewer.canvas.pack(fill=tk.BOTH, expand=True)
        # Widget, not a canvas item: pan moves every canvas item, and
        # redraw deletes them. place() stays centered on resize.
        self.empty_hint = tk.Frame(
            self.viewer.canvas,
            bg=THEME["canvas_bg"],
            highlightthickness=0,
            bd=0,
        )
        self.empty_label = tk.Label(
            self.empty_hint,
            text=msg.EMPTY_CANVAS,
            bg=THEME["canvas_bg"],
            fg=THEME["canvas_empty"],
            font=theme_font(13),
            justify=tk.CENTER,
            borderwidth=0,
            highlightthickness=0,
        )
        self.empty_label.pack()
        self.empty_open = quiet_button(
            self.empty_hint, msg.EMPTY_OPEN, self.open_dialog)
        self.empty_open.pack(pady=(12, 0))
        self._show_empty_hint()
        self.workflow: ApplyAllWorkflowUI | None = None
        # T key toggles trim mode (ADR-025(d)); needs keyboard focus on
        # the canvas — bound on the root so it works whenever the app
        # has focus. Fold mode takes precedence visually; toggling trim
        # while fold mode is ON is refused with a status hint.
        root.bind("<t>", self._toggle_trim_mode)
        root.bind("<T>", self._toggle_trim_mode)
        root.bind("<Escape>", self._on_escape)
        # Same path as the Undo / Redo buttons, including fold and trim
        # refresh. Bound on the root so the shortcut works when focus is
        # on the canvas or a rail field. Both cases: Caps Lock.
        root.bind("<Control-z>", self._on_undo_key)
        root.bind("<Control-Z>", self._on_undo_key)
        root.bind("<Control-y>", self._on_redo_key)
        root.bind("<Control-Y>", self._on_redo_key)
        # Maximized, with the title bar. geometry() above is the restored
        # size. A withdrawn root (the UI tests) stays withdrawn.
        try:
            if root.state() != "withdrawn":
                root.state("zoomed")
        except tk.TclError:
            pass

    def _show_empty_hint(self) -> None:
        self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")

    def _hide_empty_hint(self) -> None:
        self.empty_hint.place_forget()

    def _sidebar_hover(self, inside: bool) -> None:
        """While the pointer is over the rail, the wheel scrolls sections
        instead of zooming the drawing."""
        if inside:
            self.viewer.canvas.unbind("<MouseWheel>")
        else:
            self.viewer.canvas.bind("<MouseWheel>", self.viewer._on_wheel)

    def _on_escape(self, _ev=None):
        """Esc works when focus has left the canvas. Fold, then trim,
        then a corner pick. ``return "break"`` so the canvas handler
        and this one do not both run."""
        from ui.fold_panel import FoldMode
        from ui.trim_panel import TrimMode

        if (self.fold_panel is not None
                and self.fold_panel.fsm.mode == FoldMode.ON):
            self.fold_panel._on_esc(None)
            return "break"
        if (self.trim_panel is not None
                and self.trim_panel.fsm.mode == TrimMode.ON):
            self.trim_panel._on_esc(None)
            return "break"
        if self.workflow is not None:
            self.workflow._on_esc(None)
            self._update_confirm()
            return "break"
        return None

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
            # ADR-025: the trim panel mutates through the same stack.
            # ADR-027: fold designation abandons redo through it too.
            # on_change keeps the Undo/Redo buttons in step with pushes
            # that do not go through the workflow (trim confirm).
            self.trim_panel.model = self.model
            self.trim_panel.stack = stack
            self.fold_panel.stack = stack
            stack.on_change = self.workflow._notify_queue
            self._update_confirm()

    def _exit_edit_modes(self) -> None:
        """Fold and trim must not keep the previous file's bindings or pick."""
        if self.fold_panel.fsm.mode.name == "ON":
            self.fold_panel.toggle_mode()
        if self.trim_panel.fsm.mode.name == "ON":
            self.trim_panel.toggle_mode()
        self.trim_panel.fsm._clear_pick()
        self.trim_panel._clear_overlays()

    def _retarget_model(
        self,
        model: Model,
        *,
        start: bool,
        layer_of: dict[str, str] | None,
    ) -> None:
        """Point the existing workflow at ``model``. Does not build a
        second ApplyAllWorkflowUI (its canvas bindings would stack)."""
        if self.workflow is None:
            return
        stack = SnapshotStack(model)
        self.workflow.model = model
        self.workflow.queue.model = model
        self.workflow.stack = stack
        self.workflow.queue.stack = stack
        self.trim_panel.model = model
        self.trim_panel.stack = stack
        self.fold_panel.model = model
        self.fold_panel.stack = stack
        self.workflow.queue.clear()
        self.workflow.clear_unapplied_undo()
        self.workflow.bind_history_hooks(stack)
        stack.on_change = self.workflow._notify_queue
        stack.push_load()
        if layer_of is not None:
            self.fold_panel.on_load(layer_of)
        else:
            self.fold_panel.on_model_change()
        if start:
            self.workflow.start()
        else:
            # Clear a half-finished corner pick. start() would ask for
            # edge 1 and overwrite the startup status line.
            self.workflow.fsm.esc()
            self.workflow._sync_view()
        self._update_confirm()

    def _paint_file_chip(self, hot: bool) -> None:
        bg = THEME["file_chip_hover"] if hot else THEME["file_chip"]
        self.file_chip.configure(bg=bg)
        self.file_btn.configure(bg=bg)

    def _file_chip_hover_off(self, _event=None) -> None:
        widget = self.file_chip.winfo_containing(*self.file_chip.winfo_pointerxy())
        while widget is not None:
            if widget == self.file_chip:
                return
            widget = getattr(widget, "master", None)
        self._paint_file_chip(False)

    def _post_file_menu(self, _ev=None):
        """Open the File menu under its chip. Alt+F uses the same path."""
        chip = self.file_chip
        chip.update_idletasks()
        x = chip.winfo_rootx()
        y = chip.winfo_rooty() + chip.winfo_height()
        try:
            self.file_menu.tk_popup(x, y)
        finally:
            self.file_menu.grab_release()
        return "break"

    def close_dxf(self) -> None:
        """✕ and the prompt shared with File > Open. No file: do nothing."""
        if self.source_path is None:
            return
        if not messagebox.askyesno(msg.CLOSE_DXF_TITLE, msg.CLOSE_DXF_BODY):
            return
        self.clear_session()

    def clear_session(self) -> None:
        """Drop the loaded drawing. The file on disk is not deleted."""
        self._exit_edit_modes()
        model = Model(ModelState())
        self.model = model
        self.source_path = None
        self.header = {}
        self.viewer.set_model(model.state)
        self.root.title(_TITLE)
        self._show_empty_hint()
        self._ensure_workflow()
        self._retarget_model(model, start=False, layer_of=None)
        self.status_var.set(_STARTUP_STATUS)

    def on_apply_all(self) -> None:
        """M4: Apply All drives the batch (snapshot -> re-place each
        pending live -> apply in click order; skips toasted)."""
        if self.workflow is None:
            return
        applied, skips = self.workflow.apply_all()
        self._update_confirm()
        if applied:
            self.summary_var.set("")

    def _on_undo_key(self, _ev=None):
        """Ctrl+Z. ``return "break"`` so the key is not also typed."""
        self.on_undo()
        return "break"

    def _on_redo_key(self, _ev=None):
        """Ctrl+Y. ``return "break"`` so the key is not also typed."""
        self.on_redo()
        return "break"

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

    def on_redo(self) -> None:
        if self.workflow is None:
            return
        self.workflow.redo()
        self._update_confirm()
        if self.fold_panel is not None:
            self.fold_panel.on_model_change()
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

    def _update_confirm(self) -> None:
        from ui.workflow import WorkflowState
        if self.workflow is None:
            self.summary_var.set("")
            return
        st = self.workflow.fsm.state
        s = self.workflow.summary_line()
        self.summary_var.set(s if st == WorkflowState.SIDE_PICKED else "")

    def export_dialog(self) -> None:
        """Final preview. Back leaves the working model untouched."""
        if self.model is None or self.workflow is None or self.source_path is None:
            messagebox.showinfo(msg.EXPORT_TITLE, msg.EXPORT_NEED_FILE)
            return
        from ui.export_dialog import ExportDialog

        initial = self.export_dir or self.source_path.parent
        dialog = ExportDialog(
            self.root,
            self.model,
            self.header,
            self.source_path,
            self.workflow.stack.load_snapshot,
            initial,
        )
        self.root.wait_window(dialog)
        if dialog.saved_path is not None:
            self.export_dir = dialog.saved_path.parent
            self.status_var.set(
                msg.EXPORT_SAVED.format(name=dialog.saved_path.name)
            )

    def open_dialog(self) -> None:
        if self.source_path is not None:
            if not messagebox.askyesno(msg.CLOSE_DXF_TITLE, msg.CLOSE_DXF_BODY):
                return
            self.clear_session()
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
        self._exit_edit_modes()
        model = Model(result.model_state)
        self.model = model
        self.source_path = path
        self.header = dict(result.header)
        self.viewer.set_model(model.state)
        self._hide_empty_hint()
        self.root.title(f"{_TITLE} - {path.name}")
        self._ensure_workflow()
        self._retarget_model(model, start=True, layer_of=result.layer_of)
        if result.warnings:
            messagebox.showwarning(
                "Loaded with warnings",
                "\n".join(result.warnings),
            )
        self.status_var.set(
            f"{path.name}: {len(result.model_state.primitives)} entities loaded"
        )


def main() -> int:
    _set_windows_app_id()
    root = tk.Tk()
    # Hide until the icon is applied. A window that first appears as
    # python.exe keeps that taskbar icon for the rest of the session.
    root.withdraw()
    app = App(root)
    root.deiconify()
    try:
        root.state("zoomed")
    except tk.TclError:
        pass
    if len(sys.argv) > 1:
        app.open_path(Path(sys.argv[1]))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
