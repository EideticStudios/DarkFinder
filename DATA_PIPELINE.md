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
# One-time setup — opens a browser for Google account auth
earthengine authenticate
```

No `.env` credentials are needed. GEE auth tokens are stored locally by the `earthengine` CLI.

**File properties (after download):**
- Format: GeoTIFF, single-band float32
- CRS: EPSG:4326 (geographic lat/lon)
- Resolution: 15 arc-seconds (~450m at equator)
- Extent: depends on --bbox flag (default: North America; use --global for full coverage)
- No-data value: -9999.0
- Values: radiance in nW/cm2/sr
- Size: varies by region (North America ~500MB, global ~2-3 GB)

## Processing Pipeline

### Step 1: Download from GEE

```bash
# North America (default bbox)
make download YEAR=2023

# Custom bounding box
make download YEAR=2023 BBOX="-130,24,-60,50"

# Or directly:
cd backend
python -m app.pipeline.download --year 2023
python -m app.pipeline.download --year 2023 --global
```

The download script uses `geemap.download_ee_image()` which automatically tiles large regions. Data arrives already in EPSG:4326 — no reprojection needed.

Output: `data/raw/{year}/VNL_V22_{year}_average_masked.tif`

### Step 2: Process to COG

```bash
make process YEAR=2023

# Or directly:
cd backend
python -m app.pipeline.mosaic --year 2023
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

### Step 3: Tile Serving

There is no separate tiling step. Tiles are rendered on-the-fly by rio-tiler reading the COG. The color ramp logic lives in `app/services/tile_renderer.py` and is applied per-tile at request time.

```python
import io
import numpy as np
from PIL import Image
from rio_tiler.io import Reader
from rio_tiler.errors import TileOutsideBounds

BREAKPOINTS = [0.0, 0.2, 0.4, 1.0, 3.0, 6.0, 12.0, 30.0, 60.0]
# (R, G, B, A) — alpha 200 for most classes, 220 for the bright end
COLORS = [
    (0x00, 0x00, 0x11, 200),  # Bortle 1: pristine
    (0x00, 0x00, 0x33, 200),  # Bortle 2: dark site
    (0x00, 0x33, 0x66, 200),  # Bortle 3: rural
    (0x00, 0x66, 0x33, 200),  # Bortle 4: rural/suburban
    (0x33, 0x99, 0x00, 200),  # Bortle 5: suburban
    (0xCC, 0xCC, 0x00, 200),  # Bortle 6: bright suburban
    (0xFF, 0x66, 0x00, 200),  # Bortle 7: suburban/urban
    (0xCC, 0x00, 0x00, 220),  # Bortle 8: city
    (0xFF, 0xFF, 0xFF, 220),  # Bortle 9: inner city
]

def render_tile(cog_path: str, x: int, y: int, z: int) -> bytes | None:
    """Read a COG window and apply the Bortle color ramp. Returns PNG bytes, or None if out of bounds."""
    try:
        with Reader(cog_path) as src:
            img = src.tile(x, y, z, resampling_method="bilinear")
    except TileOutsideBounds:
        return None

    band = img.data[0].astype(np.float32)
    h, w = band.shape
    rgba = np.zeros((4, h, w), dtype=np.uint8)

    for i in range(len(BREAKPOINTS) - 1):
        lo, hi = BREAKPOINTS[i], BREAKPOINTS[i + 1]
        mask = (band >= lo) & (band < hi)
        if not np.any(mask):
            continue
        t = (band[mask] - lo) / (hi - lo)
        r0, g0, b0, a0 = COLORS[i]
        r1, g1, b1, a1 = COLORS[i + 1]
        rgba[0][mask] = np.clip(r0 + t * (r1 - r0), 0, 255).astype(np.uint8)
        rgba[1][mask] = np.clip(g0 + t * (g1 - g0), 0, 255).astype(np.uint8)
        rgba[2][mask] = np.clip(b0 + t * (b1 - b0), 0, 255).astype(np.uint8)
        rgba[3][mask] = np.clip(a0 + t * (a1 - a0), 0, 255).astype(np.uint8)

    mask = band >= BREAKPOINTS[-1]
    rgba[0][mask], rgba[1][mask], rgba[2][mask], rgba[3][mask] = COLORS[-1]

    # Transparent where no light detected
    rgba[3][(band <= 0) | np.isnan(band)] = 0

    out = Image.fromarray(rgba.transpose(1, 2, 0), mode="RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
```

**Gotchas:**
- The alpha channel matters. Zero-radiance pixels MUST be fully transparent so the dark basemap shows through. Without this, the entire map turns opaque.
- Consider a logarithmic mapping: apply `np.log10(band + 1)` before the breakpoint lookup and adjust breakpoints accordingly. Human perception of brightness is logarithmic, and it often looks better.
- The color ramp in CLAUDE.md is a starting point. Tune it by comparing against lightpollutionmap.info's rendering and real SQM measurement data.
- Cache rendered tiles at the HTTP layer (`Cache-Control: public, max-age=31536000, immutable`). The data is annual and immutable once processed.
- The COG can be read directly from remote storage (e.g. Cloudflare R2) by passing a `/vsicurl/https://...` path to rio-tiler. GDAL's range-request support means only the needed tile window is fetched over the network.

## Radiance -> Bortle / SQM Conversion

These are approximate conversions. The relationship between satellite-measured radiance and ground-level sky quality is model-dependent and affected by atmospheric conditions, elevation, and the observer's specific location relative to light sources.

**Radiance (nW/cm2/sr) -> approximate SQM (mag/arcsec2):**
```
SQM ~ 22.0 - 2.5 * log10(radiance / 0.171 + 1)
```
This is a rough formula. The actual lightpollutionmap.info uses a more sophisticated sky brightness model (convolving radiance with atmospheric scattering kernels and elevation data). For a v1, the rough formula is fine.

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
- For an initial setup, processing just 2023 and one comparison year (e.g., 2015) is sufficient to demonstrate the pipeline and year-comparison capability.
