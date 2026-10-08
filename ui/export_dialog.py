"""Final export preview — OK / Back, filename, watermark checkbox.

Renders the exact post-export geometry on a read-only Viewer (same canvas
class, no pan/zoom/pick). Back closes the dialog and does not touch the
working model. A failed health check leaves the dialog open and writes
nothing.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from dxf_io.export import export, prepare_export, render_export_log
from model.model import Model
from model.state import ModelState
from ui.canvas_view import Viewer
from ui.theme import COLORS, font as theme_font
import ui.messages as msg

# Viewer binds these in __init__. The preview must not pan, zoom, or pick.
_VIEWER_SEQUENCES = (
    "<ButtonPress-1>",
    "<B1-Motion>",
    "<ButtonRelease-1>",
    "<MouseWheel>",
    "<Motion>",
)


def default_export_filename(source: Path) -> str:
    """``<original>_dogbone.dxf`` from the source file's stem."""
    return f"{source.stem}_dogbone.dxf"


class ExportDialog(tk.Toplevel):
    """Modal preview. ``saved_dir`` is the folder of a successful export."""

    def __init__(
        self,
        master: tk.Misc,
        model: Model,
        header: dict,
        source_path: Path,
        original: ModelState | None,
        initial_dir: Path,
    ) -> None:
        super().__init__(master)
        self.title(msg.EXPORT_TITLE)
        self.model = model
        self.header = header
        self.source_path = Path(source_path)
        self.original = original
        self.saved_dir: Path | None = None
        self.saved_path: Path | None = None
        self._remove = tk.BooleanVar(value=True)
        self._folder = tk.StringVar(value=str(initial_dir))
        self._filename = tk.StringVar(value=default_export_filename(self.source_path))

        self.transient(master)
        self.configure(bg=COLORS["bg"])
        self.geometry("980x760")

        buttons = ttk.Frame(self)
        buttons.pack(fill=tk.X, side=tk.BOTTOM, padx=12, pady=8)
        ttk.Button(buttons, text=msg.EXPORT_BACK, command=self.back).pack(side=tk.RIGHT)
        ttk.Button(
            buttons, text=msg.EXPORT_OK, style="Accent.TButton", command=self.ok
        ).pack(side=tk.RIGHT, padx=(0, 8))

        form = ttk.Frame(self)
        form.pack(fill=tk.X, side=tk.TOP, padx=12, pady=(12, 4))
        ttk.Label(form, text=msg.EXPORT_FOLDER).grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self._folder, width=72).grid(
            row=0, column=1, sticky="ew", padx=8
        )
        ttk.Button(form, text=msg.EXPORT_BROWSE, command=self._browse).grid(row=0, column=2)
        ttk.Label(form, text=msg.EXPORT_FILENAME).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._name = ttk.Entry(form, textvariable=self._filename, width=72)
        self._name.grid(row=1, column=1, columnspan=2, sticky="ew", padx=8, pady=(8, 0))
        form.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            form,
            text=msg.EXPORT_WATERMARK,
            variable=self._remove,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._summary = tk.Text(
            self,
            height=8,
            wrap="word",
            bg=COLORS["bg_sunken"],
            fg=COLORS["fg"],
            insertbackground=COLORS["fg"],
            relief="flat",
            font=theme_font(9),
            highlightthickness=0,
        )
        self._summary.pack(fill=tk.X, side=tk.BOTTOM, padx=12, pady=(0, 4))

        self.viewer = Viewer(self, width=940, height=420)
        for sequence in _VIEWER_SEQUENCES:
            self.viewer.canvas.unbind(sequence)
        self.viewer.canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        self._remove.trace_add("write", lambda *_a: self._refresh())
        self._refresh()
        self._name.selection_range(0, "end")
        self._name.focus_set()
        self.grab_set()

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(
            parent=self,
            title=msg.EXPORT_FOLDER,
            initialdir=self._folder.get() or str(self.source_path.parent),
        )
        if chosen:
            self._folder.set(chosen)

    def _refresh(self) -> None:
        prepared = prepare_export(
            self.model.state, remove_watermark=bool(self._remove.get())
        )
        self._prepared = prepared
        self.viewer.set_model(prepared.state)
        text = render_export_log(
            prepared,
            remove_watermark=bool(self._remove.get()),
            original=self.original,
            audit_summary=msg.EXPORT_AUDIT_PENDING,
        )
        self._set_summary(text)

    def _set_summary(self, text: str) -> None:
        self._summary.configure(state="normal")
        self._summary.delete("1.0", "end")
        self._summary.insert("1.0", text)
        self._summary.configure(state="disabled")

    def back(self) -> None:
        """Close without writing and without changing the working model."""
        self.grab_release()
        self.destroy()

    def ok(self) -> None:
        name = self._filename.get().strip()
        if not name:
            messagebox.showerror(msg.EXPORT_TITLE, msg.EXPORT_NO_NAME, parent=self)
            return
        folder = Path(self._folder.get().strip() or str(self.source_path.parent))
        out_path = folder / name
        if out_path.exists():
            if not messagebox.askyesno(
                msg.EXPORT_EXISTS_TITLE, msg.EXPORT_EXISTS, parent=self
            ):
                return
        result = export(
            self.model.state,
            self.header,
            out_path,
            remove_watermark=bool(self._remove.get()),
            original=self.original,
        )
        if not result.written:
            self._set_summary(result.audit_summary)
            messagebox.showerror(msg.EXPORT_TITLE, result.audit_summary, parent=self)
            return
        self.saved_dir = folder
        self.saved_path = out_path
        self.grab_release()
        self.destroy()
