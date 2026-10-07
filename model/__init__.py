"""model/ — working document state, snapshots, flag persistence (stdlib + geometry only).

CONTRACTS §1 "Model state" is binding. M1 scaffolds the ModelState dataclass
ONLY (ADR-014(d)); the Model class (snapshot/restore/get/apply_corner) is
M2/M4 scope.
"""
