# DarkFinder — Data Pipeline Reference

This document covers the specifics of working with NASA VIIRS nighttime lights data — the gotchas, the file formats, and the exact processing steps.

## Data Source Details

### EOG VNP46A4 Annual Composites

The Earth Observation Group (EOG) at Colorado School of Mines publishes annual VIIRS nighttime lights composites. These are the same data products used by lightpollutionmap.info.

**Download base URL:**
```
https://eogdata.mines.edu/nighttime_light/annual/v22/
```

**Directory structure on EOG:**
```
/nighttime_light/annual/v22/{year}/
  VNL_v22_npp_{year}0101-{year}1231_global_vcmslcfg_c202XXXXXXXX.average.tif
  VNL_v22_npp_{year}0101-{year}1231_global_vcmslcfg_c202XXXXXXXX.average_masked.tif
  VNL_v22_npp_{year}0101-{year}1231_global_vcmslcfg_c202XXXXXXXX.cf_cvg.tif
  ...
```

**Which file to use:**
- Use the `average_masked` variant — this has background (non-light) values set to zero and outliers removed
- Alternatively, use `vcm-orm-ntl` if available (outlier-removed, nighttime-lights only)
- The `cf_cvg` file contains cloud-free observation counts — useful for quality assessment but not for the heat map

**File properties:**
- Format: GeoTIFF, single-band float32
- CRS: EPSG:4326 (geographic lat/lon)
- Resolution: 15 arc-seconds (~450m at equator)
- Extent: -180 to 180 longitude, -65 to 75 latitude
- No-data value: typically `NaN` or a large negative number; check with `gdalinfo`
- Values: radiance in nW/cm²/sr
- Size: 2-3 GB per global file (or ~500MB per tile if tiled into 6 pieces)

### Alternative: NASA LAADS DAAC (VNP46A4 / VJ146A4)

The same data is also available from NASA's LAADS DAAC in HDF5 format, tiled in the sinusoidal grid. This is harder to work with — prefer the EOG GeoTIFFs.

If you do use LAADS DAAC:
- Requires a NASA Earthdata account and bearer token
- HDF5 format with multiple science datasets (SDS)
- The relevant SDS is `AllAngle_Composite_Snow_Free` (or `NearNadir_Composite_Snow_Free`)
- Tiled in the MODIS sinusoidal grid (10°×10° tiles), requiring mosaicking

## Processing Pipeline

### Step 1: Download

```python
# Key considerations:
# - Files are 2-3 GB each; use streaming downloads
# - EOG server can be slow; implement retry logic
# - Check file integrity after download (file size at minimum)
# - Store in data/raw/{year}/

import requests

def download_file(url: str, dest: str) -> None:
    """Download with resume support."""
    headers = {}
    existing_size = 0
    if os.path.exists(dest):
        existing_size = os.path.getsize(dest)
        headers['Range'] = f'bytes={existing_size}-'
    
    response = requests.get(url, headers=headers, stream=True)
    mode = 'ab' if existing_size else 'wb'
    
    with open(dest, mode) as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
```

### Step 2: Mosaic → COG

Merge the 6 tiles and save as a Cloud-Optimized GeoTIFF. This is the only processed artifact — reprojection and colorization happen at serve time.

```python
import subprocess
import rasterio
from rasterio.merge import merge

# Mosaic the 6 source tiles:
datasets = [rasterio.open(f) for f in tile_paths]
mosaic, mosaic_transform = merge(datasets)
# Write the merged raster to a temporary file first...

# Build overviews (must happen before the COG conversion):
subprocess.run([
    "gdaladdo", "-r", "bilinear", merged_path,
    "2", "4", "8", "16", "32", "64", "128", "256"
], check=True)

# Convert to COG with compression:
subprocess.run([
    "gdal_translate",
    "-of", "COG",
    "-co", "COMPRESS=DEFLATE",
    "-co", "PREDICTOR=3",        # float predictor — better compression on float32
    "-co", "RESAMPLING=BILINEAR",
    "-co", "OVERVIEWS=IGNORE_EXISTING",
    merged_path,
    output_cog_path,             # e.g. data/processed/2023_cog.tif
], check=True)
```

Output: `data/processed/{year}_cog.tif` — single-band float32, EPSG:4326, internally tiled with overview pyramid. Size: ~3–5 GB per year.

**Gotchas:**
- Keep the COG in EPSG:4326. Do not reproject to EPSG:3857. rio-tiler handles per-tile reprojection at serve time; a global reproject produces a larger, distorted file with no benefit for storage.
- `PREDICTOR=3` is the floating-point predictor for DEFLATE. It significantly improves compression on float32 data.
- Overviews must be built *before* `gdal_translate -of COG` — the COG driver embeds them from the source file.
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

## Radiance → Bortle / SQM Conversion

These are approximate conversions. The relationship between satellite-measured radiance and ground-level sky quality is model-dependent and affected by atmospheric conditions, elevation, and the observer's specific location relative to light sources.

**Radiance (nW/cm²/sr) → approximate SQM (mag/arcsec²):**
```
SQM ≈ 22.0 - 2.5 * log10(radiance / 0.171 + 1)
```
This is a rough formula. The actual lightpollutionmap.info uses a more sophisticated sky brightness model (convolving radiance with atmospheric scattering kernels and elevation data). For a v1, the rough formula is fine.

**SQM → Bortle class:**
| SQM Range         | Bortle |
|--------------------|--------|
| > 21.75            | 1      |
| 21.50 – 21.75      | 2      |
| 21.25 – 21.50      | 3      |
| 20.50 – 21.25      | 4      |
| 19.50 – 20.50      | 5      |
| 18.50 – 19.50      | 6      |
| 18.00 – 18.50      | 7      |
| < 18.00            | 8–9    |

## Performance Notes

- A full global raster at 15 arc-second resolution is approximately 86400 × 33600 pixels. At float32, that's ~11 GB uncompressed; with DEFLATE + float predictor the COG compresses to ~3–5 GB.
- The download + mosaic + COG pipeline for one year takes roughly 30–90 minutes on a modern laptop, depending on internet speed and CPU cores. There is no slow tile-generation step.
- rio-tiler renders a single 256×256 tile from a COG in ~5–50ms depending on zoom level and whether GDAL's block cache is warm.
- For an initial setup, processing just 2023 and one comparison year (e.g., 2015) is sufficient to demonstrate the pipeline and year-comparison capability.
