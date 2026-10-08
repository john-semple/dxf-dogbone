"""Model — CONTRACTS §1 (snapshot/restore/get/apply_corner/apply_edit), M2 minimal.

ADR-001 deep-copy snapshots; ADR-012 reconciliation; ADR-015(c) arc n<seq>
minting + (k) model-legal run re-derivation via geometry.runs (model may
import geometry, never rules — SPEC §11.1). The undo STACK and
Revert-to-Original are M4 scope; this class provides the operations M2's
ADR-012 tests need. apply_edit is the ADR-025 manual-edit mutation
(trim-to-closest / stray-delete).
"""
from __future__ import annotations

import copy
import math

from dataclasses import replace

from geometry import geomops as go
from geometry.entities import Arc, CornerResult, EditResult, Entity, Seg
from geometry.runs import chain_run
from geometry.tolerances import EPS_COINCIDE
from model.state import ModelState


class Model:
    def __init__(self, state: ModelState | None = None):
        self._state = state if state is not None else ModelState()

    @property
    def state(self) -> ModelState:
        return self._state

    def snapshot(self) -> ModelState:
        """Deep copy (ADR-001); ID<->entity mapping preserved (ADR-010)."""
        return copy.deepcopy(self._state)

    def restore(self, s: ModelState) -> None:
        """Swap to the given snapshot (deep copy in; working state replaced)."""
        self._state = copy.deepcopy(s)

    def get(self, eid: str) -> Entity | None:
        for e in self._state.primitives:
            if e.eid == eid:
                return e
        return None

    def apply_corner(self, res: CornerResult) -> None:
        """Mutate per result (CONTRACTS §1/§2, ADR-012):
        - replace each main-edge member run with the rebuilt composite
          (registered under the promoted eid; members preserved per
          ADR-012(c); no member eid referenced twice),
        - execute deletions and trims,
        - mint the placed arc eid via next_seq (ADR-015(c)), insert the Arc,
          append the Dogbone re-recorded with the minted eid,
        - persist scripted flag decisions (ADR-009/013 sticky).
        """
        if not res.ok or res.dogbone is None:
            raise ValueError("apply_corner requires res.ok with a dogbone")
        db = res.dogbone
        st = self._state
        rebuilds = {rb.eid: rb for rb in res.rebuilt}

        composites: dict[str, tuple[Seg, frozenset[str], str]] = {}
        removed_members: set[str] = set()
        for edge_eid in (db.edge1_eid, db.edge2_eid):
            seed_eid = edge_eid
            seed = None
            while True:
                seed = next(
                    (
                        e
                        for e in st.primitives
                        if isinstance(e, Seg) and e.eid == seed_eid
                    ),
                    None,
                )
                if seed is not None:
                    break
                if seed_eid.startswith("promoted-"):
                    seed_eid = seed_eid[len("promoted-"):]
                else:
                    break
            if seed is None:
                raise ValueError(f"apply_corner: edge {edge_eid} not resolvable")
            # ADR-016(h): the single chain walk returns the run's ENTITY-level
            # eids (plain members AND registered composites present in
            # primitives) — the removal set for the composite replacement.
            chained = chain_run(st.primitives, seed, EPS_COINCIDE)
            if chained is None:
                raise ValueError(f"apply_corner: edge {edge_eid} not resolvable")
            run, ent_eids = chained
            removal = frozenset(ent_eids) | {seed.eid}
            members = run.members if run.members else (run.eid,)
            if removed_members & set(removal):
                raise ValueError("apply_corner: member eid referenced twice across edges")
            removed_members.update(removal)
            rb = next(
                (
                    rebuilds[m]
                    for m in (seed.eid, *ent_eids, *members)
                    if m in rebuilds
                ),
                None,
            )
            if rb is None:
                raise ValueError(f"apply_corner: no Rebuild for edge {edge_eid}")
            a, b = run.a, run.b
            if go.dist(rb.old, run.a) <= EPS_COINCIDE:
                a = rb.new
            elif go.dist(rb.old, run.b) <= EPS_COINCIDE:
                b = rb.new
            else:
                raise ValueError(
                    f"apply_corner: rebuild old point not on run extent for {edge_eid}"
                )
            # ADR-016(g)/(h): register under the CANONICAL run eid; the
            # caller's label must agree (forward the promoted_edge_at eid).
            expected = (
                edge_eid if edge_eid.startswith("promoted-") else f"promoted-{edge_eid}"
            )
            if expected != run.eid and edge_eid != run.eid:
                raise ValueError(
                    f"apply_corner: edge label {edge_eid} does not match the "
                    f"canonical run eid {run.eid} (forward the promoted_edge_at eid)"
                )
            composite_eid = run.eid
            composites[edge_eid] = (
                Seg(eid=composite_eid, a=a, b=b, members=tuple(members), pick_eid=""),
                removal,
                seed.eid,
            )

        deletions = list(res.deletions)
        present = {e.eid for e in st.primitives}
        missing = [d for d in deletions if d not in present]
        if missing:
            raise ValueError(f"apply_corner: deletions not in primitives: {missing}")
        if set(deletions) & removed_members:
            raise ValueError("apply_corner: deletion references a main-edge member")

        # rebuild the ordered list: each composite is inserted at its SEED
        # entity's document position (ADR-016(h)); all run entities and
        # deletions are removed.
        dels = set(deletions)
        out: list[Entity] = []
        inserted: set[str] = set()
        for e in st.primitives:
            if e.eid in removed_members or e.eid in dels:
                for edge_eid, (_comp, _removal, comp_seed) in composites.items():
                    if comp_seed == e.eid and edge_eid not in inserted:
                        out.append(composites[edge_eid][0])
                        inserted.add(edge_eid)
                continue
            out.append(e)
        for edge_eid in composites:
            if edge_eid not in inserted:
                raise ValueError(f"apply_corner: run seed missing for {edge_eid}")

        trims = {t.eid: t for t in res.trims}
        for i, e in enumerate(out):
            t = trims.get(e.eid)
            if t is None:
                continue
            if isinstance(e, Seg):
                out[i] = replace(e, a=t.new[0], b=t.new[1])
            elif isinstance(e, Arc):
                out[i] = replace(e, start_deg=t.new[0], end_deg=t.new[1])

        arc_eid = f"n{st.next_seq}"
        st.next_seq += 1
        placed = replace(db.arc, eid=arc_eid)
        out.append(placed)
        st.primitives = out
        st.dogbones.append(replace(db, arc=placed))

        for f in res.flags:
            if f.decision is not None:
                st.flag_decisions[f.eid] = f.decision

    def apply_edit(self, res: EditResult) -> None:
        """ADR-025 manual-edit mutation (CONTRACTS §1):
        - deletions (stray rule): removed from primitives AND scrubbed
          from fold_eids and flag_decisions (a designated fold that no
          longer exists must not linger; a trimmed fold KEEPS its eid
          and designation),
        - trims: Seg-only, applied via replace(a=..., b=...) on the
          entity carrying trims[0].eid (the promoted-run eid resolves to
          the run's entities; plain members AND registered composites
          both reposition — the whole run moves per ADR-025),
        - every referenced eid must be present (asserts).
        """
        if not res.ok:
            raise ValueError("apply_edit requires res.ok")
        st = self._state
        present = {e.eid for e in st.primitives}
        missing = [d for d in res.deletions if d not in present]
        if missing:
            raise ValueError(f"apply_edit: deletions not in primitives: {missing}")

        if res.deletions:
            dels = set(res.deletions)
            st.primitives = [e for e in st.primitives if e.eid not in dels]
            st.fold_eids -= dels
            for eid in dels:
                st.flag_decisions.pop(eid, None)
            return

        for t in res.trims:
            # the trim eid is the promoted-run eid (ADR-025(b)); resolve
            # to the run via chain_run (plain member pre-apply, registered
            # composite post-apply — the apply_corner walk)
            seed_eid = t.eid
            seed = None
            stripped = False
            while True:
                seed = next(
                    (e for e in st.primitives
                     if isinstance(e, Seg) and e.eid == seed_eid),
                    None,
                )
                if seed is not None:
                    break
                if not stripped and seed_eid.startswith("promoted-"):
                    seed_eid = seed_eid[len("promoted-"):]
                    stripped = True
                else:
                    break
            if seed is None:
                raise ValueError(
                    f"apply_edit: trim eid {t.eid} not resolvable in primitives")
            chained = chain_run(st.primitives, seed, EPS_COINCIDE)
            if chained is None:
                raise ValueError(
                    f"apply_edit: trim eid {t.eid} not resolvable in primitives")
            run, ent_eids = chained
            new_a, new_b = t.new

            # run axis: project everything onto a->b
            rx = run.b.x - run.a.x
            ry = run.b.y - run.a.y
            run_len = math.hypot(rx, ry)
            if run_len <= 0.0:
                raise ValueError(f"apply_edit: degenerate run for {t.eid}")

            def proj(p) -> float:
                return ((p.x - run.a.x) * rx + (p.y - run.a.y) * ry) / run_len

            p_new_a, p_new_b = proj(new_a), proj(new_b)
            moved_a = go.dist(run.a, new_a) > EPS_COINCIDE
            moved_b = go.dist(run.b, new_b) > EPS_COINCIDE
            if not (moved_a or moved_b):
                continue  # nothing to do (idempotent no-op)

            # member surgery along the axis: a member is
            #  - KEPT-AS-IS when its span lies within the kept portion,
            #  - END-MOVED when it straddles the new extent endpoint,
            #  - DELETED when its span lies entirely within the removed
            #    portion (the trim consumes it — subject redefinition, not
            #    an attachment cascade).
            lo = min(p_new_a, p_new_b)
            hi = max(p_new_a, p_new_b)
            removed: set[str] = set()
            replacements: dict[str, tuple[Pt, Pt]] = {}
            by_eid = {e.eid: e for e in st.primitives if isinstance(e, Seg)}
            for eid in ent_eids:
                e = by_eid.get(eid)
                if e is None:
                    continue
                s0, s1 = sorted((proj(e.a), proj(e.b)))
                ra, rb = e.a, e.b
                if moved_b:
                    if s0 >= p_new_b - EPS_COINCIDE and s1 > p_new_b + EPS_COINCIDE \
                            and s0 <= 1.0 + EPS_COINCIDE and s1 <= 1.0 + EPS_COINCIDE and p_new_b < s0:
                        pass  # handled below via generic rules
                # generic rules per member span vs the kept extent:
                if moved_b:
                    # fully in the removed suffix (strictly past new_b):
                    if s0 >= p_new_b - EPS_COINCIDE and s1 <= 1.0 + EPS_COINCIDE \
                            and p_new_b < s0 - EPS_COINCIDE:
                        removed.add(eid)
                        continue
                    # straddles new_b: move the endpoint nearer to run.b
                    if s0 <= p_new_b <= s1 + EPS_COINCIDE or \
                            (s0 <= p_new_b + EPS_COINCIDE and s1 >= p_new_b - EPS_COINCIDE):
                        if proj(e.b) >= proj(e.a):
                            rb = new_b
                        else:
                            ra = new_b
                        replacements[eid] = (ra, rb)
                        continue
                if moved_a:
                    # fully in the removed prefix (strictly before new_a):
                    if s1 <= p_new_a + EPS_COINCIDE and s0 >= -EPS_COINCIDE \
                            and p_new_a > s1 + EPS_COINCIDE:
                        removed.add(eid)
                        continue
                    # straddles new_a: move the endpoint nearer to run.a
                    if s0 <= p_new_a <= s1 + EPS_COINCIDE or \
                            (s0 <= p_new_a + EPS_COINCIDE and s1 >= p_new_a - EPS_COINCIDE):
                        if proj(e.b) <= proj(e.a):
                            rb = new_a
                        else:
                            ra = new_a
                        replacements[eid] = (ra, rb)
                        continue
                # extension beyond the old extent: the owner member moves
                if moved_b and s1 >= 1.0 - EPS_COINCIDE and p_new_b > 1.0:
                    if proj(e.b) >= proj(e.a):
                        rb = new_b
                    else:
                        ra = new_b
                    replacements[eid] = (ra, rb)
                elif moved_a and s0 <= 0.0 + EPS_COINCIDE and p_new_a < 0.0:
                    if proj(e.b) <= proj(e.a):
                        rb = new_a
                    else:
                        ra = new_a
                    replacements[eid] = (ra, rb)

            if not replacements and not removed:
                raise ValueError(
                    f"apply_edit: trim {t.eid} moves no run endpoint")

            # apply
            if removed:
                st.primitives = [e for e in st.primitives
                                 if e.eid not in removed]
                st.fold_eids -= removed
                for eid in removed:
                    st.flag_decisions.pop(eid, None)
            for eid, (ra, rb) in replacements.items():
                idx = next(i for i, x in enumerate(st.primitives)
                           if x.eid == eid)
                st.primitives[idx] = replace(
                    by_eid[eid], a=ra, b=rb)
