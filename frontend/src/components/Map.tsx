import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import styles from './Map.module.css'

const CARTO_DARK_TILES = ['https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png']
const API_BASE = 'http://localhost:8000/api/v1'

// Fallback: NASA GIBS pre-rendered Black Marble tiles (no backend required)
const GIBS_TILES = [
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png',
]

const TILE_VERSION = 2

function tileUrl(year: number): string {
  return `${API_BASE}/tiles/${year}/{z}/{x}/{y}.png?v=${TILE_VERSION}`
}

interface MapProps {
  year: number
  hasData: boolean
}

export default function Map({ year, hasData }: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)

  // Initialize map once — hasData is already resolved before this mounts
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          'carto-dark': {
            type: 'raster',
            tiles: CARTO_DARK_TILES,
            tileSize: 256,
            attribution:
              '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          },
          viirs: {
            type: 'raster',
            tiles: hasData ? [tileUrl(year)] : GIBS_TILES,
            tileSize: 256,
            maxzoom: 8,
            attribution: 'NASA Black Marble VIIRS &copy; NASA / EOG',
          },
        },
        layers: [
          { id: 'carto-dark', type: 'raster', source: 'carto-dark' },
          {
            id: 'viirs-overlay',
            type: 'raster',
            source: 'viirs',
            paint: { 'raster-opacity': 0.85 },
          },
        ],
      },
      center: [-95, 38],
      zoom: 3,
      minZoom: 3,
      maxBounds: [[-175, 5], [-40, 75]],
    })

    map.addControl(new maplibregl.NavigationControl(), 'top-right')

    const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false })

    map.on('click', async (e) => {
      const { lat, lng } = e.lngLat

      let html = `<strong>${lat.toFixed(4)}°, ${lng.toFixed(4)}°</strong><br/>`

      try {
        const resp = await fetch(
          `${API_BASE}/radiance?lat=${lat}&lng=${lng}&year=${year}`
        )
        if (resp.ok) {
          const data = await resp.json()
          html +=
            `Bortle class: <strong>${data.bortle}</strong><br/>` +
            `SQM: ${data.sqm} mag/arcsec²<br/>` +
            `Radiance: ${data.radiance} nW/cm²/sr`
        }
      } catch {
        // backend not available — show coords only
      }

      popup.setLngLat(e.lngLat).setHTML(html).addTo(map)
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Update tile source when year changes
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const updateSource = () => {
      const source = map.getSource('viirs') as maplibregl.RasterTileSource | undefined
      if (!source) return

      const newTiles = hasData ? [tileUrl(year)] : GIBS_TILES
      source.setTiles(newTiles)
    }

    if (map.isStyleLoaded()) {
      updateSource()
    } else {
      map.once('load', updateSource)
      return () => { map.off('load', updateSource) }
    }
  }, [year, hasData])

  return <div ref={containerRef} className={styles.container} />
}
