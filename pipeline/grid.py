"""Assign H3 cells and aggregate detections per cell, day, sensor and satellite.

Usage: uv run python -m pipeline.grid
Output: data/interim/daily_cell.parquet  columns: h3, date, sensor, satellite, n, frp_sum
"""

import h3
import pandas as pd

from pipeline import config

INPUT = config.INTERIM_DIR / "detections.parquet"
OUTPUT = config.INTERIM_DIR / "daily_cell.parquet"


def assign_cells(df: pd.DataFrame, resolution: int) -> pd.Series:
    return pd.Series(
        [h3.latlng_to_cell(lat, lon, resolution) for lat, lon in zip(df["lat"], df["lon"])],
        index=df.index,
        name="h3",
    )


def aggregate(df: pd.DataFrame, resolution: int = config.H3_RESOLUTION) -> pd.DataFrame:
    """Count detections and sum FRP per (h3, date, sensor, satellite)."""
    cells = assign_cells(df, resolution)
    out = (
        df.assign(h3=cells, date=df["date_local"])
        .groupby(["h3", "date", "sensor", "satellite"], as_index=False)
        .agg(n=("frp", "size"), frp_sum=("frp", "sum"))
    )
    out["n"] = out["n"].astype("int32")
    return out.sort_values(["h3", "date", "sensor", "satellite"], ignore_index=True)


def main() -> int:
    detections = pd.read_parquet(INPUT)
    daily = aggregate(detections)
    daily.to_parquet(OUTPUT, index=False)
    assert daily["n"].sum() == len(detections), "aggregated n does not match clean rows"
    print(f"Wrote {OUTPUT.relative_to(config.ROOT)}: {len(daily):,} cell-day-satellite rows, "
          f"{daily['h3'].nunique():,} cells at res {config.H3_RESOLUTION}, "
          f"n total {daily['n'].sum():,} (= clean rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
