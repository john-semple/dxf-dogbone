# Decision Log (ADR format)

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
