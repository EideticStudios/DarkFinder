"""
Data quality check for GEE-downloaded VIIRS GeoTIFFs.

Opens GeoTIFF(s) in data/raw/{year}/, checks CRS is EPSG:4326, reports
basic stats, and spot-checks radiance at known city coordinates.

Usage:
    python -m app.pipeline.validate --year 2023
"""

import sys
from pathlib import Path

import click
import numpy as np
import rasterio

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# Key cities with (lat, lon) for spot-checking radiance values
CITIES = [
    # North America
    ("Los Angeles",  34.05, -118.24),
    ("Denver",       39.74, -104.99),
    ("Chicago",      41.88,  -87.63),
    ("NYC",          40.71,  -74.01),
    # Europe
    ("London",       51.51,   -0.13),
    ("Paris",        48.86,    2.35),
    # Asia
    ("Tokyo",        35.68,  139.69),
    ("Shanghai",     31.23,  121.47),
    ("Mumbai",       19.08,   72.88),
    # Southern Hemisphere
    ("Sydney",      -33.87,  151.21),
    ("São Paulo",   -23.55,  -46.63),
    ("Johannesburg",-26.20,   28.04),
]


def sample_point(ds, lat: float, lon: float) -> float | None:
    """Sample a single pixel value at (lat, lon) using rasterio's index method."""
    try:
        row, col = ds.index(lon, lat)
    except Exception:
        return None
    if 0 <= row < ds.height and 0 <= col < ds.width:
        val = ds.read(1, window=rasterio.windows.Window(col, row, 1, 1))
        return float(val[0, 0])
    return None


@click.command()
@click.option("--year", required=True, type=int)
def main(year: int) -> None:
    """Validate GEE-downloaded VIIRS GeoTIFFs for a given year."""
    raw_dir = DATA_DIR / "raw" / str(year)

    # Find GeoTIFFs
    tifs = sorted(raw_dir.glob(f"VNL_V22_{year}_average_masked.tif"))
    if not tifs:
        tifs = sorted(raw_dir.glob("*average_masked*.tif"))
    if not tifs:
        tifs = sorted(raw_dir.glob("*.tif"))
    if not tifs:
        click.echo(f"No GeoTIFF files found in {raw_dir}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(tifs)} GeoTIFF(s) for {year}\n")

    # Per-file summary
    click.echo(f"{'File':<45}  {'CRS':<12}  {'Size':>10}  {'Dims':>16}  {'Nodata':>8}")
    click.echo("-" * 100)

    for p in tifs:
        with rasterio.open(p) as ds:
            crs_str = str(ds.crs) if ds.crs else "None"
            size_mb = p.stat().st_size / 1e6
            dims = f"{ds.width}x{ds.height}"
            nodata_str = str(ds.nodata) if ds.nodata is not None else "None"

            crs_ok = ds.crs is not None and ds.crs.to_epsg() == 4326
            crs_flag = "" if crs_ok else " [WARN: expected EPSG:4326]"

            click.echo(
                f"{p.name:<45}  {crs_str:<12}  {size_mb:>8.1f}MB  {dims:>16}  {nodata_str:>8}"
                f"{crs_flag}"
            )

    # Stats on the first (or only) file
    click.echo(f"\n--- Raster statistics ({tifs[0].name}) ---")
    with rasterio.open(tifs[0]) as ds:
        data = ds.read(1)
        nodata = ds.nodata

        if nodata is not None:
            valid = data[data != nodata]
        else:
            valid = data[~np.isnan(data)]

        total_pixels = data.size
        nonzero = (valid > 0).sum()
        pct_nonzero = 100 * nonzero / total_pixels if total_pixels > 0 else 0

        click.echo(f"  Total pixels:   {total_pixels:,}")
        click.echo(f"  Valid pixels:   {len(valid):,}")
        click.echo(f"  Nonzero:        {nonzero:,} ({pct_nonzero:.1f}%)")
        if len(valid) > 0:
            click.echo(f"  Min radiance:   {valid.min():.4f} nW/cm2/sr")
            click.echo(f"  Max radiance:   {valid.max():.4f} nW/cm2/sr")
            click.echo(f"  Mean radiance:  {valid.mean():.4f} nW/cm2/sr")

    # City spot-check
    click.echo(f"\n--- City spot-check ---")
    click.echo(f"{'City':<16}  {'Value':>12}  {'Status'}")
    click.echo("-" * 50)

    with rasterio.open(tifs[0]) as ds:
        for name, lat, lon in CITIES:
            val = sample_point(ds, lat, lon)

            if val is None:
                status = "out of bounds"
                val_str = "N/A"
            elif nodata is not None and val == nodata:
                status = "nodata"
                val_str = "nodata"
            elif val <= 0:
                status = "WARN: zero radiance at city center"
                val_str = f"{val:.4f}"
            elif val < 0.5:
                status = f"low ({val:.4f} nW)"
                val_str = f"{val:.4f}"
            else:
                status = "ok"
                val_str = f"{val:.3f}"

            click.echo(f"{name:<16}  {val_str:>12}  {status}")

    click.echo("\nValidation complete.")


if __name__ == "__main__":
    main()
