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
STATUS_PICK_EDGE1 = "Click edge 1 (the click promotes to the full collinear run)."
STATUS_PICK_EDGE2 = "Click edge 2."
STATUS_GHOSTS = "Click a ghost preview to choose the dogbone side."
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
UNDO_EMPTY = "Nothing to undo."
REVERT_TOAST = "Reverted to the original DXF."
REVERT_CONFIRM = ("Revert to Original discards every applied dogbone and "
                  "flag decision. Continue?")
REVERT_TITLE = "Revert to Original"
BTN_APPLY_ALL = "Apply All"
BTN_UNDO = "Undo"
BTN_REVERT = "Revert to Original"
PANEL_TITLE = "Tool"
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

# -- fold designation (M5b) ---------------------------------------------------
FOLD_MODE_ENTER = ("Fold mode: click or box-select lines to designate / "
                   "undesignate folds. Middle-drag pans; Esc exits.")
FOLD_MODE_EXIT = "Exited fold mode."
FOLD_MODE_TOGGLE_ON = "Designate Folds"
FOLD_MODE_TOGGLE_OFF = "Exit Fold Mode"
FOLD_BADGE = "{n} of {m} straight lines designated"
FOLD_PATTERN_LABEL = "Auto-pick layers:"
FOLD_PATTERN_DEFAULTS = "bend, fold, centerline"
FOLD_DESIGNATED_WARNING = "fold {eid} runs within {eps} mm of contour edge {other}"

# -- manual trim tool (ADR-025) ----------------------------------------------
TRIM_MODE_ENTER = ("Trim mode: click the LINE end you want to move — it snaps "
                   "to its closest intersection. Esc exits.")
TRIM_MODE_EXIT = "Exited trim mode."
TRIM_MODE_TOGGLE_ON = "Trim to Closest"
TRIM_MODE_TOGGLE_OFF = "Exit Trim Mode"
TRIM_PICK_STATUS = "Click a line near the end you want to trim or extend."
TRIM_TOAST_REFUSED = "Trim refused: {reason}"
TRIM_PREVIEW_STATUS = "Review the trim preview, then Confirm or Esc to cancel."
TRIM_TOAST_APPLIED = "Trim applied."
TRIM_DELETE_APPLIED = "Stray line deleted."
TRIM_PREVIEW_DELETE = "Stray line (no attachments) — the whole run will be deleted."
TRIM_PILL_CONFIRM = "CONFIRM\nTRIM"


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