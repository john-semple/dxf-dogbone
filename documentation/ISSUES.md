# Issues / Backlog

Single backlog for the project. Agents: read this file first, append new issues at the bottom, update status in place (`open` / `in_progress` / `done` / `deferred`). Never delete entries.

Status legend: `open` | `in_progress` | `done` | `deferred`

---

## Milestone checklist (PM plan, SPEC §11.9)

| ID | Milestone | Est. | Status | Acceptance |
|----|-----------|------|--------|------------|
| M0 | Env checkpoint: python ≥3.11, venv, pinned ezdxf, 20-line sample-load script | 0.5h | done | script prints entity counts of both sample DXFs |
| M0.5 | Commit `/samples` (both DXFs) + SAMPLES.md inventory | 0.5h | done | SAMPLES.md lists entity counts, 3 corner coords, per-corner golden radii (3.175/3.175/1.5875) |
| M1 | Viewer: load + render LINE/ARC/CIRCLE/POINT/MTEXT, pan/zoom | 2–3h | done | both samples render correctly; fallback ladder invoked if >3h — human visual checklist confirmed by user 2026-10-05 ("ran and the dxf looked fine") |
| M2 | Geometry core headless + unit tests (no GUI) | 2–3h | done | corner-LOCAL golden vs SAMPLES.md per-corner radii ±0.001 (corners 2/3 vs after-file; corner 1 self-consistent per user decision 2026-10-05 — user's arc is a hand-made tangent-fit relief, not construction-reproducible) + WORKED-EXAMPLE identity block passes; whole-file normalized diff deferred to M6 |
| M2.1 | Hardening per ADR-016 (3-round review loop) | 1h | done | all Plan-v4 item-0 defects fixed w/ regressions; 114 tests green; verify_m2 + verify_gui ALL PASS |
| M2.2 | Hygiene pass (persona reviews; gate integrity; ISSUE-015) | 1–2h | done | briefs/M2.2.md binding, executed 2026-10-07: verify_m2 exact cleanup/flag sets + constants pin (mutation probes: 5e-3 trips the pin, 2e-2 trips corner-2 cleanup set — silent wrong-deletion-set PASS now impossible); adjacency + _shared_point unified to Euclidean w/ diagonal regression; resolve_edge walks chain_run from the seed (X-crossing false-refusal fixed w/ regressions); chain_run canonical direction from run extent w/ dominant-axis snap (drift two-ids defect; twin-sync corpus extended); place_corner decomposed (_validate_inputs/_truth_table/_rebuild_and_arc over _Ctx) byte-identical; CONTRACTS §1/§2 refreshed; WE errata line; 131 tests green; verify_m2 + verify_gui ALL PASS |
| M3 | Corner workflow GUI: edge promotion, two clicks, ghosts, side pick, red deletion preview | 2–4h | done | executed 2026-10-07 (session log 2026-10-07-M3): `python tools/verify_gui.py --full` drives all 3 sample corners corner-to-corner via synthetic events (two edge clicks → ghost click → confirm) — final ModelState asserts PASS per corner (dogbone count 1, center ±0.001 vs SAMPLES.md, rebuilt endpoints ±0.001, exact deletion sets {B9,BA}/{B5,B4}/{85–89}, flags {BA}/{B4} CASCADE_DANGLING + {85,89} CHORD_CROSSER, arc eid minted n<seq>); parallel-pair refusal toast carries the engine string verbatim (PICK_EDGE2, PARALLEL on status line); pytest -q 148 green (13 new headless FSM tests); verify_m2 ALL PASS. Human visual checklist PENDING user confirmation (ghosts both visible, flash distinct from red, auto-zoom framing, refusal toast) — M3 row marked done by the milestone-owning session per acceptance criteria; checklist note left for the user below. |
| M4 | Apply All + snapshot undo + revert + overlap warn/skip | 1–2h | done | executed 2026-10-07 (session log 2026-10-07-M4; human checklist user-confirmed same day): `model/snapshots.py` SnapshotStack (load seed + unbounded pre-batch pushes; undo False at bottom; revert = load + flag_decisions cleared + stack emptied), `ui/apply_panel.py` (ApplyQueue headless driver: click-order live re-place per ADR-016(k), warn-and-skip engine-verbatim, skips dropped; ToolPanel w/ ADR-005 diameter entry + mm/inch + decision-7 quick-pick buttons + trailing-`"` per-entry inch override; ApplyAllWorkflowUI seam over byte-identical M3 base), app.py glue; pytest 182 green (31 new incl. tool-panel parse); verify_m2 ALL PASS; verify_gui --full ALL PASS incl. 3 new M4 drives (apply-undo-apply: 1st undo = exact pre-apply ModelState incl. flag_decisions, 2nd = original, bottom disabled-not-crashed; revert: flags cleared + queue kept; overlap: twin corner OVERLAP verbatim skip, tangent passes in engine tests); app smoke via real panel callbacks ALL OK; BooleanVar truthiness defect found+fixed via smoke. Same-sitting follow-ups: post-Confirm auto-zoom-out (viewer.fit on enqueue) and inch-entry-with-`"` parse, both gated green. |
| M4b | Apply-to-Similar **dot flow** — re-planned 2026-10-07 per ADR-019; loop-1 amendments ADR-020 (review 6.0/10); loop-2 pin-set ADR-021 (review 7.0/10); loop-3 TECHNICAL pins ADR-023 (review 7.0/10 technical readiness, UX excluded per user ruling; 2 blockers found+fixed: construction timing, composite-run lengths; argmin renormalization pinned). Brief v4. | 8–12h | open | single SimilarWorkflowUI instance at load + arm boolean (ADR-023(a)); armed confirm_click intercepts before M4 post-confirm body (ADR-023(b)); TemplateShape captured in armed apply() pre-mutation (ADR-023(c)); composite runs = one member of run length (ADR-023(d)); argmin mapping renormalized+rescaled, 1.9°-in fixture first (ADR-023(e)); entry mapping failures exclude not crash (ADR-023(f)); ledger post-push keys + M4 labels + can_undo guard (ADR-023(g)); undo toast branches on ledger label, M4 strings frozen (ADR-023(h)); Apply-All disable via glue + _notify_queue guard (ADR-023(i)); one mode-exit routine del-wrapper/unbind/cancel-afters/kill-tag/exit-before-undo (ADR-023(j)); rules/similar.py imports rules.engine (ADR-023(k)); plus all ADR-020/021 dot/predicate/undo rulings; pytest + drive per brief v4 DoD; M4 batch semantics untouched |
| M4c | Guided Dogbone Tour — planned 2026-10-07 per ADR-022 (sprint-start Q&A; brief: `documentation/briefs/M4c.md`; supersedes M4b first-draft Feature B). Phased: M4c1 detector 3–4h, M4c2 tour UI 4–6h. Registers ISSUE-019 + designs/owns ISSUE-010. Prerequisite: M4b shipped. | 7–10h | open | M4c1: `rules/joints.py` recall-first joint detector (chain_run pairs, apex-gate authority, golden counts on samples + syn corpus). M4c2: sequential walk, suggested ghost + red preview, three-button stack Next/Skip/Edit (user design) + Prev, safe-split tour-scoped flag auto (ADR-009 amendment (e): debris del / crosser trim / CIRCLE-MTEXT keep), refused joints show+auto-skip, current panel R, per-item undo (one-corner batches), end report; FSM tests + verify_gui tour drive + human checklist |
| M5a | Fold engine headless + export fold stage — split from M5 per ADR-024 (2026-10-07) | 1–1.5h | done | Executed 2026-10-07 (session log 2026-10-07-M5a): `rules/folds.py` (resolve_folds/validate_fold_against_contours/out_of_reach_warnings, FOLD_REACH_FACTOR=2.0; imports geometry only — architecture matrix green) + `dxf_io/export.py` (export + ExportResult + FOLD_COLOR_CONST=7; deep copy ADR-004; fold stage → layer move → ezdxf.audit pre-check → save; $INSUNITS=4 on output). Gates: pytest 202 passed/2 skipped (15 new `test_rules_folds_goldens` + 7 new `test_dxf_io_export_fold`); WE Step 6 golden (44.7941, 51.2634) ±0.001 PASS; golden replay R=3.175 crossings 44.77237 ±0.001 PASS; idempotency double-resolve=no-op PASS; both-sides trim (full-circle arc) trims each endpoint to its near entry PASS; validation-warning (fold within eps of contour edge via seg-seg distance) PASS; out-of-reach extend warns+unchanged PASS, trim has no cap PASS; ISSUE-012(d) corner-1 engine-arc trim golden 46.5744 ±0.001 PASS (SAMPLES.md 46.1138 confirmed as M6 residual); export purity (working ModelState bit-identical) PASS; re-export idempotency (export→reload→re-designate→export, no double trim) PASS; trimmed endpoints on engine arc within 0.001 PASS; verify_m2 ALL PASS; verify_gui --full ALL PASS (byte-unchanged); architecture matrix green (folds.py imports geometry only, export.py in dxf_io/ may import ezdxf). |
| M5b | Fold selection UI — split from M5 per ADR-024; starts only when M5a gates green | 1h | done | Executed 2026-10-07 (session log 2026-10-07-M5b): `ui/fold_panel.py` (FoldFSM canvas-free core + FoldPanel tkinter shell: mode toggle, click/shift-click toggle, box-select ≥5px, live badge "N of M straight lines designated", auto-preselect once-per-load on layers case-insensitive containing bend|fold|centerline, designation warnings via `validate_fold_against_contours`); `ui/canvas_view.py` fold-color rendering at draw time from `fold_eids` (survives full-wipe redraw); `ui/theme.py` fold_designated key (#facc15 warm gold); `ui/messages.py` fold strings; `dxf_io/load.py` `layer_of` eid→layer map on LoadResult for auto-preselect; `app.py` glue (FoldPanel creation + auto-preselect after load + badge refresh on undo/revert); `tools/verify_gui.py --folds` drive on syn-fold-heavy.dxf. Gates: pytest 226 passed (22 new `test_ui_fold_fsm`: mode toggle/exit/isolation, click/shift-click toggle, box-select threshold+toggle-out, badge-on-every-mutation, auto-preselect case-insensitive+custom-patterns+user-authoritative-after, Esc exit, validation warnings, set_primitives drops stale eids + no re-fire on model change); verify_gui --folds PASS (auto-preselect 3 BEND_UP+FOLD_LINES lines, click 1, box-select 2, shift-click 1, Esc exit, fold-color rendering, near-contour warning); verify_m2 ALL PASS; verify_gui --full ALL PASS (byte-unchanged); architecture matrix green; grep-clean (fold color via theme key, new strings in messages.py). **Post-checklist bugfix 2026-10-07 (session log 2026-10-07-M5b-fix), user-reported: exiting fold mode killed pan + corner picking** — root cause: `unbind(seq)` deletes EVERY Tk handler for a sequence (not just the caller's) + `add=True` let fold-mode clicks co-fire the corner workflow (pinned isolation gate broken at the real-binding level). Fix: binding REPLACEMENT w/ saved-script restore on exit (no unbind anywhere), middle-drag pan added in fold mode (B2 save/restore; wheel untouched); new `verify_fold_mode_binding_regression` drive under --folds (real-binding mode isolation + script-identical restore + pan/corner-pick-alive-after-exit asserts); FOLD_MODE_ENTER string updated. Gates re-run: pytest 226 passed; verify_m2 / --full / --folds ALL PASS. Human visual checklist PENDING user confirmation. |
| M-TRIM | Manual trim-to-closest tool — user-approved spec lock 2026-10-07, designed per ADR-025 | 1.5–2h | done | Executed 2026-10-07 (session log 2026-10-07-M-TRIM): `geometry/entities.py` EditResult/Trim; `rules/manual_edit.py trim_to_closest` (pure: promoted-run subject, moving end = run-extent endpoint nearest click, closest supporting-geometry candidate min-dist from pre-move endpoint w/ flip guard (extend allowed, past-far-endpoint rejected), arc radial-projection-when-spanned else nearest-spanned-crossing (ENTRY crossing must be spanned), point targets, stray-first rule (zero external attachments → propose whole-run deletion), pinned NO_TARGET/UNKNOWN_EDGE strings verbatim, run's own members excluded as targets); `model/model.py apply_edit` (deletions scrub primitives+fold_eids+flag_decisions; trims resolve promoted-* via chain_run, project members on run axis, delete fully-consumed members, end-move straddlers/extension owner; one SnapshotStack push per Confirm); `ui/trim_panel.py` TrimFSM (canvas-free) + TrimPanel shell (M5b binding-replacement pattern, red overlay preview + Confirm pill, bottom-bar toggle + `T` key, NO_TARGET toast+stay); `ui/messages.py` TRIM_* strings; `app.py` glue (undo/revert/load clear pending pick). Gates: pytest 267 passed / 2 skipped (43 new: 24 `test_rules_manual_edit` + 8 `test_model_apply_edit` + 11 `test_ui_trim_fsm`); verify_m2 ALL PASS; verify_gui --full ALL PASS; verify_gui --trim ALL PASS (trim-overshoot, extend + fold designation KEPT, stray delete + fold_eids scrub, NO_TARGET toast+stay, 3-push/3-undo restore, corner-workflow binding isolation + script restore); architecture matrix green (manual_edit imports geometry only); ADR-025 Consequence items all landed (CONTRACTS §1/§2 amended, ISSUE-020 registered). Arc-subject deferred → ISSUE-020. NOTE for M6: manual trims are engine-invisible (engine has no dogbone record) — whole-file diff must map manual-edit residuals separately (ISSUE-012(e) residual class extended). |
| M6 | Final preview (OK/Back) + export dialog + ezdxf audit gate + Fusion round-trip | 1–2h | open | whole-file normalized diff vs after-file passes (golden radii) + audit clean + Fusion round-trip |
| M6.5 | Export-time removal of the SolidWorks Educational watermark MTEXT (exact-text match only; user-facing toggle, default ON) — registered 2026-10-05 per user request; depends on M6's export dialog | 0.5–1h | open | exported DXF contains zero MTEXT matching WATERMARK_TEXTS with toggle ON (both golden files); every other MTEXT preserved; toggle OFF keeps watermark; export stays idempotent (ADR-017) |
| M7 | 3D fold studio, view-only (browser/three.js scene of the folded part; boss request 2026-10-07) — **RE-PLANNED 2026-10-07 per ADR-018** (user's fold-studio design + two 3-persona review loops: UI/UX 7→8, CAD 6→8, architect 7→8): phased M7a (~5–7h: fold math, per-vertex sign-vector folding, sharp-fold plates via edgeminer/edgesmith outer loops, assignment popover + callouts + docked material panel, three.js r147 UMD vendored + self-contained HTML, trust furniture, localStorage camera restore) + M7b (~2–3h, additive: bend skins + pullback coordinated, ACM V-groove mode, fold animation); per-fold direction/angle assignment (angles NOT in DXF — never fabrication data); SM/ACM material panel, T:=R, ACM radius = residual exterior corner; units bind $INSUNITS; session-only persistence (sidecar = V1.1); sequencing unchanged: after M5+M6 (user decision) | 7–10h | open | M7a: golden fold tests (L-fold + zigzag ±1e-9, rib-wall-crossing fixture, dogbone-tangent silhouette fixture); determinism byte-equal; scene-JSON structure + template placeholder checks; human checklist (after-file folded w/ visible dogbone, before-file flat w/ hint, camera survives Refresh); CONTRACTS §6 + AGENTS stack-map row. M7b: skins continuous 45/90/135, ACM goldens (groove = 180−θ), animation checklist. Brief rewritten: `documentation/briefs/M7.md` (supersedes first draft w/ ADR-018) |

**Total estimate:** 10–16 h (re-baselined per ADR-007)

**Cut list if overrun (in order):** hover highlight → fold trim/extend (→V1.1) → box-select polish. Deletion preview is never cut.

---

## Open issues

### ISSUE-001 (done) — Sample DXFs committed
User dropped both files into `/samples` (actual names: `base-rectangular-before-AI.DXF` / `base-rectangular - partially radiused.DXF` — the latter is the part SPEC §10 cites as "Flat pattern - …", same file under a shorter name; recorded in SAMPLES.md). `documentation/SAMPLES.md` generated by `tools/samples_md.py` (script-printed, never hand-transcribed): censuses (before 78L/14A/27C/2M, after 85L/15A/2P/2M), the three radiused corners with golden radii — right T-junction apex (45.0, 51.5168) R=3.175, left T-junction apex (−45.0, 51.5168) R=3.175, top corner apex (45.2534, 120.5168) R=1.5875 — all identity checks pass (|c−apex| = R, rebuilt endpoints (±45.0, 47.0267)/(±49.4901, 51.5168) on the circles ±0.001, matching WORKED-EXAMPLE's golden replay). Folds: before-file has NO bend lines; after-file adds y=51.2634 (4 spans) + y=120.7702 (5 spans + trim stubs), trimmed endpoints (44.3930/46.1138, 120.7702) lie ON the R=1.5875 circle (M5 fold-on-arc golden). Fold constants extracted: color ACI 7, Continuous, layer 0. Known-residuals exception list registered in SAMPLES.md: the bend lines, the two POINTs at (±45, 51.5168), the bottom-tab slot (r=2.5 arcs + slot lines, before-only), the after-only interior rib walls x=±45.2534 y∈[51.7444,120.5168] (right = rebuilt vertical edge of the R=1.5875 corner; left mirror has NO dogbone — user consolidation, M6 must map it), and the SolidWorks Educational MTEXT. Negative control: exactly 3 dogbone arcs exist in the after-file; left mirror top corner untouched. M2 golden gate unblocked.

### ISSUE-011 (done) — Synthetic sample set generation
12 synthetic DXFs (9 positive + 3 negative) generated by `tools/gen_samples.py`; all reload-asserts PASS (12/12). `documentation/SAMPLES-SYN.md` carries the manifest from the reload output. Brief-vs-geometry contradictions resolved in-session (see log): L-bracket & fold-heavy air-side wording was wrong (both are NW of the step void — centers (28.8775,31.1225) and (18.8775,61.1225)); syn-arc-tears A2 wasn't actually a chord-crosser as specified (min-dist 2.6225, not 0.1275) — corrected to center (99.122533, 53.8775), span 90→270 (min-dist 0.25, endpoints 4.07 out); `neg-r12.dxf` got `$INSUNITS=4` hand-patched because ezdxf never writes drawing units for R12; fold-heavy §11.3 case-5 overlay moved to `FOLD_LINES` so the loader's duplicate-merge pass sees the contour edge by geometry; the DoD's "11 files" was off-by-one (12 enumerated: 9 syn + 3 neg). Unblocks M2 fixture work in parallel with the user providing SolidWorks files.

### ISSUE-002 (done) — Environment checkpoint not yet run
Python 3.14.6 confirmed → run.bat fell through `py -3.11` → `py -3`; `.venv` created on 3.14.6. `requirements.txt` pinned `ezdxf==1.4.4` (latest stable, verified on PyPI) + `pytest==9.1.1` (the installed version); numpy pulled in by ezdxf itself (its `Requires` still lists numpy — ADR-008 bars *our* numpy use, not ezdxf's internals). `tools/census.py` reads a DXF from argv, prints per-type counts/layer list/`$INSUNITS`/`$ACADVER` with `ezdxf.recover` fallback (SPEC §11.3). `run.bat` gained an `app.py`-absent early-exit so it works from a clean checkout. `pytest -q` → 2 passed (placeholder marker). See session log `documentation/sessions/2026-09-29-M0.md`.

### ISSUE-003 (open) — SolidWorks bend-layer names unknown
User doesn't know what layer names SolidWorks uses for bend lines in their export setup. Auto-detect list defaults to `bend`, `fold`, `centerline` (case-insensitive) and is editable in GUI. When user discovers real names, update defaults and document here.

### ISSUE-004 (open, deferred to V1.1) — Per-dogbone removal after apply
User review F6: after applying 8 corners with one wrong, undo restores everything. V1.1: click an applied dogbone → "remove this one" → rebuild corner from original snapshot geometry.

### ISSUE-005 (open, deferred to V1.1) — Overlap → shrink-R offer
User review F8: warn-and-skip evaporates the corner's work. V1.1: offer "shrink R to X to fit?" one-click instead of skip.

### ISSUE-006 (open, deferred to V1.1) — Per-corner radius override
User review F7: mixed-tool parts need per-corner radius. Interim (V1): radius editable between applies, pending previews recompute. V1.1: per-corner override field at confirm time.

### ISSUE-007 (open, V1) — Deletion preview must include flagged-entity flow
CIRCLE/MTEXT near corners are never auto-deleted (SPEC §11.5); preview must list them as "Flagged: 1 CIRCLE" with explicit yes/no. Part of M3 acceptance.

### ISSUE-008 (open, V1) — Fusion 360 round-trip gate
Final DoD: exported sample opens in user's actual Fusion 360 CAM setup. Requires user participation at M6; schedule with user.

### ISSUE-009 (open, post-V1) — PyInstaller onefile build
Not required for V1 done (ADR-007/SPEC §11.10); ship `run.bat` first, package later.

### ISSUE-010 (open, post-V1) — Auto-detect corner candidates
First future sprint per SPEC §8. Requires tear-geometry-resistant junction detection; design after V1 real-world usage feedback.
### ISSUE-012 (partially done - (a)/(b)/(d) narrative fixed 2026-10-05 by the M2.1 session; M5/M6 items open) ? Corner-1 golden block unreproducible; SAMPLES.md notes misclassified
M2 exploration (session 2026-10-05-M2) proved: the top corner (R=1.5875) in the after-file is a
hand-made tangent-fit relief (circle tangent to the tear line at (45.2534, 120.5168), inset 0.4537
above the true ramp apex (45.2534, 120.0631)); zero before-file edge pairs reproduce it under the
SPEC 11.4 construction (exhaustive 3003-pair scan). User decision 2026-10-05: corner 1 excluded
from the M2 after-file replay (gate = corners 2/3; corner 1 self-consistent). Consequences:
(a) SAMPLES.md's corner-1 "apex" is a derived gloss (samples_md.py line ~100: apex = (c[0], c[1]-r)),
not an edge intersection; (b) SAMPLES.md's "right wall = the r=1.5875 corner's rebuilt vertical edge"
is wrong (the rib wall ends at mid-arc; user-drawn, like the left mirror); (c) WE Step-5 row 3
("tab-top run") does not exist in the before-file (open tab mouth; bottom edge stored as 63 east /
B3 west); (d) M5's fold-trim golden values (44.3930/46.1138, 120.7702) were measured on the USER's
arc ? M5 must re-derive them against the engine's arc for the replay portion, or map them as
residuals; (e) M6's whole-file diff must treat the corner-1 arc, the rib wall, and those fold trims
as documented residuals. Routing: samples_md.py narrative fix belongs to its owner session (M0
closed; next session touching SAMPLES.md applies). ADR-015(j) carries the ruling.

### ISSUE-013 (open, M6.5) — SolidWorks Educational watermark MTEXT removal at export
User request 2026-10-05 (M1 session): the SolidWorks Educational flat-pattern export stamps two
MTEXT entities ("SOLIDWORKS Educational Product." / "For Instructional Use Only." — confirmed present
in both golden files; also in the user's "ISO 30 holder bottom 1.0.DXF", not in repo). Everything
lives on layer 0, so a layer filter cannot catch them. Scope: recognize and remove THAT text only —
never other text. Mechanism decided in ADR-017: exact plain-text match against a constant list at
export time (deep copy, ADR-004 purity — working model and viewer untouched), export-dialog
checkbox "Remove SolidWorks Educational watermark", default ON. The word-search/block-selection UI
alternative (isolate text into blocks, user picks deletions) was considered and deferred: heavier
UI+model-mutation surface, unnecessary for a deterministic watermark; revisit as V1.1 if real files
carry other text needing removal. Does NOT alter the SPEC 11.5 corner-window MTEXT flag flow. If the
user drops "ISO 30 holder bottom 1.0.DXF" into /samples it becomes the third watermark fixture
(not required).

### ISSUE-014 (done) - M2.1 hardening per ADR-016 (the 3-round post-M2 review loop)
(numbering slip: originally appended as a duplicate ISSUE-013 during the M2.1 session; renumbered to ISSUE-014 by the M2.2 session 2026-10-05 - the original ISSUE-013 is the watermark entry above. Kept visible per the never-delete rule.)
All Plan-v4 M2.1 items landed before M3: apply_corner composite re-apply crash fixed; applied-edge
protection via canonical eids + resolve-at-use (tangent/crossing regression green); flag-decision
validation (invalid never destructive); flag dedup; radius validation; filters/runs unified into
geometry/runs.chain_run (canonical member order + eid - also fixed a latent two-eids-for-one-run
defect); CornerResult.warnings added (ADR-009 keep-warning carrier); SAMPLES.md narrative fixed.
Ratings that drove it: R1 6.5/10, R2 6/10, R3 6/10 (plan v1 -> v4 in the session log). 114 tests
green; verify_m2 + verify_gui ALL PASS.
### ISSUE-015 (done) - Hygiene pass from the two persona reviews (mathematician 8/10, senior developer 8/10; session log 2026-10-05-M2 "Persona reviews")
Executed 2026-10-07 (M2.2 session; brief = documentation/briefs/M2.2.md, binding).
All items closed: verify_m2 cleanup sets/flags pinned exactly + tests/test_constants_pin.py
(the golden gate can no longer PASS a wrong deletion set — mutation-probed: EPS_COINCIDE
5e-3 fails the pin, 2e-2 fails the corner-2 set probe); adjacency pairing metric unified to
Euclidean (adjacency.py + engine._shared_point; cascade never counts box-only diagonal
contacts); resolve_edge walks chain_run from the seed (X-crossing at the seed midpoint no
longer false-refuses UNKNOWN_EDGE, both directions regression-pinned); chain_run canonical
direction derives from the run extent with dominant-axis snap (alternating-drift runs mint
ONE eid from clicks on both members; fixture added to the twin-sync corpus); place_corner
decomposed into _validate_inputs/_truth_table/_rebuild_and_arc over an internal _Ctx
(byte-identical API/strings; the `run is run1` identity comparison replaced by explicit
triples); CONTRACTS §1/§2 refreshed (place_corner/resolve_edge/ghost_candidates normative
blocks, Trim.old/new annotation); WE golden-section errata line added (append-only).
Optional item 7 executed in part: bounded prefix unrolling + keep-warning predicate
symmetry — see the session log for the split. Q&A rulings applied: corner-1 flags pinned
as the two decided CHORD_CROSSER flags (ADR-016(d) forbids emptying the list); mutation
acceptance split 5e-3 (pin) / 2e-2 (cleanup sets); extent direction = dominant-axis snap.
The M2.1-hardening entry was renumbered from a duplicate ISSUE-013 to ISSUE-014 by the
M2.2 pre-work (slip recorded there).
### ISSUE-016 (done) � M3 human visual checklist confirmed by user 2026-10-07
The M3 synthetic-event gate (tools/verify_gui.py --full) is ALL PASS and pytest -q is 148
green, but the M3 brief's human visual checklist (2 minutes, per SPEC �11.9 "human performs
a 2-minute visual checklist per GUI milestone") still needs eyeballs:
1. both ghost circles visible (dashed, one per valid ray);
2. promoted-edge flash distinguishable from deletion red (cyan vs thick red);
3. auto-zoom framing correct on preview entry (corner window � 4� tool diameter);
4. refusal toast appears when clicking two parallel edges (e.g. the tab left/right walls).
Run via `run.bat` or `python app.py samples\base-rectangular-before-AI.DXF`, click two
edges near a corner, click a ghost, review the red preview + summary line, Confirm.
Reply here or in the session log; a failed item reopens the M3 acceptance note.
### ISSUE-017 (done) — UI-UPGRADE theme pass (dark modern shell)
Executed 2026-10-07 (brief = documentation/briefs/UI-UPGRADE.md, binding; session log
2026-10-07-UI-UPGRADE). New `ui/theme.py`: single `COLORS` dict + `apply(root) -> ttk.Style`
(clam, dark #1e1f26-class panels, accent blue, Segoe UI with TkDefaultFont fallback, flat
TButton + Accent.TButton, 8/12 px padding) called from `App.__init__` and both verify_gui
harness roots. Canvas dark theme: BG #17181e, light geometry strokes #c8cdd9, readable
MTEXT; overlay semantics preserved — flash/ghost cyan-family #22d3ee, delete dark-bg-safe
red #ff4d4d, flag orange #ff9900, edge-2 pick green; all from theme.COLORS. app.py:
ttk status bar (Status.TLabel + ttk.Separator), Confirm as Accent.TButton, themed tk.Menu,
zero sunkent-bar chrome; same status/summary strings + StringVars, `App` public methods
untouched. Confirm pill restyled via theme keys (round-7 look kept). Brief item 5 (toast
cards) no-op: M3 toasts are status-line strings, not Toplevels. Constructor signatures of
Viewer/WorkflowUI unchanged; no FSM/engine changes. Gates: pytest -q 151 green (148 + 3
new theme tests), verify_m2 ALL PASS, verify_gui --full ALL PASS; grep-clean — no hex
literals outside ui/theme.py, no relief=/bd= in app.py. Human visual checklist CONFIRMED
by user 2026-10-07 (same sitting as the M4 checklist — "it all works great": dark canvas,
part legible, status bar readable, Confirm accented, flash/ghost/delete/flag mutually
distinct); closes this issue alongside ISSUE-016.

### ISSUE-018 (open, M4b) — Apply-to-similar geometry, dot flow (user request 2026-10-07)
User: "I want to be able to do one instance and have the program apply it to similar/identical geometry."
Second user request same day matured the review surface: "show what it thinks are all the similar
geometries and have a largish dot on each one I can select or deselect (green or red) before hitting
go and having it apply the same dogbone." RE-SCOPED 2026-10-07 per ADR-019 (sprint-start Q&A, 10
answers): predicate = angle ±2° (ANG_TOL_DEG) + promoted-run shape (member count + length sequence,
mirror/reversal allowed, LEN_TOL_MM 0.01), mirrored/rotated corners included, tear debris excluded;
matching = new pure `rules/similar.py` surface (eid-referenced, ADR-010); review = post-Confirm dot
map, all-green default, hover deletion summary + click-through red preview (deletion preview never
cut); Go = template-R replay in document order through ApplyQueue w/ M4 warn-and-skip verbatim;
undo = per-corner one-corner batches + panel "Undo Batch" pre-Go restore (user ruling). ADR-009 is
NOT amended this sprint. Brief rewritten: `documentation/briefs/M4b.md` (supersedes first draft w/
ADR-019). Estimated 3-4h.

### ISSUE-019 (open, M4c) — Guided dogbone tour (user request 2026-10-07)
User: "a mode where it leads me through every joint that should have a dogbone, each direction (the
four ghosts) shows up for me to click, a Skip button, allow-all so I'm not clicking allow three
times, and Undo = last item in that list." RE-SCOPED 2026-10-07 per ADR-022 (sprint-start Q&A, 11
answers; brief documentation/briefs/M4c.md; registered as milestone M4c in two phases): sequential
walk (user reaffirmed over dot-map hybrid), recall-first detector (ISSUE-010 now designed — M4c1
owns it: chain_run pairs, apex-gate authority, misses recoverable via manual flow), suggested ghost
(mapped-center argmin from last manual pick, clearance fallback — reuses M4b machinery), three-button
stack Next/Skip/Edit (user's own design) + Prev, safe-split tour-scoped flag auto-decide (ADR-009
amendment (e): CASCADE_DANGLING delete / CHORD_CROSSER trim / CIRCLE-MTEXT-keep; zero modals in
tour; sticky mechanics unchanged; normal flow byte-unchanged), refused joints show + auto-skip,
current panel R live, per-item undo (one-corner batches per ADR-020(g)), end report. Prerequisite:
M4b shipped. Estimated M4c1 3-4h + M4c2 4-6h.

### ISSUE-020 (open, deferred to V1.1) — Arc subject for the manual trim tool
User spec lock 2026-10-07 (ADR-025): subject of `trim_to_closest` is the promoted run of a LINE
only. An ARC as TARGET (supporting geometry: radial projection when spanned, else nearest
spanned-crossing) is fully supported in V1. Clicking an ARC as the SUBJECT (moving its endpoint to
a snap) is deferred to V1.1 — arc endpoint motion needs arc-rebuild semantics (span recompute,
endpoint flags) that the manual-edit carrier (Seg-only replace) does not model. Refusal string if
an arc subject is presented in V1: engine falls through to NO_TARGET/UNKNOWN_EDGE — no dedicated
string. Registered per ADR-025 Consequence. Estimated V1.1: 0.5-1h (Extend Trim endpoints model +
arc replace + drive case).
