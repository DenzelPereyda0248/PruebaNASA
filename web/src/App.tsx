import { useEffect, useMemo, useState } from 'react'
import { cellToLatLng } from 'h3-js'
import HexMap, { MAP_BREAKS, colorFor } from './HexMap'
import CalendarChart from './CalendarChart'
import {
  SERIES, fmt, loadCell, loadCells, loadMeta, loadNational,
  type CellTotal, type DayRow, type Meta, type SeriesKey,
} from './data'

interface Base { meta: Meta; national: DayRow[]; cells: CellTotal[] }

function weekStart(date: string): string {
  const d = new Date(date + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7))
  return d.toISOString().slice(0, 10)
}

function topWeeks(rows: DayRow[], key: SeriesKey, n = 3) {
  const weeks = new Map<string, number>()
  for (const r of rows) {
    const v = r[key]
    if (v) weeks.set(weekStart(r.date), (weeks.get(weekStart(r.date)) ?? 0) + v)
  }
  return [...weeks.entries()].sort((a, b) => b[1] - a[1]).slice(0, n)
}

const shortDate = (d: string) =>
  new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })

/** "May 30–Jun 3, Sep 26" from a sorted list of ISO dates. */
function gapRuns(days: string[]): string {
  const runs: [string, string][] = []
  for (const d of days) {
    const last = runs[runs.length - 1]
    const next = last && new Date(Date.parse(last[1] + 'T00:00:00Z') + 864e5).toISOString().slice(0, 10)
    if (last && next === d) last[1] = d
    else runs.push([d, d])
  }
  return runs.map(([a, b]) => (a === b ? shortDate(a) : `${shortDate(a)}–${shortDate(b)}`)).join(', ')
}

function sum(rows: DayRow[], key: SeriesKey) {
  return rows.reduce((acc, r) => acc + (r[key] ?? 0), 0)
}

export default function App() {
  const [base, setBase] = useState<Base | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [series, setSeries] = useState<SeriesKey>('viirs_h')
  const [selected, setSelected] = useState<string | null>(null)
  const [cellRows, setCellRows] = useState<DayRow[] | null>(null)

  useEffect(() => {
    Promise.all([loadMeta(), loadNational(), loadCells()])
      .then(([meta, national, cells]) => setBase({ meta, national, cells }))
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!selected) return
    let live = true
    loadCell(selected)
      .then((rows) => live && setCellRows(rows))
      .catch((e: Error) => live && setError(e.message))
    return () => { live = false }
  }, [selected])

  const select = (h3: string | null) => {
    setCellRows(null)
    setSelected(h3)
  }

  const rows = selected ? cellRows : base?.national ?? null
  const seriesInfo = SERIES.find((s) => s.key === series)!
  const weeks = useMemo(() => (rows ? topWeeks(rows, series) : []), [rows, series])
  const activeDays = rows ? rows.filter((r) => (r[series] ?? 0) > 0).length : 0

  if (error) {
    return (
      <main className="state">
        <h1>Data could not be loaded</h1>
        <p>{error}. Run <code>uv run python -m pipeline.run_all</code> to generate <code>web/public/data/</code>, then reload.</p>
      </main>
    )
  }
  if (!base) return <main className="state"><p>Loading 2024 detections…</p></main>

  const { meta } = base
  const gaps = meta.no_data_days.viirs
  const [lat, lng] = selected ? cellToLatLng(selected) : [0, 0]
  const maxWeek = weeks[0]?.[1] ?? 1

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>Burning calendar</h1>
          <p className="lede">
            Satellite fire detections across {meta.country}, {meta.year}. VIIRS sees about
            {' '}{fmt(1 / meta.harmonization.annual_factor, 1)}× more hot spots than MODIS, so its counts are
            rescaled to “MODIS Aqua equivalent” before comparing.
          </p>
        </div>
        <div className="switch" role="radiogroup" aria-label="Series shown in the calendar">
          {SERIES.map((s) => (
            <button
              key={s.key}
              role="radio"
              aria-checked={series === s.key}
              className={series === s.key ? 'on' : ''}
              onClick={() => setSeries(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </header>

      <section className="map-wrap" aria-label="Map of hexagon cells">
        <HexMap cells={base.cells} selected={selected} onSelect={select} />
        <div className="legend">
          <p>Harmonized detections per hexagon, {meta.year}</p>
          <div className="ramp">
            {[0, ...MAP_BREAKS].map((b, i) => (
              <span key={b}>
                <i style={{ background: colorFor(b) }} />
                {i === 0 ? `< ${MAP_BREAKS[0]}` : i === MAP_BREAKS.length ? `${b}+` : `${b}`}
              </span>
            ))}
          </div>
        </div>
        {!selected && <p className="hint">Select a hexagon to see its calendar</p>}
      </section>

      <aside className="panel">
        <div className="where">
          {selected ? (
            <>
              <h2>Hexagon at {lat.toFixed(2)}°, {lng.toFixed(2)}°</h2>
              <p className="sub">
                About 250 km² · H3 cell <code>{selected}</code>{' '}
                <button className="link" onClick={() => select(null)}>Back to all of {meta.country}</button>
              </p>
            </>
          ) : (
            <>
              <h2>All of {meta.country}</h2>
              <p className="sub">{fmt(base.cells.length)} hexagons with at least one detection</p>
            </>
          )}
        </div>

        <dl className="totals">
          {SERIES.map((s) => (
            <div key={s.key} className={s.key === series ? 'cur' : ''}>
              <dt>{s.label}</dt>
              <dd>{rows ? fmt(sum(rows, s.key), s.key === 'viirs_h' && sum(rows, s.key) < 100 ? 1 : 0) : '–'}</dd>
            </div>
          ))}
        </dl>

        <div className="cal">
          <h3>
            Daily {seriesInfo.label}
            <span>{rows ? `${activeDays} days with detections` : ''}</span>
          </h3>
          {rows ? (
            <CalendarChart
              year={meta.year}
              rows={rows}
              series={series}
              noDataDays={gaps}
              label={series === 'modis' ? 'MODIS Aqua detections' : series === 'viirs' ? 'VIIRS detections' : 'harmonized detections'}
            />
          ) : (
            <p className="loading">Loading hexagon…</p>
          )}
          {series !== 'modis' && (
            <p className="gapnote">
              <i /> No VIIRS data on {gaps.length} days ({gapRuns(gaps)}). These are satellite outages, not days without fire.
            </p>
          )}
        </div>

        <div className="weeks">
          <h3>Most active weeks</h3>
          {weeks.length ? (
            <ol>
              {weeks.map(([w, v]) => (
                <li key={w}>
                  <span className="wk">Week of {shortDate(w)}</span>
                  <span className="bar"><b style={{ width: `${(v / maxWeek) * 100}%` }} /></span>
                  <span className="val">{fmt(v, series === 'viirs_h' ? 1 : 0)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">No detections in this series.</p>
          )}
        </div>

        <details className="about">
          <summary>How the harmonization works</summary>
          <p>
            Where both satellites see fire in the same hexagon on the same day, MODIS Aqua reports
            {' '}{fmt(meta.harmonization.annual_factor, 2)} detections per VIIRS detection over the year. VIIRS counts are
            multiplied by a monthly version of this factor
            ({fmt(Math.min(...Object.values(meta.harmonization.factors)), 2)}–{fmt(Math.max(...Object.values(meta.harmonization.factors)), 2)}).
          </p>
          <p>
            The timing of burning matches MODIS closely, but harmonized totals are still about twice MODIS,
            because VIIRS also catches small fires MODIS misses. Read the calendar for <em>when</em> fires happen,
            not for exact counts.
          </p>
          <p className="muted">
            Data: {meta.sources.join(', ')}. Vegetation fires only, low-confidence detections removed,
            dates in UTC−6.
          </p>
        </details>
      </aside>
    </div>
  )
}
