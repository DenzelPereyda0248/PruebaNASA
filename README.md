# Fire Calendar — Harmonized MODIS + VIIRS burning activity (Mexico, 2024)

Prototype for the NASA Space Apps Challenge 2026 challenge
**"Harmonization of MODIS and VIIRS Hot Spots"**.

MODIS (since 2000, ~1 km pixels) and VIIRS (since 2012, 375 m pixels) detect
active fires very differently: VIIRS sees many more, smaller fires. Mixing them
naively makes it look like fires increased just because the instrument changed.
This prototype harmonizes both records on an H3 hexagon grid and shows a daily
burning-activity calendar for any hexagon in Mexico during 2024.

> Work in progress. See `PLAN.md` for the roadmap.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
# Python pipeline
uv sync
uv run python -m pipeline.run_all   # available from Phase 4

# Web app
cd web
npm install
npm run dev
```

## Data

NASA FIRMS Country Yearly Summary for Mexico, 2024: MODIS C6.1 (Terra + Aqua)
and VIIRS S-NPP 375 m. Raw CSVs go in `data/raw/` and are not committed.

## License

MIT
