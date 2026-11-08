"""Run the whole pipeline: raw FIRMS CSVs -> reports -> web JSON.

Usage: uv run python -m pipeline.run_all
Stops at the first step that fails (e.g. missing input files).
"""

import time

from pipeline import clean, download, export, grid, harmonize, inspect_data, validate

STEPS = [
    ("download (verify inputs)", download.main),
    ("inspect_data", inspect_data.main),
    ("clean", clean.main),
    ("grid", grid.main),
    ("harmonize", harmonize.main),
    ("validate", validate.main),
    ("export", export.main),
]


def main() -> int:
    for name, step in STEPS:
        print(f"\n=== {name} ===")
        start = time.perf_counter()
        code = step()
        if code:
            print(f"\nStep '{name}' failed (exit {code}). Stopping.")
            return code
        print(f"--- {name} done in {time.perf_counter() - start:.1f} s")
    print("\nPipeline finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
