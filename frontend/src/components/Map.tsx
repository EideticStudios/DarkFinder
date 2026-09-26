import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { LayerId } from '../lib/layers'
import { API_BASE } from '../lib/api'
import styles from './Map.module.css'

// Carto Dark Matter, vector. Requires an API key since Carto's 2026-09-23 terms;
// without one every tile comes back stamped "API KEY REQUIRED". The key is appended
// by transformRequest below rather than baked into this URL, because it is also
// required on the glyph, sprite and vector-tile requests the style fans out to.
const CARTO_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const CARTO_KEY = import.meta.env.VITE_CARTO_KEY
const CARTO_HOST = 'basemaps.cartocdn.com'

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
  // Latest desired layer/hasData, readable from map event callbacks.
  const layerRef = useRef(layer)
  const hasDataRef = useRef(hasData)
  // Latches true on the map's first 'load' and stays true. We must NOT gate tile
  // updates on map.isStyleLoaded(), which flaps back to false whenever tiles are
  // still loading — a toggle during that window would otherwise be silently dropped.
  const styleReadyRef = useRef(false)
  // Imperative "apply the current layer to the viirs source" set up at init.
  const applyLayerRef = useRef<(() => void) | null>(null)
  const [loading, setLoading] = useState(false)

  // Initialize map once — hasData is already resolved before this mounts
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: CARTO_STYLE,
      // The style pulls tiles, glyphs and sprites from tiles*.basemaps.cartocdn.com
      // subdomains, and every one of them needs the key — so match on the host suffix
      // rather than adding it to each URL by hand.
      transformRequest: (url) =>
        CARTO_KEY && url.includes(CARTO_HOST)
          ? { url: `${url}${url.includes('?') ? '&' : '?'}key=${CARTO_KEY}` }
          : { url },
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

    // Push the currently-selected layer onto the viirs source. Reads the refs, so it
    // always applies the newest selection even if it was queued during a load.
    const applyLayer = () => {
      const source = map.getSource('viirs') as maplibregl.RasterTileSource | undefined
      if (!source) return
      const l = layerRef.current
      const newTiles = hasDataRef.current ? [tileUrl(l)] : GIBS_TILES
      source.setTiles(newTiles)
      map.setPaintProperty('viirs-overlay', 'raster-opacity', l === 'skyglow' ? 0.78 : 0.85)
    }
    applyLayerRef.current = applyLayer

    map.on('load', () => {
      // The basemap style is fetched remotely, so the overlay can only be added once
      // it has arrived. Insert it beneath the first symbol layer so place names keep
      // rendering above the VIIRS raster.
      map.addSource('viirs', {
        type: 'raster',
        tiles: hasDataRef.current ? [tileUrl(layerRef.current)] : GIBS_TILES,
        tileSize: 256,
        maxzoom: hasDataRef.current ? 13 : 8,
        attribution: 'NASA Black Marble VIIRS &copy; NASA / EOG',
      })
      const firstSymbolId = map.getStyle().layers?.find((l) => l.type === 'symbol')?.id
      map.addLayer(
        {
          id: 'viirs-overlay',
          type: 'raster',
          source: 'viirs',
          paint: { 'raster-opacity': layerRef.current === 'skyglow' ? 0.78 : 0.85 },
        },
        firstSymbolId,
      )
      // Latch ready and apply the latest selection in case it changed mid-load.
      styleReadyRef.current = true
      applyLayer()
    })
    // Loading feedback: the map is "busy" while any tiles are in flight.
    map.on('dataloading', () => setLoading(true))
    map.on('idle', () => setLoading(false))

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      applyLayerRef.current = null
      styleReadyRef.current = false
    }
  }, []) // init once; layer/hasData reach the callbacks via refs, never via deps

  // Apply layer/hasData changes. Update the refs first so both the immediate call and the
  // deferred 'load' handler see the newest selection. Once the style has loaded, setTiles
  // can be called at any time — so we gate on the latching styleReadyRef, never on
  // isStyleLoaded() (which flaps false while tiles load). If the style isn't ready yet, the
  // map's 'load' handler applies the latest ref values.
  useEffect(() => {
    layerRef.current = layer
    hasDataRef.current = hasData
    if (styleReadyRef.current) applyLayerRef.current?.()
  }, [layer, hasData])

  return (
    <div className={styles.wrapper}>
      <div ref={containerRef} className={styles.container} />
      {loading && (
        <div className={styles.loading} role="status" aria-label="Loading map data">
          <span className={styles.spinner} />
        </div>
      )}
    </div>
  )
}
