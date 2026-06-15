# DarkFinder — Data Pipeline Reference

This document covers the specifics of working with NASA VIIRS nighttime lights data — the gotchas, the file formats, and the exact processing steps.

## Data Source Details

### VIIRS VNL V2.2 via Google Earth Engine

The Earth Observation Group (EOG) at Colorado School of Mines publishes annual VIIRS nighttime lights composites. DarkFinder accesses these through Google Earth Engine's public catalog, which hosts the same data without requiring EOG credentials.

**GEE collection:**
```
NOAA/VIIRS/DNB/ANNUAL_V22
```

**Band:** `average_masked` (background zeroed, outliers removed)

**Authentication:**
```bash
# One-time setup — opens a browser for Google account auth.
# The earthengine CLI lives in the backend venv, so run it via the Make target:
make auth        # = cd backend && .venv/bin/earthengine authenticate
```

Auth tokens are stored locally by the `earthengine` CLI. In addition, the download step
needs a Google Cloud project with the Earth Engine API enabled — set its ID in
`backend/.env`, or the download exits with `GEE_PROJECT not set`:

```bash
cp backend/.env.example backend/.env
# then set GEE_PROJECT=your-gcp-project-id
```

**File properties (after download):**
- Format: GeoTIFF, single-band float32
- CRS: EPSG:4326 (geographic lat/lon)
- Resolution: 15 arc-seconds (~464 m at equator; downloaded at 463.83 m native scale)
- Extent: global when built via `make` (the `download` target passes `--global`); the bare `download` script's `--bbox` defaults to a North America box
- No-data value: -9999.0
- Values: radiance in nW/cm2/sr
- Size: varies by region (North America ~500MB, global ~2-3 GB)

## Processing Pipeline

### Step 1: Download from GEE

```bash
# Global coverage — make download defaults to --global
make download

# Limit to a bounding box
make download BBOX="-130,24,-60,50"

# Or directly (the bare script's --bbox defaults to a North America box):
cd backend
.venv/bin/python -m app.pipeline.download            # North America box
.venv/bin/python -m app.pipeline.download --global   # full globe
```

`YEAR` defaults to 2023 everywhere; pass `YEAR=2022` (or `--year 2022`) to target another year.

The download script uses `geemap.download_ee_image()` which automatically tiles large regions. Data arrives already in EPSG:4326 — no reprojection needed.

Output: `data/raw/{year}/VNL_V22_{year}_average_masked.tif`

### Step 2: Mosaic to an emission COG

`make process` runs two sub-steps in sequence: the mosaic below, then the Sky Glow
convolution (Step 3). To build only the emission COG, call the mosaic module directly:

```bash
make process                     # mosaic + sky glow

# Or just the emission COG:
cd backend
.venv/bin/python -m app.pipeline.mosaic
```

This step:
1. Discovers GeoTIFF(s) in `data/raw/{year}/`
2. If multiple files, merges them with a streaming mosaic (memory-safe)
3. Builds GDAL overview levels (2x through 256x)
4. Converts to a Cloud-Optimized GeoTIFF with DEFLATE compression
5. Validates the COG structure

Output: `data/processed/{year}_cog.tif` — single-band float32, EPSG:4326, internally tiled with overview pyramid.

**Gotchas:**
- Keep the COG in EPSG:4326. Do not reproject to EPSG:3857. rio-tiler handles per-tile reprojection at serve time; a global reproject produces a larger, distorted file with no benefit for storage.
- `PREDICTOR=3` is the floating-point predictor for DEFLATE. It significantly improves compression on float32 data.
- Verify the output: `rio cogeo validate data/processed/2023_cog.tif` (requires `rio-cogeo` package).

### Step 3: Sky Glow COG

The emission COG only shows where light is produced. The Sky Glow layer models where that
light ends up by propagating each source outward ~100 km. `app/pipeline/skyglow.py`
convolves the emission raster with a Falchi/Garstang distance-falloff kernel
`w(d) = (1 + d/d0)^-alpha` (defaults: `d0` = 2.5 km, `alpha` = 2.8), truncated at 120 km
and normalized to sum = 1, so the output stays in the same nW/cm²/sr units as the input.

```bash
make process                     # runs this right after the mosaic
# Or directly:
cd backend
.venv/bin/python -m app.pipeline.skyglow
```

Implementation notes:
- The emission raster is block-averaged (default 4x) before convolution, read in row
  chunks so the full ~2 GB array is never held in memory.
- The convolution (SciPy `oaconvolve`, FFT-based) runs in ~10° latitude bands, rebuilding
  the kernel at each band's center latitude so longitude km-per-pixel (`cos(lat)`) stays
  correct; near the poles `cos(lat)` is clamped to 0.1. Adjacent bands are blended to avoid
  seams.

Output: `data/processed/{year}_skyglow_cog.tif` — same grid and format as the emission COG.

### Step 4: Tile Serving

There is no separate tiling step. Tiles are rendered on the fly by rio-tiler reading the
COG, with the color ramp applied per tile at request time. The endpoint is
`GET /api/v1/tiles/{layer}/{z}/{x}/{y}.png`, where `layer` is `emission` or `skyglow`; the
backend auto-discovers the newest processed COG for that layer (`app/config.py`). All the
rendering logic lives in `app/services/tile_renderer.py`.

Both layers share one 9-stop vivid palette (`RAMP_COLORS`, Bortle classes 1–9, magenta at
the bright end) so the map and the frontend legend (`frontend/src/lib/bortleScale.ts`)
always agree. They differ only in how values map onto that palette:

- **Emission** — linear interpolation between fixed radiance breakpoints
  `[0.0, 0.2, 0.4, 1.0, 3.0, 6.0, 12.0, 30.0, 60.0]` (nW/cm²/sr).
- **Sky Glow** — log10 interpolation between anchors tuned to the post-convolution
  distribution; values below the lowest anchor fade to transparent so pristine areas reveal
  the dark basemap.

**Gotchas:**
- The alpha channel matters. Zero-radiance / nodata pixels MUST be fully transparent so the
  dark basemap shows through. Without this, the entire map turns opaque.
- `tile_renderer.py` is the single source of truth for the breakpoints and palette — keep
  the frontend legend (`bortleScale.ts`) and the color-ramp table in `CLAUDE.md` in sync
  with it, and tune against real SQM measurement data.
- Cache rendered tiles at the HTTP layer (`Cache-Control: public, max-age=31536000, immutable`). The data is annual and immutable once processed.
- The COG can be read directly from remote storage (e.g. Cloudflare R2) by passing a `/vsicurl/https://...` path to rio-tiler. GDAL's range-request support means only the needed tile window is fetched over the network.

## Radiance -> Bortle / SQM Conversion

These are approximate conversions. The relationship between satellite-measured radiance and ground-level sky quality is model-dependent and affected by atmospheric conditions, elevation, and the observer's specific location relative to light sources.

**Radiance (nW/cm2/sr) -> approximate SQM (mag/arcsec2):**
```
SQM ~ 22.0 - 2.5 * log10(radiance / 0.171 + 1)
```
This is a rough point conversion. A fuller treatment convolves radiance with atmospheric scattering kernels (and ideally elevation data) — which is essentially what the Sky Glow layer (Step 3) does. The radiance endpoint reflects this: it samples the sky-glow COG for the SQM estimate when one is available, falling back to raw emission otherwise. Bortle class is computed directly from the radiance breakpoints above, not via SQM.

**SQM -> Bortle class:**
| SQM Range          | Bortle |
|--------------------|--------|
| > 21.75            | 1      |
| 21.50 - 21.75      | 2      |
| 21.25 - 21.50      | 3      |
| 20.50 - 21.25      | 4      |
| 19.50 - 20.50      | 5      |
| 18.50 - 19.50      | 6      |
| 18.00 - 18.50      | 7      |
| < 18.00            | 8-9    |

## Performance Notes

- A full global raster at 15 arc-second resolution is approximately 86400 x 33600 pixels. At float32, that's ~11 GB uncompressed; with DEFLATE + float predictor the COG compresses to ~3-5 GB.
- The download + COG pipeline for one year takes roughly 15-60 minutes depending on region size and internet speed. There is no slow tile-generation step.
- rio-tiler renders a single 256x256 tile from a COG in ~5-50ms depending on zoom level and whether GDAL's block cache is warm.
- The app serves a single year (2023 by default). The pipeline stays year-parameterized only so you can rebuild against a newer composite later; the serving layer always picks up the newest processed COG.
