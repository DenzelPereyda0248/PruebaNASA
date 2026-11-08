"""Validation of the harmonization (PLAN.md, Phase 3).

Usage: uv run python -m pipeline.validate
Output: data/reports/03_validacion.md and PNG charts in data/reports/

All comparisons exclude VIIRS no-data days (outages) on both sides.
"""

import json
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import config, grid, harmonize  # noqa: E402

REPORT = config.REPORTS_DIR / "03_validacion.md"
FIG_FACTORS = config.REPORTS_DIR / "03_monthly_factors.png"
FIG_NATIONAL = config.REPORTS_DIR / "03_national_daily.png"
FIG_SCATTER = config.REPORTS_DIR / "03_scatter_cell_week.png"

COLORS = {"modis": "#2a6fdb", "viirs": "#e8590c", "viirs_h": "#2f9e44", "gap": "#adb5bd"}


# --- helpers -------------------------------------------------------------------

def md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def cell_week(wide: pd.DataFrame, pred: pd.Series) -> pd.DataFrame:
    """Aggregate observed MODIS Aqua and a predicted series to cell-week."""
    df = pd.DataFrame({
        "h3": wide["h3"],
        "week": wide["date"] - pd.to_timedelta(wide["date"].dt.day_of_week, unit="D"),
        "obs": wide["modis"],
        "pred": pred,
    })
    agg = df.groupby(["h3", "week"], as_index=False)[["obs", "pred"]].sum()
    return agg[(agg["obs"] > 0) | (agg["pred"] > 0)]


def metrics(cw: pd.DataFrame) -> dict:
    obs, pred = cw["obs"], cw["pred"]
    err = pred - obs
    return {
        "cell_weeks": len(cw),
        "pearson_r": obs.corr(pred),
        "spearman_rho": obs.rank().corr(pred.rank()),  # Spearman without scipy
        "mean_error": err.mean(),
        "mae": err.abs().mean(),
        "total_ratio": pred.sum() / obs.sum(),
    }


def fmt_metrics(name: str, m: dict) -> dict:
    return {
        "series vs MODIS Aqua": name,
        "cell-weeks": f"{m['cell_weeks']:,}",
        "Pearson r": f"{m['pearson_r']:.3f}",
        "Spearman ρ": f"{m['spearman_rho']:.3f}",
        "mean error": f"{m['mean_error']:+.2f}",
        "MAE": f"{m['mae']:.2f}",
        "total ratio": f"{m['total_ratio']:.2f}",
    }


def no_gap(wide: pd.DataFrame, gaps: list[str]) -> pd.DataFrame:
    return wide[~wide["date"].isin(pd.to_datetime(gaps))].reset_index(drop=True)


def total_ratio_factors(wide: pd.DataFrame) -> pd.Series:
    """Candidate for discussion (NOT the exported method): monthly factor
    from ALL cell-days, i.e. sum(MODIS Aqua) / sum(VIIRS) per month."""
    g = wide.groupby("month")[["modis", "viirs"]].sum()
    return g["modis"] / g["viirs"]


# --- analyses ------------------------------------------------------------------

def method_comparison(wide: pd.DataFrame, factors: pd.Series, annual: float) -> pd.DataFrame:
    month = wide["month"]
    candidates = {
        "VIIRS raw (no harmonization)": wide["viirs"].astype(float),
        "VIIRS × annual factor": wide["viirs"] * annual,
        "**VIIRS × monthly_ratio_v1 (exported)**": wide["viirs"] * month.map(factors),
        "VIIRS × total-ratio monthly (candidate, not exported)": wide["viirs"] * month.map(total_ratio_factors(wide)),
    }
    return pd.DataFrame([fmt_metrics(k, metrics(cell_week(wide, v))) for k, v in candidates.items()])


def leave_one_month_out(wide: pd.DataFrame, factors: pd.Series) -> pd.DataFrame:
    """For each month m: factor = ratio on common cell-days of the OTHER months,
    evaluated on month m. Compared with the in-sample monthly factor."""
    common = harmonize.common_cell_days(wide)
    rows = []
    for month in sorted(wide["month"].unique()):
        f_cv = harmonize.ratio(common[common["month"] != month])
        w = wide[wide["month"] == month]
        m_in = metrics(cell_week(w, w["viirs"] * factors[month]))
        m_cv = metrics(cell_week(w, w["viirs"] * f_cv))
        rows.append({
            "month": month,
            "factor in-sample": f"{factors[month]:.3f}",
            "factor held-out": f"{f_cv:.3f}",
            "total ratio in-sample": f"{m_in['total_ratio']:.2f}",
            "total ratio held-out": f"{m_cv['total_ratio']:.2f}",
            "MAE in-sample": f"{m_in['mae']:.2f}",
            "MAE held-out": f"{m_cv['mae']:.2f}",
        })
    return pd.DataFrame(rows)


def resolution_sensitivity(detections: pd.DataFrame, gaps: list[str], wide5: pd.DataFrame,
                           factors5: pd.Series, annual5: float) -> pd.DataFrame:
    rows = []
    for res in (config.H3_RESOLUTION, config.H3_RESOLUTION_ALT):
        if res == config.H3_RESOLUTION:
            wide, factors, annual = wide5, factors5, annual5
        else:
            wide = harmonize.to_wide(grid.aggregate(detections, resolution=res))
            table, annual = harmonize.compute_factors(wide)
            factors = table.set_index("month")["factor"]
            wide = no_gap(wide, gaps)
        m = metrics(cell_week(wide, wide["viirs"] * wide["month"].map(factors)))
        common = harmonize.common_cell_days(wide)
        rows.append({
            "H3 res": res,
            "cells with detections": f"{wide['h3'].nunique():,}",
            "common cell-days": f"{len(common):,}",
            "annual factor": f"{annual:.3f}",
            "Pearson r (cell-week)": f"{m['pearson_r']:.3f}",
            "total ratio": f"{m['total_ratio']:.2f}",
        })
    return pd.DataFrame(rows)


# --- charts --------------------------------------------------------------------

def style(ax):
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)


def chart_factors(table: pd.DataFrame, annual: float):
    fig, ax = plt.subplots(figsize=(9, 3.8), dpi=120)
    labels = pd.to_datetime(table["month"]).dt.strftime("%b")
    ax.bar(labels, table["factor"], color=COLORS["viirs_h"], width=0.65)
    ax.axhline(annual, color="#495057", linestyle="--", linewidth=1.2, label=f"annual factor {annual:.3f}")
    for x, (f, n) in enumerate(zip(table["factor"], table["common_cell_days"])):
        ax.text(x, f + 0.008, f"{f:.2f}\nn={n:,}", ha="center", va="bottom", fontsize=7.5)
    ax.set_ylim(0, table["factor"].max() * 1.3)
    ax.set_ylabel("MODIS Aqua / VIIRS S-NPP")
    ax.set_title("Monthly harmonization factors (common cell-days, H3 res 5)")
    ax.legend(frameon=False, loc="upper center")
    style(ax)
    fig.tight_layout()
    fig.savefig(FIG_FACTORS)
    plt.close(fig)


def chart_national(national: pd.DataFrame, gaps: list[str]):
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), dpi=120, sharex=True)
    for ax, col, title in [
        (axes[0], "viirs", "Before: MODIS Aqua vs VIIRS S-NPP raw"),
        (axes[1], "viirs_h", "After: MODIS Aqua vs VIIRS harmonized (MODIS Aqua equivalent)"),
    ]:
        for g in pd.to_datetime(gaps):
            ax.axvspan(g, g + pd.Timedelta(days=1), color=COLORS["gap"], alpha=0.35, linewidth=0)
        ax.plot(national.index, national["modis"], color=COLORS["modis"], linewidth=1.2, label="MODIS Aqua")
        ax.plot(national.index, national[col], color=COLORS[col], linewidth=1.2,
                label="VIIRS raw" if col == "viirs" else "VIIRS harmonized")
        ax.set_title(title, fontsize=10.5, loc="left")
        ax.set_ylabel("detections / day")
        ax.legend(frameon=False, loc="upper left")
        style(ax)
    axes[1].text(0.995, 0.95, "grey = VIIRS no-data days", transform=axes[1].transAxes,
                 ha="right", va="top", fontsize=8, color="#495057")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.suptitle(f"National daily detections — {config.COUNTRY} {config.YEAR}", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG_NATIONAL)
    plt.close(fig)


def chart_scatter(cw: pd.DataFrame, m: dict):
    fig, ax = plt.subplots(figsize=(5.5, 5.2), dpi=120)
    x, y = np.log10(cw["obs"] + 1), np.log10(cw["pred"] + 1)
    hb = ax.hexbin(x, y, gridsize=45, bins="log", cmap="viridis", mincnt=1)
    lim = max(x.max(), y.max()) * 1.02
    ax.plot([0, lim], [0, lim], color="#e03131", linewidth=1, label="1:1")
    values = np.array([0, 1, 3, 10, 30, 100, 300])
    pos = np.log10(values + 1)
    ax.set_xticks(pos, [str(v) for v in values])
    ax.set_yticks(pos, [str(v) for v in values])
    ax.set_xlim(-0.05, lim)
    ax.set_ylim(-0.05, lim)
    ax.set_xlabel("MODIS Aqua detections (cell-week)")
    ax.set_ylabel("VIIRS harmonized (cell-week)")
    ax.set_title(f"Cell-week agreement, r = {m['pearson_r']:.2f}", fontsize=10.5)
    fig.colorbar(hb, ax=ax, label="cell-weeks")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG_SCATTER)
    plt.close(fig)


# --- report --------------------------------------------------------------------

def main() -> int:
    daily = pd.read_parquet(harmonize.INPUT)
    detections = pd.read_parquet(config.INTERIM_DIR / "detections.parquet")
    gaps = harmonize.load_gaps()["viirs"]

    wide_all = harmonize.to_wide(daily)
    table, annual = harmonize.compute_factors(wide_all)
    factors = table.set_index("month")["factor"]
    wide = no_gap(wide_all, gaps)

    # National daily series (all days of the year, gaps as NaN)
    days = pd.date_range(f"{config.YEAR}-01-01", f"{config.YEAR}-12-31", freq="D")
    nat = wide_all.groupby("date")[["modis", "viirs"]].sum().reindex(days, fill_value=0)
    nat["viirs"] = nat["viirs"].astype(float)
    nat["viirs_h"] = nat["viirs"] * nat.index.strftime("%Y-%m").map(factors).to_numpy()
    nat.loc[nat.index.isin(pd.to_datetime(gaps)), ["viirs", "viirs_h"]] = np.nan
    nat_ok = nat.dropna()
    daily_r = nat_ok["modis"].corr(nat_ok["viirs_h"])

    comparison = method_comparison(wide, factors, annual)
    v1 = metrics(cell_week(wide, wide["viirs"] * wide["month"].map(factors)))
    lomo = leave_one_month_out(wide, factors)
    lomo_better = int((lomo["MAE held-out"].astype(float) < lomo["MAE in-sample"].astype(float)).sum())
    annual_m = metrics(cell_week(wide, wide["viirs"] * annual))
    sens = resolution_sensitivity(detections, gaps, wide, factors, annual)
    counts = json.loads((config.INTERIM_DIR / "clean_counts.json").read_text())

    chart_factors(table, annual)
    chart_national(nat, gaps)
    chart_scatter(cell_week(wide, wide["viirs"] * wide["month"].map(factors)), v1)

    both = ((wide["modis"] > 0) & (wide["viirs"] > 0)).sum()
    only_v = ((wide["modis"] == 0) & (wide["viirs"] > 0)).sum()
    only_m = ((wide["modis"] > 0) & (wide["viirs"] == 0)).sum()
    only_v_share = wide.loc[wide["modis"] == 0, "viirs"].sum() / wide["viirs"].sum()

    ftable = table.assign(
        factor_month=table["factor_month"].map(lambda x: f"{x:.3f}"),
        factor=table["factor"].map(lambda x: f"{x:.3f}"),
        fallback_annual=table["fallback_annual"].map({True: "yes", False: "no"}),
        common_cell_days=table["common_cell_days"].map(lambda x: f"{x:,}"),
        modis_aqua_sum=table["modis_aqua_sum"].map(lambda x: f"{x:,}"),
        viirs_sum=table["viirs_sum"].map(lambda x: f"{x:,}"),
    )
    step_rows = []
    for sensor, steps in counts.items():
        for step, n in steps.items():
            step_rows.append({"sensor": sensor, "step": step, "rows": f"{n:,}"})

    out = [
        f"# 03 — Harmonization v1 and validation ({config.COUNTRY}, {config.YEAR})",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by `pipeline/validate.py`.",
        "",
        "## Summary",
        "",
        f"- Method `{config.HARMONIZATION_METHOD}`: VIIRS S-NPP × monthly factor = \"MODIS Aqua equivalent\".",
        f"- Annual factor **{annual:.3f}**: on cell-days where both sensors see fire, MODIS Aqua "
        f"reports about {annual:.2f} detections per VIIRS detection (≈ 1 per {1 / annual:.1f}).",
        f"- Factors range from {table['factor'].min():.2f} (fire season) to {table['factor'].max():.2f} "
        "(wet season); no month needed the annual fallback.",
        f"- Timing agrees well: national daily Pearson r = **{daily_r:.2f}**, cell-week r = **{v1['pearson_r']:.2f}**.",
        f"- **Totals do not agree yet**: harmonized VIIRS sums to **{v1['total_ratio']:.2f}×** MODIS Aqua. "
        f"{only_v:,} cell-days ({only_v_share:.0%} of VIIRS detections) have VIIRS fire but no MODIS Aqua "
        "detection; the factor, learned only where both see fire, is applied to them too.",
        f"- Monthly factors do not beat a single factor: in the leave-one-month-out test the held-out "
        f"(annual-like) factor has lower cell-week MAE in {lomo_better} of 12 months, and a single "
        f"annual factor scores MAE {annual_m['mae']:.2f} vs {v1['mae']:.2f} for monthly factors.",
        f"- {len(gaps)} VIIRS no-data days are excluded from every comparison and exported as missing.",
        "",
        "## Rows after each cleaning step",
        "",
        md_table(pd.DataFrame(step_rows)),
        "",
        "## Monthly factors",
        "",
        f"Common cell-days = H3 res {config.H3_RESOLUTION} cell and local day where MODIS Aqua ≥ 1 and "
        f"VIIRS S-NPP ≥ 1. Fallback to the annual factor below {config.MIN_COMMON_CELL_DAYS} common cell-days.",
        "",
        md_table(ftable[["month", "common_cell_days", "modis_aqua_sum", "viirs_sum",
                         "factor_month", "fallback_annual", "factor"]]),
        "",
        f"![Monthly factors]({FIG_FACTORS.name})",
        "",
        "## National daily series",
        "",
        f"![National daily series]({FIG_NATIONAL.name})",
        "",
        "## Agreement at cell-week level",
        "",
        f"Cell-week = H3 res {config.H3_RESOLUTION} cell × Monday-based week; only cell-weeks with any "
        "detection. Mean error = mean(series − MODIS Aqua). Total ratio = sum(series) / sum(MODIS Aqua) "
        "(1.00 = same totals).",
        "",
        md_table(comparison),
        "",
        f"Cell-day overlap (VIIRS data days): both {both:,} · VIIRS only {only_v:,} · MODIS Aqua only {only_m:,}.",
        "",
        f"![Cell-week scatter]({FIG_SCATTER.name})",
        "",
        "## Leave-one-month-out cross-validation",
        "",
        "For each month the factor is recomputed from the other 11 months (common cell-days) and "
        "evaluated on the held-out month.",
        "",
        md_table(lomo),
        "",
        "## Grid resolution sensitivity",
        "",
        md_table(sens),
        "",
        "## Limitations (plain language)",
        "",
        "- **One year only.** Factors are fitted and checked on 2024 data; they may differ in other years.",
        "- **Totals are inflated.** The factor is learned where both satellites see fire, but VIIRS also "
        "sees many small fires where MODIS sees nothing. Multiplying those by the same factor adds "
        "detections that MODIS would not have reported. The calendar shape (when burning happens) is "
        "reliable; the absolute numbers of `viirs_h` are about twice what MODIS Aqua would show.",
        "- **Counts, not burned area.** A detection is a hot pixel at the moment of the overpass; one fire "
        "can produce many detections and short fires between overpasses are missed.",
        "- **Fixed UTC−6.** Local dates use one time zone for all of Mexico; a few night detections in "
        "Baja California, Sonora and Quintana Roo may fall on a neighbouring day.",
        "- **VIIRS outages.** 20 days in 2024 have no VIIRS data at all; they are shown as \"no data\". "
        "Partial-coverage days (fewer orbits than usual) are not detected and look like low activity.",
        "- **Only MODIS Aqua is the reference.** Terra (morning pass) is not used in the harmonized series.",
        "",
        "## Open question for the team",
        "",
        "The candidate `total-ratio monthly` row shows a simple alternative (factor from all cell-days) "
        "that matches totals by construction while keeping the same correlation. It is **not** applied; "
        "the exported data uses `monthly_ratio_v1` as specified in PLAN.md.",
        "",
    ]
    REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {REPORT.relative_to(config.ROOT)}")
    print(comparison.to_string(index=False))
    print(sens.to_string(index=False))
    print(f"daily national r={daily_r:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
