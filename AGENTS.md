# AGENTS.md — Session Entry Point

**Read order per session (exactly this, nothing more):**
1. This file
2. `documentation/briefs/M<your-milestone>.md`
3. SPEC/ADR sections cited *in that brief only*
4. Your module's section of `documentation/CONTRACTS.md`

## Project (30 seconds)

Python 3.11+ / tkinter / ezdxf — adds dogbone corner reliefs to SolidWorks sheet-metal DXF flat patterns. User clicks two edges in a GUI; engine computes/preview/checks; pure export. Windows. No ML. No numpy.

## Commands

```bat
run.bat                      :: bootstrap venv + pip install -r requirements.txt + launch app
pytest -q                    :: all tests (headless; MUST pass before any session ends)
python tools/verify_m2.py    :: M2 golden check (corner-local)
python tools/verify_gui.py   :: synthetic-click GUI harness (M1/M3/M5)
```

## Stack map

```
geometry/   pure math + entity dataclasses (stdlib ONLY, no ezdxf/tkinter/numpy)
rules/      engine: corner pipeline, truth table, promotion, hit-test (no ezdxf/tkinter)
model/      ModelState, snapshots, flag persistence (stdlib + geometry)
dxf_io/     load/export (ezdxf allowed), audit gate
ui/         thin tkinter shell ONLY (screen↔world, events → engine calls)
tools/      verify_* harnesses
```

Full import matrix + function signatures: `documentation/CONTRACTS.md` (binding; changes need an ADR).

## Hard invariants (violating any = failed session)

1. `geometry/`, `rules/`, `model/` import neither tkinter nor ezdxf.
2. No `==` on coordinates — use `geometry/tolerances.py` values, passed explicitly.
3. Rules reference entity IDs (`eid`), never coordinates or object refs (identity is stable across Apply/Undo/Revert).
4. Export is pure (deep copy); working model immutable under export.
5. Deletion preview is never cut (cut list: hover → fold trim/extend → box-select polish).
6. Blocked >2 loops → STOP, write blocker in session log, do NOT improvise around contracts.

## Conventions

- Docs canonical order: CONTRACTS.md > WORKED-EXAMPLE.md > SPEC.md (§11 overrides §1–10 where conflicting; ADRs override both; newest ADR wins conflicts).
- Status source of truth: `documentation/ISSUES.md` milestone table — but **single-writer**: only the session owning milestone M# edits its M# row; all sessions append `documentation/sessions/YYYY-MM-DD-M#.md` (done, test output pasted, decisions, blockers) — never edit another session's log.
- Tests: pytest (pinned). Test names: `test_<module>_<behavior>.py`. Fixtures for 90/60/120°, T-junction gate, shallow-refusal, chord-crosser, tangent stray, POINT-in-circle, ARC-in-circle, fold extend/trim + idempotency (SPEC §11.9).
- ADR-012 applies to any test touching promoted edges: member eids in results, composite after apply.
- Where docs disagree, raise it in the session log; CONTRACTS > WORKED-EXAMPLE > SPEC, then newest ADR.

## Before you start coding

Confirm in your first log entry: (a) brief read, (b) contracts section read, (c) pytest runs green pre-change. If pytest doesn't exist yet (M0/M1), say so — the brief tells you what scaffold to create.