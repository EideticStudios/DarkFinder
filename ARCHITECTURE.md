# DarkFinder — Architecture & Plan

## 1. What This Project Is

DarkFinder is a clean, ad-free, open-source light pollution map. It renders NASA VIIRS satellite nighttime radiance data as a color-coded heat map overlay on an interactive web map, letting users explore light pollution levels anywhere on Earth.

The reference app is [lightpollutionmap.info](https://www.lightpollutionmap.info/). DarkFinder aims to replicate its core value — the heat map overlay — with a cleaner UX, no ads, and a transparent open-source codebase.

## 2. Data Source

### VIIRS Nighttime Lights (VNL V2.2) via Google Earth Engine

The underlying data comes from NASA's VIIRS (Visible Infrared Imaging Radiometer Suite) Day/Night Band sensor aboard the Suomi NPP and NOAA-20 satellites. The Earth Observation Group (EOG) at Colorado School of Mines produces annual cloud-free composite products from this data. DarkFinder accesses these composites through Google Earth Engine's public catalog.

**Key facts:**
- GEE collection: `NOAA/VIIRS/DNB/ANNUAL_V22`
- Band: `average_masked` (background zeroed, outliers removed)
- Spatial resolution: 15 arc-seconds (~450m at equator)
- Coverage: 75N to 65S latitude
- Format: GeoTIFF (downloaded via geemap)
- Projection: Geographic (EPSG:4326)
- License: **Public domain** (Colorado School of Mines / EOG)
- Available years: 2014-2023 (as of 2025)
- Authentication: `earthengine authenticate` (one-time, no API keys or credentials needed in .env)

The radiance values are in units of nW/cm2/sr (nanowatts per square centimeter per steradian). Values range from 0 (no detectable light) to several hundred in bright urban cores.

## 3. Architecture

### Frontend (React + TypeScript + Vite)

The frontend is a single-page app with one primary view: a full-viewport map.

**Map library: MapLibre GL JS**
- Open-source fork of Mapbox GL JS (BSD license)
- WebGL-accelerated, smooth tile rendering
- No API key required
- npm package: `maplibre-gl`
- Used directly via its imperative API (`map.addSource` / `map.addLayer`) inside a
  custom React `Map` component — there is no `react-map-gl` wrapper dependency

**Base map: Carto Dark Matter**
- Free, no API key (fair use policy)
- Raster tile URL: `https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`
- Dark background is ideal for light pollution overlays
- Alternative: MapTiler Dark (requires free API key, better vector quality)

**Overlay rendering:**
The light pollution layer is a standard raster tile layer added on top of the basemap with partial opacity (50-70%). MapLibre's `addSource` + `addLayer` API handles this natively:
```ts
map.addSource('light-pollution', {
  type: 'raster',
  tiles: ['https://your-backend.com/api/v1/tiles/{layer}/{z}/{x}/{y}.png'],
  tileSize: 256,
  attribution: 'VIIRS VNL V2.2 / EOG Colorado School of Mines via GEE'
});

map.addLayer({
  id: 'light-pollution-layer',
  type: 'raster',
  source: 'light-pollution',
  paint: { 'raster-opacity': 0.6 }
});
```

**UI components:**
- `Map` — full-viewport MapLibre instance; a click opens a popup with the sampled radiance
- `LayerToggle` — switches between the Sky Glow and Emission layers (Sky Glow is the default)
- `BortleLegend` — Bortle color-ramp legend, shown for the Sky Glow layer
- `EmissionLegend` — color-ramp legend, shown for the Emission layer
- `IntroModal` — first-visit intro overlay (dismissal remembered in localStorage)
- `AboutModal` — about / methodology panel, opened from the header "Info" button
- `Footer` — minimal bottom bar with attribution

The top bar itself is inline markup in `App.tsx` (title, `LayerToggle`, Info button)
rather than a dedicated component.

### Backend (Python + FastAPI)

The backend has three responsibilities: serve tiles, answer point queries, and report
which layers are available for the frontend to bootstrap against.

**Tile serving:**
Tiles are rendered on-the-fly from Cloud-Optimized GeoTIFFs (COGs) using rio-tiler. FastAPI acts as the tile server and the API for point queries.

**Endpoints:**
```
GET /api/v1/tiles/{layer}/{z}/{x}/{y}.png
  -> layer is "emission" or "skyglow"
  -> Returns a 256x256 PNG tile rendered on the fly from that layer's COG
  -> 404 if the tile falls outside the data bounds (ocean, out of bounds)
     or no COG is available for the layer
  -> Cache-Control: public, max-age=3600

GET /api/v1/radiance?lat={lat}&lng={lng}
  -> Returns JSON: { radiance: float, bortle: int, sqm: float, skyglow: float | null }
  -> Samples the emission COG via rasterio; also samples the sky-glow COG when one
     is present (used for the SQM estimate, a better proxy than point emission)
  -> 422 if lat/lng are out of range

GET /api/v1/layers
  -> Returns JSON: { emission: bool, skyglow: bool }
  -> Reports which layers have a processed COG available, for frontend bootstrap

GET /api/v1/health
  -> Returns JSON: { status: "ok" }
```

The serving layer is single-year: it auto-discovers the newest processed COG for each
layer. Year is only a pipeline/build concept and never appears in the served API.

### Data Pipeline (Python scripts)

The pipeline is a set of CLI scripts in `backend/app/pipeline/` that download and process the data. These are run manually (or via Makefile) before deploying — they are not part of the running application.

**Pipeline steps:**

1. **Download** (`download.py`)
   - Fetch VNL V2.2 annual composite from GEE (`NOAA/VIIRS/DNB/ANNUAL_V22`)
   - Uses `geemap.download_ee_image()` with configurable bounding box
   - Store in `backend/data/raw/{year}/`
   - Data arrives in EPSG:4326 — no reprojection needed

2. **Mosaic -> COG** (`mosaic.py`)
   - If multiple files, merge into a single raster
   - Build GDAL overview levels (for fast access at each zoom)
   - Save as a Cloud-Optimized GeoTIFF (COG), single-band float32, EPSG:4326
   - Output: `backend/data/processed/{year}_cog.tif`

3. **Sky Glow** (`skyglow.py`)
   - Models where emitted light ends up by propagating each source outward ~100 km
   - Convolves the emission raster with a Falchi/Garstang distance-falloff kernel
     (FFT-based, run in latitude bands so the kernel stays physically correct toward
     the poles)
   - Output: `backend/data/processed/{year}_skyglow_cog.tif` — same grid/format as
     the emission COG. This is the app's default layer.

There is no reprojection or tile-pyramid generation step. Reprojection to EPSG:3857 and
the radiance -> RGBA color ramp are applied per-tile at serve time by rio-tiler reading
the COG. Colorization is likewise a serve-time step, not baked into the COGs. See
`DATA_PIPELINE.md` for the full processing reference (including the optional `validate.py`
data-quality check).

## 4. Data Flow

```
User loads map -> MapLibre requests tile -> FastAPI + rio-tiler reads COG window -> colorizes -> serves PNG
User clicks map -> Frontend sends lat/lng -> FastAPI samples GeoTIFF -> returns radiance JSON
User toggles layer -> Frontend swaps the tile source's {layer} URL -> new tiles load
```

## 5. Key Design Decisions

**Why MapLibre over Leaflet?**
MapLibre is WebGL-accelerated, handles raster tile overlays smoothly, and supports vector basemaps for future enhancement. Leaflet would work fine for an MVP but MapLibre handles the use case better at scale.

**Why COG + on-the-fly rendering over pre-generated tiles?**
A Cloud-Optimized GeoTIFF stores internal tile overviews so that rio-tiler can fetch only the spatial window needed for a given XYZ tile, without reading the whole file. This eliminates two large intermediate files from the pipeline (a reprojected EPSG:3857 raster and a colorized RGBA raster) and keeps the color ramp as a runtime config rather than pixels baked into thousands of PNGs. With cache headers (`Cache-Control: public, max-age=3600`) or a CDN in front, popular tiles are cached after the first render; since the data only changes once a year, the cache hit rate is high. The tradeoff is a running Python process in production, which the FastAPI backend already provides.

**Why FastAPI over Flask/Django?**
FastAPI is the modern Python web framework with built-in OpenAPI docs, async support, and type validation via Pydantic. It's a better fit than Flask and far less overhead than Django for an API-only backend.

**Why Google Earth Engine?**
GEE hosts the same EOG VNL V2.2 data in a public catalog with no credential wall. Authentication is a one-time `earthengine authenticate` command. The `geemap` library handles tiled downloads for large regions automatically.

**Why Carto Dark Matter?**
It's free with no API key, has a dark aesthetic that naturally complements a light pollution overlay, and the attribution requirements are minimal (link to Carto + OSM). Not having a paywall or key management simplifies setup and deployment.

## 6. Deployment Considerations

The simplest deployment:

- **Frontend:** Vercel or Netlify (free tier, auto-deploys from GitHub)
- **Backend API:** Fly.io or Railway (free/cheap tier, runs FastAPI)
- **COG files:** Cloudflare R2 (free egress, S3-compatible) — rio-tiler can read COGs directly from R2 via HTTPS range requests, so no need to copy them to the backend instance

The COG files are the heaviest asset (~3-5 GB per year). For an initial deployment, one or two years is sufficient.

## 7. License

The project code should be MIT licensed. The data is public domain (EOG/Colorado School of Mines, accessed via Google Earth Engine). Attribution to NASA, EOG, and GEE is appreciated but not legally mandated.
