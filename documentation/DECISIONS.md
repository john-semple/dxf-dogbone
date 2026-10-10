# Decision Log (ADR format)

> **Status: In progress**

Every entry: date / decision / why / alternatives considered. Agents must read this file before working. New sessions append entries; never delete.

---

## ADR-001 — 2026-09-28 — Undo model: snapshot stack, not deltas
**Decision:** Working model is an ordered list of primitive entities. Apply All takes a deep-copy snapshot before mutating; undo swaps to the previous snapshot; Revert-to-Original swaps to the load snapshot. No per-operation delta list, no redo stack in V1.
**Why:** Documents are tiny (<1 MB), snapshots are nearly free, and they eliminate the entire class of incremental-undo bugs (partial mutations, inverse-operation errors). Single-level undo was rejected because it strands users who applied several correct corners plus one wrong one.
**Alternatives:** Command-pattern deltas (more code, more bugs); single-level undo (accepted UX loss); event-sourcing (overkill).
**Consequence:** Export must operate on a deep copy so re-export after undo cannot double-trim fold lines (see ADR-004).

## ADR-002 — 2026-09-28 — Deletion rule: circle test is the rule, 4× window is a prefilter only
**Decision:** ~~An entity is deleted iff (a) it falls in the 4×-tool-diameter window around the corner AND (b) it has an endpoint inside the dogbone circle — and it is not protected.~~ **AMENDED (loop-2):** deletion is governed entirely by the SPEC §11.5 truth table: in-window endpoint-in-circle entities are delete candidates EXCEPT protected entities and flagged classes (CIRCLE/MTEXT/ARC cases/chord-crossers) which flow through the ADR-009/013 flagged flow {pending → delete|keep|trim}, sticky per eid. The 4× window remains a prefilter only, never part of the geometric rule.
**Why:** User confirmed "any line within 3–4× bit diameter with an endpoint within the dogbone area." Separating prefilter from rule prevents future confusion when tuning the window (the circle test alone is mathematically sufficient for correctness).
**Alternatives:** Window-only deletion (leaves tear lines that extend past the circle); collinearity-based trimming of tear segments (fragile at near-collinear fragments).
**Consequence:** Truth table in SPEC §11.5 governs every case; chord-crossers are FLAGGED (sticky keep/trim), not auto-deleted; CIRCLE/MTEXT always flagged, never auto-deleted.

## ADR-003 — 2026-09-28 — Edge rebuild is per-endpoint on the ray, not on the infinite line
**Decision:** When a dogbone is placed, only the endpoint of each main edge on the dogbone side moves; it moves to the intersection of its supporting line's ray (dogbone side) with the dogbone circle. Never use the opposite-ray intersection.
**Why:** "Far intersection on the infinite line" can destroy the untouched half of a shared T-cap edge (the cap line's far circle intersection lies on the other dogbone's side) and can extend edges into empty air for T geometry.
**Alternatives:** Per-entity rebuild (destroys shared T-caps); trim-to-apex-then-rebuild (two-step, harder to reason about).
**Consequence:** Invariant: after rebuild, edge endpoint == arc endpoint (single source of truth), asserted within EPS_CONSTRUCTION. Apex-proximity gate (K=5 ×R) rejects misclicked edge pairs.

## ADR-004 — 2026-09-28 — Export is pure: deep copy + idempotent folds
**Decision:** Export deep-copies the working document; all fold trim/extend executes on the copy; the rule skips any endpoint already on an arc within EPS_COINCIDE. Working model is immutable under export.
**Why:** Guarantees export can be repeated (undo → re-export, preview → back → re-export) without double-trimming or double-extending fold lines, and keeps undo semantics independent of exports by construction.
**Alternatives:** Mutate-then-export (requires exact inverse ops for undo — bug-prone); fold-state flags (state drift).
**Consequence:** Export is a pure function of (model, dogbones, folds, radius); same inputs → same bytes modulo timestamps.

## ADR-005 — 2026-09-28 — User input is tool DIAMETER, not radius
**Decision:** GUI takes tool diameter with an mm/inch toggle; radius is derived and displayed live ("Dia 0.1250 in → R 1.5875 mm"). Internally, everything is mm.
**Why:** The user's own sample files document this exact mistake (1/8" entered as radius instead of diameter, producing R=3.175 instead of 1.5875). US shops think in bit diameters off the tool drawer.
**Alternatives:** Radius-only input (repeat of documented error); no unit toggle (US-shop friction).
**Consequence:** Load-time $INSUNITS check (must be 4 = mm) backs this up; diameter/radius shown together everywhere radius appears.

## ADR-006 — 2026-09-28 — Headless geometry core is a hard boundary
**Decision:** `geometry/` and `rules/` modules import neither ezdxf-IO nor tkinter; the full corner/fold/deletion pipeline is runnable headless with an entity list as input. UI translates clicks into engine calls; engine never touches tkinter.
**Why:** The project is developed by AI agents across sessions (Cursor, OpenChamber). Without an import-level boundary, agents will entangle math with canvas callbacks; tests then require a GUI to run, which agents cannot.
**Alternatives:** Trust conventions (fails in practice with agents); full MVC framework (overkill for V1).
**Consequence:** All acceptance criteria in SPEC §11.9 are testable headless; UI is replaceable.

## ADR-007 — 2026-09-28 — V1 re-baselined from "few hours" to 10–16 h with milestone gates
**Decision:** V1 scope is unchanged in features but re-estimated at 10–16 supervised hours, structured as milestones M0–M6 (env → samples → viewer → headless core → corner workflow → apply/undo → folds → export). Cut list under overrun: hover → fold trim/extend → box-select polish. Deletion preview is never cut.
**Why:** Original "usable within a few hours" was 3–10× optimistic against the agreed feature list (pan/zoom canvas, 4-stage workflow, rule engine, fold engine, undo, export gates). Honest re-baselining prevents schedule-pressure scope cuts in exactly the wrong places (the preview).
**Alternatives:** Descope V1 to viewer+manual-arc-only (loses the tool's core value: tear cleanup + fold handling).
**Consequence:** PM review's milestone plan adopted; every agent session ends with the milestone checklist updated in ISSUES.md.
## ADR-008 — 2026-09-28 — stdlib-only geometry; entity dataclasses live there; hit-test/promotion are rules functions
**Decision:** (a) numpy removed from the project entirely (was "optional" — created two divergent code paths); geometry and rules are stdlib-only. (b) Entity dataclasses (Pt/Seg/Arc/Circ/PointEnt/TextEnt, eid-carrying) live in `geometry/entities.py`; model may import geometry types. (c) Hit-testing, EPS_PICK derivation from zoom, and edge promotion are `rules/` functions of (entity list, click point, eps) — headless-testable; the UI only converts screen↔world.
**Why:** Review loop found the import matrix unsatisfiable (model needed types it couldn't import; picking logic would have landed in UI where "UI never computes geometry" is violated and nothing is testable headless). Pinning dataclasses prevents M1/M2/M3 from inventing incompatible entity representations.
**Alternatives:** Leave responsibilities vague (each agent session invents its own — the #1 rework source); numpy dual-path (shop PC crash risk).
**Consequence:** CONTRACTS.md is the binding interface document; changes require an ADR.

## ADR-009 — 2026-09-28 — Flagged-entity flow: sticky per-session decisions + keep-intersection warning
**Decision:** Flagged entities (CIRCLE/MTEXT/ARC cases/chord-crossers) have states {pending → delete | keep}. Decisions are sticky per entity eid, stored in ModelState.flag_decisions, travel in snapshots, restored by undo, cleared only by Revert-to-Original. Recompute honors existing decisions (no re-prompting per corner). A kept entity intersecting any applied circle beyond tangency produces a non-blocking warning in the preview summary; the chord-crosser keep-text states the gouge consequence explicitly.
**Why:** The first-pass truth table left the flagged flow undefined: re-prompting per corner (8 corners = up to 8 redundant prompts), decisions lost on undo, and a kept chord-crosser could silently ship gouging geometry to the machine.
**Alternatives:** Per-corner re-decision (prompt fatigue); auto-delete everything flagged (wrong on holes); persist decisions across files (out of scope).

## ADR-010 — 2026-09-28 — Entity identity by immutable eid
**Decision:** Every primitive carries an immutable string ID (DXF handle at load; minted for new entities). All rule decisions (duplicate-pick, protected set, flag decisions, census dedup) reference eid, never object references or raw coordinates. Snapshots preserve ID↔entity mapping; identity is stable across Apply/Undo/Revert.
**Why:** Deep-copy snapshots (ADR-001) break object identity; rebuild moves coordinates. Identity-based rules keyed on either would misfire after the first Apply All (same edge re-picked undetected, or innocent edges falsely refused).
**Alternatives:** Coordinate keys (unstable under rebuild); object refs (unstable under snapshot swap); hashable-by-value entities (fragile).

## ADR-011 — 2026-09-28 — Doc canon and context discipline for agent sessions
**Decision:** Documentation canon: CONTRACTS.md > WORKED-EXAMPLE.md > SPEC.md (§11 overrides §1–10; newest ADR wins). Session context diet: each agent session reads AGENTS.md + its one milestone brief + cited sections only (~3–4 KB), never the full doc suite. Per-session append-only logs under documentation/sessions/; ISSUES.md milestone table is the canonical status source with single-writer enforcement. GUI milestones verified by tooling (verify_gui.py synthetic events + human checklist), never by agent eyeballing.
**Why:** Three reviews converged on the same failure modes: context flooding, ambiguous interfaces, unverifiable GUI acceptance, lost updates across parallel sessions.
**Alternatives:** Full-doc reads each session (refloods context, stale-override risk); parallel multi-writer (merge conflicts in status tables).

## ADR-012 — 2026-09-28 — Promoted-edge reconciliation and attachment cascade
**Decision:** (a) A promoted edge carries the ordered member-eid list it merges. CornerResult deletions/trims/rebuilds reference member eids, not the composite id. Model.apply_corner replaces the member run with the rebuilt composite, registers it in the model under the promoted eid, and asserts no member eid remains referenced elsewhere (protected set migrates to the composite). (b) **Cascade trigger (loop-2 amendment, both required):** the entity's attachment endpoint lies in a rebuilt edge's removed portion (± EPS_COINCIDE) AND the attaching entity has no remaining attached neighbor after that portion is removed — **a surviving entity's contact at a vertex inside the removed portion does NOT count as a remaining attached neighbor; the cascade is evaluated transitively (truth-table deletions first, then iterate to fixed-point)** (loop-3 final clause). Adjacency = endpoint-keyed map (eid → touching member eids), built at load, traveling in snapshots. Cascade deletes are flagged (edit via sticky decision; identity-block fixtures script the expected decisions — see WORKED-EXAMPLE identity block #5). (c) **Re-promotion (loop-2 addendum):** a composite may be re-promoted for subsequent dogbones on the same supporting line (T-cap case); its members list is preserved across generations; Rebuild may reference a composite eid; promoted ids de-duplicate by prefixing the existing composite eid, never minting a second.
**Why:** Sample edges decompose into micro-segments, so every realistic corner produces a promoted composite; without reconciliation rules the rebuild either duplicates geometry or dangles members. The cascade mirrors the hand-cleaned after-file (tear stubs dangling off removed portions do not survive there).
**Alternatives:** Keep members and composite (duplicate geometry); delete all members and store only composite (loses per-member history for undo display); leave dangling stubs (contradicts validated sample diff).

## ADR-013 — 2026-09-28 — Flag carries options; trim is a first-class flag outcome
**Decision:** CornerResult.Flag = (eid, reason, options: {delete, keep, trim}, decision). Flagged ARC chord-crossers expose the trim-to-sub-arc option of SPEC §11.5; trim produces a Trim like any other trim. M4's confirm-gate blocks only while state == pending. **Persistence (loop-2 amendment): decisions are stored as `dict[str, str]` over {"keep","delete","trim"} in ModelState.flag_decisions (bool type withdrawn), and M4's snapshot-equality test asserts a trim decision round-trips as "trim".**
**Why:** The {delete|keep} enum could not express the ARC-chord-crosser trim row §11.5 grants, forcing either feature loss or a permanent workflow block.
**Alternatives:** Drop ARC trim (stricter than the LINE rule for no reason); auto-trim (removes user control from destructive ops).

---

## Loop-2 amendment record (2026-09-28, folded into ADR-012/013 above)

- ADR-002 decision line amended in place (stale iff withdrawn; truth-table governance referenced). Canon: newest ADR text wins; agents must never quote ADR-002's original iff in tests.
- pytest conflict resolved: the pin lives in requirements.txt via M0; CONTRACTS §4 asserts the pin exists, M0 brief owns creating it.
- §11.9's self-violating milestone restatement removed (ISSUES.md table is the sole carrier).
- Run.bat loop-2 actions: delete the stray `python -c "print('Interpreter check failed')"` diagnostic line (Store-stub pop risk on py-launcher-only machines); on venv reuse, echo the venv's Python version; add one retry pip install with corrective message on app-launch ImportError.
- M0.5 acceptance wording updated to "per-corner golden radii (3.175/3.175/1.5875)" (ISSUES.md M0.5 row).
- WORKED-EXAMPLE Step 1 wording corrected: apex distance is 0.0 to edge 2's interior and 0.0050 (within-overshoot) past edge 1's endpoint; Step 5 cascade table now carries the exact recomputed distances and the adjacency-discriminator (stub vs run).

## Loop-3 amendment record (2026-09-28, final loop)

- B1 CLOSED: cascade criterion final clause added to ADR-012(b) and CONTRACTS §1 — removed-portion-vertex contacts don't count as remaining attached neighbors; transitive (truth-table-first, fixed-point) evaluation. WORKED-EXAMPLE Step 5 self-correction artifact replaced with the formal criterion.
- B2 CLOSED: M0 brief line 9 now pins pytest (`pytest==<installed version>`). This record supersedes the loop-2 record's pytest claim, which was false as written (the M0 edit had not been made at that time); the append-only log keeps the false claim visible rather than hiding it.
- Precision polish applied (non-blocking per review): golden-replay intermediates reprinted exact in WORKED-EXAMPLE's print-precision note; M5 brief fold endpoint re-pinned to 44.7941 (single binding for the number, matching WE).
- Non-blocking leftovers accepted as-is: ADR-009's original {delete|keep} text (canon: newest ADR wins), M3/M4 cite-line polish, run.bat retry-gating polish, §11.8.1 "through the click point" sentence (CONTRACTS wins), 10–17 h vs 10–16 rounding.

---

## ADR-014 — 2026-10-05 — M1 scaffold rulings: Seg promotion fields, promoted_edge_at home, dxf_io→model import

**Decision:** (a) `Seg` gains optional fields `members: tuple[str, ...] = ()` and `pick_eid: str = ""` — the frozen-safe immutable form of CONTRACTS §2's "members: list[str]"; empty `pick_eid` cannot collide with handle / `n<seq>` / `promoted-*` eids — so `promoted_edge_at` can return the promoted Seg exactly as §2 specifies. (b) `promoted_edge_at` lives in `rules/filters.py` (per its ownership row CONTRACTS §5 and the M1 brief); `rules/engine.py` may re-export it (M2's choice). (c) `dxf_io.load` imports model's `ModelState` dataclass to fill the contracted `LoadResult.model_state` (CONTRACTS §3 binds; SPEC §11.1's dxf_io import row omits model — CONTRACTS > SPEC per ADR-011). (d) M1 scaffolds `model/state.py` with the `ModelState` dataclass only (CONTRACTS §1); the `Model` class and its methods remain M2/M4 scope. (e) SPEC §11.3 case-3 "contour-scale" is machine-decided as: unsupported entity bbox diagonal ≥ 20% of supported-model bbox diagonal → refuse; unsizable → passthrough + warning; zero supported geometry + any unsupported → refuse.

**Why:** CONTRACTS §1 vs §2 conflicted on Seg's fields; §2 vs §5/brief conflicted on the function's module; §3 vs SPEC §11.1 conflicted on dxf_io imports; §11.3 case 3 was not machine-decidable as written. All five rulings were user-approved in the 2026-10-05 M1 pre-work Q&A before any code was written.

**Alternatives:** `PromotedEdge` wrapper (deviates from §2's "Seg carries fields"); deferring the model/ scaffold (blocks load()); `load()` returning a bare entity list (deviates from §3); type-based instead of size-based case-3 rule (makes §6's passthrough unreachable); always-refuse unsupported (same).

**Consequence:** `geometry/entities.py`, `geometry/tolerances.py`, `rules/filters.py`, `model/state.py` are M1-written scaffolds; M2 treats them as given (no rewrite). `filters.py` promotion follows ADR-012(c): composite members flatten into the run's member list; re-promotion prefixes the existing composite eid, never minting a second.

## ADR-015 — 2026-10-05 — M2 contract clarifications (user-approved in the 2026-10-05 M2 pre-work Q&A)

**Decision:**
(a) `Refusal(reason: str)` frozen dataclass added to `geometry/entities.py` — CONTRACTS §2 returns `tuple[Pt, float] | Refusal` but never defines the type; §1 already hosts non-primitive result types.
(b) `place_corner` gains keyword-only defaulted params `eps_construction=EPS_CONSTRUCTION`, `eps_coincide=EPS_COINCIDE`, `flag_decisions: dict[str, str] = {}`, and `db_id: str | None = None` — explicit tolerance parameters are the CONTRACTS §1 preamble convention; ADR-009/013 sticky decisions change CornerResult content (ARC chord-crosser trim vs delete) so the engine must receive them; `db_id` defaults to the deterministic `"db-<edge1_eid>+<edge2_eid>"` so previews recompute stably (callers may pass their own).
(c) The placed arc carries the placeholder eid `"arc-pending-<db_id>"` in CornerResult.dogbone; `Model.apply_corner` mints the real eid via `ModelState.next_seq` (`n<seq>`), inserts the Arc primitive, and re-records the Dogbone with the minted eid.
(d) `Trim.old/new` tuple semantics per entity kind: Seg → `(Pt, Pt)` endpoints; Arc → `(start_deg, end_deg)` angles. ARC-chord-crosser trim keeps the single sub-arc ("kept side") whose midpoint is farther from the dogbone apex; ties → longer piece; still tied → first in CCW order. A scripted "trim" that would split the arc into two kept pieces and cannot pick a side falls back to no-trim with the flag retained.
(e) Adjacency (ADR-012 endpoint-keyed map) is a pure derived function `geometry/adjacency.py: build_adjacency(entities, eps_coincide)`; no ModelState field is added — CONTRACTS §1's "maintained/traveling in snapshots" is satisfied by derivation from the snapshot's primitives (documents are tiny). rules (cascade) and model (M4 cache) both import it (model may import geometry, never rules).
(f) Overlap (SPEC §11.2): refuse when `|c_new - c_old| < r_new + r_old - EPS_COINCIDE` (strict with eps; tangent circles pass); reason in `refusals`. Deletion window = 4× tool diameter disk around the apex (prefilter only, never the rule). Protected set inside place_corner = {resolved edge member eids + composite eids} ∪ fold_eids ∪ {placed dogbone arc eids} ∪ the new arc.
(g) Angle conventions: `compute_apex` returns half of the SMALLER angle between the supporting lines (intrinsic; side unknown at call time). Band [15°,165°] on it ⇔ near-collinear refused at BOTH ends (edge direction angle within 30° of 0° or 180°). place_corner derives per-side geometry: bisector = unit(u1 ± u2) per Side.sign (+1 = u1+u2), center = apex + R·bisector, half_side = angle between bisector and each supporting line (equal; asserted), arc span = 360° − 4·half_side, apex strictly mid-arc. This resolves the M0-logged SAMPLES-GEN vs WORKED-EXAMPLE air-side conflict for line pairs (same accept/reject on every documented site); logged per AGENTS.
(h) Attachment cascade: default (no decision) = delete + Flag(reason="CASCADE_DANGLING", options={"delete","keep"}, decision=None) present in `flags`; scripted "keep" survives. Evaluation: truth-table/decision deletions first, then transitive fixed-point; surviving-entity contacts at vertices inside a removed portion do not count as remaining attached neighbors (ADR-012(b) loop-3 clause).
(i) Refusal strings pinned (exact, ASCII, deterministic formatting) in `rules/engine.py` and asserted verbatim by tests: SAME_EDGE / PARALLEL / SHALLOW / APEX_GATE / OVERLAP / TANGENT / SPAN / PROTECTED_ARC.
(j) M2 golden gate per user decision (2026-10-05): corners 2/3 replay vs after-file ±0.001; corner 1 self-consistent fixture only (user's arc = hand-made tangent-fit relief, tangent to the tear line at (45.2534, 120.5168), inset 0.4537 above the true apex; zero before-file pairs reproduce it). WE Step-5 row 3 ("tab-top run") does not exist in the before-file; fixture set uses the actual entities.

**Why:** CONTRACTS §2 leaves Refusal/place_corner inputs/arc-eid minting/trim semantics/cascade defaults undefined; ADR-014 numbers and rules were already taken; corner-1 non-reproducibility was proven by exhaustive scan (3003 pairs) and confirmed by an independent reviewer agent.

**Alternatives:** Consuming M1 scaffolds with ad-hoc semantics per test (drift); storing adjacency in ModelState (CONTRACTS §1 field change); matching the user's tangent-fit corner-1 construction (would amend SPEC §11.4/ADR-003 — rejected: T-junction goldens verify the through-apex rule to 1e-5).

**Consequence:** CONTRACTS §1/§2 amended in place (Refusal; place_corner signature note; Trim note; §1 adjacency wording now read as derivation per (e)). verify_m2 covers corners 2/3 golden + corner 1 self-consistency; M6 maps the user's corner-1 arc as a residual.

## ADR-016 ? 2026-10-05 ? M2.1 hardening rulings (from the 3-round post-M2 review loop; user-approved "Run it")

**Decision:**
(a) ADR-015 clauses (k)(l)(m) recorded as written in the M2 code: (k) geometry/runs.py re-derives a
    promoted run model-legally (model may import geometry, never rules); (l) rebuild tie-break ?
    when BOTH endpoint alternatives pass the kept-interior test (extension-type rebuilds), the
    endpoint nearer the apex moves (ADR-003 "dogbone side"); (m) ghost_candidates enumerates all
    four (Side, side_flip) candidates and place_corner takes the kwarg side_flip ? one sign bit
    cannot address four ghost rays.
(b) `CornerResult` gains `warnings: list[str]` (non-blocking, human-readable; CONTRACTS ?1
    amended). It is the ADR-009 keep-warning carrier: kept chord-crossers warn
    "KEPT_CROSSER: kept entity <eid> will cross the relief cut"; kept CIRCLEs intersecting the
    dogbone circle beyond tangency warn "KEPT_INTERSECTS: ..."; invalid flag_decisions warn
    "FLAG_DECISION: ...".
(c) flag_decisions are validated per-case against each Flag.options; an invalid value is IGNORED
    (the entity falls back to its pending/default flag-flow outcome, never auto-deleted by the
    invalid value) and a warning is recorded.
(d) Flags dedup per eid within one CornerResult (first flag wins). Cascade evaluation skips any
    eid already flagged by the truth table (flagged classes flow through the flagged flow, never
    auto-deleted ? ADR-002 amended) and skips already-cascade-flagged eids on re-iteration.
(e) Radius validation: place_corner refuses r <= 0 or r < EPS_COINCIDE with the pinned string
    "RADIUS: tool radius must exceed EPS_COINCIDE (got <r>)" (replaces the accidental
    TANGENT/APEX_GATE/SPAN refusals with wrong diagnoses).
(f) Promotion re-promotion eid rule AMENDED (supersedes ADR-012(c)'s "prefixing" mechanism and
    M1's promoted-promoted-* behavior): re-promotion of a registered composite keeps the
    composite's own eid (never prefixes, never mints a second id ? ADR-012(c)'s intent). The
    single chain-walk implementation lives in geometry/runs.py; rules/filters.py delegates its
    walk to it (ADR-014's "no rewrite" is superseded for this fix) and its pick is first-wins on
    ties (docstring semantics). resolve_edge stays prefix-chain aware for any legacy eids.
(g) Canonical edge eid (the M3 "eid-forwarding" ruling): ONE eid ? the promoted Seg's eid from
    promoted_edge_at ? is consumed identically by UI-forward, Dogbone.edgeN_eid, the protected
    set, _owning_member, and apply_corner's seed resolution. Applied dogbones' edge eids are
    resolved AT USE via resolve_edge against current primitives (Dogbone stays immutable;
    rejected: re-recording dogbone eids at apply ? CONTRACTS ?1 change with M4/M6 ripple).
(h) apply_corner on registered composites: removal set = the run's ENTITY-level eids present in
    primitives (flattened members PLUS composite eids); insertion anchored at the seed entity's
    document position; the registered composite keeps its eid across generations.
(i) Export fold-stage import ruling (M5/M6 input): fold trim/extend math lives in geometry/
    (dxf_io may import ezdxf+geometry only, SPEC ?11.1; dxf_io NEVER imports rules) or app.py
    computes Trims and passes them into export.
(j) Pending corners live in the UI workflow layer as a PendingCorner record (edge1_eid,
    edge2_eid, Side, side_flip, r, db_id) ? NOT a ModelState field (no CONTRACTS ?1 change).
(k) Overlap semantics: place_corner's place-time overlap refusal is evaluated against APPLIED
    dogbones only; pending-vs-pending overlap is confirm-time warn + skip at Apply All
    (SPEC ?11.7). M4's Apply All re-places each pending against the live model immediately
    before applying it (never applies a stale CornerResult).

**Why:** Three independent review rounds (6.5/6/6) probe-confirmed: apply_corner crashed on the
ADR-012(c) re-apply flow; applied dogbones kept stale edge eids so a tangent-adjacent placement
silently deleted the first corner's rebuilt composite while its arc survived; filters.py and
runs.py had diverged on mixed-direction runs (place/apply disagreement -> Apply All crash);
flag_decisions outside Flag.options were persisted and destructive; one eid could carry two
flags; r<=0 gave wrong-diagnosis refusals; ADR-015(k)(l)(m) were cited in code but unrecorded.

**Alternatives:** Re-recording Dogbone eids at apply (CONTRACTS ?1 ripple); keeping the twin
promotion implementations with a sync test (divergence already happened once); prefix-chain-only
resolution without the canonical-eid ruling (leaves three consumers behaving differently).

**Consequence:** CONTRACTS ?1/?2 amended (CornerResult.warnings; side_flip + ghost_candidates +
resolve_edge signatures; RADIUS + unified UNKNOWN_EDGE strings pinned). M1's
test_rules_filters_promotion re-promotion assertion updates to the keep-seed-eid rule. M3
consumes (g)/(j)/(k); M4 consumes (b)/(c)/(d)/(k); M5/M6 consume (i).

## ADR-017 — 2026-10-05 — Export-time SolidWorks Educational watermark removal (M6.5; user-approved)

**Decision:** M6.5 removes the SolidWorks Educational watermark MTEXT at EXPORT time only, by exact plain-text match against a constant list `WATERMARK_TEXTS = ("SOLIDWORKS Educational Product.", "For Instructional Use Only.")` (the loader already stores plain text via `plain_mtext`; exact match, NEVER substring/word search — a user note merely containing "SOLIDWORKS" is untouched, honoring the user's "not other text, just that text"). The filter runs on the export deep copy (ADR-004 purity): working model, viewer, and the SPEC 11.5 corner-window MTEXT flag flow are unchanged. Controlled by an export-dialog checkbox "Remove SolidWorks Educational watermark", default ON; toggle OFF keeps the watermark. The list constant lives with the export code (M6.5 session pins the module) and is extendable if new watermark variants appear. The M6 final preview renders the export view (filter applied when ON) so the preview is WYSIWYG.

**Why:** The watermark is deterministic (identical two MTEXT strings in every SolidWorks Educational export — confirmed in both golden files and the user's "ISO 30 holder bottom 1.0.DXF"); all entities sit on layer 0, so layer filtering cannot catch it; and CAM behavior toward DXF text is not guaranteed (most CAM imports text as non-cuttable text, but SHX stroke-font text can explode into cuttable line geometry on some import paths).

**Alternatives:** Text-block UI (isolate MTEXT into blocks, user selects deletions — user's other suggestion): deferred to V1.1; it needs new selection/model-mutation/undo surface, unnecessary for a deterministic watermark, but remains the fallback if real files carry OTHER text needing removal. Substring/keyword match (risks deleting user text). Removal at load (breaks model↔file fidelity and reversibility). Doing nothing (relies on CAM behavior that is not guaranteed).

**Consequence:** New milestone row M6.5 (0.5–1h, depends on M6's export dialog) + ISSUE-013 registered. This ADR does NOT amend SPEC 11.5's "MTEXT never auto-deleted" — that clause governs the corner deletion pipeline; this is a user-configured, export-side filter (explicit checkbox, newest ADR wins). Acceptance: exported DXF has zero MTEXT matching WATERMARK_TEXTS with the toggle ON, every other MTEXT preserved byte-for-byte, toggle OFF keeps everything, double-export idempotent.

## ADR-018 — 2026-10-07 — M7 re-plan: 3D fold studio (scope-snap; user-approved; two review loops)

**Decision:** M7 is re-planned from "wireframe fold viewer" to a **view-only 3D fold studio**, phased **M7a (~5–7h)** + **M7b (~2–3h, additive)**. The tkinter canvas stays the editor and gains fold assignment; the browser is a dumb renderer of a Python-computed scene. Rulings (lettered; M7a session pins exact signatures in CONTRACTS §6, which this ADR authorizes):

(a) **Renderer.** Vendored three.js **r147 UMD** `three.min.js` + classic-script `OrbitControls.js` — NOT `three.module.js` (ES modules are CORS-blocked on `file://` in Chrome/Edge; `examples/js` was removed at r148 and UMD builds by ~r160 — r147 is the last release carrying both, that pin rationale is part of this ADR). The emitter assembles output = template + vendored three + scene JSON into ONE self-contained HTML (~600 KB, emailable, offline); the vendored file stays separate for diffability. Scene JSON rides in a `<script type="application/json">` block, parsed via `JSON.parse`, with `<` escaped as `\u003c`. Upgrade path (dev-time esbuild bundle of modern three) requires its own ADR; a banner comment in `template.html` forbids silent upgrades.

(b) **No assignment mode.** After M5 designation, every fold RUN (`chain_run`-merged; the after-file's 4-span bend is ONE run — golden-tested) auto-carries defaults (direction up, angle 90°). Click a run → inline popover at the run: up/down toggle, angle presets 45/90/135/180, custom field applying on Enter. No persistent spawned buttons. 2D callouts (teal up-arrow / amber down-arrow glyph + angle text at run midpoints; glyph direction carries the meaning, color secondary) are the pre-render review surface; they auto-declutter when crowded at current zoom + a panel toggle exists.

(c) **Click precedence lives in `rules/`** (pytest-able, not a canvas handler): corner-placement mode, when engaged, wins over everything; fold assignment hit-tests only designated fold runs at a tighter `EPS_FOLD` (< `EPS_PICK`).

(d) **Per-vertex folding.** `fold_point(plan, p)` classifies p by its sign vector against the fold runs (k-bit key, one bit per run; on-line → BFS-parent side), then applies the flip-one-bit BFS-composed transform chain (BFS rooted at the largest region, tie → lowest eid; each flip = Rodrigues rotation about the fold line in the parent's folded frame). Every emitted VERTEX is folded through `fold_point` — entities crossing a fold line kink across it (visually correct), replacing per-entity classification (loop-2 finding: per-entity folds straddling geometry wholesale to one side). Warn-only failure modes: through-slot disconnect (two areas, same key), uncloseable chains.

(e) **M7a geometry = sharp folds.** Plate polygons share vertices at fold lines (the folded-paper look). The tangent model — pullback `d = R·tan((180°−θ)/2)`, axis offset R — lives in scene-JSON **metadata** per fold (`R, θ, T, axis, δ, adjacent plate edges`) so **M7b** applies pullback + stitched bend skins (cylinder sectors radius R inner / R+T outer + ring end caps, one parameterized code path for ALL angles) + ACM V-grooves as ONE coordinated emit/template bump. M7a never bakes pullback into plate vertices (loop-2 finding: gappy floating plates for a whole milestone). Rigidity golden (distance preservation) stays exact in both phases. Accepted simplification, logged: tangent spacing vs neutral-axis arc costs ~0.3 mm per 90° fold at R=2/T=1 (~1.4 mm over 4 folds) — a render is a sanity check, never fabrication data.

(f) **Materials.** Docked panel (no modal): Sheet Metal / ACM radio; ACM thickness buttons 3/4/6 mm/custom (default 4 mm); radius field default 2 mm, editable; Enter-in-thickness advances focus to radius. Sheet-metal thickness derived `T := R`, displayed explicitly ("T = R = 2 mm — edit radius to adjust"). ACM radius = **residual exterior corner radius** (user decision 2026-10-07). All inputs bind to `$INSUNITS` with dual display (e.g. "R = 1.59 mm (1/16″)"); default radius derives from file units.

(g) **Emission purity.** `to_scene_json` reads (entities, fold_eids, fold_props, material, units) **from the snapshot only** — a pure function, byte-equal on two runs (determinism golden). "Session memory" for material = new parts inherit last-used defaults INTO their snapshot; nothing floats in UI state. All warnings (box corners, hems: run pairs closer than 2·d, through-slot, uncloseable→wireframe degrade) are computed **Python-side** into `meta.warnings`; JS only renders the list.

(h) **Box corners** (intersecting folds): warn + affected region renders FLAT with ghost-dash styling + named HUD banner ("corner region not folded — intersecting bend lines"). No notch synthesis, no composition. Hems: HUD warning only. Never a silent omission.

(i) **Outline chaining** uses ezdxf 1.4.4's own `edgeminer`/`edgesmith` (verified present in the pinned venv this date; `visualization/` may import ezdxf per CONTRACTS §5). Outer-loop-only extrusion in V1; interior loops (tab slot, rib walls) render as top-face line loops; any entity set that won't close degrades to wireframe with a warning — the plan never fails. LoopFinder's loop ORDER is not a contract: normalize (sort by min vertex tuple, canonical orientation) before emit. Prototype-first: whether `Edge` accepts our endpoints directly or needs a scratch doc is M7a's opening spike.

(j) **State split.** M5 owns `fold_eids` (designation); M7 adds `fold_props: dict[eid → {direction, angle}]` + part-level render props (material, thickness, radius) to ModelState snapshots — undo/snapshot-integrated, never exported. **Session-only** for V1 (user decision 2026-10-07): sidecar-JSON persistence is a deliberate V1.1 deferral, not an oversight (re-assignment costs ~4–6 clicks on a typical part).

(k) **Camera state.** The browser page persists orbit pose to `localStorage` keyed by preview filename and restores on reload (pure JS, `file://`-legal, no server) — Refresh = regenerate + reopen WITHOUT losing the view (both loop-2 UX critiques named this the highest-leverage fix).

(l) **Trust furniture** (browser page): axes triad; HUD line (material, T, R, dual units, "angles assumed — visualization only, not fabrication data"); translucent bend-zone bands at each fold (relief-vs-bend proximity at a glance); iso/dimetric camera presets; flat↔folded toggle. Visualize button disabled with an inline hint at zero designated folds.

(m) **Tests (headless).** Golden L-fold + zigzag U-bracket (hand-computed ±1e-9); rigidity spot-check; determinism (byte-equal JSON, two runs); 4-spans→1-run merge assert; **rib-wall-crossing-a-fold fixture** (encodes the per-vertex ruling); dogbone-tangent-to-run silhouette fixture (arc stays attached after folding); scene-JSON key-structure golden + template placeholder check (the emitter↔template contract); min-angle guard (10°, tan blow-up) refusal.

(n) **Cut from the first draft:** edge bevels (invisible at judging zoom), blue/red direction coding (red = deletion on our theme; teal/amber glyphs instead), custom-angle-button-creation flow (popover field instead), the global zigzag scheme (explicit per-run assignment replaces it), per-entity region classification (see (d)).

**Why:** The 2026-10-07 first-draft brief predates the user's product decisions (per-fold direction/angle assignment, material selector SM/ACM with V-grooves, radius field, white ACM render) and two three-persona review loops (UI/UX 7→8, CAD professional 6→8, senior architect 7→8; artifacts in session log 2026-10-07-M7-plan). The loops converged: correction-loop cost is the feature (angles/directions are guesses by construction — neither is in the DXF), never fail silently, and the JS half must stay a dumb renderer (all logic Python-side, golden-testable).

**Alternatives:** pywebview/cef embed (process/DPI/shutdown burden, own-ADR deferred); vpython/pythreejs/vedo/pyvista (pip/numpy/server — violate ADR-008/ADR-018 constraints); `ezdxf.addons.drawing` backends (2D-only, doc-coupled); py3d (unmaintained); localhost live-poll server (contradicts the locked offline/no-server ruling; V1.1 candidate, own ADR); per-entity classification (loop-2 falsified: straddling rib walls); M7a with baked pullback (floating gappy plates for a milestone); modal material dialog (mode/confusion findings); persisting assignments to a sidecar now (speculative — empirical V1.1 call).

**Consequence:** `documentation/briefs/M7.md` is REWRITTEN (this ADR + the rewritten brief supersede the 2026-10-07 first draft together); ISSUES.md M7 row updated by the planning session; CONTRACTS §6 (visualization contracts) is pinned at M7a session start under this ADR's authority; AGENTS.md gains the `visualization/` stack-map row at implementation. Sequencing unchanged: M7 runs after M5+M6 (user decision). Estimates: M7a 5–7 h, M7b 2–3 h (the UI items are the flagged chronic-underestimate risk; M7a DoD gates on a clickable UI before any skin polish).


## ADR-019 - 2026-10-07 - M4b re-plan: Apply-to-Similar dot flow (scope-snap; user-approved sprint-start Q&A)

**Decision:** M4b's Feature A (ISSUE-018) is re-planned around a **dot-selection review flow** (user request 2026-10-07: "show what it thinks are all the similar geometries and have a largish dot on each one I can select or deselect (green or red) before hitting go"). Feature B (guided tour, ISSUE-019 - and with it ISSUE-010 joint auto-detection) moves to a LATER sitting: the detection risk stays isolated and the dot flow ships first. Rulings (lettered; the M4b session pins exact signatures in a new CONTRACTS section under this ADR's authority):

(a) **Similarity predicate = angle + run shape.** A candidate corner matches the template corner iff: (1) corner angle within **ANG_TOL_DEG = 2.0 degrees** (explicit tolerances.py constant, never inline; the apex gate's own [15,165] band applies first), AND (2) promoted-run shape match: run member-count and per-member length sequence equivalent under the candidate-vs-template comparison, where **mirrored and rotated configurations are ALLOWED** (both reversal and reflection of the member-length sequence; rotation invariance falls out of angle-only comparison, reflection handles the corner2/corner3 mirror pair), within **LEN_TOL_MM = 0.01 mm** per member (EPS_COINCIDE-class). The template's OWN corner never appears in its own match set; already-dogboned corners are excluded (their edges are composites under applied arcs). Tear debris/stubs/holes near the apex are NOT part of the predicate - the predicate reads promoted RUNS only (the never-cut deletion review, (d), is what protects against surprise deletions).

(b) **Matching lives in `rules/` as a new pure surface** (ADR-010-safe: consumes eids, returns eids; may import geometry only): `similar_corners(primitives, template: CornerResult|Dogbone, ang_tol_deg, len_tol_mm) -> list[SimilarMatch]`, where `SimilarMatch` carries the candidate edge-pair eids, the mapped Side/side_flip, and the recomputed dogbone construction for review. The UI never matches geometry itself.

(c) **Mirror-mapped replay.** A mirrored candidate receives the Side/side_flip mapped through the mirror transform (the template's bisector sign flips under reflection); the mapped construction must still pass the full place_corner pipeline at review and at Go time - the mapping is a candidate SEED, never a bypass of the truth table, overlap check, or flag flow.

(d) **Dots + hover review = the never-cut surface.** After Confirm of the template corner, every match renders as a largish canvas dot at the candidate apex: default ALL GREEN (opt-out by clicking; red = deselected), template's own corner marked distinctly. Hover a dot -> status-line/tooltip summary of THAT candidate's place_corner result (deletion summary EXACT format "Deleting: N LINE, N ARC - Trimming: N - Flagged: ...", plus refusals/warnings); click a dot -> auto-zoom to that corner with the full red deletion preview (the M3 preview surface, read-only), then return to the dot map. Go requires zero pending review; nothing applies unaudited.

(e) **Go = template-R replay through the existing ApplyQueue.** Go applies the selected (green) candidates in document order, each re-placed LIVE per ADR-016(k) with the TEMPLATE dogbone's R (not the current panel field - the user's words "apply the same dogbone" are the contract; a mid-review panel edit does not silently resize a replay), its own db_id (deterministic "db-<e1>+<e2>" stays), and the mirror-mapped Side/flip. Failure policy = M4 warn-and-skip VERBATIM (engine string, corner dropped, batch continues); a candidate that refuses or surfaces NEW pending flags at Go time is skipped, never blocked.

(f) **Undo granularity (user ruling 2026-10-07: "per corner with an escape feature that essentially undoes all the progress").** Each green candidate applies as its OWN one-corner batch (ADR-001 snapshot immediately before each mutation) - Undo walks back applied matches one at a time. The pre-Go snapshot is ALSO kept on the stack; the tool panel gains **"Undo Batch"**, which restores the pre-Go snapshot in one hit (escape hatch). This makes M4b Feature A the first multi-granularity consumer of ADR-001; the guided tour's "one-corner batches" line (planned Feature B ADR) merely reuses this precedent. Revert-to-Original unchanged (M4).

(g) **No FSM contract change to M3/M4 seams.** The dot flow is a new post-Confirm mode in `ui/` (new owner file, e.g. ui/similar_panel.py) driving the EXISTING WorkflowUI/ApplyQueue ports; `rules/`, `geometry/`, `model/` internals untouched beyond the new `rules/similar.py` surface + `geometry/tolerances.py` constants (ANG_TOL_DEG, LEN_TOL_MM). CONTRACTS gains the similarity section under this ADR.

**Why:** The 2026-10-07 M4b brief left the predicate, review surface, and undo semantics as sprint-start open questions; the user's dot-flow request answers the review-surface question directly (batch-review-by-map replaces the sequential candidate list - one pass over the part replaces N list entries) and the sprint-start Q&A locked the rest (10 answers recorded in session log 2026-10-07-M4b-plan). All-green default + hover-audit + click-through preview preserves the deletion-preview-never-cut invariant (AGENTS #5) at BATCH scale without per-candidate modals.

**Alternatives:** Sequential candidate list w/ per-item Confirm (the brief's first draft: N confirms, highest click cost); angle-only predicate (false positives on same-angle/different-tab corners); strict neighborhood match incl. tear debris (the golden pair's tear layouts DIFFER - near-zero recall on real parts); current-panel-R at Go (silent resize contradicts "the same dogbone"); single batch snapshot w/ one Undo (cannot surgically remove one wrong match - user explicitly ruled per-corner + batch escape); Go-time summary list before apply (extra click; hover + click-through already carries the never-cut audit).

**Consequence:** `documentation/briefs/M4b.md` is REWRITTEN (this ADR + the rewritten brief supersede the 2026-10-07 first draft together); ISSUE-018 scope updated (dots; Feature B split out); ISSUES.md M4b row updated by this planning session; the M4b session pins the CONTRACTS similarity section (signatures per (b)) at sprint start. Gates: pytest similarity-predicate unit tests (mirror pair matches, angle-drift boundary, run-shape rejection, template exclusion, dogboned-corner exclusion), dot-flow harness drive on the golden sample (corner2 template -> corner3 match -> dot toggle -> Go -> model assert), verify_m2/verify_gui --full unchanged-and-green, human checklist (dots visible/largish, green/red toggle, hover summary, click-through zoom, Go applies, per-corner Undo, Undo Batch escape). Feature B (guided tour + ISSUE-010 detection + ADR-009 allow-all amendment) re-scoped to a LATER sprint under its own brief revision; ADR-009 is NOT amended in this sprint.

## ADR-020 - 2026-10-07 - M4b loop-1 amendments (senior-UI-review findings; user-approved review process)

**Decision:** ADR-019 is AMENDED per the loop-1 plan review (persona: senior full-stack/desktop-UI developer; verdict 6.0/10; 15 findings; full text in session log 2026-10-07-M4b-plan). Rulings supersede conflicting ADR-019 lines (newest ADR wins, ADR-011):

(a) **Template application timing (review blocker 1):** Confirm APPLIES the template corner immediately as its own one-corner batch (reading (B)); the dot mode runs against a model where the template is already applied. Dot mode suppresses the M4 queue UI for the template corner (Confirm in dot-entry = apply, never enqueue); Apply All is disabled while dot mode is active. "Undo Batch" removes the SIMILAR MATCHES only (the pre-Go snapshot keeps the template applied); plain Undo pops the last one-corner batch (template or match, whichever applied most recently). The dogboned-corner exclusion (ADR-019(a)) is live: candidates already under applied arcs are excluded.

(b) **TemplateShape capture (review blocker 2):** the predicate cannot read the template's run shape post-apply (apply_corner removes run members and shortens the composite - per-member lengths are unrecoverable from a Dogbone). The dot-mode entry captures a `TemplateShape` record at confirm time, pre-apply: per edge, the promoted run's member count + per-member length sequence (resolved via chain_run) + the corner's smaller angle. `similar_corners` takes `template_shape` (not a Dogbone/CornerResult - the ADR-019(b) type union is void).

(c) **Click semantics pinned (review major 3):** single-click a dot = TOGGLE green/red (the user's requested interaction - now in the ADR, not just the brief); double-click (or right-click on a dot) = click-through zoom preview; canvas-miss = no-op (never starts an edge pick inside dot mode). Esc = exit dot mode (match set dropped, model unchanged - template stays applied).

(d) **Dot shape-coding + theme keys (review major 4):** state must be legible WITHOUT color (deuteranopia; red already means "will be cut" app-wide): filled dot = will apply, hollow/X-slit dot = deselected. New theme keys `similar_on`/`similar_off` (green / neutral gray, NOT delete-red - a red dot must never read as inert when the app teaches red = deletion). Color is secondary, shape/glyph carries the meaning (ADR-018(b) precedent).

(e) **Dot re-render after viewer redraws (review major 5):** the dot layer re-renders on EVERY viewer redraw (pan/zoom `redraw`, `set_model`) via a deferred post-redraw hook, recomputing screen positions from world apexes. Harness test: wheel-zoom mid-dot-mode asserts the dot item count survives. Dots carry a MINIMUM screen size (constant px radius, clamped world-size) - "largish" = a pinned constant, not an adjective.

(f) **Event interception via owner-file subclass (review major 6):** `SimilarWorkflowUI(ApplyAllWorkflowUI)` lives in ui/similar_panel.py and overrides `_on_left`/`_on_right`/`_on_esc`/`_sync_view` - dot mode CONSUMES all canvas events (workflow.py/apply_panel.py untouched). Dot hit-test is a screen-px radius test against world apexes (the ghosts' math-list pattern).

(g) **Per-corner batch mechanism pinned (review major 7):** one ApplyQueue instance per candidate (each one-corner apply_all pushes its own pre-mutation snapshot - zero edits to apply_panel.py) OR a similar_panel-local ApplyQueue subclass with a per-candidate snapshot policy; the session picks one and writes it into the CONTRACTS section. "Undo Batch" = pop-until-preGo (`stack.undo()` until state equals the held pre-Go snapshot), implementable without touching model/snapshots.py; zero mutations at Go -> Undo Batch disabled, not no-op.

(h) **Undo Batch availability rule (review major 8):** Undo Batch is enabled only while the current top-of-stack segment above the held pre-Go snapshot is THIS batch's work; disabled once fully unwound or superseded by later applies (restoring pre-Go past newer work would silently destroy it). Undo toasts carry WHAT was undone ("Undid similar corner 2 of 3" / "Restored pre-Go state (N similar corners undone)"); plain Undo's toast names its granularity.

(i) **Side/flip mapping = mapped-center argmin (review major 9):** map the template's dogbone center through the canonical local-frame transform (apex + run directions) into the candidate's frame, enumerate the candidate's `ghost_candidates`, pick the (Side, flip) whose center is NEAREST (argmin), assert the distance within eps_coincide-class tolerance. Self-validating, uniform across mirror/rotation/role-swap; a mis-mapped seed that lands wrong fails the assert rather than placing inside material. The ±2° tolerance applies to the CORNER angle (the smaller included angle, ADR-015(g)'s compute_apex half-angle x2); the boundary test pins 1.9-in/2.1-out on that quantity. ROLE-SWAP (edge1<->edge2, which a 90-degree-rotated corner produces) is IN scope - the mapped-center argmin handles it uniformly; a rotated fixture joins the DoD.

(j) **ADR-019(d)/(e) reconciled (review minor 13):** Go is NEVER blocked by review state. "Zero pending review" is deleted from ADR-019(d); candidates surfacing NEW pending flags at Go time are warn-and-skipped per (e), never blockers. (ADR-019(d)'s never-cut surface = the hover + click-through affordances + per-dot deletion counts (k); audit availability, not audit compulsion.)

(k) **Precomputed previews + zero-click visibility (review minor 11):** all candidate CornerResults are precomputed at dot-mode entry (the model cannot change between entry and Go - Undo/Revert exit the mode first; Go's live re-place per ADR-016(k) stays the safety). Each dot renders its deletion count as a text badge ("3L 1A") beside it - zero-click review, the mitigation that makes the all-green default safe.

(l) **Enumeration + document order pinned (review minor 10):** candidates = all Seg pairs after per-Seg chain_run promotion, deduped by canonical run eid (each physical corner appears once), apex-gate before predicate; "document order" = index of the run's first-appearing member in primitives.

(m) **Summary-format byte-drift guard (review minor 12):** similar_panel reimplements the M3 summary composition (workflow.py untouched) + a byte-equality pytest against `WorkflowUI.summary_line()` fed the same CornerResult.

(n) **Click-through view restore (review minor 14):** click-through zoom stores the pre-zoom transform and restores it on return, so the dot map position survives the detour.

**Why:** The loop-1 review found the two blockers that would stall the sprint mid-implementation (template timing ambiguity forks every downstream artifact; the planned signature computes with data that no longer exists post-apply), five event/undo integration landmines the plan was silent on, and a colorblind/color-grammar defect against the repo's own ADR-018 precedent. All are pin-able now at zero code cost.

**Alternatives:** Reading (A) (Confirm enqueues, Go flushes queue+greens) - rejected: forks Undo-Batch semantics, kills the dogboned-corner exclusion, and leaves the queue UI enabled mid-dot-mode; angle-only tolerance on the half-angle - rejected as a 2x drift error; compute-on-Motion hover - rejected (wasteful, flicker-adjacent; precompute is provably fresh until Go's live re-place); tooltip widget as primary hover surface - deferred (the bottom status line is the pinned home; a cursor tooltip only if warnings overflow the line); rotation/role-swap cut to V1.1 - rejected (the argmin mapping covers it at no extra design cost; the rotated fixture pins it).

**Consequence:** ADR-019 rulings (b)(d) are superseded where ADR-020 conflicts (ADR-011: newest ADR wins): similar_corners takes template_shape; click semantics, dot coding, re-render, interception, batch mechanism, Undo-Batch availability, argmin mapping, and precompute are now contractual. `documentation/briefs/M4b.md` is amended to match (flow steps 1-4, predicate section, dot UI section, Go semantics, Undo section, DoD). The M4b session pins the CONTRACTS similarity section per ADR-019(b) as amended here. Estimate re-baselined 5-8h per the review (ADR-019's 3-4h line is void); DoD extends with the loop-1 tests (0-match exit, all-red Go, zoom survival, mid-mode Undo/Revert, Undo-Batch-after-interleaved-work, deterministic toggle-negative drive, rotated fixture, byte-equality summary test, dot minimum-size assert).

## ADR-021 - 2026-10-07 - M4b loop-2 pin-set (second senior-UI review; implementation-ready rulings)

**Decision:** The loop-2 review (same persona, fresh eyes on the ADR-020-amended plan; verdict 7.0/10, loop-1 fix quality 7.5/10, full ledger in session log 2026-10-07-M4b-plan) graded loop-1 fixes 9 RESOLVED / 4 PARTIAL / 0 WORSE and found 1 new blocker + 6 majors + 3 minors. This ADR pins the remaining pin-set; it supersedes conflicting ADR-019/020 lines (ADR-011: newest ADR wins). Rulings:

(a) **Dot-mode entry is OPT-IN via an app.py-glue "Apply to Similar" arm button** (the loop-2 blocker; also loop-1 blocker 1 reborn one level up). Armed: the NEXT Confirm applies the template immediately (ADR-020(a)) and enters dot mode. Unarmed: Confirm = M4 enqueue, BYTE-UNCHANGED (M4 batch semantics untouched, per the ISSUES M4b row's own clause). app.py glue owns the arm button + constructs SimilarWorkflowUI (is-a ApplyAllWorkflowUI; unarmed behavior is inherited M4). The verify_gui drive arms explicitly before Confirming the template.

(b) **TemplateShape gains r: float** (the template dogbone radius, captured pre-apply; equivalently |center-apex| - asserted at capture). The argmin mapping's ghost enumeration needs it; the hidden derivation is now a stated field, not an implied invariant.

(c) **Argmin frame variants:** the mapper enumerates the role assignment(s) that the run-shape predicate MATCHED (identity and/or edge1<->edge2 swap) and argmins per matched assignment (global argmin across enumerated variants is equivalent and the session pins which). Side is edge1-relative, so a role-swapped candidate maps through the swapped frame or the seed lands on the mirror ghost. Assert per matched assignment (ADR-020(i) unchanged otherwise).

(d) **Green means appliable - hard invariant.** Candidates whose entry precompute returns !ok (apex-band, span, tangent refusals) are EXCLUDED from the match set (never rendered as green dots - a green dot must mean "will apply or warn-and-skip at Go", and a refused candidate can never apply; the loop-2 review called rendering them green "hollow"). Badge gains the flag count ("3L 1A +2F" style - session pins the exact badge grammar).

(e) **Pending flags at Go route through the sticky decide_flag flow, not silent skip.** At Go, a green candidate with new pending flags triggers the existing first-occurrence decide_flag port (sticky per eid per ADR-009 - typically 1-2 modals per part, then re-place honors decisions); a still-refused re-place warn-and-skips verbatim (ADR-020(j) unchanged: Go never blocks).

(f) **Post-redraw dot re-render = instance-level redraw wrapper installed by similar_panel at dot entry, removed at exit** (canvas_view.py untouched - the "deferred post-redraw hook" ADR-020(e) assumed does not exist in Viewer.redraw; wheel bindings fire but PROGRAMMATIC redraws - click-through zoom, set_model->fit - fire none). DoD adds a programmatic-redraw dot-survival test alongside the wheel test (ADR-020(e)'s wheel-only test would pass while click-through ships broken).

(g) **Undo Batch lives in app.py glue** (persistent across mode exit - the escape hatch is needed post-Go review, when similar_panel's own panel is gone; ToolPanel is in frozen apply_panel.py). Availability per ADR-020(h) via a **depth-keyed provenance ledger** ({stack length at push: label} maintained at every push seam similar_panel drives; SnapshotStack stores no labels - snapshots.py untouched); M4's existing toast strings stay BYTE-IDENTICAL (M4 harness gates pin them); only the new M4b toasts are new strings in ui/messages.py.

(h) **Click mechanics refined:** toggle on RELEASE-if-no-drag (press+drag = pan; toggle-on-press would fire during pans); double-click = zoom-through ONLY (the first press of a double-click would otherwise toggle twice with 2px jitter risk - the toggle applies on release only when not part of a double-click; tkinter Double event suppresses the second toggle). Click-through return: any click or Esc returns to the map; Esc AT THE MAP level exits dot mode (two-level Esc). **Esc-at-exit toast states the match set is dropped permanently** (TemplateShape cannot be re-derived post-apply - ADR-020(b)'s whole point); the template stays applied.

(i) **Queue coexistence:** queued pendings persist through dot mode (M4 revert-keeps-queue precedent); a corner that is BOTH queued and a green candidate applies once at Go and warn-and-skips as OVERLAP at the later Apply All (documented passthrough, not exclusion - the live re-place's overlap check is the safety; the toast names it).

(j) **files-owned += ui/theme.py + ui/messages.py** (similar_on/similar_off keys + new M4b strings have no other legal home - grep-clean forbids hex outside theme.py; loop-2 minor 8 would otherwise STOP a literal-minded implementer). ui/workflow.py, ui/apply_panel.py, model/, rules/engine.py, rules/filters.py, geometry/ internals remain frozen.

(k) **Estimate re-baselined 8-12h** (loop-2: the amended DoD's ~15 test cases + drive are half the sprint; 5-8h was still optimistic for rules module + panel + wrapper + ledger + badges).

**Why:** Loop-2 verified the ADR-020 fixes are real (9/15 fully resolved) but found the entry gesture undefined (every reading of "Confirm applies immediately" either killed M4's queue or contradicted the row's own untouched clause), two silent argmin math gaps (r missing from TemplateShape; role-swap frame variant unnamed), the green=appliable invariant broken by refused-candidate dots, flag-pending candidates silently skipping at Go, a redraw hook that Viewer does not actually provide, Undo Batch's home on a frozen file, and estimate still ~40% optimistic.

**Alternatives:** Dot mode on every Confirm (kills M4 queueing - rejected); exclusion of queued-and-candidate corners at Go (rejected - passthrough with overlap skip is the M4-verbatim behavior and documents itself); rendering refused candidates as a distinct glyph (rejected - adds a third dot state for zero apply value; exclusion keeps green=appliable total); deriving r silently from |center-apex| (rejected - the assert at capture makes the invariant self-documenting); tooltip home for the badge grammar (rejected - status line + badge text only, per ADR-020(k)); cutting the DoD instead of re-baselining (rejected - the loop-2 tests encode the loop-1/2 findings; cutting them re-opens the defects).

**Consequence:** briefs/M4b.md is amended to v3 (flow, TemplateShape, predicate pin, dot UI, Go, undo, DoD, files-owned, estimate); ISSUES.md M4b row updated; session log appends the loop-2 ledger + actions. The M4b session pins the CONTRACTS similarity section per ADR-019(b) as amended by ADR-020/021. Loop-2's "do NOT fix" list is preserved: per-corner batches via one-queue-per-candidate, TemplateShape capture, argmin-as-self-validating-seed, availability rule, template-R replay, warn-and-skip verbatim, headless rules/similar.py, rotated fixture + byte-equality + interleaved-undo tests.

## ADR-022 - 2026-10-07 - M4c re-plan: Guided Dogbone Tour (sequential walk; user-approved sprint-start Q&A; splits from M4b per ADR-019)

**Decision:** The guided tour (ISSUE-019; user request 2026-10-07: "a mode where it leads me through every joint that should have a dogbone and each direction shows up for me to click, plus a Skip button; allow-all so I'm not clicking allow three times; Undo undoes the last one in that list") is registered as milestone **M4c** with its own brief, superseding the first-draft M4b Feature B text and fulfilling ADR-019's "Feature B re-scoped to a later sprint under its own brief revision." Rulings (lettered; the M4c sessions pin exact signatures in CONTRACTS under this ADR's authority):

(a) **Sequential walk** (user ruling, reaffirmed over the dot-map hybrid): auto-zoom walks joint-to-joint in document order; the stop is the unit of interaction. M4b's plumbing (redraw-survival wrapper ADR-021(f), event-consumption subclass pattern ADR-020(f), per-corner batch precedent ADR-020(g)) is INHERITED, not redesigned.

(b) **Detector = recall-first** (ISSUE-010, forced and now designed): propose every plausible junction (two-run corners meeting within gate geometry); false positives surface as skippable stops (cheap); misses are recoverable via the normal manual flow (the tour is an assistant, never the only path). The detector is a NEW pure `rules/joints.py` surface (headless, eid-referenced, imports geometry only); apex gate + place_corner remain the authority. Joint = a pair of promoted runs sharing an endpoint region (chain_run + adjacency machinery); document order per ADR-020(l).

(c) **Suggested ghost + three-button stack** (user custom ruling 2026-10-07, reconciling the two direction answers): at each stop the engine's best-guess ghost renders HIGHLIGHTED (ring) with its red deletion preview - the never-cut invariant makes the preview visible BEFORE Next applies; the other three ghosts stay hidden until **Edit** reveals all four for selection. The stop carries three buttons stacked vertically, persistent through the tour: **Next** (apply the current selection - suggested or edited - and advance), **Skip** (no dogbone here, advance, joint marked skipped), **Edit** (reveal the four-ghost picker; a ghost click sets the current selection and updates the preview; Edit never applies). Plus **Prev** (revisit the previous joint: skipped joints re-open as normal stops; applied joints re-open read-only showing the applied dogbone - plain Undo pops it, ADR-020(g) one-corner batches - and Next moves forward again).

(d) **Suggestion algorithm:** the suggested (Side, flip) at a joint = argmin-mapped from the user's most recent manual pick at a SIMILAR corner (reuses M4b's mapped-center argmin machinery - the tour's template is the last manual pick), falling back to a clearance heuristic (the ghost center with max min-distance to non-corner entities in the corner window) when no similar prior exists. Session pins details in CONTRACTS; the suggestion is a SEED - every apply runs the full place_corner pipeline.

(e) **Flag allow-all = safe-split auto, TOUR-SCOPED** (ADR-009 AMENDMENT, narrow): during tour mode ONLY, flagged entities auto-decide by class with zero modals: CASCADE_DANGLING debris -> auto-DELETE (the cascade already orphaned it); CHORD_CROSSER ARC -> auto-TRIM (geometric resolve, never deletion; trim unavailable -> keep + warning); CIRCLE_IN_WINDOW / MTEXT_IN_WINDOW / ARC_ENDPOINT_IN -> auto-KEEP (never auto-destroy) with the non-blocking warning in the stop summary. Decisions stay sticky per ADR-009 (travel in snapshots; Revert clears). Outside tour mode the per-entity first-occurrence modals are BYTE-UNCHANGED. No mid-tour per-entity override in V1 (the stop summary + end report list kept entities; the manual flow remains the override path).

(f) **Refused joints: show + auto-skip.** A detected joint that fails gates (apex band, place refusal) shows its stop briefly with the engine refusal string on the status line and auto-skips into the end report. Nothing invisible, nothing blocks the walk.

(g) **Radius = current panel R**, live mid-tour (quick-pick buttons re-place the current stop per ADR-016(k); applied joints are done).

(h) **Per-item undo:** every tour-applied joint is its own one-corner batch (ADR-020(g) precedent - no new snapshot machinery); plain Undo mid-tour pops the last applied joint; mid-tour Undo/Revert exits the tour cleanly first (M4b mode-exit precedent).

(i) **End-of-tour report:** status-line + toast summary - applied N, skipped M, auto-skipped-refused K, kept-flagged list (per stop: joint id + class). No new dialog.

(j) **Sprint split (user ruling; one-shot-ability):** **M4c1 = headless detector** (~3-4h): rules/joints.py + golden tests on the sample pair (both T-junctions + the ramp corner = 3 joints detected) + the syn corpus (SAMPLES-SYN.md 12-file manifest as negative/positive controls) + suggestion-algorithm unit tests. **M4c2 = tour UI** (~4-6h): ui/tour_panel.py (the button stack + stop overlays), FSM tests, verify_gui drive, human checklist. One brief, two phases (M7a/M7b precedent); M4c2 starts only when M4c1's gates are green.

**Why:** ADR-019 split the tour out to isolate ISSUE-010's detection risk; this Q&A (11 answers, session log 2026-10-07-M4c-plan) designs it: recall-first makes detector misses cheap (manual flow unchanged), the three-button stack replaces per-stop modal friction with one persistent control surface (the user's own design), safe-split auto kills the "clicking allow three times" complaint without shipping a geometry-eater, and the M4b machinery (argmin mapping, redraw survival, one-corner batches, mode-exit rules) is directly reusable - the tour is now mostly an FSM over existing engine surfaces.

**Alternatives:** Dot-map hybrid (rejected by the user - "leads me through" reaffirmed; the hybrid remains a V1.1 candidate reusing both features); precision-first detection (rejected - misses on odd joints are the expensive failure once the tour is trusted); auto-delete-all flags (rejected - risks holes/text near corners); session-wide allow-all (rejected - the normal flow keeps its modals byte-unchanged, harness gates depend on them); four-ghosts-always-visible (rejected - user's Edit ruling; Edit reveals them; the suggestion + preview still satisfies never-cut); auto-advance after apply (rejected - user's three-button ruling replaces it; Next is the advance gesture); per-joint R override field (stays V1.1 ISSUE-006).

**Consequence:** `documentation/briefs/M4c.md` is WRITTEN (supersedes the first-draft M4b Feature B text together with this ADR); ISSUES.md gains the M4c row (M4c1+M4c2 phases); ISSUE-019 re-scoped to M4c; ISSUE-010 is now designed (recall-first, rules/joints.py) and owned by M4c1; ADR-009 amendment recorded per (e) (narrow, tour-scoped; sticky mechanics unchanged). The M4c sessions pin the CONTRACTS sections (joint detector + suggestion algorithm + tour FSM) at sprint start under this ADR's authority. Estimates: M4c1 3-4h, M4c2 4-6h (M4b reviews' 1.5-2x lesson applied). DoD: M4c1 - golden detection counts on both sample files + syn corpus + suggestion goldens; M4c2 - FSM tests (next/skip/edit/prev, refusal auto-skip, allow-all class mapping, sticky travel, per-item undo, mid-tour undo/revert exit, redraw survival) + verify_gui tour drive (walk the before-file: 3 joints, apply 2 + skip 1 + edit-override 1, undo pops one, report contents) + human checklist.

## ADR-023 - 2026-10-07 - M4b loop-3 technical pin-set (third review; construction seams + mapping math + ledger keys)

**Decision:** The loop-3 review (persona: senior engineer, state machines/undo systems/geometric algorithms; TECHNICAL-ONLY scope per user ruling - UX excluded; verdict 7.0/10 technical readiness; ADR-021 fix quality 9/11 sound) found 2 blockers + 5 majors + 5 minors, mostly seams ADR-021 named but did not pin to the call site. This ADR is the loop-3 pin-set; it supersedes conflicting ADR-019/020/021 lines (ADR-011: newest wins). Rulings:

(a) **Construction timing (loop-3 blocker D1):** `_ensure_workflow` constructs **SimilarWorkflowUI ONCE AT LOAD** (is-a ApplyAllWorkflowUI; unarmed behavior inherited byte-unchanged); the arm button flips an instance boolean. NEVER a second bound instance - a second `add=True`-bound instance double-fires every canvas click, and replacing `self.workflow` constructs a fresh SnapshotStack whose `push_load()` erases all undo history (app.py:85-90, snapshots.py:55-58).

(b) **Armed-Confirm interception seam (D3):** intercept at `confirm_click`, not merely at `apply()`. Armed: `SimilarWorkflowUI.confirm_click` calls `WorkflowUI.confirm_click(self)` (grandparent; frozen files untouched) then runs its own dot-entry path (status, fit, dot render, precompute) - it must NOT fall through to ApplyAllWorkflowUI's post-confirm body, which posts ENQUEUED_TOAST ("Corner queued (1 pending)") and restarts to PICK_EDGE1, byte-wrong for an immediate apply (apply_panel.py:439-449). Unarmed: inherits M4 confirm_click byte-unchanged.

(c) **TemplateShape capture seam (D2-adjacent, question B):** capture INSIDE the armed `apply()` override, pre-mutation, from `fsm.pending.edge1/2_eid` + `resolve_edge` against pre-apply primitives + `res.dogbone.center/apex/r` (the FSM restart wipes pick state after apply - there is no post-Confirm seam).

(d) **Composite-run rule (loop-3 blocker D2):** a run whose flattened member list includes eids ABSENT from primitives (rebuilt composites - apply_corner removes members, model.py:144-151; chain_run preserves their eids via _member_ids, runs.py:143-147) counts as **ONE member of length |run.b - run.a|**, for template capture AND candidate runs alike. Alternative (exclude composite runs from the predicate) is equivalent; the one-member rule is pinned because it never crashes either side. DoD gains a re-promoted-composite fixture (T-cap template).

(e) **Argmin mapping formula - renormalized + rescaled (D4):** the affine frame map alone leaves a radial error of R*|cos(phi_c/2)/cos(phi_t/2)-1| (~0.055 mm at 2 deg drift - 55x EPS_COINCIDE), failing the pinned boundary test. The mapping is: mapped center = `apex_c + r * unit(L(center_t - apex_t))` per matched role assignment (L = the affine frame map u1->v1, u2->v2); assert against the ARGMIN ghost within EPS_COINCIDE. Argmin robustness is proven: the ghost-direction set {+/-unit(u1+u2), +/-unit(u1-u2)} is invariant under sign/role perturbations and min ghost separation is r*sqrt(2). The 1.9-deg-in DoD fixture is the FIRST test written (the canary).

(f) **Entry-time mapping-assert failure = exclude, never crash (D5):** a predicate-matched candidate whose mapped center misses all four ghosts within eps is EXCLUDED from the match set + status note (consistent with ADR-021(d) green=appliable); the hard assert lives only in the Go-time live re-place path where warn-and-skip catches it. Bare asserts at dot-mode entry kill the whole mode on one degenerate candidate.

(g) **Ledger keys + guards (D7):** ledger key = POST-PUSH stack length (template push T, candidates T+1..T+k); M4's own Apply-All pushes (same object, apply_panel.py:119-122) are labeled via the subclass's apply_all override (call super, then record - behavior byte-unchanged); unlabeled entries read as FOREIGN (availability disabled). Pop-until-preGo is guarded by can_undo() (no infinite loop on availability misfire) and uses plain `model.state == held_preGo` equality (the M4-proven deepcopy bit-exact pattern, verify_gui.py:332-339).

(h) **Plain-Undo toast branching (D8):** `SimilarWorkflowUI.undo()` override branches on the popped entry's ledger label - similar-batch pops get the new M4b granular toast; everything else falls through to super() with M4 strings byte-unchanged (frozen `ApplyAllWorkflowUI.undo` hard-codes UNDO_TOAST, apply_panel.py:395-405).

(i) **Apply-All disable slot (D6):** dot mode disables Apply All via direct glue-level `apply_btn` config (app.py owns construction) + a `_notify_queue` guard in the owned subclass (set_pending_count re-enables it otherwise, apply_panel.py:283-288); the disabled button still displays the true pending count (queue persists per ADR-021(i)).

(j) **One mode-exit routine (D12):** exit = (1) `del viewer.redraw` instance attribute (NOT rebind - a rebound captured method shadows the class method forever), (2) unbind the panel's add=True bindings, (3) cancel pending after callbacks (the deferred toggle-commit), (4) delete the dot/badge canvas tag (base _clear_overlays does not know it), (5) exit BEFORE undo/revert so set_model's redraw cannot resurrect dots on the restored model.

(k) **Import + determinism pins (D10 + advice 6):** rules/similar.py imports rules.engine (ghost_candidates/place_corner/resolve_edge/compute_apex) + geometry; never model/ui/tkinter/ezdxf (ADR-019(b)'s "geometry only" line is void as written). Enumeration iterates primitives in document order, insertion-ordered dedup, sorted tie-breaks - no set-iteration order anywhere (PYTHONHASHSEED discipline).

(l) **Accepted-stale badges (D9) + passthrough toast wording (D11), both pinned-as-documented:** mid-Go flag decisions can stale a later candidate's ENTRY-precomputed badge (display-only; Go's live re-place is authoritative - hover is entry-time information); the queue+green passthrough's self-referential overlap toast ("db-X+Y overlaps db-X+Y") is verbatim-correct per M4 and accepted as documented cosmetic (no uniqueness invariant touched; arc eids mint via next_seq).

**Why:** Loop-2 verified the design; loop-3 verified the DESIGN AGAINST THE CODE. The two blockers are construction-order and post-confirm-path landmines an implementer following the brief's letter would hit in the first hour (double-bound instances fire both handler sets; the armed Confirm posts "Corner queued" and restarts); the mapping-math gap (renormalization) would fail the plan's own boundary fixture late and expensively; the ledger keys/guards each have concrete failure modes (infinite pop loop; foreign-entry ambiguity).

**Alternatives:** Constructing SimilarWorkflowUI at arm time (rejected - D1 double-bind + stack erasure); intercepting armed Confirm at the apply() port only (rejected - D3 leaves M4's toast/restart running); excluding composite runs from the predicate entirely (equivalent to (d) but silently shrinks candidate sets - the one-member rule is crash-proof and observable); affine-only mapping without renormalization (rejected - fails the pinned 1.9-deg fixture by 55x); hard assert at entry (rejected - one degenerate candidate kills the mode); a comparator other than plain equality for pop-until-preGo (rejected - M4 proves deepcopy bit-exactness).

**Consequence:** briefs/M4b.md amended to v4 with the loop-3 pins (construction, capture seam, composite rule, mapping formula, entry-assert exclusion, ledger keys, toast branching, Apply-All disable, exit routine, imports, determinism); DoD adds: re-promoted-composite fixture, 1.9-deg-in-first canary ordering, mis-mapped-seed exclusion (not crash), guarded pop-until-preGo, foreign-ledger-entry disable, mode-exit routine test (bindings/afters/tag/wrapper restored). The M4b session pins the CONTRACTS similarity section per ADR-019(b) as amended by ADR-020/021/023 (note: ADR-022 is M4c; this ADR takes number 023). ISSUES.md M4b row updated. Estimate unchanged 8-12h.

## ADR-024 - 2026-10-07 - M5 split into M5a (headless fold engine + export stage) and M5b (fold selection UI)

**Decision:** Milestone M5 is re-baselined as **two sittings with separate gates** (M4c1/M4c2 and M7a/M7b precedent; user request 2026-10-07 for one-shot-ability). The original M5 brief mixed a headless, contract-pinned surface (
esolve_folds/

(a) **M5a - headless fold engine + export fold stage** (~1-1.5h): 
ules/folds.py (new pure surface, headless: imports geometry only, never tkinter/ezdxf - ADR-023(k) discipline), dxf_io/export.py fold stage (layer move to FOLD_LINES + fold_color, CONTRACTS SS3 pipeline order: fold stage -> layer move -> audit pre-check -> save), pytest goldens. Files owned: 
ules/folds.py, dxf_io/export.py, 	ests/test_rules_folds_*.py, 	ests/test_dxf_io_export_fold_*.py.

(b) **M5b - fold selection UI** (~1h): ui/fold_panel.py (new owner file), the fold section of 	ools/verify_gui.py (synthetic box-select + clicks), app-glue mode toggle, badge + fold-color rendering, auto-preselect fire-once-per-load (layers case-insensitive containing bend|fold|centerline - ISSUE-003 defaults; user changes after that are authoritative). Files owned: ui/fold_panel.py, fold section of 	ools/verify_gui.py, fold tests, pp.py glue, ui/theme.py/ui/messages.py new keys/strings ONLY (fold color = theme key pinned to ACI 7 semantics; grep-clean). ui/workflow.py, ui/apply_panel.py, model/, 
ules/engine.py, 
ules/folds.py, dxf_io/export.py, geometry/ stay untouched (gap >2 loops -> STOP, log).

(c) **Phase order pinned:** M5a FIRST (engine before UI - M2-before-M3 precedent; the UI consumes the engine's validation warnings and the fold_eids the model already carries). M5b starts only when M5a's gates are green. M5a's verify-gui section is engine-only (no synthetic fold events exist yet); M5b adds the --folds drive.

(d) **Gates per phase:** M5a - pytest fold goldens (WORKED-EXAMPLE Step 6: R=1.5875 extend endpoint (44.7941, 51.2634) +-0.001; golden replay R=3.175 crossings 49.71757/44.77237; idempotency double-resolve = no-op; validation-warning: fold collinear with contour -> warning string present), export-stage pytest (layer move + color, purity: working model untouched, idempotent re-export), verify_m2 + verify_gui --full byte-unchanged-green, architecture matrix green (folds.py imports geometry only). M5b - 	ools/verify_gui.py --folds drive (3 folds via synthetic box-select + clicks on syn-fold-heavy or the after-file, fold_eids assert), badge-count FSM tests headless, verify_m2/verify_gui --full green, human visual checklist (badge counts, designated folds render in fold color, drag >=5px box-select vs <5px click).

(e) **The M5 DoD's escape hatch is void as written across the split:** the original 'if cut-list invoked, resolve_folds becomes a documented no-op returning []' clause dies with the split (the engine stage is now M5a's core deliverable, ~the cheaper half; cutting it empties the milestone). Deletion preview remains never-cut (AGENTS #5) and stays out of scope here entirely.

**Why:** One-shot risk: the original brief binds a contract-pinned numeric gate (WORKED-EXAMPLE Step 6) to a fresh canvas-interaction surface in one sitting; a UI defect late in the sitting would stall the numeric gate with it. The repo's own phased precedent (M4c1 headless detector before M4c2 tour UI, per ADR-022(i)) exists precisely because 'engine before UI' isolates numeric-golden risk from interaction risk. The user explicitly asked to split (one-shot-ability).

**Alternatives:** Single sitting (original brief - rejected: two failure domains, one late-defect blast radius); UI first (rejected: the UI would consume validation warnings and fold_eids semantics not yet pinned, and every UI test would be rewritten after the engine lands); three-way split with export as its own sitting (rejected: export fold stage is ~30 lines inside M5a's own pipeline - CONTRACTS SS3 already orders it; M6 keeps audit+save finalization).

**Consequence:** briefs/M5.md REWRITTEN as the phased brief (supersedes the 22-line original together with this ADR); ISSUES.md M5 row SPLIT into M5a + M5b rows (this planning session writes both; the implementing sessions update their own row only - single-writer); estimates 1-1.5h + 1h (total unchanged). M5a pins the CONTRACTS SS3-fold-section signatures at sprint start (resolve_folds / validate_fold_against_contours already named in CONTRACTS SS2/SPEC SS11.6 - pinning = writing the normative block, no contract CHANGE, no new ADR needed beyond this one). M5b consumes: model.state.fold_eids (exists, M2 scaffold), place_corner's protected set (folds exempt from truth table), load's _fold_contour_warnings stub (M5b makes it live by designating folds at load... AMENDED in-session: auto-preselect fires at load but fold ONTOUR warnings fire at designation time (the brief pins the seam), the load-time stub stays empty-by-construction per its existing docstring). M6 unchanged (audit gate + dialog wiring consume M5a's export stage). Cut list priority within M5b per ADR-007 unchanged (box-select polish first). Session log 2026-10-07-M5-plan (this split). M5 acceptance in the milestone table maps: 'fold endpoints on arc within 0.001' -> M5a; 'idempotency fixture' -> M5a; 'selection + badge + auto-preselect' -> M5b.



## ADR-025 - 2026-10-07 - Manual trim-to-closest-line tool (user-approved spec lock; milestone M-TRIM)

**Decision:** A new manual-editing tool lets the user click any LINE and snap its nearest-clicked endpoint to that end's closest intersection with any other entity's SUPPORTING geometry (LINE/ARC/CIRCLE/POINT; supporting line/curve counts, not segment-reach); falls-short EXTENDS, overshoot TRIMS. The whole promoted run (chain_run) is the subject. A run with ZERO external attachments (build_adjacency minus its own members, within EPS_COINCIDE) is a STRAY: the tool proposes deleting the whole run instead of trimming (user rule: "if the line is connected to nothing the whole thing should be deleted"). Manual trims NEVER touch attachment neighbors (explicit manual fix; no cascade) and no post-trim re-check. Folds are fully allowed as subjects and targets (folds are trims, not rebuilds; M5a's resolve_folds is idempotent on on-arc endpoints by construction). Deleted run eids are scrubbed from fold_eids at apply; trim eids keep their designation.

**API (CONTRACTS section 1/2 amendments, this ADR is their authority):**

(a) `geometry/entities.py` + `EditResult(ok, reason: str|None, deletions: list[str], trims: list[Trim], warnings)` - the manual-edit result carrier; `trims[0].eid` is the promoted-run eid; `reason` carries the refusal string verbatim (pinned: `"NO_TARGET: no supporting-geometry intersection found"` / `"UNKNOWN_EDGE: <eid> is not resolvable in primitives"`).

(b) `rules/manual_edit.py: trim_to_closest(primitives, p_world, eid, eps_construction=EPS_CONSTRUCTION, eps_coincide=EPS_COINCIDE) -> EditResult` - pure engine (imports geometry only); eid is the promoted_edge_at Seg (run members via .members, extent a/b). Candidate targets exclude the run's OWN member eids. Closest = min world distance from the moving endpoint (pre-move position) over all supporting-geometry intersections. Endpoint moves to the candidate point exactly (EPS_CONSTRUCTION). Moving end = run-extent endpoint nearest the click (click-near-end authority, user answer 1).

(c) `model/model.py: apply_edit(res: EditResult) -> None` - mutates per result: deletions removed from primitives AND fold_eids AND flag_decisions keys; trims applied Seg-only via replace(a=..., b=...); asserts every referenced eid present. Undo = existing SnapshotStack.push before the first mutation of the manual batch (one push per Confirm, ADR-001 unchanged).

(d) UI: `ui/trim_panel.py` (TrimFSM canvas-free + TrimPanel tkinter shell), the M5b mode-isolation binding pattern (REPLACEMENT, never unbind; saved-script restore), bottom-bar toggle button + `T` key, red overlay preview + Confirm pill, toast+stay on NO_TARGET. Strings in `ui/messages.py` (grep-clean rule unchanged).

**Why:** Weird-geometry manual fixes need an escape hatch the corner pipeline refuses (tangent stray, near-collinear fragments); the corner flow's preview/confirm UX is proven and reused. Extend+trim both needed because SolidWorks tears leave both overshoots and gaps; supporting-line authority matches the project's apex-gate philosophy (tear-truncated edges).

**Alternatives:** Extending CornerResult (rejected: forces a fake Dogbone through apply_corner); separate EditHistory (rejected: snapshots already travel - duplication); UI-side math (rejected: ADR-006).

**Consequence:** CONTRACTS.md gains the EditResult block + trim_to_closest + apply_edit normative signatures; ISSUES.md gains the M-TRIM row (this session writes it; single-writer); tests test_rules_manual_edit_*.py / test_model_apply_edit.py / test_ui_trim_fsm.py; verify_gui.py gains --trim (synthetic drive: trim, extend, stray-delete, NO_TARGET stay, undo, fold-designation scrub, binding isolation). M6 must map manual-edit residuals separately (manual trims are engine-invisible by design; ISSUE-012(e) residual class extended). ISSUE-020 registered (arc-subject deferred to V1.1).

## ADR-027 — 2026-10-08 — Redo stack beside Undo (amends ADR-001)

ADR-026 is left unused on purpose: the M-TRIM session reserved it for the M6 session that was in flight while this entry was written.

**Decision:** Undo keeps the state it leaves on a redo stack of the same deep-copy snapshots (ADR-001). Redo swaps that state back and pushes the current state onto the undo stack. A new `SnapshotStack.push` (Apply All or trim confirm), `revert`, a fold designation, or a sticky flag decision clears the redo stack. The Redo button sits beside Undo and is disabled when the redo stack is empty (disabled, never a crash — the same rule as Undo at stack bottom).

**Why:** The snapshot model already copies the whole document before each edit. Redo is retaining the copy undo used to discard. Users who undo one step past a good apply can return to it without redoing the click sequence.

**Alternatives:** Leave redo out of V1 (ADR-001's original scope cut — rejected once the user asked for the button); command-pattern inverse ops (rejected: ADR-001's reason for snapshots still holds).

**Consequence:** `SnapshotStack` gains `can_redo` / `redo` / `discard_redo`. CONTRACTS §5 ownership row names redo. Fold designation and flag decisions are not their own undo steps; they only clear redo so a later redo cannot overwrite that edit. Export stays pure and does not read the stack (ADR-004 unchanged). ISSUES.md was not edited — the M6 session owns that file's milestone row while this work ran beside it.

## ADR-028 — 2026-10-08 — Trim removes the collinear span between intersections (amends ADR-025)

**Decision:** `trim_to_closest` still deletes a run with zero external attachments, and still moves one endpoint along a perpendicular foot when the click has an intersection on only one side. When the click lies between an intersection on each side, that path is not used. An intersection is an external attachment at an endpoint of the collinear piece, or a finite crossing through the piece interior. Collinear neighbors with only an endpoint gap stay in the piece. The piece stops at the first intersection on each side.

If every member of that span lies wholly inside it, the result is a deletion of those entity-level eids and the pinned warning `SPAN_DELETE`. If one segment continues past both intersections, that whole segment is deleted and collinear geometry past either intersection is kept. If a member continues past exactly one intersection, the result is one on-axis `Trim` of the surviving stub. The UI shows a span sentence for `SPAN_DELETE` and keeps the stray sentence for a stray deletion.

**Why:** A line whose ends both meet other geometry was swung off its axis onto the perpendicular foot of an off-axis line. The line between those joints should come out, and the walk should not continue through a joint into the next collinear segment.

**Alternatives:** Keep the foot and accept the rotation (rejected: the reported bug). Cut a window out of a segment that continues past both intersections (rejected: `EditResult` has deletions and one `Trim`, and `apply_edit` cannot split one entity). Shorten one end and drop the other overhang (rejected: the user asked to delete the whole segment and stop at both intersections).

**Consequence:** CONTRACTS §2 `trim_to_closest` comment gains the span rule. ADR-025's body is unchanged; this entry amends it. `rules/manual_edit.py` pins `SPAN_DELETE_WARNING`. `ui/messages.py` gains the span preview sentence. ISSUES.md was not edited.

## ADR-029 — 2026-10-08 — Undo of queued corners, then of Apply All (amends ADR-001 / ADR-016(j))

**Decision:** The pending queue stays out of `ModelState`. Its undo history lives in the corner workflow.

- Each confirm records the snapshot-stack depth. Undo removes that one corner, newest first, while the depth still matches, and does not pop a snapshot.
- A later trim or other snapshot is undone first. The queued corner waits until the stack length matches the recorded depth.
- Apply All remembers the queue it consumed, tied to the snapshot it pushed. Undo of that snapshot restores the pre-apply drawing and puts those corners back, including corners the batch skipped. Further Undos remove them newest-first. If every corner is skipped, no snapshot is pushed, the queue is dropped, and Undo does not bring it back.
- Redo of that Apply All snapshot puts the dogbones back and removes the restored corners from the front of the queue. A corner confirmed after that undo stays queued. Redo does not restore a corner removed by the confirm-undo above.
- Confirm does not clear the redo stack. ADR-027's clear list is unchanged: a new push, revert, a fold designation, or a sticky flag decision.
- Revert-to-Original still keeps the pending queue and forgets the confirm depths and the Apply All batch memory. Opening another file or clearing the session clears the queue and that memory.

**Why:** A corner confirmed and then undone stayed queued, so a later Apply All still cut it. One Undo of Apply All also removed every dogbone and left the list empty, so one corner of the batch could not be taken back on its own.

**Alternatives:** Store the queue in `ModelState` (rejected: ADR-016(j); Revert's keep-queue rule would ride along inside the snapshot). Clear the whole queue on every Undo (rejected: a corner queued after an apply would vanish when that apply was undone). Split one Apply All into one snapshot per dogbone (rejected: the batch stays one drawing step; the corners come off the list after that step is undone).

**Consequence:** SPEC §11.7 and CONTRACTS §5 name this. `ApplyQueue` and the contents of a `SnapshotStack` snapshot are unchanged. Tests live in `tests/test_ui_unapplied_undo.py`. The `verify_gui.py` apply-undo drive restores the batch, then undoes each corner, before it reaches the load snapshot. ISSUES.md was not edited.

## ADR-030 — 2026-10-09 — Long lines are trimmed to the dogbone, not deleted

**Decision:** An undesignated straight line with an end inside the dogbone circle is still deleted when its length is at most 3 mm (`DELETE_MAX_MM` in `rules/engine.py`), or when both ends are inside the circle. If the line is longer than 3 mm and only one end is inside, that end moves to the circle crossing nearest the outside end. The other end stays. The attachment cascade does not then delete that line: the end it would have called dangling is the end the trim just moved. A longer line whose end already lies on the circle, and whose body stays outside, is left unchanged. Designated folds stay exempt; export still trims those.

**Why:** A bend that was not marked as a fold was deleted in full when one end sat in the relief. On the rectangular samples the tear scraps are at most 2.121 mm and the next real lines are 10 mm, so 3 mm removes the tears and keeps a forgotten bend. Both ends inside means the whole segment lies in the cut, so length does not save it.

**Alternatives:** Cap at the 4×-diameter window, 12.7 mm for the default tool (rejected: that still deletes the 10 mm lines on these files). Cap at under 2 mm (rejected: the tear floors are exactly 2 mm). Ask with a flag instead of trimming (rejected: a forgotten bend would block Apply All again).

**Consequence:** SPEC §11.5 rows for a line end in or on the circle, and the `place_corner` note in CONTRACTS §2, follow this. `Model.apply_corner` already applies a segment `Trim`. ISSUES.md was not edited.

## ADR-031 — 2026-10-09 — Designated folds trim when the dogbone is applied

**Decision:** A designated fold is still never deleted. When `place_corner` builds a dogbone, it trims that fold with `resolve_folds`, the same rule export uses, against the new relief and any dogbones already placed. The trim is part of the corner result, so the preview and Apply All move the endpoint onto the relief arc. Export runs the same function again and leaves an end that is already on the arc. An endpoint farther than the extend cap stays put, with the existing out-of-reach warning.

**Why:** ADR-030 trims a long undesignated line, and the protected-fold rule skipped designated bends, so a marked bend still ran into the relief until export.

**Alternatives:** Trim a designated fold with the 3 mm line rule (rejected: folds already have an arc-span rule, including extend). Trim only at export (rejected: the working drawing kept the bend across the cut).

**Consequence:** SPEC §4.5 and the CONTRACTS §2 `place_corner` note say the trim happens at apply and again at export. ISSUES.md was not edited.
