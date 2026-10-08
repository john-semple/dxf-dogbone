# Brief — M4b: Apply-to-Similar (dot flow)

**Status: planned 2026-10-07 (ADR-019 + ADR-020 loop-1 + ADR-021 loop-2 + ADR-023
loop-3 technical pins; supersedes all earlier drafts of this brief).**

**Registers:** ISSUE-018 (apply-to-similar, re-scoped to the dot flow).
**Feature B (guided tour) is NOT in this sprint** — registered as M4c per
ADR-022 with its own brief (`briefs/M4c.md`).

**Builds on:** M4's `ApplyQueue` / `SnapshotStack` / `ApplyAllWorkflowUI` seams.

**Files you own:** `rules/similar.py` (new), `ui/similar_panel.py` (new),
`ui/theme.py` (two new keys ONLY: `similar_on`/`similar_off`), `ui/messages.py`
(new M4b strings ONLY), `geometry/tolerances.py` (two new constants ONLY), glue
in `app.py`, `tools/verify_gui.py` (new drive), CONTRACTS similarity section,
tests. `ui/workflow.py`, `ui/apply_panel.py`, `model/`, `rules/engine.py`,
`rules/filters.py`, `geometry/` internals stay untouched (gap >2 loops → STOP,
log). **Estimate: 8–12h** (ADR-021(k); ADR-019's 3–4h and ADR-020's 5–8h are
void).

## The flow (user request; ADR-019 + ADR-020 + ADR-021 + ADR-023)

1. **Arm → Confirm.** Dot mode is OPT-IN: an app.py-glue **"Apply to Similar"**
   arm button (ADR-021(a)) flips a boolean on the ONE SimilarWorkflowUI instance
   constructed **at load** (ADR-023(a) — never a second bound instance: double
   `add=True` bindings double-fire; a replacement instance's fresh SnapshotStack
   erases undo history). Armed → the NEXT Confirm applies the template
   immediately as its own one-corner batch. Unarmed → Confirm = M4 enqueue,
   BYTE-UNCHANGED.
2. **Capture + entry.** The armed `confirm_click` intercepts at
   `confirm_click` (ADR-023(b)): grandparent `WorkflowUI.confirm_click(self)`
   then the dot-entry path — NOT ApplyAllWorkflowUI's post-confirm body (its
   ENQUEUED_TOAST + PICK_EDGE1 restart are byte-wrong for armed mode).
   `TemplateShape` is captured inside the armed `apply()` override, pre-mutation,
   from `fsm.pending` eids + `resolve_edge` on pre-apply primitives +
   `res.dogbone` (ADR-023(c) — the FSM restart wipes pick state post-apply).
3. **Dots.** Matches render at candidate apexes: **filled = will apply (green,
   `similar_on`)**, **hollow/X-slit = deselected (neutral gray, `similar_off`)** —
   shape carries the state, color secondary; NEVER delete-red (ADR-020(d)).
   Default all filled. Each dot: pinned minimum screen size + deletion/flag
   badge ("3L 1A +2F" — session pins exact grammar). Template corner marked
   distinctly, never applies twice. **Green = appliable — hard invariant**
   (ADR-021(d)): refused-at-entry candidates are EXCLUDED; entry-time argmin
   mapping failures exclude + status note, never a crash (ADR-023(f)).
4. **Interactions (ADR-020(c) + ADR-021(h)):** click-release (no drag) = toggle
   (press+drag = pan; deferred commit so a double-click's first release doesn't
   double-toggle); double-click (or right-click) = click-through zoom preview
   (red preview read-only; pre-zoom transform stored/restored — ADR-020(n));
   any click or Esc returns from the detour; **Esc at the map = exit dot mode**
   (match set dropped PERMANENTLY — toast says so; template stays applied).
   Canvas-miss = no-op. Hover → status line (precomputed summary, EXACT M3
   format). Apply All disabled while dot mode is active (glue-level
   `apply_btn` config + `_notify_queue` guard, ADR-023(i); pending count still
   displayed).
5. **Go.** Applies every still-selected candidate in document order. No matches
   → toast + clean exit. All deselected → zero mutations. Go never blocked
   (ADR-020(j)). Queued pendings persist through dot mode (ADR-021(i)); a corner
   both queued and green applies at Go and warn-and-skips OVERLAP at the later
   Apply All (documented passthrough; self-referential toast accepted as
   cosmetic, ADR-023(l)).

## Predicate (ADR-019(a)/(b) as amended by ADR-020(b)/(i) + ADR-021(b)/(c) + ADR-023(d)/(e))

Candidate matches template iff BOTH:

- **Angle:** same CORNER angle (compute_apex half-angle ×2, ADR-015(g)) within
  `ANG_TOL_DEG = 2.0°` on that quantity.
- **Run shape:** promoted-run member count equal AND per-member length sequence
  equivalent under reversal AND **role-swap (edge1↔edge2)**, each member within
  `LEN_TOL_MM = 0.01`. **Composite-run rule (ADR-023(d)):** a run whose
  flattened members include eids absent from primitives (rebuilt composites)
  counts as ONE member of length |run.b − run.a| — template capture and
  candidates alike.

**Argmin mapping (ADR-023(e)):** mapped center = `apex_c + r · unit(L(center_t −
apex_t))` per matched role assignment (L = affine frame map u1→v1, u2→v2;
renormalized+rescaled — affine-only leaves a 55× EPS_COINCIDE error at 2°
drift); pick the (Side, flip) whose ghost center is nearest; assert vs the
argmin ghost within EPS_COINCIDE. Argmin robustness: the ghost-direction set is
invariant under sign/role perturbations; min ghost separation r√2.

**Enumeration + document order (ADR-020(l) + ADR-023(k)):** per-Seg
`chain_run` promotion, dedup by canonical run eid (insertion-ordered — no
set-iteration order; PYTHONHASHSEED discipline), apex-gate first. "Document
order" = index of the run's first-appearing member in primitives. **Exclusions:**
template corner; dogboned corners; apex-gate failures; entry-precompute
refusals; mapping-assert failures (ADR-023(f)). Tear debris is NOT a predicate
input.

New pure surface (headless; imports **rules.engine** + geometry — ADR-023(k);
never model/ui/tkinter/ezdxf):

```python
def similar_corners(primitives: list[Entity], template_shape: TemplateShape,
                    ang_tol_deg: float = ANG_TOL_DEG,
                    len_tol_mm: float = LEN_TOL_MM,
                    eps_construction: float = EPS_CONSTRUCTION,
                    eps_coincide: float = EPS_COINCIDE) -> list[SimilarMatch]

@dataclass(frozen=True)
class TemplateShape:      # captured at armed-apply, PRE-mutation (ADR-023(c))
    edge1_members: tuple[str, ...]     # member eids (composite rule: ADR-023(d))
    edge2_members: tuple[str, ...]
    edge1_lengths: tuple[float, ...]  # per-member lengths (composite: one)
    edge2_lengths: tuple[float, ...]
    angle_deg: float                   # smaller CORNER angle
    center: Pt                        # template dogbone center (argmin seed)
    apex: Pt
    r: float                          # template radius (|center-apex|, asserted)

@dataclass(frozen=True)
class SimilarMatch:        # exact fields pinned by the session in CONTRACTS
    edge1_eid: str
    edge2_eid: str
    side: Side             # argmin-mapped per matched role assignment
    side_flip: int
    apex: Pt
    angle_deg: float
```

## Dot review UI — `ui/similar_panel.py`

- `SimilarWorkflowUI(ApplyAllWorkflowUI)` constructed ONCE at load
  (ADR-023(a)); dot mode consumes all canvas events (ADR-020(f)).
- **Redraw survival (ADR-021(f) + ADR-023(j)):** instance-level `viewer.redraw`
  wrapper installed at dot entry, removed at exit via `del` (not rebind);
  re-renders dots on EVERY redraw incl. programmatic (click-through zoom,
  `set_model`→fit fire no bindings). DoD tests dot survival through wheel-zoom
  AND programmatic redraw.
- **Precomputed previews:** all candidate CornerResults computed at entry
  (ADR-020(k)); Go's live re-place per ADR-016(k) stays the safety. Mid-Go flag
  decisions can stale entry-time badges (display-only; hover is entry-time
  information — documented, ADR-023(l)).
- Hover → status line. Click-through → full red preview, read-only.
- **Summary format:** local reimplementation + byte-equality pytest vs
  `WorkflowUI.summary_line()` (ADR-020(m)).
- **Mode-exit routine (ADR-023(j)):** (1) `del viewer.redraw` wrapper, (2)
  unbind the panel's add=True bindings, (3) cancel pending `after` callbacks
  (deferred toggle commits), (4) delete dot/badge canvas tag, (5) exit BEFORE
  undo/revert so the restored model's redraw cannot resurrect dots.
- Panel buttons: **Go** and **Cancel** (permanent drop, template stays).
  Undo/Revert during the mode exits it cleanly first.

## Go semantics (ADR-019(e), ADR-020(g), ADR-021(e), ADR-023(f))

- Document order; live re-place per ADR-016(k) with the **template dogbone's
  R**. Failure = M4 warn-and-skip VERBATIM; Go never blocked (ADR-020(j)).
- **Pending flags at Go (ADR-021(e)):** route through the sticky `decide_flag`
  first-occurrence flow (harness scripts it — M4 precedent), then re-place;
  still-refused → warn-and-skip verbatim.
- **Batch mechanism (ADR-020(g)):** one ApplyQueue instance per candidate OR a
  similar_panel-local subclass — the session picks and writes it into the
  CONTRACTS section.

## Undo (ADR-019(f) + ADR-020(g)/(h) + ADR-021(g) + ADR-023(g)/(h))

- Each selected candidate = its own one-corner batch; the template's armed
  Confirm was also its own batch; plain Undo pops the most recent one-corner
  batch. **Plain-Undo toast branches on the popped ledger label**
  (ADR-023(h)): similar-batch pops get the new granular toast ("Undid similar
  corner 2 of 3"); everything else falls through to super() with M4 strings
  BYTE-UNCHANGED (frozen `ApplyAllWorkflowUI.undo` hard-codes UNDO_TOAST).
- **Undo Batch lives in app.py glue** (persistent across mode exit); Undo Batch
  = pop-until-preGo **guarded by can_undo()** (ADR-023(g)) with plain
  `model.state == held_preGo` equality (M4's deepcopy bit-exact pattern).
  **Ledger keys = POST-PUSH stack length** (template T, candidates T+1..T+k);
  M4's own Apply-All pushes labeled via the subclass's `apply_all` override;
  unlabeled entries read as FOREIGN (availability disabled). Availability per
  ADR-020(h): enabled only while the top-of-stack segment above pre-Go is this
  batch's work; disabled when unwound/superseded/zero-mutations. New M4b toasts
  name what was undone. Revert-to-Original unchanged (M4).

## DoD

- pytest `test_rules_similar_*`: mirror pair matches; **1.9°-in / 2.1°-out
  boundary on the CORNER angle — WRITTEN FIRST (the argmin-renormalization
  canary, ADR-023(e))**; run-shape rejection; reversal + role-swap equivalence;
  90°-rotated fixture (argmin under the SWAPPED frame); template exclusion;
  dogboned-corner exclusion; refused-at-entry exclusion; **mapping-assert
  failure excludes (not crash)** (ADR-023(f)); **re-promoted-composite fixture**
  (T-cap template; composite-run rule, ADR-023(d)); LEN_TOL boundary; argmin
  assert (renormalized mapping) vs ghost centers.
- pytest dot-mode FSM tests: arm-button entry (armed Confirm applies + enters;
  unarmed Confirm enqueues, M4 byte-unchanged); **single instance, single bind
  set** (no double-fire — ADR-023(a)); armed confirm_click intercepts BEFORE
  ApplyAllWorkflowUI's post-confirm body (no ENQUEUED_TOAST leak —
  ADR-023(b)); toggle on release-no-drag; double-click zoom-only (deferred
  commit); click-through + view restore; two-level Esc (detour return; map-level
  exit w/ permanent-drop toast); 0-match exit; all-deselected Go (zero
  mutations); refused-candidate exclusion; flag-pending-at-Go routes decide_flag
  then re-places; warn-and-skip drops candidate; per-corner undo pops exactly
  one; **undo toast branch on ledger label** (ADR-023(h)); Undo Batch restores
  pre-Go; **guarded pop-until-preGo + foreign-ledger-entry disable**
  (ADR-023(g)); availability rule (unwound/superseded/zero-mutations/
  interleaved re-enable); queue coexistence passthrough; dot survival through
  wheel-zoom AND programmatic redraw; **mode-exit routine** (wrapper deleted,
  bindings unbound, afters cancelled, dot tag gone — ADR-023(j)); mid-mode
  Undo/Revert exit; summary byte-equality vs `WorkflowUI.summary_line()`; dot
  minimum-size assert; badge grammar incl. flag count.
- `tools/verify_gui.py` new drive, deterministic: **arm →** confirm corner2 on
  the before-file → corner3 found as match (argmin-mapped) → toggle corner3 red
  → Go → assert corner3 NOT applied + template applied → re-toggle green → Go
  → assert corner3 applied (golden center −47.2451, 49.2717 R 3.175 per
  SAMPLES.md); Undo ×1 pops only corner3; Undo Batch → pre-Go state (template
  still applied).
- verify_m2 / verify_gui --full / pytest all green; M3/M4 gates byte-unchanged;
  grep-clean (no hex literals outside ui/theme.py).
- Human checklist (~2 min): arm button; dots largish + visible on dark bg;
  filled/hollow + green/gray legible (squint test); single-click toggle;
  double-click zoom + return restores the map; hover summary reads; Go applies
  the same dogbone; per-corner Undo; Undo Batch escape after leaving the mode;
  zoom mid-mode keeps dots.

**Cite:** ADR-019 + ADR-020 + ADR-021 + ADR-023 (binding; newest wins),
ADR-016(j)(k), ADR-009, ADR-010, ADR-001; ISSUE-018; SPEC §11.5, §11.7;
CONTRACTS §1/§2 (reused surfaces) + the new similarity section this sprint pins.