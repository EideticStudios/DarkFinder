# DarkFinder — Implementation Plan

This document breaks the project into concrete, shippable phases. Each phase produces a working app. Don't skip phases — each one builds on the last.

---

## Phase 1: Map with Base Overlay (Frontend Only) [DONE]

**Goal:** A working light pollution map in the browser with no backend.

**What was built:**
A React SPA that renders a MapLibre map with a dark basemap and a nighttime lights tile overlay.

**Tasks:**

1. Scaffold the frontend with Vite + React + TypeScript
2. Create the `Map` component with Carto Dark Matter basemap
3. Create the `BortleLegend` component
4. Wire up a click handler (lat/lng display)
5. Add a minimal header

**Deliverable:** A deployable static site on Vercel/Netlify.

---

## Phase 2: Data Pipeline [DONE]

**Goal:** Download VIIRS data from GEE and process it into a Cloud-Optimized GeoTIFF (COG).

**What was built:**
Python CLI scripts that download from Google Earth Engine and produce one COG per year.

**Tasks:**

1. Set up the backend Python project:
   ```bash
   cd backend
   uv venv .venv --python 3.12
   uv pip install -r requirements.txt --python .venv/bin/python
   ```

2. `pipeline/download.py` — Download from GEE:
   ```bash
   # One-time auth
   earthengine authenticate

   # Download
   make download YEAR=2023
   ```

3. `pipeline/mosaic.py` — Build COG:
   ```bash
   make process YEAR=2023
   ```

4. Makefile targets: `download`, `process`, `pipeline`, `validate`

**Deliverable:** A `data/processed/2023_cog.tif` you can inspect in QGIS and validate with `rio cogeo validate`.

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
   - Use rio-tiler to read the COG for that year, render the 256x256 tile window, apply the Bortle color ramp
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
   - Swap the tile URL for `http://localhost:8000/api/v1/tiles/{year}/{z}/{x}/{y}.png`
   - Add a `YearSelector` component (dropdown)
   - On year change, update the tile source URL and reload the layer

7. Update the click handler:
   - On map click, call `/api/v1/radiance?lat=...&lng=...&year=...`
   - Display radiance value, Bortle class, and SQM estimate in the popup

**Deliverable:** A fully working local dev setup where the frontend talks to the FastAPI backend, rendering your custom-colored tiles and providing point queries.

---

## Phase 4: Polish & Launch

**Goal:** Make it look great, deploy it, write the README.

**Tasks:**

1. **Search bar:**
   - Add geocoding via Nominatim (OpenStreetMap's free geocoding API)
   - On result select, fly the map to that location

2. **Geolocation:**
   - "Find my location" button using the browser Geolocation API
   - Fly to user's position and show their Bortle class

3. **"Find darkest sky near me" (stretch):**
   - Given user's location, search outward for the nearest tile below a radiance threshold

4. **Responsive design:**
   - Collapse legend/controls into a bottom sheet or hamburger on mobile

5. **README.md:**
   - Clear project description with a screenshot/GIF
   - Live demo link
   - Local dev setup instructions

6. **Deploy:**
   - Frontend -> Vercel or Netlify
   - Backend -> Fly.io (Dockerfile)
   - COG files -> Cloudflare R2

7. **CI:**
   - GitHub Actions workflow for lint + typecheck (frontend)
   - GitHub Actions workflow for ruff + mypy (backend)

---

## Phase 5 (Optional): Advanced Features

These are nice-to-haves that further differentiate the project:

- **Year-over-year comparison:** Side-by-side or swipe slider showing two years
- **Trend overlay:** Show areas where light pollution increased/decreased (diff of two years)
- **Dark Sky Parks:** Overlay International Dark-Sky Association certified locations
- **Observatory locations:** Overlay IAU observatory positions
- **Time-lapse animation:** Animate through years 2014-2023
- **Bortle sky simulation:** On click, show a simulated sky view at that Bortle level

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
rio-cogeo>=5.0.0
click>=8.1.0
pyproj>=3.7.0
pydantic>=2.10.0
Pillow>=10.0.0
rich>=13.0.0
earthengine-api>=0.1.390
geemap>=0.33.0
```
