# 2026-10-10 — Rail order restored

User request, not a milestone. The 2026-10-09 numbering (session log `documentation/sessions/2026-10-09-RAIL-STEPS.md`) is reverted.

## What changed

Section order in `Sidebar.body` is Dogbone, Folds, Trim. Titles in `ui/messages.py` are `Dogbone`, `Folds`, and `Trim`. The header title no longer wraps. Undo, Redo, and Revert stay on `Sidebar.pin`.

Docs updated the same day: `README.md` Use, `documentation/briefs/UI-UPGRADE.md` ("Revision — 2026-10-10"), ISSUE-021, and the Sidebar sentence in `documentation/briefs/MINI-SPRINTS.md`. The 2026-10-09 session log was left as written.

## Gates

```
pytest -q tests/test_ui_collapsible.py tests/test_ui_escape.py tests/test_app_open_retarget.py
17 passed, 1 skipped
```
