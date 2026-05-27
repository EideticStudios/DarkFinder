# DarkFinder — Implementation Plan

This document breaks the project into concrete, shippable phases. Each phase produces a working app. Don't skip phases — each one builds on the last.

---

## Phase 1: Map with GIBS Overlay (Frontend Only)

**Goal:** A working light pollution map in the browser with no backend.

**What you're building:**
A React SPA that renders a MapLibre map with a dark basemap and a NASA GIBS nighttime lights tile overlay.

**Tasks:**

1. Scaffold the frontend:
   ```bash
   cd frontend
   npm create vite@latest . -- --template react-ts
   npm install maplibre-gl react-map-gl
   ```

2. Create the `Map` component:
   - Full-viewport MapLibre instance
   - Carto Dark Matter basemap
   - GIBS `VIIRS_Black_Marble` raster tile overlay at 60% opacity
   - Basic zoom/pan controls

3. Create the `BortleLegend` component:
   - Static color ramp legend positioned bottom-right
   - Labels for each Bortle class (1–9)
   - Semi-transparent dark background panel

4. Wire up a click handler:
   - On map click, show a popup with the lat/lng coordinates
   - (No radiance query yet — just coordinates)

5. Add a minimal header with the project name and a GitHub link.

**Deliverable:** A deployable static site you can push to Vercel/Netlify. The GIBS overlay is the "heat map" — it's not custom-colored yet, but it proves the map rendering pipeline works.

**Estimated effort:** 3–5 hours.

---

## Phase 2: Data Pipeline

**Goal:** Download VIIRS data and process it into a Cloud-Optimized GeoTIFF (COG).

**What you're building:**
A set of Python CLI scripts that download raw NASA data and produce one COG per year. The COG is the only processed artifact — colorization and reprojection happen at serve time.

**Tasks:**

1. Set up the backend Python project:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install rasterio numpy requests click rio-cogeo
   ```

2. Write `pipeline/download.py`:
   - Accept a year argument (e.g., `--year 2023`)
   - Download VNP46A4 annual composite GeoTIFFs from EOG
   - URL pattern: `https://eogdata.mines.edu/nighttime_light/annual/v22/{year}/`
   - The "vcm-orm-ntl" variant is the one you want (outlier-removed, background zeroed)
   - Save to `data/raw/{year}/`
   - Implement resume capability (check file size before re-downloading)

3. Write `pipeline/mosaic.py`:
   - Merge the 6 tiles into a single raster using rasterio
   - Build GDAL overviews with `gdaladdo -r bilinear`
   - Convert to COG with `gdal_translate -of COG -co COMPRESS=DEFLATE -co PREDICTOR=3`
   - Output: `data/processed/{year}_cog.tif` (float32, EPSG:4326, ~3–5 GB)
   - Validate with `rio cogeo validate data/processed/{year}_cog.tif`

4. Create a `Makefile` or `justfile` with targets:
   ```makefile
   download-2023:
       python -m app.pipeline.download --year 2023

   process-2023: download-2023
       python -m app.pipeline.mosaic --year 2023
   ```

**Deliverable:** A `data/processed/2023_cog.tif` you can inspect in QGIS and validate with `rio cogeo validate`. The raw radiance values are preserved and ready for the tile server to colorize on demand.

**Estimated effort:** 8–15 hours (mostly fighting rasterio/GDAL quirks).

---

## Phase 3: Tile Server + Custom Overlay

**Goal:** Serve your custom tiles from FastAPI and swap the frontend to use them.

**Tasks:**

1. Set up FastAPI and tile renderer:
   ```bash
   pip install fastapi uvicorn rio-tiler pillow
   ```

2. Write `app/main.py`:
   - Mount a static files directory for tiles
   - Add CORS middleware (allow `localhost:5173`)
   - Add health check endpoint

3. Write `app/routers/tiles.py` and `app/services/tile_renderer.py`:
   - `GET /api/v1/tiles/{year}/{z}/{x}/{y}.png`
   - Use rio-tiler to read the COG for that year, render the 256×256 tile window, apply the Bortle color ramp
   - Return 404 if the tile is outside the COG extent (`TileOutsideBounds`)
   - Set `Cache-Control: public, max-age=31536000, immutable`

4. Write `app/routers/radiance.py`:
   - `GET /api/v1/radiance?lat={lat}&lng={lng}&year={year}`
   - Open the source GeoTIFF with rasterio
   - Sample the pixel at the given coordinates
   - Return `{ radiance, bortle, sqm_estimate, year }`
   - Cache the rasterio dataset handle (don't re-open on every request)

5. Write `app/routers/years.py`:
   - `GET /api/v1/years`
   - Scan `data/processed/` for `{year}_cog.tif` files
   - Return sorted list of available years

6. Update the frontend:
   - Swap the GIBS tile URL for `http://localhost:8000/api/v1/tiles/{year}/{z}/{x}/{y}.png`
   - Add a `YearSelector` component (dropdown)
   - On year change, update the tile source URL and reload the layer

7. Update the click handler:
   - On map click, call `/api/v1/radiance?lat=...&lng=...&year=...`
   - Display radiance value, Bortle class, and SQM estimate in the popup

**Deliverable:** A fully working local dev setup where the frontend talks to the FastAPI backend, rendering your custom-colored tiles and providing point queries.

**Estimated effort:** 5–8 hours.

---

## Phase 4: Polish & Launch

**Goal:** Make it look great, deploy it, write the README.

**Tasks:**

1. **Search bar:**
   - Add geocoding via Nominatim (OpenStreetMap's free geocoding API)
   - `https://nominatim.openstreetmap.org/search?q={query}&format=json`
   - Rate limit to 1 req/sec per Nominatim's usage policy
   - On result select, fly the map to that location

2. **Geolocation:**
   - "Find my location" button using the browser Geolocation API
   - Fly to user's position and show their Bortle class

3. **"Find darkest sky near me" (stretch):**
   - Given user's location, search outward for the nearest tile below a radiance threshold
   - This is a fun feature that's hard to find elsewhere

4. **Responsive design:**
   - Collapse legend/controls into a bottom sheet or hamburger on mobile
   - Touch-friendly map interaction (MapLibre handles this natively)

5. **README.md:**
   - Clear project description with a screenshot/GIF
   - Live demo link
   - Local dev setup instructions
   - Architecture overview (link to docs/)
   - Data attribution
   - License

6. **Deploy:**
   - Frontend → Vercel or Netlify
   - Backend → Fly.io (Dockerfile)
   - COG files → Cloudflare R2 (rio-tiler reads them via HTTPS range requests; no need to copy to the instance)

7. **CI:**
   - GitHub Actions workflow for lint + typecheck (frontend)
   - GitHub Actions workflow for ruff + mypy (backend)

**Estimated effort:** 8–12 hours.

---

## Phase 5 (Optional): Advanced Features

These are nice-to-haves that further differentiate the project:

- **Year-over-year comparison:** Side-by-side or swipe slider showing two years
- **Trend overlay:** Show areas where light pollution increased/decreased (diff of two years)
- **Dark Sky Parks:** Overlay International Dark-Sky Association certified locations
- **Observatory locations:** Overlay IAU observatory positions
- **Time-lapse animation:** Animate through years 2012–2024
- **Bortle sky simulation:** On click, show a simulated sky view at that Bortle level (what the stars actually look like)

---

## Dependency Summary

### Frontend (package.json)
```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "maplibre-gl": "^4.0.0",
    "react-map-gl": "^7.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "@vitejs/plugin-react": "^4.0.0"
  }
}
```

### Backend (requirements.txt)
```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
rasterio>=1.4.0
numpy>=2.0.0
rio-tiler>=7.0.0
click>=8.1.0
requests>=2.32.0
pyproj>=3.7.0
pydantic>=2.10.0
```
