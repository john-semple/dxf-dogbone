"""Model — CONTRACTS §1 (snapshot/restore/get/apply_corner), M2 minimal.

ADR-001 deep-copy snapshots; ADR-012 reconciliation; ADR-015(c) arc n<seq>
minting + (k) model-legal run re-derivation via geometry.runs (model may
import geometry, never rules — SPEC §11.1). The undo STACK and
Revert-to-Original are M4 scope; this class provides the operations M2's
ADR-012 tests need.
"""
from __future__ import annotations

import copy

from dataclasses import replace

from geometry import geomops as go
from geometry.entities import Arc, CornerResult, Entity, Seg
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
