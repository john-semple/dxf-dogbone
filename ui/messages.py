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