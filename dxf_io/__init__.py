"""dxf_io/ — load/export (ezdxf allowed; headless). CONTRACTS §3 is binding.

M1 implements the load half fully (SPEC §11.3 cases 1–4; case 5 folds stubbed as
pass-through warnings — no folds are designated at load, M5 owns designation).
M5a implements the export fold stage (CONTRACTS §3 pipeline: fold extend/trim
→ layer move → audit pre-check → save; ADR-004 purity via deep copy).
"""
from dxf_io.export import FOLD_COLOR_CONST, ExportResult, export
from dxf_io.load import LoadRefused, LoadResult, load

__all__ = [
    "load",
    "LoadResult",
    "LoadRefused",
    "export",
    "ExportResult",
    "FOLD_COLOR_CONST",
]
