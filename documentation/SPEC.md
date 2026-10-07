# DXF Dogbone Tool — Project Specification & Agent Context

**Project:** DXF corner radiusing / dogbone tool for SolidWorks sheet metal flat patterns
**Target user:** Solo machinist using SolidWorks sheet metal → DXF flat pattern export → Fusion 360 CAM
**Platform:** Windows (native Python, no WSL needed)
**Language:** Python 3, minimal dependencies (`ezdxf` + stdlib tkinter)
**Status:** Spec agreed 2026-09-28. Code not yet written.

---

## 1. Purpose

Take DXF files exported from SolidWorks sheet metal and replace tight inside corners with **dogbones** (corner relief cuts) sized to a given tool diameter, so a round end mill can reach the corner. SolidWorks flat patterns contain "tear" relief geometry at corners that must be removed and replaced cleanly, and fold (bend) lines must be extended/trimmed to the new radiused edges.

## 2. Scope Decisions (agreed)

- **No machine learning.** Deterministic computational geometry only.
- **V1 feature = dogbone only.** Feature-based expansion deferred.
- V1 is **manual-click first** (safe, direct). Auto-detection of corners is a future sprint.

## 3. Input / Output

- **Input:** DXF (SolidWorks flat pattern export). Sample files confirmed pure `LINE` / `ARC` / `CIRCLE` / `POINT` / `MTEXT`, all on layer `0`.
- **Output:** new DXF file, **filename typed by user in GUI at end of process**. Original file never modified.
- **Output DXF version** matches input (R2000/AC1015).
- **Units: millimeters.** Radius input in mm, default `1.5875` (1/8" tool diameter = 3.175 mm), editable in GUI.

## 4. Core Algorithm

### 4.1 Corner / dogbone geometry (confirmed)
- **Apex** = intersection of the two main edges' *infinite lines* (theoretical sharp corner).
- **Dogbone circle:** center on the air-side bisector at distance **R** from apex; circle passes exactly through the apex.
- **Do not force a 180° semicircle** — arc span varies with corner angle. Edges are extended/trimmed to their far intersections with the circle; the arc between those intersections (passing through the apex) replaces the corner.
- Angled main edges may need extension to meet the dogbone when R is small (user did this manually for sample corner #3).
- **Shallow-angle corners (near-collinear edges): program refuses** with a warning rather than producing a degenerate dogbone.

### 4.2 Corner selection workflow (GUI)
1. User clicks **edge 1**, then **edge 2**.
2. **Two ghost dogbone previews** appear (one per valid side) — this replaces a separate arrow-step for T-junctions; works uniformly for normal corners and T-junctions.
3. User clicks the ghost they want.
4. **Deletion preview:** everything to be deleted is highlighted **red**; user confirms/backs out.

Manual corner add: **user explicitly clicks the two edges** (user input is the safe, direct fallback — no auto edge-picking in V1).

### 4.3 Tear-geometry deletion rule (confirmed)
- **Exempt:** the two main edges (rebuilt, not deleted) and designated fold lines (extended/trimmed, never deleted).
- **Window:** entities within **3–4× bit diameter** of the corner are considered (use 4×).
- **Delete:** any entity in the window with **an endpoint inside the dogbone circle**.
- **Strays** (cross the circle, no endpoint inside, not a main edge or fold line): **trimmed at the circle**.
- **Preview mode is the safety net** — user sees exactly what will be deleted before confirming.
- Known limitation (accepted): a legitimate short edge starting inside the circle would be deleted; preview catches it.

### 4.4 Dogbone overlap
- If two selected dogbone circles intersect: **warn and skip the second**. (User states this shouldn't occur in practice.)

### 4.5 Fold lines
- **Auto-detect:** if layers exist with case-insensitive names containing `bend`, `fold`, or `centerline`, preselect those entities. Match list **editable in GUI** (user doesn't yet know SolidWorks export layer names).
- **User selection:** regardless of auto-detect, user can select/deselect fold lines in the GUI (single-layer DXFs must still work).
- **On export:** designated fold lines are **moved** (not copied) to layer **`FOLD_LINES`**, drawn in a distinct color.
- Fold lines are straight `LINE` entities **only** (for now).
- Fold lines are never collinear with / lying on top of contour lines (user: "should never meet").
- **Extend/trim rule:** fold-line endpoints end **exactly at the dogbone arc** — extend straight if short, trim if crossing ("extend until it bumps into something, usually the dogbone"). Confirmed in sample: one fold line was trimmed where dogbone crossed it, others extended to reach the arc.
- **Trim/extend executes at export time** against all applied dogbones — order-independent, so folds can be designated before or after radiusing.

## 5. GUI Behavior

- **Canvas:** pan/zoom, hover highlight, clickable entities, ghost previews, red deletion highlight.
- **Undo model:** toggle multiple corners → all pending changes previewed → single **Apply All** → **snapshot-stack Undo** (multiple undos permitted; per §11.7 which supersedes the earlier single-level plan) + **Revert to Original** (nuclear option).
- **Final export step:** a **final DXF preview with OK / Back buttons** before writing the file; filename entered here.

## 6. Unsupported Entities

Polylines, splines, ellipses, etc.: **passed through untouched, with a warning listing them**. (SolidWorks exports so far are pure LINE/ARC, so may never trigger.)

## 7. Hole Protection

None needed in V1. All holes are >1/8" and/or far from joints. (Revisit if small features near corners appear.)

## 8. V1 / Future Sprint Split

**V1 (target: usable within a few hours of work):**
1. Load DXF; render LINE/ARC/CIRCLE/POINT/MTEXT on pan/zoom canvas with hover highlight
2. Corner workflow (click two edges → ghost previews → pick side → red deletion preview → confirm)
3. Tear cleanup per §4.3
4. Dogbone overlap warn-and-skip
5. Fold-line selection panel/mode + auto-detect on bend-named layers; export on `FOLD_LINES`
6. Apply All + snapshot-stack Undo (multiple undos permitted, per §11.7/ADR-001) + Revert to Original
7. Final preview (OK/Back) + user-named export

**Future sprints:**
- Auto-detection of too-tight inside corners (highlight candidates)
- Circle/lasso a missed corner → program picks the two edges
- LWPOLYLINE / SPLINE support
- Per-corner radius override, keyboard shortcuts, snap indicators
- Batch mode (folder of DXFs)

## 9. Environment / Location

- **Project folder:** `C:\Users\Owner\Projects\dxf-dogbone\`
- User has small programming background; codes via AI agents (Cursor, OpenChamber).
- Python 3 presence to be verified at execution stage (`pip install ezdxf` required).
- Sample before/after DXFs from user to be added as built-in test files (user will provide placement later).
- Known user note: sample file's two larger dogbones (R=3.175) were a user error (entered 1/8" as radius instead of diameter); all radii should be 1.5875 mm.

## 10. Sample Data (user-provided, referenced during spec)

- Before: `base-rectangular-before-AI.DXF` — three T/corners cluttered with tear geometry
- After: `Flat pattern - base-rectangular - partially radiused.DXF` — same three corners dogboned (R=3.175 ×2, R=1.5875 ×1), tear geometry gone, fold lines at y≈51.2634 extended/trimmed to the new edges
- Difference confirms: dogbone arc replaces corner, main edges rebuilt to arc, local tear segments deleted, fold lines end on the dogbone arc.

## 11. Technical Requirements v2 (post-review, 2026-09-28)

Derived from three independent reviews (programmer, CAD-user, PM) of this spec, then hardened by three further senior-programmer review loops. **Reading order note: §11 supersedes §1–10 where they conflict; ADRs in DECISIONS.md supersede both; CONTRACTS.md is binding for interfaces.** Sections below extend/override §1–10 where they conflict.

### 11.1 Architecture (non-negotiable)

| Module | Responsibility | May import |
|---|---|---|
| `geometry/` | Pure math: points, lines, arcs, circle intersection, trim/extend, tolerance-parameterized predicates | stdlib only *(numpy removed by ADR-008 — see §11.10)* |
| `dxf_io/` | Load/save, entity census, layer ops, audit | ezdxf, geometry |
| `rules/` | Deletion rule, protected set, fold extend/trim, overlap check | geometry |
| `model/` | Working document state: entity list, snapshots, undo | stdlib |
| `ui/` | Thin tkinter shell: renders model, translates clicks → engine calls | tkinter, model, rules |
| `app.py` | Composition root, entry point | all |

*(v3 amendments, ADR-008: entity dataclasses live in `geometry/` — pure, stdlib-only; `model/` may additionally import geometry types; hit-testing, EPS_PICK derivation from the zoom transform, and edge promotion are `rules/` functions — headless-testable, UI only converts screen→world. See CONTRACTS.md §5 ownership matrix.)*

- The geometry + rules core **must run headless** (no tkinter import). All unit tests run against it.
- UI never computes geometry; engine never touches tkinter.

### 11.2 Tolerance policy

Single source: `geometry/tolerances.py`. Every geometric predicate takes an explicit tolerance parameter with a documented default. Raw `==` on coordinates is banned.

| Name | Default | Justification |
|---|---|---|
| `EPS_CONSTRUCTION` | 1e-9 mm | analytic construction (apex, circle centers) |
| `EPS_COINCIDE` | 1e-3 mm | point/endpoint coincide decisions; DXF rounds to 4 decimals |
| `EPS_PICK` | world-units ≙ 3 screen px | GUI picking, derived from zoom |

Documented uses: point-in-circle (COINCIDE), on-arc (COINCIDE), collinear (COINCIDE + direction dot ≥ 0.999), tangency (CONSTRUCTION + COINCIDE), overlap of circles (strict with EPS_COINCIDE; tangent circles are allowed).

### 11.3 Load-time validation (refuse upfront, with reason)

1. **`$INSUNITS`** must be 4 (mm); else refuse with dialog. (Also guards the 25.4× radius error class.)
2. **DXF version:** accept R2000+; warn on R12; refuse older. Output version = input version (copy header of loaded doc).
3. **Entity census:** if contour-scale LWPOLYLINE/SPLINE/ELLIPSE present → refuse ("V1 cannot process"); scattered unsupported entities → passthrough + warning list (per §6).
4. **Duplicate entities** (same type, endpoints within EPS_COINCIDE): merge duplicates, log count.
5. **Fold lines:** each designated fold's distance to every contour edge must exceed EPS_COINCIDE — else warn per violating fold (never silently assume §4.5's rule).

### 11.3a Entity identity (v3)

Every primitive carries an immutable string ID (`eid`: DXF handle at load, minted for new entities). All rule decisions — duplicate-pick refusal, protected-set membership, flagged decisions, census dedup — reference `eid`, never object references or raw coordinates (coordinates move under rebuild; object identity dies under snapshot swap). Snapshots preserve the ID↔entity mapping; invariant: identity is stable across Apply/Undo/Revert. (ADR-010.)

### 11.4 Corner construction (hardened §4.1)

- Apex = intersection of the two clicked edges' supporting lines.
- **Rebuild is per-endpoint, operationally defined:** the rebuilt endpoint = the **unique non-apex intersection** of the edge's supporting line with the dogbone circle (the circle always passes through the apex, so exactly two intersections exist: apex + one other). Refusals: supporting line tangent to the circle; or the edge's opposite endpoint is not on the far side of the rebuilt point (segment no longer spans the intersection). The "ray, dogbone side" language of ADR-003 is a *consequence* of this definition, not the definition itself.
- Invariant: after rebuild, edge endpoint == arc endpoint (same stored point), asserted within EPS_CONSTRUCTION. For a shared T-cap edge, each dogbone owns exactly one endpoint-side.
- **Apex-proximity gate (v3 fix):** point-to-**SEGMENT** distance — apex must lie within K×R (K=5, constant) of each edge **segment** (perpendicular projection; apex interior to the segment passes at distance 0, which is the T-cap case). Overshoot past a segment's end is allowed if ≤ K×R (tear-truncated edges). Measuring to endpoints (the earlier wording) falsely rejected real corners. A T-junction gate fixture is mandatory in §11.9's test list.
- **Refuse** identical-edge, collinear/parallel-edge pairs; refuse half-angle outside **[15°, 165°]** (constants, tunable). Same edge may not be picked twice (identity rule below).

### 11.5 Stray / deletion truth table (hardened §4.3)

For each entity in the 4×-diameter window (window is a **prefilter only** — the circle test is the rule):

| Case | Action |
|---|---|
| LINE, one endpoint in circle | delete |
| LINE, endpoint exactly on circle (±EPS_COINCIDE) | counts as inside → delete |
| LINE tangent to circle | no-op |
| LINE chord-crosser (both endpoints outside) | **flagged** (v3): user chooses delete or keep; keep → sticky decision (see flow below) |
| ARC, ≥1 endpoint inside circle (v3) | delete, **flagged** |
| ARC chord-crosser (v3) | **flagged**: delete or trim to the kept-side sub-arc (single piece, no two-piece splitting) |
| ARC crossing circle where arc is protected | refuse this corner with highlighted warning |
| CIRCLE (arc hole) | **flagged**, never auto-deleted/trimmed |
| MTEXT | **flagged**, never auto-deleted/trimmed |
| POINT inside circle | delete |
| Protected entities (main edges, folds, placed arcs) | exempt |

- Overlapping-window conflict order: **delete > trim > keep**; previews recomputed against the current protected set after every apply.
- **Protected set (global, monotone):** all main edges (applied + pending) ∪ designated folds ∪ placed dogbone arcs.

**Flagged-entity flow (v3, ADR-009/013):** states {pending → delete | keep | trim}. `Flag(eid, reason, options, decision)` — options per case (ARC chord-crosser offers trim-to-sub-arc; trim yields a Trim like any other). A non-pending decision is **sticky per entity eid** for the session (stored in `ModelState.flag_decisions`, travels in snapshots, restored by undo; cleared only by Revert-to-Original). Recompute honors existing decisions — no repeated prompts across corners. On keep: intersection check of the kept entity against every applied circle; overlap beyond tangency ⇒ non-blocking warning in the preview summary ("kept CIRCLE intersects dogbone 2"). Chord-crosser override text states the consequence: "kept entity will cross the relief cut." Confirm-gate blocks only while any flag is pending.

### 11.6 Export semantics (hardened §4.5)

- Export operates on a **deep copy** of the working document; the working model is immutable under export.
- Fold trim/extend is **idempotent by construction** (endpoint already on arc within EPS_COINCIDE → skip).
- Fold rule (deterministic): extend along line direction to the **first** dogbone-circle intersection; if none within **max 2× deletion window**, leave unchanged and warn. Trim at first circle entry from the kept side.
- Pre-write automated gate: `ezdxf.audit` clean; output version == input version; original file checksum unchanged.

### 11.7 State / undo (ADR-001)

- Model = ordered list of primitive entities. **Snapshot stack** (deep copy per Apply All — documents are tiny). Single undo = swap to previous snapshot; multiple undos allowed (replaces "single-level"); Revert-to-Original = swap to load snapshot. No per-operation deltas.
- Overlap check at confirm time: warn + skip second dogbone (unchanged §4.4). Shrink-to-fit and per-dogbone removal are V1.1.

### 11.8 UX requirements (from user review)

1. **Edge promotion:** click promotes to the longest collinear entity run through the click point (world-space, EPS_COINCIDE collinearity); inferred edge flashes in highlight color before ghosts appear. **Esc / right-click** = restart current corner pick at any time.
2. **Radius input = tool diameter**, mm/inch toggle; live display "Dia 0.1250 in → R 1.5875 mm"; default dia = 3.175 mm. Radius may be changed between applies (mixed-tool parts) — all pending previews recompute.
3. **Deletion preview:** auto-zoom to corner window; text summary ("Deleting: 3 LINE, 1 ARC — Trimming: 1 LINE — Flagged: 1 CIRCLE"); delete/trim highlights thick + red.
4. **Fold selection:** box/marquee select + shift-click toggle; live badge "7 of 9 straight lines designated"; straight LINEs only (§4.5). Drag ≥5 px = box select; below = click (CONTRACTS §3).
5. **Export dialog:** filename prefilled `<original>_dogbone.dxf` in source folder, text pre-selected; last-used folder remembered; Back preserves all pending/applied state.
6. Canvas: single zoom-factor world↔screen transform; hit-test in world coords with EPS_PICK; no full redraw per mouse-move (dirty-region only). Fallback ladder per M1: drop hover → keep click-select + status prompts; last resort matplotlib embed.

### 11.9 Process scaffolding (from PM review)

- **Canonical status source:** the ISSUES.md milestone table carries the authoritative milestone list with estimates, statuses and acceptance criteria (single-writer per row). This section deliberately does NOT restate the milestone chain; ADR-007 records the original re-baselining decision only.
- **Acceptance criteria (numeric):** dogbone center within 0.001 mm of distance R from apex; arc passes through apex ±0.001; after export no non-protected endpoint strictly inside any applied circle; fold endpoints on arc/edge within 0.001; **M2 gate (v3 fix): corner-LOCAL golden test using the documented golden radii of the after-file (two corners R=3.175, one R=1.5875) as test-only parameters, per-corner blocks from SAMPLES.md; whole-file normalized diff deferred to M6** (the earlier whole-file-at-M2 wording was unsatisfiable: the after-file's fold trims don't exist until M5 and its radii are the documented user error). Every agent task cites the criterion it satisfies.
- **Normalization recipe (v3):** compare only tuples `(type, layer, color, round(coord,3))` for LINE/ARC/CIRCLE/POINT, sorted by `(type, rounded center/start, rounded end)`; exclude header, tables, handles, timestamps, MTEXT styling. Fold-line color = named constant recorded in SAMPLES.md (extracted from sample), enforced identically in export and tests.
- **Unit tests (headless):** fixtures 90°/60°/120°, **T-junction gate (mandatory since the §11.4 v3 gate fix)**, shallow-refusal, chord-crosser, tangent stray, POINT-in-circle, ARC-in-circle, fold extend/trim + idempotency; property invariants (§11.4, §11.6); golden tests per the normalization recipe and M2/M6 gate split. **Test runner pinned: pytest.**
- **GUI verification:** agents cannot see the canvas — `tools/verify_gui.py` drives synthetic events and asserts on model state; human performs a 2-minute visual checklist per GUI milestone (briefs cite it).
- **Cut-list amendment (v3):** each cut-list invocation must annotate the affected acceptance criteria in ISSUES.md (e.g., cutting fold trim/extend invalidates M5's "fold endpoints on arc" criterion — resolve_folds then ships as documented no-op).
- **Docs convention:** `DECISIONS.md` (date/decision/why/alternatives — ADR-001 §11.7 is entry 1), `ISSUES.md` as single backlog; every agent session opens by reading AGENTS.md + its brief + cited sections only (~3–4 KB context); session logs are append-only under `documentation/sessions/`; single-writer per milestone row; one agent writes while another reviews — no parallel edits to the same file.
- **DoD gate:** exported sample file opens correctly in user's Fusion 360 CAM.
- **Cut list if overrun:** hover highlight → fold trim/extend (→V1.1) → box-select polish. Deletion preview is **never cut**.

### 11.10 Dependency policy

- `requirements.txt` pins `ezdxf==<tested version>`. **numpy is banned** (ADR-008: §11.1 originally permitted it while §11.10 called it optional — two divergent code paths; stdlib-only geometry needs nothing numpy provides). Header-import audit in M2's DoD enforces this.
- `run.bat` (written, in repo root) tries `py -3.11` → `py -3` → `python`, verifies ≥3.11, gives actionable Windows Store-stub instructions, exits non-zero on failure.
- No matplotlib: the M1 fallback ladder must require no new runtime packages (agents must not ad-hoc install mid-milestone); if a canvas fallback beyond stock tkinter is ever needed it requires a new ADR.
- PyInstaller onefile build is a post-V1 deliverable, not required for V1 done.

### 11.11 V1 / V1.1 boundary (revised §8)

**V1** = §8 V1 list + §11.1–11.10 above (edge promotion, diameter input, deletion summary/auto-zoom, box-select folds, snapshot undo, load-time validation, export gates).
**V1.1 (first sprint after V1):** per-dogbone removal after apply, overlap → shrink-R offer, per-corner radius override, fold trim/extend if cut from V1.
**Future sprints (unchanged):** auto-detect corners, lasso, polyline/spline, batch mode.