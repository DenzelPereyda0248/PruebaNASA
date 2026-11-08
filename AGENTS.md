# AGENTS.md — Fire Calendar prototype (Mexico, 2024)

NASA Space Apps 2026, "Harmonization of MODIS and VIIRS Hot Spots".
Static prototype: Python turns FIRMS CSVs into JSON; a React app shows a
hexagon map of Mexico and a 2024 daily burning calendar per cell.
Full plan and phase rules: `PLAN.md` (read it first).

## Structure
- `pipeline/` Python steps: config, download, inspect_data, clean, grid, harmonize, validate, export
- `data/raw/` FIRMS CSVs (git-ignored) · `data/interim/` Parquet (git-ignored)
- `data/reports/` Markdown reports + PNG charts (committed)
- `tests/` pytest · `web/` Vite + React + TS · `web/public/data/` exported JSON

## JSON contract (`web/public/data/`, total < 15 MB)
- `meta.json`: country, year, h3_resolution, filters, harmonization factors, sources
- `cells.json`: `[{h3, modis, viirs, viirs_h}]` totals per cell
- `national.json`: `[{date, modis, viirs, viirs_h}]` daily, whole country
- `cells/<h3>.json`: `[{date, modis, viirs, viirs_h}]` daily, days with detections only
- `viirs_h` = VIIRS expressed as "MODIS Aqua equivalent"

## Commands
- `uv sync` · `uv run pytest` · `uv run python -m pipeline.run_all`
- `cd web && npm install && npm run dev` · `npm run build`

## Rules
- Talk to the team in Spanish; code, comments, README and UI in English.
- Never invent data or results. If a download or step fails, say so and stop.
- Never commit `data/raw/`, `data/interim/`, `.env` or keys.
- All method constants live in `pipeline/config.py`; propose changes, don't apply silently.
- Only dependencies listed in PLAN.md section 3; ask before adding others.
- Work one phase at a time; stop at the end of each phase for review.
- Small commits with clear messages.
