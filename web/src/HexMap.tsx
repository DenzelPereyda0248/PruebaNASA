import { useMemo } from 'react'
import { GeoJSON, MapContainer, TileLayer } from 'react-leaflet'
import { cellToBoundary } from 'h3-js'
import type { Feature, FeatureCollection, Polygon } from 'geojson'
import type { Layer, LeafletMouseEvent, PathOptions } from 'leaflet'
import { FIRE, fmt, type CellTotal } from './data'

const MEXICO_BOUNDS: [[number, number], [number, number]] = [[14.4, -117.4], [32.8, -86.6]]

// Fixed breaks on the yearly harmonized total per cell (MODIS Aqua equivalent).
export const MAP_BREAKS = [1, 5, 10, 25, 50, 100]

export function colorFor(v: number): string {
  let i = 0
  while (i < MAP_BREAKS.length && v >= MAP_BREAKS[i]) i++
  return FIRE[i]
}

interface Props {
  cells: CellTotal[]
  selected: string | null
  onSelect: (h3: string | null) => void
}

type CellFeature = Feature<Polygon, CellTotal>

function toFeature(c: CellTotal): CellFeature {
  return {
    type: 'Feature',
    properties: c,
    geometry: { type: 'Polygon', coordinates: [cellToBoundary(c.h3, true)] },
  }
}

export default function HexMap({ cells, selected, onSelect }: Props) {
  const collection = useMemo<FeatureCollection<Polygon, CellTotal>>(
    () => ({ type: 'FeatureCollection', features: [...cells].reverse().map(toFeature) }),
    [cells],
  )
  const selectedFeature = useMemo(() => {
    const c = cells.find((x) => x.h3 === selected)
    return c ? toFeature(c) : null
  }, [cells, selected])

  const style = (f?: Feature): PathOptions => ({
    fillColor: colorFor((f?.properties as CellTotal).viirs_h),
    fillOpacity: 0.82,
    color: '#ffffff',
    weight: 0.4,
  })

  const onEach = (f: Feature, layer: Layer) => {
    const p = f.properties as CellTotal
    layer.bindTooltip(
      `<strong>${fmt(p.viirs_h, 1)}</strong> harmonized detections<br>` +
        `MODIS Aqua ${fmt(p.modis)} · VIIRS raw ${fmt(p.viirs)}`,
      { sticky: true, direction: 'top', className: 'hex-tip' },
    )
    layer.on('click', (e: LeafletMouseEvent) => {
      e.originalEvent.stopPropagation()
      onSelect(p.h3)
    })
  }

  return (
    <MapContainer
      bounds={MEXICO_BOUNDS}
      minZoom={3}
      maxZoom={10}
      preferCanvas
      className="map"
      worldCopyJump={false}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
        subdomains="abcd"
      />
      <GeoJSON data={collection} style={style} onEachFeature={onEach} />
      {selectedFeature && (
        <GeoJSON
          key={selectedFeature.properties.h3}
          data={selectedFeature}
          interactive={false}
          style={{ fill: false, color: '#123a63', weight: 3 }}
        />
      )}
    </MapContainer>
  )
}
