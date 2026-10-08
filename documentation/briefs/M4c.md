# Brief — M4c: Guided Dogbone Tour (sequential walk)

> **Status: Not started**

Planned 2026-10-07 (ADR-022 sprint-start Q&A; supersedes the first-draft M4b Feature B text per ADR-019's split ruling).

**Registers:** ISSUE-019 (guided tour), ISSUE-010 (joint auto-detection — now
designed, owned by M4c1), ADR-009 amendment (e) (narrow, tour-scoped allow-all).
**Prerequisite:** M4b shipped (tour inherits its machinery: argmin mapping
ADR-020(i)/021(c), redraw-survival wrapper ADR-021(f), event-consumption
subclass ADR-020(f), one-corner batches ADR-020(g), mode-exit rules).

**Phases (one brief, two sittings; M4c2 starts only when M4c1's gates are
green):**
- **M4c1 — headless detector** (`rules/joints.py` + tests), 3–4h.
- **M4c2 — tour UI** (`ui/tour_panel.py` + FSM tests + drive), 4–6h.

**Files you own:** `rules/joints.py` (new, M4c1), `ui/tour_panel.py` (new,
M4c2), `ui/theme.py`/`ui/messages.py` (new keys/strings ONLY), `geometry/`
(only if a detector primitive is genuinely needed — pin first), glue in
`app.py`, `tools/verify_gui.py` (new drive), CONTRACTS sections, tests.
`ui/workflow.py`, `ui/apply_panel.py`, `ui/similar_panel.py`, `model/`,
`rules/engine.py`, `rules/filters.py`, `rules/similar.py`, `geometry/`
internals stay untouched (gap >2 loops → STOP, log).

## The flow (user request; ADR-022)

1. **Start Tour** (app-glue button). The detector finds candidate joints
   (recall-first — see below); the tour walks them in document order
   (ADR-020(l)), auto-zooming stop to stop.
2. **At each stop:** the engine's **suggested ghost** renders highlighted with
   its **red deletion preview** (never-cut: the preview is visible before Next
   applies). The stop carries **three stacked buttons, persistent through the
   tour** (user's design):
   - **Next** — apply the current selection (suggested or edited) and advance.
   - **Skip** — no dogbone here; advance; joint marked skipped.
   - **Edit** — reveal all four ghosts; a ghost click becomes the current
     selection and re-renders the preview; Edit never applies.
   Plus **Prev** — revisit the previous joint (skipped → normal stop; applied →
   read-only view of the applied dogbone, plain Undo pops it).
3. **Flags: zero modals, safe-split auto** (ADR-022(e)): debris
   (CASCADE_DANGLING) auto-deletes; ARC chord-crossers auto-TRIM (trim
   unavailable → keep + warning); CIRCLE/MTEXT/ARC-endpoint auto-KEEP; the
   non-blocking warning rides the stop summary. Sticky per ADR-009 (snapshots
   travel, Revert clears). Outside tour mode the modal flow is byte-unchanged.
4. **Refused joints show + auto-skip** (ADR-022(f)): stop flashes the engine
   refusal string, lands in the end report.
5. **Radius = current panel R**, live mid-tour (quick-picks re-place the
   current stop per ADR-016(k); applied joints are done).
6. **End of tour:** report — applied N, skipped M, auto-skipped-refused K,
   kept-flagged list per stop. Status line + toast (no new dialog).

## Detector (ADR-022(b)) — `rules/joints.py`, M4c1

- **Recall-first:** propose every plausible junction; false positives are
  skippable stops (cheap); misses recover via the normal manual flow (the tour
  is an assistant, never the only path).
- **Joint definition:** a pair of promoted runs (per-Seg `chain_run` promotion,
  dedup by canonical eid — ADR-020(l) machinery) sharing an endpoint region
  (adjacency within EPS_COINCIDE); apex gate + `place_corner` remain the
  authority — the detector proposes, the engine disposes.
- New pure surface (headless; imports geometry only; eid-referenced per
  ADR-010):

```python
def detect_joints(primitives: list[Entity],
                  eps_construction: float = EPS_CONSTRUCTION,
                  eps_coincide: float = EPS_COINCIDE) -> list[JointCandidate]

@dataclass(frozen=True)
class JointCandidate:
    edge1_eid: str
    edge2_eid: str
    apex: Pt                   # gate-pending (place CornerResult decides)
    order_index: int           # document order key (ADR-020(l))
```

## Suggestion algorithm (ADR-022(c)/(d))

- Suggested (Side, flip) at a stop = **mapped-center argmin from the user's
  most recent manual pick at a similar corner** (reuses M4b's argmin machinery
  + similarity predicate; the "template" is the last manual pick), falling back
  to a **clearance heuristic** (ghost center with max min-distance to
  non-corner entities in the corner window) when no similar prior exists.
- The suggestion is a SEED; every Next runs the FULL `place_corner` pipeline
  (truth table, overlap, flags). Session pins details in CONTRACTS.

## Tour UI (ADR-022(a)/(c)) — `ui/tour_panel.py`, M4c2

- `TourWorkflowUI(ApplyAllWorkflowUI)` — the M4b pattern: tour mode consumes
  all canvas events; pan/zoom stays live (redraw-survival wrapper per
  ADR-021(f)); Esc = exit tour cleanly (progress kept: applied joints stay
  applied; the walk position is lost — restart resumes from the report's
  undone list).
- Stop overlays: suggested-ghost highlight ring + red preview (the M3
  surfaces, read-only until Next); Edit reveals the four-ghost picker (the M3
  ghost render + `_ghost_at` hit-test, reused).
- Undo/Revert mid-tour exits the tour first (M4b mode-exit precedent).
- **Every applied joint = its own one-corner batch** (ADR-020(g)): plain Undo
  pops the last applied joint; report/stop state reflects the pop.

## DoD

### M4c1 (detector, headless)

- pytest `test_rules_joints_*`: **golden detection counts** — before-file: 3
  joints (both T-junctions + the ramp corner); after-file golden per
  SAMPLES.md; recall fixtures (shallow joint proposed-then-refused; open-tab
  mouth; tear debris near an apex); **syn corpus controls** — the 12-file
  SAMPLES-SYN.md manifest: positive files yield their specified joints,
  negative files yield zero (assert per manifest); dedup (each physical corner
  once); document-order key; apex-region sharing boundary tests.
- Suggestion unit tests: argmin-from-last-pick goldens (mirror pair; rotated
  role-swap per ADR-021(c)); clearance-heuristic fallback golden; suggestion
  is a seed (refused suggestion → refusal surfaces, no crash).
- verify_m2 / verify_gui --full / pytest all green, M3/M4/M4b gates
  byte-unchanged. (No UI exists yet — nothing else to gate.)

### M4c2 (tour UI)

- pytest tour FSM tests: Next applies + advances; Skip marks + advances; Edit
  reveals ghosts, ghost click re-renders preview, Edit never applies; Prev
  reopens skipped / read-only applied; refusal auto-skip + report entry;
  safe-split allow-all class mapping (delete/trim/keep per class; sticky
  travel in snapshots; Revert clears); zero modals in tour mode (scripted-UI
  assert); per-item undo pops exactly one; mid-tour Undo/Revert exit; redraw
  survival (wheel + programmatic, ADR-021(f)); panel-R change re-places
  current stop; end-report contents (applied/skipped/refused/kept-flagged).
- `tools/verify_gui.py` new drive: walk the before-file — 3 joints; apply 2 +
  skip 1, Edit-override the suggestion on one, refuse-auto-skip fixture;
  Undo ×1 pops exactly the last applied joint; report asserts; model-state
  golden (dogbone count 2, centers vs SAMPLES.md).
- verify_m2 / verify_gui --full / pytest all green; grep-clean.
- Human checklist (~2 min): Start Tour; suggested ghost + preview visible;
  Next applies and advances; Skip works; Edit shows four ghosts and override
  applies; Prev revisits; no modals appear; Undo pops one joint; Esc exits
  cleanly; end report reads right.

**Cite:** ADR-022 (binding), ADR-020(f)/(g)/(i)/(l), ADR-021(c)/(f), ADR-009
(amendment (e)), ADR-016(j)(k), ADR-010; ISSUE-019, ISSUE-010; SPEC §11.5
(truth table — the stop preview reuses it), §11.7; CONTRACTS §1/§2 (reused
surfaces) + the new detector/suggestion sections the sessions pin.