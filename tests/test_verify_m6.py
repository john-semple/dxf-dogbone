"""verify_m6.py is the machine-checkable M6 gate."""
from pathlib import Path

from tools.verify_m6 import verify


def test_verify_m6_sample_replay_passes(tmp_path):
    out = tmp_path / "replay_dogbone.dxf"
    assert verify(out) == 0
    assert out.is_file()
    assert Path(str(out) + ".export_log.md").is_file()


def test_verify_m6_usage():
    from tools.verify_m6 import main

    assert main(["verify_m6.py"]) == 2
