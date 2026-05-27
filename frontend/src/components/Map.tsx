import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import styles from './Map.module.css'

const CARTO_DARK_TILES = ['https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png']

// GIBS WMTS uses {TileMatrix}/{TileRow}/{TileCol} — MapLibre substitutes {z}/{y}/{x} correctly
const GIBS_VIIRS_TILES = [
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png',
]

export default function Map() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)

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
            attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          },
          'viirs': {
            type: 'raster',
            tiles: GIBS_VIIRS_TILES,
            tileSize: 256,
            maxzoom: 8,
            attribution: 'NASA Black Marble VIIRS &copy; NASA',
          },
        },
        layers: [
          {
            id: 'carto-dark',
            type: 'raster',
            source: 'carto-dark',
          },
          {
            id: 'viirs-overlay',
            type: 'raster',
            source: 'viirs',
            paint: {
              'raster-opacity': 0.6,
            },
          },
        ],
      },
      center: [0, 20],
      zoom: 2,
    })

    map.addControl(new maplibregl.NavigationControl(), 'top-right')

    map.on('error', (e) => console.error('[MapLibre error]', e.error))
    map.on('load', () => {
      console.log('[MapLibre] style loaded, sources:', Object.keys(map.getStyle().sources))
    })

    const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false })

    map.on('click', (e) => {
      const { lat, lng } = e.lngLat
      popup
        .setLngLat(e.lngLat)
        .setHTML(
          `<strong>Coordinates</strong><br/>` +
          `Lat: ${lat.toFixed(5)}<br/>` +
          `Lng: ${lng.toFixed(5)}`
        )
        .addTo(map)
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  return <div ref={containerRef} className={styles.container} />
}
