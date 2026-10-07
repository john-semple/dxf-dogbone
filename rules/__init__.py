"""rules/ — engine: corner pipeline, truth table, promotion, hit-test (no ezdxf/tkinter).

M1 ships ``filters.py`` only (hit-test + EPS_PICK derivation + edge promotion,
per the M1 brief and CONTRACTS §5); ``engine.py`` (compute_apex, place_corner,
…) is M2 scope and may re-export promoted_edge_at (ADR-014(b)).
"""
