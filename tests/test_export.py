"""Contract checks for the exported web JSON."""

import pytest

from pipeline import config, export


def test_num_handles_nan_and_rounding():
    assert export.num(float("nan")) is None
    assert export.num(3.0) == 3 and isinstance(export.num(3.0), int)
    assert export.num(2.3456, 2) == 2.35


def test_exported_files_match_contract():
    if not (config.WEB_DATA_DIR / "meta.json").exists():
        pytest.skip("run `python -m pipeline.run_all` first")
    summary = export.validate_contract()
    assert summary["cells"] > 0
