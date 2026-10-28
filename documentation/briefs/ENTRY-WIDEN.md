# Brief — Dogbone Entry Widen (Parallel Throat)

> **Status: Implemented (2026-10-27)**  
> Spec lock: 2026-10-27 (user Q&A). Authority: ADR-032.  
> Session log: `documentation/sessions/2026-10-27-M-ENTRY.md`.

**Cite:** this brief; ADR-032; CONTRACTS §1 `Dogbone` / `CornerResult` and §2 `place_corner` (as amended at implement time); SPEC §11.4–§11.6 (deletion / rebuild / folds) where this brief overrides for capsule geometry; AGENTS hard invariants.

**Out of scope:** general fillet/chamfer tool, arc-subject trim (ISSUE-020), one-sided T-bone, throat wider than Ø, user-facing trigger-factor UI.

---

## Problem

Classic dogbones rebuild both edges to the non-apex circle hits `p1`, `p2` and replace the corner with an arc through the apex. Mouth width is the chord `|p1−p2|`.

| Corner | `half_side` α | Mouth (ideal) | Bit fit |
|--------|---------------|---------------|---------|
| 90° | 45° | Ø = 2R | tight (exactly Ø) |
| Acute air notch | &lt; 45° | &lt; Ø | **bit cannot enter** |
| Near 15° band | ≈ 15° | ≈ R = Ø/2 | half a bit wide |

Placement “succeeds,” but the neck is too tight for the tool to drive into the relief.

## Goal

When classic mouth &lt; bit diameter, replace the pinched V-entry with a **parallel throat of width Ø** feeding an **undercut semicircle through the apex** (capsule / slot entry), so the bit drives straight in. Auto-detect, show in the existing place/confirm preview, Confirm applies. One Confirm = one undo snapshot (throat atomic with the corner).

---

## Locked decisions (Q&A 2026-10-27)

| # | Decision |
|---|----------|
| 1 | Geometry = parallel throat (capsule), not angled chamfers |
| 2 | Auto with preview (part of place/confirm) |
| 3/5/7 | Throat width always exactly **Ø = 2R**. V1 trigger factor constant **1.0** (`widen iff mouth < Ø`). No factor UI in V1 |
| 4 | Widen only when mouth &lt; Ø; 90° and wider stay classic |
| 6/12 | If **either** edge cannot host its throat wall: warn; Confirm applies **classic** dogbone only; Esc cancels. **No one-sided throat** |
| 8 | No “decline widen” toggle: when widen is proposed and hostable, Confirm = dogbone+throat; Esc cancels the whole corner |
| 9 | Same center as classic (`apex + R·bisector`). Walls // bisector at ±R. Undercut **semicircle** (180°) through the apex (classic clearance side); throat opens on the air/mouth side at `q_i`. Sharp corner vertex is gone (apex is a point on the arc, not a V tip). *Amended 2026-10-27 after GUI: air-far semicircle was a reverse dogbone.* |
| 10 | Batch / similar: **per-candidate** `mouth < Ø` check (template throat does not force throat on a wide-mouth candidate) |
| 11 | Mouth = classic `|p1−p2|` after today’s rebuild points (before any throat) |
| 13 | Folds: `resolve_folds` against the **final contour** (throat segs and/or arc — first hit) |
| 14 | Overlap: keep circle-vs-circle; **plus** refuse/warn if a throat segment hits another dogbone’s protected geometry |

### Agent defaults (also locked)

- **Trigger inequality:** `mouth < 2R − EPS_COINCIDE` so exact 90° stays classic.
- **Protected set:** semicircle arc + both throat LINEs + rebuilt edges (same monotone rules as today).
- **Preview copy:** status/toast notes entry widened when the throat is active.
- **Truth table / cascade removed-region:** the **capsule**, not only the R-disk (see High-priority notes).

### High-priority notes (implementer must not weaken)

1. **Capsule deletion.** Throat flanks cut material outside the far half-disk. If the truth table still uses only the R-disk, tear in the throat corridor can survive. Window prefilter may stay `4 × Ø` around the apex (covers `s = R/sin(α)` for in-band α); the hit predicate itself is capsule membership.
2. **Wall consumption.** Along each edge, apex→`q` distance is `s = R / sin(α)` (~3.9R at 15°). Short-edge / not-hostable → classic+warn will fire often near the band — intentional.
3. **Sharp V tip leaves the contour.** Mating clearance is the undercut semicircle through the apex plus the parallel throat (slot entry); not the classic long arc `360°−4α`.

---

## Geometry (construction 9A)

```text
          undercut semicircle
              (through apex)
    t1 ················· t2
     |                   |
     |  walls // û       |   width Ø
     |                   |
    q1                   q2
         air / mouth open
```

Given classic placement inputs (`apex`, unit bisector `û` into air, `R`, supporting lines, `half_side` α):

1. **Classic first (always):** center `c = apex + R·û`; `p1`, `p2` = unique non-apex line∩circle per edge; `mouth = |p1−p2|`.
2. **Gate:** if `mouth >= 2R − EPS_COINCIDE` → classic dogbone unchanged (today’s arc span `360° − 4α`).
3. **Widen path** when mouth is tight **and** both edges hostable:
   - Unit perp `v̂` (consistent orientation vs edge1 / edge2).
   - Tangent points: `t1 = c + R·v̂`, `t2 = c − R·v̂`.
   - Junction on each supporting line: `q_i` at distance `s = R / sin(α)` from apex along that edge’s direction away from apex (equivalently: intersection of the edge’s supporting line with the parallel through `c ± R·v̂` spanning `û`). Pick the intersection on the kept side of the edge (§11.4 uniqueness spirit).
   - **Hostable (V1 default):** `q_i` lies on the promoted run’s finite extent (no overshoot allowance beyond the run). Both edges must pass; else fall back to classic + pinned warning.
   - **Rebuild:** move each edge endpoint to its `q_i` (not to `p_i`).
   - **Insert:** `Seg` `q1→t1`, `Seg` `q2→t2` (throat walls; open mouth at the air/notch end).
   - **Arc:** center `c`, radius `R`, 180° from `t1` to `t2` on the **apex/undercut** side (contains apex; air-far point not on arc). Endpoints equal `t1` / `t2`. *(GUI 2026-10-27: air-far semicircle was reverse dogbone — do not use.)*
4. **Invariants (tests):** `|t1−t2| = 2R`; walls // `û`; arc endpoints = throat near ends (`t_i`); apex mid-arc; air-far point off-arc; trigger was `mouth_classic < 2R − EPS_COINCIDE`.

---

## Pipeline

```text
place_corner (classic through p1,p2)
    │
    ├─ mouth ≥ Ø − eps ──► classic CornerResult
    │
    └─ mouth < Ø − eps
           │
           ├─ not both hostable ──► classic geometry + warning
           │
           └─ both hostable ──► rebuild to q1,q2 + throat segs + semicircle
                    │
                    ▼
              UI preview → Confirm → apply_corner (one snapshot)
```

- Runs inside `place_corner` (or an immediate post-stage before return) so preview, Apply All, and batch see final geometry.
- Deletion truth table + attachment cascade: entity hits **capsule** = stadium of radius R (disk ∪ throat rectangle between the walls from the apex-side opening through `c` to the far point — pin exact predicate in the implementing session log).
- Overlap: existing circle check + throat-seg vs other protected geometry (decision 14).
- Folds at place and export: `resolve_folds` targets the final contour (decision 13).
- `Dogbone` gains throat member eids (or ordered contour pieces); `CornerResult.rebuilds` target `q_i`; new entities minted `n&lt;seq&gt;` at apply like today’s arc.

---

## UX

- Ghost / confirm preview draws throat + semicircle when active.
- Status when widened (pin exact string at implement): e.g. `Entry widened to bit diameter (mouth was too tight)`.
- Not hostable: pinned warning; preview shows classic; Confirm applies classic.
- No widen toggle.
- Batch: each candidate independently mouth-gated.

---

## Contracts / files (implementing session)

**Owns:** ADR-032 follow-through in `documentation/CONTRACTS.md` (`Dogbone`, `CornerResult`, `place_corner`); `geometry/entities.py`; `rules/engine.py` (and fold resolve as needed); `model/` apply path for new inserts; UI preview/status strings in `ui/messages.py`; tests `test_rules_entry_widen_*.py` (and related); `tools/verify_*` extension if needed; session log `documentation/sessions/YYYY-MM-DD-M-ENTRY.md`; M-ENTRY row in `documentation/ISSUES.md` (single-writer).

**DoD (implement):**

- Mouth trigger boundary: 45° → no widen; α &lt; 45° with hostable edges → capsule.
- Capsule goldens on an acute fixture (e.g. syn-tight-notch class).
- Hostable failure → classic + warning.
- Batch mixed mouth (per-candidate).
- Fold first-hit on a throat wall.
- Overlap throat-vs-protected.
- Undo atomic with the corner.
- `pytest -q` green; `verify_m2` / GUI harness not regressed.

---

## Warning / status strings (pin at implement)

Implementing session pins exact ASCII strings in `rules/engine.py` / `ui/messages.py` and asserts them in tests. Suggested classes (not yet verbatim-pinned):

- Entry widened (status): mouth was below Ø; throat active in preview/result.
- Not hostable (warning): e.g. `ENTRY_WIDEN_HOST: edge too short for parallel throat; using classic dogbone`.
- Throat overlap (refusal or warning per ADR pin at implement): throat segment intersects protected geometry of dogbone `{db_id}`.
