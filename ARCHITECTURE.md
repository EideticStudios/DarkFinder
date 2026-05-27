# DarkFinder — Architecture & Plan

## 1. What This Project Is

DarkFinder is a clean, ad-free, open-source light pollution map. It renders NASA VIIRS satellite nighttime radiance data as a color-coded heat map overlay on an interactive web map, letting users explore light pollution levels anywhere on Earth.

The reference app is [lightpollutionmap.info](https://www.lightpollutionmap.info/). DarkFinder aims to replicate its core value — the heat map overlay — with a cleaner UX, no ads, and a transparent open-source codebase.

## 2. Data Source

### NASA Black Marble (VNP46A4)

The underlying data comes from NASA's VIIRS (Visible Infrared Imaging Radiometer Suite) Day/Night Band sensor aboard the Suomi NPP and NOAA-20 satellites. The Earth Observation Group at Colorado School of Mines publishes annual cloud-free composite GeoTIFFs derived from this data.

**Key facts:**
- Product: VNP46A4 (annual composite) — also available as VJ146A4 from NOAA-20
- Spatial resolution: 15 arc-seconds (~450m at equator)
- Coverage: 75°N to 65°S latitude
- Tiling: 6 tiles per year, cut at equator, each spanning 120° longitude
- Format: GeoTIFF
- Projection: Geographic (EPSG:4326), needs reprojection to EPSG:3857 for web maps
- License: **Public domain** — no restrictions on use or redistribution
- Available years: 2012–2024 (as of 2025)
- Download: https://eogdata.mines.edu/products/vnl/

The radiance values are in units of nW/cm²/sr (nanowatts per square centimeter per steradian). Values range from 0 (no detectable light) to several hundred in bright urban cores.

### Alternative / Phase 1 data: NASA GIBS

For rapid prototyping, NASA's Global Imagery Browse Services (GIBS) provides pre-rendered VIIRS Black Marble tiles via WMTS. These are a static 2016 composite with NASA's own color mapping (blue/yellow), not the Bortle-style heat map coloring, but they work immediately with no processing pipeline.

**GIBS tile URL (EPSG:3857 / Web Mercator):**
```
https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png
```

This is a WMTS endpoint but the URL pattern is compatible with XYZ tile consumers like MapLibre if you swap `{TileRow}` → `{y}` and `{TileCol}` → `{x}`. Max zoom level is 8 (~600m/px).

## 3. Architecture

### Frontend (React + TypeScript + Vite)

The frontend is a single-page app with one primary view: a full-viewport map.

**Map library: MapLibre GL JS**
- Open-source fork of Mapbox GL JS (BSD license)
- WebGL-accelerated, smooth tile rendering
- No API key required
- npm package: `maplibre-gl`
- React bindings: `react-map-gl` (supports MapLibre via the `mapLib` prop)

**Base map: Carto Dark Matter**
- Free, no API key (fair use policy)
- Raster tile URL: `https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`
- Dark background is ideal for light pollution overlays
- Alternative: MapTiler Dark (requires free API key, better vector quality)

**Overlay rendering:**
The light pollution layer is a standard raster tile layer added on top of the basemap with partial opacity (50–70%). MapLibre's `addSource` + `addLayer` API handles this natively:
```ts
map.addSource('light-pollution', {
  type: 'raster',
  tiles: ['https://your-backend.com/api/v1/tiles/{year}/{z}/{x}/{y}.png'],
  tileSize: 256,
  attribution: 'NASA Black Marble VNP46A4 / EOG Colorado School of Mines'
});

map.addLayer({
  id: 'light-pollution-layer',
  type: 'raster',
  source: 'light-pollution',
  paint: { 'raster-opacity': 0.6 }
});
```

**UI components:**
- `Map` — full-viewport MapLibre instance
- `BortleLegend` — color ramp legend (bottom-left or bottom-right)
- `YearSelector` — dropdown or slider for year selection (2012–2024)
- `InfoPanel` — shows radiance / Bortle class on click
- `SearchBar` — geocoding / place search (use Nominatim, free)
- `Header` — minimal top bar with title and about link

### Backend (Python + FastAPI)

The backend has two responsibilities: serve tiles and answer point queries.

**Tile serving:**
In production, the tile pyramid is pre-generated as static PNG files and can be served by any static file server (nginx, Caddy, S3, Cloudflare R2). FastAPI acts as the dev/staging tile server and the API for point queries.

**Endpoints:**
```
GET /api/v1/tiles/{year}/{z}/{x}/{y}.png
  → Returns a 256x256 PNG tile from the pre-generated pyramid
  → 404 if tile doesn't exist (ocean, out of bounds)
  → Cache-Control: public, max-age=31536000 (immutable data)

GET /api/v1/radiance?lat={lat}&lng={lng}&year={year}
  → Returns JSON: { radiance: float, bortle: int, sqm: float, year: int }
  → Reads directly from the source GeoTIFF via rasterio
  → No pre-processing needed, just a point sample

GET /api/v1/years
  → Returns JSON: { years: [2012, 2013, ..., 2024] }
  → Lists available processed years

GET /api/v1/health
  → Returns JSON: { status: "ok" }
```

### Data Pipeline (Python scripts)

The pipeline is a set of CLI scripts in `backend/app/pipeline/` that download and process the data. These are run manually (or via Makefile) before deploying — they are not part of the running application.

**Pipeline steps:**

1. **Download** (`download.py`)
   - Fetch VNP46A4 annual GeoTIFFs from EOG
   - Resumable downloads (check Content-Length, use Range headers)
   - Store in `backend/data/raw/{year}/`
   - ~2-3 GB per year (6 tiles)

2. **Mosaic → COG** (`mosaic.py`)
   - Merge 6 tiles into a single global raster
   - Build GDAL overview levels (for fast access at each zoom)
   - Save as a Cloud-Optimized GeoTIFF (COG), single-band float32, EPSG:4326
   - Output: `backend/data/processed/{year}_cog.tif` (~3–5 GB)

There is no reprojection, colorization, or tile-pyramid generation step. Reprojection to EPSG:3857 and the radiance → RGBA color ramp are applied per-tile at serve time by rio-tiler reading the COG.

## 4. Data Flow

```
User loads map → MapLibre requests tile → FastAPI + rio-tiler reads COG window → colorizes → serves PNG
User clicks map → Frontend sends lat/lng → FastAPI samples GeoTIFF → returns radiance JSON
User changes year → Frontend swaps tile source URL → new tiles load
```

## 5. Key Design Decisions

**Why MapLibre over Leaflet?**
MapLibre is WebGL-accelerated, handles raster tile overlays smoothly, and supports vector basemaps for future enhancement. Leaflet would work fine for an MVP but MapLibre handles the use case better at scale.

**Why COG + on-the-fly rendering over pre-generated tiles?**
A Cloud-Optimized GeoTIFF stores internal tile overviews so that rio-tiler can fetch only the spatial window needed for a given XYZ tile, without reading the whole file. This eliminates two large intermediate files from the pipeline (a reprojected EPSG:3857 raster and a colorized RGBA raster) and keeps the color ramp as a runtime config rather than pixels baked into thousands of PNGs. With `Cache-Control: immutable` headers (or a CDN), popular tiles are cached after the first render; since the data only changes once a year, the cache hit rate is high. The tradeoff is a running Python process in production, which the FastAPI backend already provides.

**Why FastAPI over Flask/Django?**
FastAPI is the modern Python web framework with built-in OpenAPI docs, async support, and type validation via Pydantic. It's a better fit than Flask and far less overhead than Django for an API-only backend.

**Why not use Google Earth Engine?**
GEE would add authentication complexity (OAuth, API keys) and a dependency on Google's platform. Downloading and processing the data yourself is more work but demonstrates deeper engineering capability and keeps the app self-contained.

**Why Carto Dark Matter?**
It's free with no API key, has a dark aesthetic that naturally complements a light pollution overlay, and the attribution requirements are minimal (link to Carto + OSM). Not having a paywall or key management simplifies setup and deployment.

## 6. Deployment Considerations

The simplest deployment:

- **Frontend:** Vercel or Netlify (free tier, auto-deploys from GitHub)
- **Backend API:** Fly.io or Railway (free/cheap tier, runs FastAPI)
- **COG files:** Cloudflare R2 (free egress, S3-compatible) — rio-tiler can read COGs directly from R2 via HTTPS range requests, so no need to copy them to the backend instance

The COG files are the heaviest asset (~3–5 GB per year). For an initial deployment, one or two years is sufficient.

## 7. License

The project code should be MIT licensed. The data is public domain (EOG/Colorado School of Mines). Attribution to NASA and EOG is required by scientific convention but not legally mandated.
