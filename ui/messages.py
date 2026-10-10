"""User-facing strings for the corner workflow (M3 brief: ui/messages.py).

Single home for every string the workflow shows (status line, prompts,
toasts, deletion summary). The summary format is pinned byte-exact by the
brief: "Deleting: N LINE, N ARC — Trimming: N — Flagged: N CIRCLE, N MTEXT"
(N=0 terms included verbatim per the format string, separators are the
em dash U+2014 with single spaces).

Refusal strings are NOT defined here — they come verbatim from the engine's
``CornerResult.refusals`` / ``Refusal.reason`` (brief item 5: no UI
reinterpretation). This module only carries the boilerplate around them.
"""
from __future__ import annotations

DASH = " — "


# -- status line / prompts (state entry texts) -------------------------------
STATUS_IDLE = "Click two edges to place a dogbone corner."
STATUS_PICK_EDGE1 = (
    "Click edge 1 (the click promotes to the full collinear run). "
    "Press Esc to cancel."
)
STATUS_PICK_EDGE2 = "Click edge 2. Press Esc to cancel."
STATUS_GHOSTS = (
    "Click a ghost preview to choose the dogbone side. Press Esc to cancel."
)
STATUS_PREVIEW = "Review the deletion preview, then Confirm or press Esc to restart."

# -- flash / restart ---------------------------------------------------------
PROMOTED_FLASH = "Edge promoted: {eid}"
SAME_EDGE_INLINE = "That is the same edge — pick a DIFFERENT second edge."
RESTARTED = "Pick restarted."

# -- toasts ------------------------------------------------------------------
TOAST_REFUSED = "Corner refused: {reason}"
TOAST_APPLIED = "Corner applied."
TOAST_PENDING_FLAG = ("Flagged entity awaiting decision — "
                      "use the flag buttons before confirming ({reasons}).")

# -- apply all / undo / revert (M4) -------------------------------------------
ENQUEUED_TOAST = "Corner queued ({n} pending) — Apply All to apply."
STATUS_PENDING_COUNT = "Pending: {n}"
STATUS_QUEUE_EMPTY = "No pending corners — click two edges to place one."
APPLY_ALL_TOAST = "Applied {n} corner{s}."
APPLY_ALL_NONE = "No pending corners to apply."
APPLY_ALL_SKIPPED = "Skipped {n} corner{s}: {reasons}"
UNDO_TOAST = "Undo — restored the previous state."
UNDO_APPLIED = "Undo — Apply All undone. Queued corners are back."
UNDO_QUEUED = "Undo — removed the last queued corner."
UNDO_EMPTY = "Nothing to undo."
REDO_TOAST = "Redo — restored the undone state."
REDO_EMPTY = "Nothing to redo."
REVERT_TOAST = "Reverted to the original DXF."
REVERT_CONFIRM = ("Revert to Original discards every applied dogbone and "
                  "flag decision. Continue?")
REVERT_TITLE = "Revert to Original"
BTN_APPLY_ALL = "Apply All"
BTN_UNDO = "Undo"
BTN_REDO = "Redo"
BTN_REVERT = "Revert to Original"
# Left-rail section titles (collapsible). Order in the shell is
# Step 1 folds, Step 2 dogbone, Step 3 trim.
# Undo/Redo/Revert are pinned above them.
SECTION_FOLDS = "Step 1 — Designate Fold Lines"
SECTION_DOGBONE = "Step 2 — Dogbone"
SECTION_TRIM = "Step 3 — Trim"
SECTION_MODE_ON = "on"
PANEL_TITLE = SECTION_DOGBONE
LABEL_DIAMETER = "Tool diameter:"
UNIT_MM = "mm"
UNIT_IN = "inch"
DIA_READOUT = "Dia {dia:.4f} {unit} → R {r:.4f} mm"
MM_PER_IN = 25.4

# -- buttons -----------------------------------------------------------------
BTN_CONFIRM = "Confirm"
BTN_CANCEL = "Cancel"

# -- flag prompt (first-occurrence yes/no, ADR-009 sticky) -------------------
# The brief's flow says "yes/no"; CAM part-owners think in keep/delete, so
# the buttons carry both words.
FLAG_PROMPT_TITLE = "Flagged entity near the corner"
FLAG_PROMPT_TEXT = (
    "{kind} {eid} ({reason}) — delete it?\n"
    "Your choice is remembered for this session."
)
FLAG_PROMPT_YES = "Delete — yes"
FLAG_PROMPT_NO = "Keep — no"

# Flag card (fixed dock on the canvas). One line above Delete and Keep.
# Buttons stay in fixed rectangles so a second click hits the same control.
CHORD_CARD_BODY = "This {kind} crosses the relief."
CHORD_CARD_DELETE = "Delete"
CHORD_CARD_KEEP = "Keep"
CHORD_CARD_KIND = {
    "LINE": "line",
    "ARC": "arc",
    "CIRCLE": "circle",
    "POINT": "point",
    "MTEXT": "note",
}
FLAG_CARD_COUNT = "{n}/{m}"
FLAG_CARD_BODY = {
    "CHORD_CROSSER": CHORD_CARD_BODY,
    "CASCADE_DANGLING": "This {kind} is no longer attached to the part.",
    "CIRCLE_IN_WINDOW": "This circle lies in the relief.",
    "MTEXT_IN_WINDOW": "This note lies in the relief.",
    "ARC_ENDPOINT_IN": "This arc ends inside the relief.",
}

# -- fold designation (M5b) ---------------------------------------------------
FOLD_MODE_ENTER = ("Fold mode: click a line to designate / undesignate it. "
                   "Drag pans; right-drag box-selects; Esc exits.")
FOLD_BOX_HINT = "Right-drag to box-select"
FOLD_MODE_EXIT = "Exited fold mode."
FOLD_MODE_TOGGLE_ON = "Designate Folds"
FOLD_MODE_TOGGLE_OFF = "Save Selection"
FOLD_BADGE = "{n} of {m} straight lines designated"
FOLD_PATTERN_LABEL = "Bend import keywords"
FOLD_PATTERN_HINT = (
    "On import, straight lines on layers whose names contain these words "
    "are marked as bends."
)
FOLD_PATTERN_DEFAULTS = "bend, fold, centerline"
FOLD_LAYER_HEADING = "Layers with straight lines"
FOLD_LAYER_HINT = "Click a layer to set it as a fold layer."
FOLD_LAYER_ROW = "{name} ({count})"
FOLD_DESIGNATED_WARNING = "fold {eid} runs within {eps} mm of contour edge {other}"

# -- manual trim tool (ADR-025) ----------------------------------------------
TRIM_MODE_ENTER = ("Trim mode: click the LINE end you want to move — it snaps "
                   "to its closest intersection. Esc exits.")
TRIM_MODE_EXIT = "Exited trim mode."
TRIM_MODE_TOGGLE_ON = "Trim to Closest"
TRIM_MODE_TOGGLE_OFF = "Done"
TRIM_HINT = (
    "Click a line near the end you want to trim or extend. Ctrl+Z undoes."
)
TRIM_PICK_STATUS = "Click a line near the end you want to trim or extend."
TRIM_TOAST_REFUSED = "Trim refused: {reason}"
TRIM_PREVIEW_STATUS = "Review the trim preview, then Confirm or Esc to cancel."
TRIM_TOAST_APPLIED = "Trim applied."
TRIM_DELETE_APPLIED = "Stray line deleted."
TRIM_PREVIEW_DELETE = "Stray line (no attachments) — the whole run will be deleted."
TRIM_PREVIEW_SPAN_DELETE = (
    "The collinear span up to the nearest intersection on each side will be deleted."
)
TRIM_SPAN_DELETE_APPLIED = "Collinear span deleted."
TRIM_PILL_CONFIRM = "Confirm trim"

# -- export dialog (M6 + M6.5 watermark checkbox) ----------------------------
EXPORT_MENU = "Export DXF..."
EXPORT_TITLE = "Export DXF"
EXPORT_NEED_FILE = "Open a DXF before exporting."
EMPTY_CANVAS = "Add a DXF to get started"
EMPTY_OPEN = "Add a DXF"
CLOSE_DXF_TITLE = "Close current DXF?"
CLOSE_DXF_BODY = (
    "This clears the drawing from the session. The file on disk is not deleted."
)
EXPORT_FOLDER = "Folder"
EXPORT_BROWSE = "Browse..."
EXPORT_FILENAME = "File name"
EXPORT_WATERMARK = "Remove SolidWorks Educational watermark"
EXPORT_OK = "OK"
EXPORT_BACK = "Back"
EXPORT_EXISTS = "A file with that name already exists. Replace it?"
EXPORT_EXISTS_TITLE = "Replace file"
EXPORT_NO_NAME = "Enter a file name."
EXPORT_SAVED = "Exported {name}."
EXPORT_AUDIT_PENDING = "The health check runs when you press OK."


def _counts(pairs: list[tuple[str, int]]) -> str:
    return ", ".join(f"{n} {name}" for name, n in pairs)


def deletion_summary(
    del_lines: int,
    del_arcs: int,
    trim_count: int,
    flag_circles: int,
    flag_mtexts: int,
) -> str:
    """Exact brief format:
    ``Deleting: N LINE, N ARC — Trimming: N — Flagged: N CIRCLE, N MTEXT``.
    """
    return (
        f"Deleting: {del_lines} LINE, {del_arcs} ARC"
        f"{DASH}Trimming: {trim_count}"
        f"{DASH}Flagged: {flag_circles} CIRCLE, {flag_mtexts} MTEXT"
    )


def reasons_text(reasons: list[str]) -> str:
    """Bullet-less reason list appended to the summary line."""
    return " | ".join(reasons)