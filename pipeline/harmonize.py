"""Harmonization v1: express VIIRS S-NPP counts as "MODIS Aqua equivalent".

Method `monthly_ratio_v1` (PLAN.md, Phase 3):
  1. Keep cell-days where BOTH MODIS Aqua and VIIRS S-NPP have >= 1 detection.
  2. f_month = sum(MODIS Aqua) / sum(VIIRS S-NPP) over those cell-days.
  3. viirs_h = viirs * f_month.
  4. Months with < MIN_COMMON_CELL_DAYS common cell-days use the annual factor.
VIIRS no-data days (outages) are kept as missing (NaN), never as zero.

Usage: uv run python -m pipeline.harmonize
Output: data/interim/harmonized.parquet, data/interim/factors.json
"""

import json

import pandas as pd

from pipeline import config

INPUT = config.INTERIM_DIR / "daily_cell.parquet"
GAPS = config.INTERIM_DIR / "gaps.json"
OUTPUT = config.INTERIM_DIR / "harmonized.parquet"
FACTORS = config.INTERIM_DIR / "factors.json"


def load_gaps() -> dict[str, list[str]]:
    return json.loads(GAPS.read_text())


def to_wide(daily: pd.DataFrame) -> pd.DataFrame:
    """One row per (h3, date) with counts per reference satellite.

    modis = MODIS Aqua (reference), modis_terra kept for diagnostics,
    viirs = VIIRS S-NPP.
    """
    key = daily["sensor"] + ":" + daily["satellite"]
    names = {
        f"modis:{config.REFERENCE_MODIS_SATELLITE}": "modis",
        "modis:Terra": "modis_terra",
        f"viirs:{config.REFERENCE_VIIRS_SATELLITE}": "viirs",
    }
    wide = (
        daily.assign(col=key.map(names))
        .dropna(subset=["col"])
        .pivot_table(index=["h3", "date"], columns="col", values="n", aggfunc="sum", fill_value=0)
        .reindex(columns=list(names.values()), fill_value=0)
        .reset_index()
    )
    wide.columns.name = None
    wide["date"] = pd.to_datetime(wide["date"])
    wide["month"] = wide["date"].dt.strftime("%Y-%m")
    return wide


def common_cell_days(wide: pd.DataFrame) -> pd.DataFrame:
    return wide[(wide["modis"] > 0) & (wide["viirs"] > 0)]


def ratio(common: pd.DataFrame) -> float:
    return float(common["modis"].sum() / common["viirs"].sum())


def compute_factors(wide: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Monthly factors with annual fallback. Returns (table, annual factor)."""
    common = common_cell_days(wide)
    annual = ratio(common)
    months = [f"{config.YEAR}-{m:02d}" for m in range(1, 13)]
    rows = []
    for month in months:
        c = common[common["month"] == month]
        n = len(c)
        monthly = ratio(c) if n > 0 else float("nan")
        fallback = n < config.MIN_COMMON_CELL_DAYS
        rows.append({
            "month": month,
            "common_cell_days": n,
            "modis_aqua_sum": int(c["modis"].sum()),
            "viirs_sum": int(c["viirs"].sum()),
            "factor_month": monthly,
            "fallback_annual": fallback,
            "factor": annual if fallback else monthly,
        })
    return pd.DataFrame(rows), annual


def apply_factors(wide: pd.DataFrame, factors: pd.Series, viirs_gaps: list[str]) -> pd.DataFrame:
    """viirs_h = viirs * factor(month); VIIRS gap days become NaN (no data)."""
    out = wide.copy()
    out["viirs"] = out["viirs"].astype("float64")
    out["viirs_h"] = out["viirs"] * out["month"].map(factors)
    gap = out["date"].isin(pd.to_datetime(viirs_gaps))
    out.loc[gap, ["viirs", "viirs_h"]] = float("nan")
    return out


def harmonize(daily: pd.DataFrame, viirs_gaps: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    wide = to_wide(daily)
    table, annual = compute_factors(wide)
    harmonized = apply_factors(wide, table.set_index("month")["factor"], viirs_gaps)
    # Keep only cell-days with a detection by a reference satellite.
    keep = (harmonized["modis"] > 0) | (harmonized["viirs"].fillna(0) > 0)
    return harmonized[keep].reset_index(drop=True), table, annual


def main() -> int:
    daily = pd.read_parquet(INPUT)
    gaps = load_gaps()
    harmonized, table, annual = harmonize(daily, gaps["viirs"])
    harmonized.to_parquet(OUTPUT, index=False)
    FACTORS.write_text(json.dumps({
        "method": config.HARMONIZATION_METHOD,
        "annual_factor": annual,
        "factors": dict(zip(table["month"], table["factor"])),
        "table": table.to_dict(orient="records"),
    }, indent=2))
    print(table.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"Annual factor: {annual:.3f}")
    print(f"Wrote {OUTPUT.relative_to(config.ROOT)} ({len(harmonized):,} cell-days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
