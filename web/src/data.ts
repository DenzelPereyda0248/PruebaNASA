// Types and loaders for the static JSON produced by `pipeline/export.py`.

export type SeriesKey = 'modis' | 'viirs' | 'viirs_h'

export interface DayRow {
  date: string
  modis: number
  viirs: number | null
  viirs_h: number | null
}

export interface CellTotal {
  h3: string
  modis: number
  viirs: number
  viirs_h: number
}

export interface Meta {
  country: string
  year: number
  h3_resolution: number
  generated_at: string
  filters: { type: number[]; modis_min_conf: number; viirs_conf: string[] }
  harmonization: {
    method: string
    factors: Record<string, number>
    annual_factor: number
    reference: { modis: string; viirs: string }
  }
  series: Record<SeriesKey, string>
  no_data_days: { modis: string[]; viirs: string[] }
  sources: string[]
}

export const SERIES: { key: SeriesKey; label: string; short: string }[] = [
  { key: 'modis', label: 'MODIS Aqua', short: 'MODIS' },
  { key: 'viirs', label: 'VIIRS raw', short: 'VIIRS raw' },
  { key: 'viirs_h', label: 'VIIRS harmonized', short: 'VIIRS harm.' },
]

const base = `${import.meta.env.BASE_URL}data/`

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(base + path)
  if (!res.ok) throw new Error(`Could not load ${path} (HTTP ${res.status})`)
  return res.json() as Promise<T>
}

export const loadMeta = () => getJson<Meta>('meta.json')
export const loadNational = () => getJson<DayRow[]>('national.json')
export const loadCells = () => getJson<CellTotal[]>('cells.json')

const cellCache = new Map<string, Promise<DayRow[]>>()
export function loadCell(h3: string): Promise<DayRow[]> {
  if (!cellCache.has(h3)) {
    const p = getJson<DayRow[]>(`cells/${h3}.json`)
    p.catch(() => cellCache.delete(h3))
    cellCache.set(h3, p)
  }
  return cellCache.get(h3)!
}

// Ember ramp shared by the map and the calendar (light straw -> char).
export const FIRE = ['#fbecc0', '#f8d27a', '#f5ae4a', '#ea7a2c', '#cf4a1d', '#9c2414', '#5a0f0f']

export const fmt = (v: number, digits = 0) =>
  v.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })

/** Legend label: integers stay integers, small breaks keep one decimal. */
export const fmtBreak = (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: v < 10 ? 1 : 0 })

/** Round a positive number to 1, 2 or 5 × 10^k for readable legend breaks. */
export function nice(v: number): number {
  if (v <= 0) return 0
  const p = 10 ** Math.floor(Math.log10(v))
  const m = v / p
  const step = m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10
  return step * p
}

/** Up to `n` increasing nice breaks from quantiles of the positive values. */
export function niceBreaks(values: number[], n: number): number[] {
  const pos = values.filter((v) => v > 0).sort((a, b) => a - b)
  if (!pos.length) return []
  const out: number[] = []
  for (let i = 1; i <= n; i++) {
    const q = pos[Math.min(pos.length - 1, Math.floor((i / (n + 1)) * pos.length))]
    const b = nice(q)
    if (b > 0 && (!out.length || b > out[out.length - 1])) out.push(b)
  }
  return out
}
