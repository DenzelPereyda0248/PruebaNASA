"""Exploration report for the raw FIRMS files.

Usage: uv run python -m pipeline.inspect_data
Output: data/reports/01_exploracion.md and data/reports/01_monthly_detections.png
"""

from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import config  # noqa: E402

REPORT = config.REPORTS_DIR / "01_exploracion.md"
FIGURE = config.REPORTS_DIR / "01_monthly_detections.png"
TYPE_LABELS = {0: "vegetation fire", 1: "active volcano", 2: "other static land source", 3: "offshore"}


def load_sources() -> dict[str, tuple[dict, pd.DataFrame]]:
    """Load every configured file that exists (main sources first)."""
    loaded = {}
    for key, src in {**config.SOURCES, **config.ALT_SOURCES}.items():
        path = config.RAW_DIR / src["file"]
        if path.exists():
            df = pd.read_csv(path, dtype={"acq_time": str, "confidence": str})
            df["acq_date"] = pd.to_datetime(df["acq_date"], format="%Y-%m-%d")
            loaded[key] = (src, df)
    return loaded


def md_table(df: pd.DataFrame, index: bool = True) -> str:
    """Render a DataFrame as a GitHub-flavoured Markdown table (no extra deps)."""
    if index:
        df = df.reset_index()
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        cells = [f"{v:,}" if isinstance(v, int) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def counts(series: pd.Series, name: str, labels: dict | None = None) -> pd.DataFrame:
    vc = series.value_counts(dropna=False).sort_index()
    out = pd.DataFrame({name: vc.index, "rows": vc.values.astype(int)})
    out["share"] = (out["rows"] / out["rows"].sum() * 100).map(lambda x: f"{x:.1f}%")
    if labels:
        out.insert(1, "meaning", out[name].map(labels).fillna("?"))
    return out


def confidence_section(key: str, df: pd.DataFrame) -> str:
    conf = df["confidence"]
    numeric = pd.to_numeric(conf, errors="coerce")
    if numeric.notna().all():  # MODIS style 0-100
        bins = pd.cut(numeric, [-1, 29, 79, 100], labels=["low (0-29)", "nominal (30-79)", "high (80-100)"])
        txt = md_table(counts(bins.astype(str), "confidence class"), index=False)
        txt += f"\n\nNumeric summary: min {numeric.min():.0f}, median {numeric.median():.0f}, max {numeric.max():.0f}."
        return txt
    return md_table(counts(conf, "confidence"), index=False)


def format_runs(days: pd.DatetimeIndex) -> str:
    """Compact consecutive days into ranges, e.g. '2024-05-30 → 06-03 (5 d)'."""
    runs: list[list[pd.Timestamp]] = []
    for d in days:
        if runs and (d - runs[-1][1]).days == 1:
            runs[-1][1] = d
        else:
            runs.append([d, d])
    parts = []
    for a, b in runs:
        n = (b - a).days + 1
        parts.append(f"{a:%Y-%m-%d}" if n == 1 else f"{a:%Y-%m-%d} → {b:%m-%d} ({n} d)")
    return ", ".join(parts)


def surprises(key: str, df: pd.DataFrame) -> list[str]:
    notes = []
    years = df["acq_date"].dt.year.unique()
    if list(years) != [config.YEAR]:
        notes.append(f"dates outside {config.YEAR}: years present {sorted(years)}")
    lon0, lat0, lon1, lat1 = config.MEXICO_BBOX
    outside = (~df["longitude"].between(lon0, lon1) | ~df["latitude"].between(lat0, lat1)).sum()
    if outside:
        notes.append(f"{outside:,} detections outside the rough Mexico bounding box")
    nulls = df[config.REQUIRED_COLUMNS].isna().sum()
    for col, n in nulls[nulls > 0].items():
        notes.append(f"{n:,} null values in `{col}`")
    dups = df.duplicated(["latitude", "longitude", "acq_date", "acq_time", "satellite"]).sum()
    if dups:
        notes.append(f"{dups:,} exact duplicate detections (same lat/lon/date/time/satellite)")
    all_days = pd.date_range(f"{config.YEAR}-01-01", f"{config.YEAR}-12-31", freq="D")
    missing = all_days.difference(df["acq_date"].dt.normalize().unique())
    if len(missing):
        notes.append(f"{len(missing)} day(s) with no detections at all "
                     f"(likely data gaps, not days without fire): {format_runs(missing)}")
    return notes


def main() -> int:
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    data = load_sources()
    if not data:
        print("No input files found in data/raw. Run `python -m pipeline.download` first.")
        return 1

    out = [
        f"# 01 — Data exploration ({config.COUNTRY}, {config.YEAR})",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by `pipeline/inspect_data.py`.",
        "Raw files, no filters applied.",
        "",
        "## Files",
        "",
    ]
    file_rows = []
    for key, src in {**config.SOURCES, **config.ALT_SOURCES}.items():
        role = "method input" if key in config.SOURCES else "alternative (not in scope)"
        n = f"{len(data[key][1]):,}" if key in data else "**MISSING**"
        file_rows.append({"key": key, "file": f"`{src['file']}`", "role": role, "rows": n})
    out += [md_table(pd.DataFrame(file_rows), index=False), ""]

    monthly = {}
    for key, (src, df) in data.items():
        out += [f"## {src['label']} (`{key}`)", ""]
        out += ["### Rows by satellite", "", md_table(counts(df["satellite"], "satellite"), index=False), ""]
        dtypes = pd.DataFrame({"column": df.columns, "dtype": df.dtypes.astype(str).values,
                               "example": [str(df[c].iloc[0]) for c in df.columns]})
        out += ["### Columns and types", "", md_table(dtypes, index=False), ""]
        out += ["### `type`", "", md_table(counts(df["type"], "type", TYPE_LABELS), index=False), ""]
        out += ["### `confidence`", "", confidence_section(key, df), ""]
        out += ["### `daynight`", "", md_table(counts(df["daynight"], "daynight"), index=False), ""]
        times = df["acq_time"].str.zfill(4)
        by_sat_hour = (df.assign(hour_utc=times.str[:2].astype(int))
                         .groupby(["satellite", "daynight"])["hour_utc"]
                         .agg(lambda h: f"{h.min():02d}–{h.max():02d}"))
        out += ["### Overpass hours (UTC, `acq_time`)", "",
                md_table(by_sat_hour.rename("hour range (UTC)").to_frame()), ""]
        lon0, lat0 = df["longitude"].min(), df["latitude"].min()
        lon1, lat1 = df["longitude"].max(), df["latitude"].max()
        out += ["### Coverage", "",
                f"- Date range: {df['acq_date'].min():%Y-%m-%d} to {df['acq_date'].max():%Y-%m-%d} "
                f"({df['acq_date'].nunique()} distinct days)",
                f"- Bounding box: lon {lon0:.3f} to {lon1:.3f}, lat {lat0:.3f} to {lat1:.3f}",
                f"- FRP (MW): median {df['frp'].median():.1f}, p95 {df['frp'].quantile(.95):.1f}, max {df['frp'].max():.1f}",
                ""]
        notes = surprises(key, df)
        out += ["### Checks", ""] + ([f"- ⚠️ {n}" for n in notes] or ["- No issues found."]) + [""]
        for sat, g in df.groupby("satellite"):
            monthly[f"{key}:{sat}"] = g.groupby(g["acq_date"].dt.month).size()

    table = pd.DataFrame(monthly).reindex(range(1, 13)).fillna(0).astype(int)
    table.index = [datetime(config.YEAR, m, 1).strftime("%b") for m in table.index]
    table.index.name = "month"
    total = table.sum().to_frame().T
    total.index = ["**total**"]
    out += ["## Detections per month (raw, all types and confidences)", "",
            md_table(pd.concat([table, total]).rename_axis("month")), "", f"![Monthly detections]({FIGURE.name})", ""]

    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=120)
    for col in table.columns:
        ax.plot(table.index, table[col], marker="o", linewidth=2, label=col)
    ax.set_title(f"Raw FIRMS detections per month — {config.COUNTRY} {config.YEAR}")
    ax.set_ylabel("detections")
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIGURE)
    plt.close(fig)

    REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {REPORT.relative_to(config.ROOT)} and {FIGURE.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
