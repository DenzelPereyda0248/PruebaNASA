"""Filter FIRMS detections and normalize them to a common schema.

Usage: uv run python -m pipeline.clean
Output:
  data/interim/detections.parquet  columns: sensor, satellite, lat, lon, date_local, frp, daynight
  data/interim/gaps.json           local days with no data at all, per sensor
  data/interim/clean_counts.json   rows remaining after each filter step
"""

import json
from datetime import timedelta

import pandas as pd

from pipeline import config

OUTPUT = config.INTERIM_DIR / "detections.parquet"
GAPS = config.INTERIM_DIR / "gaps.json"
COUNTS = config.INTERIM_DIR / "clean_counts.json"
COLUMNS = ["sensor", "satellite", "lat", "lon", "date_local", "frp", "daynight"]


def read_raw(sensor: str) -> pd.DataFrame:
    path = config.RAW_DIR / config.SOURCES[sensor]["file"]
    return pd.read_csv(
        path,
        usecols=config.REQUIRED_COLUMNS,
        dtype={"acq_time": str, "confidence": str, "satellite": str, "daynight": str},
    )


def add_local_date(df: pd.DataFrame) -> pd.DataFrame:
    """acq_date + acq_time are UTC; shift by the fixed offset and keep the date."""
    t = df["acq_time"].str.zfill(4)
    utc = pd.to_datetime(df["acq_date"] + " " + t.str[:2] + ":" + t.str[2:], format="%Y-%m-%d %H:%M")
    local = utc + timedelta(hours=config.UTC_OFFSET_HOURS)
    return df.assign(date_local=local.dt.normalize())


def confidence_mask(sensor: str, conf: pd.Series) -> pd.Series:
    if sensor == "modis":
        return pd.to_numeric(conf, errors="coerce") >= config.MODIS_MIN_CONFIDENCE
    return conf.str.lower().isin(config.VIIRS_CONFIDENCE)


def gap_days(df: pd.DataFrame) -> list[str]:
    """Days of the year with zero raw detections (uses date_local)."""
    days = pd.date_range(f"{config.YEAR}-01-01", f"{config.YEAR}-12-31", freq="D")
    missing = days.difference(df["date_local"].unique())
    return [d.strftime("%Y-%m-%d") for d in missing]


def clean_sensor(sensor: str, raw: pd.DataFrame) -> tuple[pd.DataFrame, dict, list[str]]:
    """Apply the PLAN.md section 6 filters. Returns (clean rows, counts per step, gap days)."""
    steps = {"raw": len(raw)}
    df = raw.drop_duplicates()
    steps["drop_exact_duplicates"] = len(df)
    df = add_local_date(df)
    in_year = df["date_local"].dt.year == config.YEAR
    df = df[in_year]
    steps[f"local_date_in_{config.YEAR}"] = len(df)
    # Gaps are computed before the quality filters: a day is "no data" only if
    # the instrument reported nothing at all, not if everything got filtered.
    gaps = gap_days(df)
    df = df[df["type"].isin(config.KEEP_TYPES)]
    steps[f"type_in_{config.KEEP_TYPES}"] = len(df)
    df = df[confidence_mask(sensor, df["confidence"])]
    steps["confidence"] = len(df)

    out = pd.DataFrame({
        "sensor": sensor,
        "satellite": df["satellite"].map(config.SATELLITE_NAMES).fillna(df["satellite"]),
        "lat": df["latitude"].astype("float64"),
        "lon": df["longitude"].astype("float64"),
        "date_local": df["date_local"].dt.date,
        "frp": df["frp"].astype("float64"),
        "daynight": df["daynight"],
    })
    return out.reset_index(drop=True), steps, gaps


def main() -> int:
    config.INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    frames, counts, gaps = [], {}, {}
    for sensor in config.SOURCES:
        df, steps, sensor_gaps = clean_sensor(sensor, read_raw(sensor))
        frames.append(df)
        counts[sensor] = steps
        gaps[sensor] = sensor_gaps
        print(f"[{sensor}] " + " -> ".join(f"{k}: {v:,}" for k, v in steps.items()))
        print(f"[{sensor}] {len(sensor_gaps)} no-data day(s)")

    detections = pd.concat(frames, ignore_index=True)[COLUMNS]
    detections.to_parquet(OUTPUT, index=False)
    GAPS.write_text(json.dumps(gaps, indent=2))
    COUNTS.write_text(json.dumps(counts, indent=2))
    print(f"Wrote {OUTPUT.relative_to(config.ROOT)} ({len(detections):,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
