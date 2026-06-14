"""
Compute a modeled sky-glow layer from a processed VIIRS emission COG.

Upward emission only shows where light is produced. Sky glow propagates
~200 km from sources, so this step convolves the emission raster with a
Falchi/Garstang-style distance-falloff kernel: w(d) = (1 + d/d0)^-alpha,
truncated at max_distance. The kernel is normalized to sum=1, so output
values are a weighted average of nearby radiance and stay on the same
numeric order as the raw radiance (nW/cm²/sr).

The convolution runs in latitude bands with margin rows, rebuilding the
kernel at each band's center latitude so km-per-pixel in longitude
(cos(lat)) is correct at any latitude. Near the poles cos(lat) is clamped
to 0.1 to prevent kernel explosion.

Known limitation: `mode="same"` zero-pads at the raster borders, so glow
is underestimated within ~200 km of the edges. For global data this
affects only the dateline (open Pacific Ocean) — negligible visual impact.

Input:  data/processed/{year}_cog.tif
Output: data/processed/{year}_skyglow_cog.tif

Usage:
    python -m app.pipeline.skyglow --year 2023
"""

import sys
import tempfile
from pathlib import Path

import click
import numpy as np
import rasterio
from rasterio import Affine
from rasterio.crs import CRS
from rasterio.windows import Window
from scipy.signal import oaconvolve

from app.pipeline.mosaic import NODATA, build_overviews, convert_to_cog

DATA_DIR = Path(__file__).parent.parent.parent / "data"

KM_PER_DEG = 111.32


# ── Downsample ─────────────────────────────────────────────────────────────────

def downsample_emission(src_path: Path, factor: int = 4) -> tuple[np.ndarray, Affine]:
    """
    Block-average the full-res emission COG by `factor`, reading in row chunks
    so the full ~2 GB array is never held in memory.

    NoData / NaN / negative pixels are treated as 0 emission: water and masked
    pixels emit nothing but still receive glow from neighbors.
    """
    with rasterio.open(src_path) as src:
        # Crop to a multiple of factor so blocks divide evenly
        height = (src.height // factor) * factor
        width = (src.width // factor) * factor
        out_h, out_w = height // factor, width // factor
        out = np.zeros((out_h, out_w), dtype=np.float32)

        chunk_rows = max(1, 2048 // factor) * factor
        for row0 in range(0, height, chunk_rows):
            nrows = min(chunk_rows, height - row0)
            data = src.read(1, window=Window(0, row0, width, nrows)).astype(np.float32)
            np.nan_to_num(data, copy=False, nan=0.0)
            data[data < 0] = 0.0  # nodata sentinel (-9999) and noise
            blocks = data.reshape(nrows // factor, factor, out_w, factor)
            out[row0 // factor : (row0 + nrows) // factor] = blocks.mean(axis=(1, 3))
            click.echo(f"\r  Downsampling rows {row0 + nrows}/{height}", nl=False)
        click.echo()

        transform = src.transform * Affine.scale(factor)
    return out, transform


# ── Kernel ─────────────────────────────────────────────────────────────────────

def build_kernel(
    pixel_deg: float,
    center_lat_deg: float,
    d0_km: float = 4.0,
    alpha: float = 2.5,
    max_km: float = 200.0,
) -> np.ndarray:
    """
    Distance-falloff kernel w(d) = (1 + d/d0)^-alpha, truncated at max_km,
    normalized to sum=1. Longitude km-per-pixel is scaled by cos(latitude).
    """
    km_y = pixel_deg * KM_PER_DEG
    km_x = km_y * max(float(np.cos(np.radians(center_lat_deg))), 0.1)
    ry = int(np.ceil(max_km / km_y))
    rx = int(np.ceil(max_km / km_x))
    dy = np.arange(-ry, ry + 1, dtype=np.float64)[:, None] * km_y
    dx = np.arange(-rx, rx + 1, dtype=np.float64)[None, :] * km_x
    d = np.sqrt(dy * dy + dx * dx)
    w = (1.0 + d / d0_km) ** -alpha
    w[d > max_km] = 0.0
    w /= w.sum()
    return w.astype(np.float32)


# ── Convolution ────────────────────────────────────────────────────────────────

def convolve_skyglow(
    emission: np.ndarray,
    transform: Affine,
    d0_km: float = 4.0,
    alpha: float = 2.5,
    max_km: float = 200.0,
    band_deg: float = 10.0,
) -> np.ndarray:
    """
    FFT-convolve emission with the propagation kernel in latitude bands.

    Each band uses a kernel built at its center latitude; bands include
    margin rows (~max_km of latitude) so glow crosses band boundaries.
    Adjacent bands are blended in an overlap zone to eliminate seams
    caused by abrupt kernel changes at band edges.
    """
    height, width = emission.shape
    pixel_deg = abs(transform.e)
    margin_rows = int(np.ceil((max_km / KM_PER_DEG) / pixel_deg))
    band_rows = max(1, round(band_deg / pixel_deg))
    blend_rows = margin_rows // 2

    out = np.zeros((height, width), dtype=np.float32)
    weights = np.zeros((height, width), dtype=np.float32)

    for r0 in range(0, height, band_rows):
        r1 = min(r0 + band_rows, height)
        p0 = max(0, r0 - margin_rows)
        p1 = min(height, r1 + margin_rows)

        is_first_band = (r0 == 0)
        is_last_band = (r1 >= height)
        ext0 = r0 if is_first_band else max(p0, r0 - blend_rows)
        ext1 = r1 if is_last_band else min(p1, r1 + blend_rows)

        center_lat = transform.f + transform.e * ((r0 + r1) / 2.0)
        kernel = build_kernel(pixel_deg, center_lat, d0_km, alpha, max_km)
        click.echo(
            f"  Band rows {r0}-{r1} (lat ~{center_lat:.1f}°), "
            f"kernel {kernel.shape[0]}x{kernel.shape[1]}..."
        )
        conv = oaconvolve(emission[p0:p1], kernel, mode="same")
        conv_slice = conv[ext0 - p0 : ext1 - p0]

        n = ext1 - ext0
        w = np.ones(n, dtype=np.float32)
        top_taper = r0 - ext0
        if top_taper > 0:
            w[:top_taper] = np.linspace(0.0, 1.0, top_taper, endpoint=False, dtype=np.float32)
        bottom_taper = ext1 - r1
        if bottom_taper > 0:
            w[n - bottom_taper:] = np.linspace(1.0, 0.0, bottom_taper, endpoint=False, dtype=np.float32)

        w_2d = w[:, np.newaxis]
        out[ext0:ext1] += conv_slice * w_2d
        weights[ext0:ext1] += w_2d

    np.divide(out, weights, out=out, where=weights > 0)
    return out


# ── Output ─────────────────────────────────────────────────────────────────────

def write_cog(arr: np.ndarray, transform: Affine, crs: CRS, out_path: Path) -> None:
    """Write array to a temp tiled GTiff, then convert to a COG with overviews."""
    tmp_file = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
    tmp_file.close()
    tmp_path = Path(tmp_file.name)

    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "crs": crs,
        "transform": transform,
        "width": arr.shape[1],
        "height": arr.shape[0],
        "nodata": NODATA,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    }
    try:
        with rasterio.open(tmp_path, "w", **profile) as dst:
            dst.write(arr, 1)
        build_overviews(tmp_path)
        convert_to_cog(tmp_path, out_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def print_percentiles(arr: np.ndarray) -> None:
    """Print distribution stats to inform colormap anchor tuning."""
    positive = arr[arr > 0]
    if positive.size == 0:
        click.echo("  No positive sky-glow values?!")
        return
    p50, p90, p99 = np.percentile(positive, [50, 90, 99])
    click.echo("  Sky-glow distribution (positive pixels, nW/cm²/sr):")
    click.echo(f"    p50: {p50:.4f}   p90: {p90:.4f}   p99: {p99:.4f}   max: {positive.max():.2f}")


# ── CLI ────────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--year", required=True, type=int, help="Year to process (e.g. 2023)")
@click.option("--factor", default=4, type=int, help="Downsample factor before convolution")
@click.option("--d0", default=4.0, type=float, help="Kernel falloff scale distance (km)")
@click.option("--alpha", default=2.5, type=float, help="Kernel falloff exponent")
@click.option("--max-distance", default=200.0, type=float, help="Kernel truncation distance (km)")
def main(year: int, factor: int, d0: float, alpha: float, max_distance: float) -> None:
    """Convolve a year's emission COG into a modeled sky-glow COG."""
    src_cog = DATA_DIR / "processed" / f"{year}_cog.tif"
    out_cog = DATA_DIR / "processed" / f"{year}_skyglow_cog.tif"

    if not src_cog.exists():
        click.echo(
            f"Error: {src_cog} not found.\n"
            f"Run the emission pipeline first:  make process YEAR={year}",
            err=True,
        )
        sys.exit(1)

    with rasterio.open(src_cog) as src:
        crs = src.crs

    click.echo(f"Downsampling {src_cog.name} by {factor}x...")
    emission, transform = downsample_emission(src_cog, factor=factor)
    click.echo(f"  Working grid: {emission.shape[1]}x{emission.shape[0]} pixels")

    click.echo(
        f"\nConvolving sky glow (d0={d0} km, alpha={alpha}, max={max_distance} km)..."
    )
    skyglow = convolve_skyglow(
        emission, transform, d0_km=d0, alpha=alpha, max_km=max_distance
    )

    print_percentiles(skyglow)

    click.echo(f"\nWriting COG -> {out_cog}")
    write_cog(skyglow, transform, crs, out_cog)

    size_mb = out_cog.stat().st_size / 1e6
    click.echo(f"\nDone. Sky-glow COG saved to {out_cog}  ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
