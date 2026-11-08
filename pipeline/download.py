"""Download (or verify) the FIRMS country-yearly CSV files.

Usage: uv run python -m pipeline.download

If a file is missing and cannot be downloaded, the script stops with an error
and tells the team how to get it manually. It never creates placeholder data.
"""

import csv
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pipeline import config

TIMEOUT_S = 60


def header_of(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def check_file(path: Path) -> list[str]:
    """Return a list of problems with a CSV file (empty list = OK)."""
    if path.stat().st_size == 0:
        return ["file is empty"]
    missing = [c for c in config.REQUIRED_COLUMNS if c not in header_of(path)]
    return [f"missing columns: {missing}"] if missing else []


def try_download(url: str, dest: Path) -> str | None:
    """Download url to dest. Return None on success or an error message."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fire-calendar-pipeline"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp, tmp.open("wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
    except (urllib.error.URLError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        return str(exc)
    tmp.replace(dest)
    return None


def count_rows(path: Path) -> int:
    with path.open("rb") as f:
        return max(sum(1 for _ in f) - 1, 0)


def main() -> int:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    failed = []

    for key, src in config.SOURCES.items():
        path = config.RAW_DIR / src["file"]
        if not path.exists():
            print(f"[{key}] {src['file']} not found, downloading from {src['url']} ...")
            error = try_download(src["url"], path)
            if error:
                print(f"[{key}] download FAILED: {error}")
                failed.append(src)
                continue
        problems = check_file(path)
        if problems:
            print(f"[{key}] {src['file']} is INVALID: {'; '.join(problems)}")
            failed.append(src)
        else:
            print(f"[{key}] OK  {src['file']}  ({count_rows(path):,} rows)")

    for key, src in config.ALT_SOURCES.items():
        path = config.RAW_DIR / src["file"]
        if path.exists():
            print(f"[{key}] present (not used by the method): {src['file']} ({count_rows(path):,} rows)")

    if failed:
        print("\nMissing or invalid input files. Do NOT replace them with synthetic data.")
        print("Download them manually from NASA FIRMS (https://firms.modaps.eosdis.nasa.gov/country/),")
        print(f"year {config.YEAR}, country {config.COUNTRY}, and save them in {config.RAW_DIR} as:")
        for src in failed:
            print(f"  - {src['file']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
