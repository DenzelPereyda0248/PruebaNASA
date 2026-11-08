"""Write the static JSON files read by the web app (PLAN.md section 7).

Usage: uv run python -m pipeline.export

Contract (web/public/data/):
  meta.json         run metadata, filters, factors, no-data days
  national.json     [{date, modis, viirs, viirs_h}] every day of the year
  cells.json        [{h3, modis, viirs, viirs_h}] yearly totals per cell
  cells/<h3>.json   [{date, modis, viirs, viirs_h}] days with detections only

modis = MODIS Aqua (reference satellite). viirs = VIIRS S-NPP raw.
viirs_h = VIIRS in "MODIS Aqua equivalent". On VIIRS no-data days
(meta.no_data_days.viirs) viirs and viirs_h are null, never 0.
"""

import json
import math
import shutil
from datetime import datetime, timezone

import pandas as pd

from pipeline import config, harmonize

CELLS_DIR = config.WEB_DATA_DIR / "cells"
SERIES_KEYS = ["modis", "viirs", "viirs_h"]


def num(value, digits: int | None = None):
    """JSON-friendly number: NaN -> None, ints stay ints, floats rounded."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if digits is None:
        return int(value)
    return round(float(value), digits)


def series_rows(df: pd.DataFrame) -> list[dict]:
    return [
        {"date": d.strftime("%Y-%m-%d"), "modis": num(m), "viirs": num(v), "viirs_h": num(h, 2)}
        for d, m, v, h in zip(df["date"], df["modis"], df["viirs"], df["viirs_h"])
    ]


def build_national(h: pd.DataFrame, gaps: list[str], factors: dict[str, float]) -> list[dict]:
    days = pd.date_range(f"{config.YEAR}-01-01", f"{config.YEAR}-12-31", freq="D")
    nat = h.groupby("date")[["modis", "viirs"]].sum(min_count=0).reindex(days, fill_value=0)
    nat["viirs_h"] = nat["viirs"] * nat.index.strftime("%Y-%m").map(factors).to_numpy()
    gap = nat.index.isin(pd.to_datetime(gaps))
    nat.loc[gap, ["viirs", "viirs_h"]] = float("nan")
    return series_rows(nat.rename_axis("date").reset_index())


def build_cells(h: pd.DataFrame) -> list[dict]:
    totals = h.groupby("h3")[["modis", "viirs", "viirs_h"]].sum(min_count=0)
    totals = totals.sort_values("viirs_h", ascending=False)
    return [
        {"h3": c, "modis": num(m), "viirs": num(v), "viirs_h": num(vh, 2)}
        for c, m, v, vh in zip(totals.index, totals["modis"], totals["viirs"], totals["viirs_h"])
    ]


def write_json(path, obj) -> None:
    path.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def validate_contract(data_dir=config.WEB_DATA_DIR) -> dict:
    """Check the exported files against the contract. Raises AssertionError."""
    meta = json.loads((data_dir / "meta.json").read_text())
    for key in ["country", "year", "h3_resolution", "generated_at", "filters",
                "harmonization", "sources", "no_data_days"]:
        assert key in meta, f"meta.json missing {key}"
    assert len(meta["harmonization"]["factors"]) == 12
    gaps = set(meta["no_data_days"]["viirs"])

    national = json.loads((data_dir / "national.json").read_text())
    n_days = 366 if meta["year"] % 4 == 0 else 365
    assert len(national) == n_days, "national.json must have every day of the year"
    for row in national:
        assert set(row) == {"date", *SERIES_KEYS}
        if row["date"] in gaps:
            assert row["viirs"] is None and row["viirs_h"] is None
        else:
            assert isinstance(row["viirs"], int) and isinstance(row["viirs_h"], (int, float))

    cells = json.loads((data_dir / "cells.json").read_text())
    files = {p.stem for p in (data_dir / "cells").glob("*.json")}
    assert {c["h3"] for c in cells} == files, "cells.json and cells/ files differ"
    for c in cells:
        assert set(c) == {"h3", *SERIES_KEYS}

    size = sum(p.stat().st_size for p in data_dir.rglob("*.json"))
    assert size < config.MAX_WEB_DATA_MB * 1024 * 1024, f"web data is {size / 1e6:.1f} MB"
    return {"cells": len(cells), "days": len(national), "bytes": size, "files": len(files) + 3}


def main() -> int:
    harmonized = pd.read_parquet(harmonize.OUTPUT)
    factors_info = json.loads(harmonize.FACTORS.read_text())
    gaps = harmonize.load_gaps()

    if CELLS_DIR.exists():
        shutil.rmtree(CELLS_DIR)
    CELLS_DIR.mkdir(parents=True)

    meta = {
        "country": config.COUNTRY,
        "year": config.YEAR,
        "h3_resolution": config.H3_RESOLUTION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filters": {
            "type": config.KEEP_TYPES,
            "modis_min_conf": config.MODIS_MIN_CONFIDENCE,
            "viirs_conf": config.VIIRS_CONFIDENCE,
        },
        "harmonization": {
            "method": factors_info["method"],
            "factors": {k: round(v, 4) for k, v in factors_info["factors"].items()},
            "annual_factor": round(factors_info["annual_factor"], 4),
            "reference": {"modis": config.REFERENCE_MODIS_SATELLITE, "viirs": config.REFERENCE_VIIRS_SATELLITE},
        },
        "series": {
            "modis": f"MODIS {config.REFERENCE_MODIS_SATELLITE} detections",
            "viirs": f"VIIRS {config.REFERENCE_VIIRS_SATELLITE} detections (raw)",
            "viirs_h": f"VIIRS harmonized to MODIS {config.REFERENCE_MODIS_SATELLITE} equivalent",
        },
        "no_data_days": gaps,
        "utc_offset_hours": config.UTC_OFFSET_HOURS,
        "sources": [config.SOURCES["modis"]["label"], config.SOURCES["viirs"]["label"]],
    }

    write_json(config.WEB_DATA_DIR / "meta.json", meta)
    write_json(config.WEB_DATA_DIR / "national.json",
               build_national(harmonized, gaps["viirs"], factors_info["factors"]))
    cells = build_cells(harmonized)
    write_json(config.WEB_DATA_DIR / "cells.json", cells)
    for cell, g in harmonized.sort_values("date").groupby("h3"):
        write_json(CELLS_DIR / f"{cell}.json", series_rows(g))

    summary = validate_contract()
    print(f"Exported {summary['cells']:,} cells, {summary['days']} national days, "
          f"{summary['files']:,} files, {summary['bytes'] / 1e6:.2f} MB "
          f"(limit {config.MAX_WEB_DATA_MB} MB). Contract OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
