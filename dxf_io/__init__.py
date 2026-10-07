"""dxf_io/ — load/export (ezdxf allowed; headless). CONTRACTS §3 is binding.

M1 implements the load half fully (SPEC §11.3 cases 1–4; case 5 folds stubbed as
pass-through warnings — no folds are designated at load, M5 owns designation).
The export half (`export`) is M5/M6 scope and is deliberately absent here.
"""
from dxf_io.load import LoadRefused, LoadResult, load

__all__ = ["load", "LoadResult", "LoadRefused"]
