import { useMemo } from 'react'
import ReactEChartsCore from 'echarts-for-react/esm/core'
import * as echarts from 'echarts/core'
import { HeatmapChart } from 'echarts/charts'
import { CalendarComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { FIRE, fmt, fmtBreak, niceBreaks, type DayRow, type SeriesKey } from './data'

echarts.use([HeatmapChart, CalendarComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

const NONE = '#e7ebea'
const FONT = "'Public Sans', system-ui, sans-serif"
const NO_DATA = '#9aa5a8'
// Gap days are encoded as -1 so a single heatmap series (and one visualMap)
// covers every day: ECharts requires a visualMap for each heatmap series.
const GAP = -1

interface Props {
  year: number
  rows: DayRow[]
  series: SeriesKey
  noDataDays: string[]
  label: string
}

export default function CalendarChart({ year, rows, series, noDataDays, label }: Props) {
  const { option, pieces } = useMemo(() => {
    const gaps = series === 'modis' ? new Set<string>() : new Set(noDataDays)
    const byDate = new Map(rows.map((r) => [r.date, r[series]]))
    const values: [string, number][] = []
    const day = new Date(Date.UTC(year, 0, 1))
    while (day.getUTCFullYear() === year) {
      const d = day.toISOString().slice(0, 10)
      values.push([d, gaps.has(d) ? GAP : byDate.get(d) ?? 0])
      day.setUTCDate(day.getUTCDate() + 1)
    }
    const breaks = niceBreaks(values.map((v) => v[1]), 5)
    const digits = series === 'viirs_h' ? 1 : 0
    const pieces = [
      ...(gaps.size ? [{ value: GAP, color: NO_DATA, label: 'No data' }] : []),
      { min: 0, max: 0, color: NONE, label: 'None' },
      ...breaks.map((b, i) => ({
        gt: i === 0 ? 0 : breaks[i - 1],
        lte: b,
        color: FIRE[i],
        label: i === 0 ? `≤ ${fmtBreak(b)}` : `${fmtBreak(breaks[i - 1])}–${fmtBreak(b)}`,
      })),
      ...(breaks.length
        ? [{ gt: breaks[breaks.length - 1], color: FIRE[breaks.length], label: `> ${fmtBreak(breaks[breaks.length - 1])}` }]
        : []),
    ]

    const option = {
      animation: false,
      tooltip: {
        formatter: (p: { value: [string, number] }) => {
          const date = new Date(p.value[0] + 'T12:00:00Z').toLocaleDateString('en-US', {
            weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC',
          })
          return p.value[1] === GAP
            ? `${date}<br><strong>No VIIRS data</strong> (satellite outage)`
            : `${date}<br><strong>${fmt(p.value[1], digits)}</strong> ${label}`
        },
      },
      visualMap: { type: 'piecewise', seriesIndex: 0, pieces, show: false },
      calendar: {
        range: String(year),
        orient: 'horizontal',
        top: 22,
        left: 28,
        right: 4,
        cellSize: ['auto', 13],
        splitLine: { show: true, lineStyle: { color: '#ffffff', width: 2 } },
        itemStyle: { color: NONE, borderColor: '#ffffff', borderWidth: 1.5 },
        yearLabel: { show: false },
        dayLabel: { firstDay: 1, nameMap: ['S', 'M', 'T', 'W', 'T', 'F', 'S'], color: '#6b777c', fontSize: 10, fontFamily: FONT },
        monthLabel: { color: '#33403f', fontSize: 11, fontFamily: FONT, fontWeight: 600 },
      },
      series: [
        { type: 'heatmap', coordinateSystem: 'calendar', data: values },
      ],
    }
    return { option, pieces }
  }, [year, rows, series, noDataDays, label])

  return (
    <>
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        notMerge
        style={{ height: 136, width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
      <ul className="cal-legend" aria-label="Color scale">
        {pieces.map((p) => (
          <li key={p.label}>
            <i style={{ background: p.color }} />
            {p.label}
          </li>
        ))}
      </ul>
    </>
  )
}
