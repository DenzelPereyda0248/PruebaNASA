"""Tests for monthly_ratio_v1 (hand-made fixtures only)."""

import math

import pandas as pd
import pytest

from pipeline import config, harmonize


def daily(rows: list[tuple]) -> pd.DataFrame:
    """rows: (h3, date, sensor, satellite, n)."""
    df = pd.DataFrame(rows, columns=["h3", "date", "sensor", "satellite", "n"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["frp_sum"] = 1.0
    return df


def test_factor_uses_only_common_cell_days(monkeypatch):
    monkeypatch.setattr(config, "MIN_COMMON_CELL_DAYS", 1)
    d = daily([
        ("a", "2024-04-01", "modis", "Aqua", 2), ("a", "2024-04-01", "viirs", "S-NPP", 8),   # common
        ("b", "2024-04-01", "viirs", "S-NPP", 100),                                          # VIIRS only
        ("c", "2024-04-01", "modis", "Aqua", 50),                                            # MODIS only
        ("a", "2024-04-01", "modis", "Terra", 99),                                           # Terra ignored
    ])
    table, annual = harmonize.compute_factors(harmonize.to_wide(d))
    april = table.set_index("month").loc["2024-04"]
    assert april["factor"] == pytest.approx(2 / 8)
    assert april["common_cell_days"] == 1
    assert annual == pytest.approx(2 / 8)


def test_fallback_to_annual_when_few_common_cell_days(monkeypatch):
    monkeypatch.setattr(config, "MIN_COMMON_CELL_DAYS", 2)
    d = daily([
        ("a", "2024-04-01", "modis", "Aqua", 1), ("a", "2024-04-01", "viirs", "S-NPP", 4),
        ("a", "2024-04-02", "modis", "Aqua", 1), ("a", "2024-04-02", "viirs", "S-NPP", 4),
        ("a", "2024-05-01", "modis", "Aqua", 3), ("a", "2024-05-01", "viirs", "S-NPP", 4),
    ])
    table, annual = harmonize.compute_factors(harmonize.to_wide(d))
    t = table.set_index("month")
    assert annual == pytest.approx(5 / 12)
    assert not t.loc["2024-04", "fallback_annual"] and t.loc["2024-04", "factor"] == pytest.approx(0.25)
    assert t.loc["2024-05", "fallback_annual"] and t.loc["2024-05", "factor"] == pytest.approx(annual)


def test_gap_days_are_missing_not_zero(monkeypatch):
    monkeypatch.setattr(config, "MIN_COMMON_CELL_DAYS", 1)
    d = daily([
        ("a", "2024-04-01", "modis", "Aqua", 1), ("a", "2024-04-01", "viirs", "S-NPP", 4),
        ("a", "2024-04-02", "modis", "Aqua", 3),                    # VIIRS outage day
    ])
    out, _, _ = harmonize.harmonize(d, viirs_gaps=["2024-04-02"])
    gap_row = out[out["date"] == pd.Timestamp("2024-04-02")].iloc[0]
    assert gap_row["modis"] == 3
    assert math.isnan(gap_row["viirs"]) and math.isnan(gap_row["viirs_h"])
    ok_row = out[out["date"] == pd.Timestamp("2024-04-01")].iloc[0]
    assert ok_row["viirs_h"] == pytest.approx(4 * 0.25)
