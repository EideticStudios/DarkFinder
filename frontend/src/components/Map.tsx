import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { LayerId } from '../lib/layers'
import { API_BASE } from '../lib/api'
import styles from './Map.module.css'

const CARTO_DARK_BASE_TILES = ['https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png']
const CARTO_DARK_LABEL_TILES = ['https://basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png']

// Fallback: NASA GIBS pre-rendered Black Marble tiles (no backend required)
const GIBS_TILES = [
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png',
]

const TILE_VERSION = 7

function tileUrl(layer: LayerId): string {
  return `${API_BASE}/tiles/${layer}/{z}/{x}/{y}.png?v=${TILE_VERSION}`
}

interface MapProps {
  layer: LayerId
  hasData: boolean
}

export default function Map({ layer, hasData }: MapProps) {
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
          'carto-dark-base': {
            type: 'raster',
            tiles: CARTO_DARK_BASE_TILES,
            tileSize: 256,
            attribution:
              '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          },
          viirs: {
            type: 'raster',
            tiles: hasData ? [tileUrl(layer)] : GIBS_TILES,
            tileSize: 256,
            maxzoom: hasData ? 13 : 8,
            attribution: 'NASA Black Marble VIIRS &copy; NASA / EOG',
          },
          'carto-dark-labels': {
            type: 'raster',
            tiles: CARTO_DARK_LABEL_TILES,
            tileSize: 256,
          },
        },
        layers: [
          { id: 'carto-dark-base', type: 'raster', source: 'carto-dark-base' },
          {
            id: 'viirs-overlay',
            type: 'raster',
            source: 'viirs',
            paint: { 'raster-opacity': layer === 'skyglow' ? 0.78 : 0.85 },
          },
          { id: 'carto-dark-labels', type: 'raster', source: 'carto-dark-labels' },
        ],
      },
      center: [-95, 38],
      zoom: 3,
      minZoom: 2,
      attributionControl: false,
    })

    map.addControl(new maplibregl.NavigationControl(), 'top-right')

    const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false })

    map.on('click', async (e) => {
      const { lat, lng } = e.lngLat

      let html = `<strong>${lat.toFixed(4)}°, ${lng.toFixed(4)}°</strong><br/>`

      try {
        const resp = await fetch(`${API_BASE}/radiance?lat=${lat}&lng=${lng}`)
        if (resp.ok) {
          const data = await resp.json()
          html +=
            `Bortle class: <strong>${data.bortle}</strong><br/>` +
            `SQM: ${data.sqm} mag/arcsec²<br/>` +
            `Radiance: ${data.radiance} nW/cm²/sr`
          if (data.skyglow != null) {
            html += `<br/>Sky glow: ${data.skyglow} nW/cm²/sr`
          }
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

  // Update tile source and opacity when the layer changes
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const updateSource = () => {
      const source = map.getSource('viirs') as maplibregl.RasterTileSource | undefined
      if (!source) return

      const newTiles = hasData ? [tileUrl(layer)] : GIBS_TILES
      source.setTiles(newTiles)
      map.setPaintProperty('viirs-overlay', 'raster-opacity', layer === 'skyglow' ? 0.78 : 0.85)
    }

    if (map.isStyleLoaded()) {
      updateSource()
    } else {
      map.once('load', updateSource)
      return () => { map.off('load', updateSource) }
    }
  }, [layer, hasData])

  return <div ref={containerRef} className={styles.container} />
}
