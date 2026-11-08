"""Tests for filters, local-date conversion, gap detection and H3 aggregation.

Small hand-made frames are used as test fixtures only; they are never written
to data/ or used as real observations.
"""

import h3
import pandas as pd
import pytest

from pipeline import clean, config, grid


def raw_rows(rows: list[dict]) -> pd.DataFrame:
    base = {"latitude": 19.4, "longitude": -99.1, "acq_date": "2024-04-15", "acq_time": "1930",
            "satellite": "Aqua", "confidence": "50", "frp": 10.0, "daynight": "D", "type": 0}
    return pd.DataFrame([{**base, **r} for r in rows])


# --- filters -------------------------------------------------------------------

def test_modis_filters_type_and_confidence():
    raw = raw_rows([
        {},                                   # kept
        {"type": 2},                          # static source -> dropped
        {"type": 1},                          # volcano -> dropped
        {"confidence": "29"},                 # low -> dropped
        {"confidence": "30"},                 # boundary -> kept
    ])
    out, steps, _ = clean.clean_sensor("modis", raw)
    assert len(out) == 2
    assert steps["raw"] == 5 and steps["confidence"] == 2


def test_viirs_confidence_letters():
    raw = raw_rows([
        {"satellite": "N", "confidence": "l", "acq_time": "1930"},
        {"satellite": "N", "confidence": "n", "acq_time": "1931"},
        {"satellite": "N", "confidence": "h", "acq_time": "1932"},
    ])
    out, _, _ = clean.clean_sensor("viirs", raw)
    assert len(out) == 2
    assert set(out["satellite"]) == {"S-NPP"}


def test_exact_duplicates_dropped():
    raw = raw_rows([{}, {}])
    out, steps, _ = clean.clean_sensor("modis", raw)
    assert steps["drop_exact_duplicates"] == 1 and len(out) == 1


def test_output_schema():
    out, _, _ = clean.clean_sensor("modis", raw_rows([{}]))
    assert list(out.columns) == clean.COLUMNS


# --- local date ----------------------------------------------------------------

@pytest.mark.parametrize(("acq_date", "acq_time", "expected"), [
    ("2024-06-01", "1900", "2024-06-01"),   # 13:00 local, same day
    ("2024-06-02", "0450", "2024-06-01"),   # 22:50 local, previous day
    ("2024-06-02", "0600", "2024-06-02"),   # exactly midnight local
    ("2024-06-02", "559", "2024-06-01"),    # acq_time without leading zero
])
def test_local_date_conversion(acq_date, acq_time, expected):
    df = clean.add_local_date(raw_rows([{"acq_date": acq_date, "acq_time": acq_time}]))
    assert df["date_local"].iloc[0] == pd.Timestamp(expected)


def test_rows_outside_year_after_shift_are_dropped():
    raw = raw_rows([{"acq_date": "2024-01-01", "acq_time": "0450"}])  # -> 2023-12-31 local
    out, steps, _ = clean.clean_sensor("modis", raw)
    assert len(out) == 0 and steps[f"local_date_in_{config.YEAR}"] == 0


# --- gaps ----------------------------------------------------------------------

def test_gap_days_ignore_quality_filters():
    days = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    rows = [{"acq_date": d.strftime("%Y-%m-%d"), "acq_time": "1930"} for d in days
            if d != pd.Timestamp("2024-03-10")]
    rows.append({"acq_date": "2024-03-11", "acq_time": "1931", "type": 2})
    _, _, gaps = clean.clean_sensor("modis", raw_rows(rows))
    assert gaps == ["2024-03-10"]


def test_day_with_only_filtered_rows_is_not_a_gap():
    days = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    rows = [{"acq_date": d.strftime("%Y-%m-%d"), "acq_time": "1930",
             "type": 2 if d == pd.Timestamp("2024-03-10") else 0} for d in days]
    out, _, gaps = clean.clean_sensor("modis", raw_rows(rows))
    assert gaps == [] and len(out) == len(days) - 1


# --- grid ----------------------------------------------------------------------

def test_aggregate_counts_match_rows():
    raw = raw_rows([
        {"acq_time": "1930"}, {"acq_time": "1931"},                       # same cell, same day
        {"acq_time": "1932", "latitude": 25.0, "longitude": -105.0},      # other cell
        {"acq_time": "1930", "acq_date": "2024-04-16"},                   # other day
    ])
    out, _, _ = clean.clean_sensor("modis", raw)
    daily = grid.aggregate(out, resolution=5)
    assert daily["n"].sum() == len(out) == 4
    assert len(daily) == 3
    cell = h3.latlng_to_cell(19.4, -99.1, 5)
    row = daily[(daily["h3"] == cell) & (daily["date"] == pd.Timestamp("2024-04-15").date())]
    assert row["n"].item() == 2 and row["frp_sum"].item() == pytest.approx(20.0)


def test_real_interim_files_are_consistent():
    det_path = config.INTERIM_DIR / "detections.parquet"
    daily_path = config.INTERIM_DIR / "daily_cell.parquet"
    if not (det_path.exists() and daily_path.exists()):
        pytest.skip("run the pipeline first")
    det = pd.read_parquet(det_path)
    daily = pd.read_parquet(daily_path)
    assert daily["n"].sum() == len(det)
    for (sensor, sat), g in det.groupby(["sensor", "satellite"]):
        sub = daily[(daily["sensor"] == sensor) & (daily["satellite"] == sat)]
        assert sub["n"].sum() == len(g)
    assert h3.get_resolution(daily["h3"].iloc[0]) == config.H3_RESOLUTION
