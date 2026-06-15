"""
Merge raw VIIRS GeoTIFFs from GEE for a year into a Cloud-Optimized GeoTIFF (COG).

Input: GEE-downloaded GeoTIFFs in data/raw/{year}/ (EPSG:4326, float32)
Output: data/processed/{year}_cog.tif (COG with overviews)

Usage:
    python -m app.pipeline.mosaic --year 2023
"""

import sys
import tempfile
from pathlib import Path

import click
import numpy as np
import rasterio
import rasterio.windows as rw
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

DATA_DIR = Path(__file__).parent.parent.parent / "data"

NODATA = -9999.0

VIIRS_LAT_NORTH = 72.0   # ~3° buffer inside 75°N coverage limit
VIIRS_LAT_SOUTH = -63.0  # ~2° buffer inside 65°S coverage limit


# ── Polar masking ─────────────────────────────────────────────────────────────

def mask_polar_rows(path: Path) -> None:
    """Set pixels outside VIIRS clean-data latitudes to NODATA."""
    with rasterio.open(path, "r+") as ds:
        transform = ds.transform
        nodata = ds.nodata if ds.nodata is not None else NODATA

        # Scan from top to find first valid row
        north_cutoff = 0
        for row in range(ds.height):
            lat = transform.f + transform.e * (row + 0.5)
            if lat > VIIRS_LAT_NORTH:
                north_cutoff = row + 1
            else:
                break

        # Scan from bottom to find last valid row
        south_cutoff = ds.height
        for row in range(ds.height - 1, -1, -1):
            lat = transform.f + transform.e * (row + 0.5)
            if lat < VIIRS_LAT_SOUTH:
                south_cutoff = row
            else:
                break

        if north_cutoff > 0:
            win = rw.Window(0, 0, ds.width, north_cutoff)
            data = np.full((north_cutoff, ds.width), nodata, dtype=np.float32)
            ds.write(data, 1, window=win)
            click.echo(f"  Masked {north_cutoff} polar rows at top (>{VIIRS_LAT_NORTH}°N)")

        remaining = ds.height - south_cutoff
        if remaining > 0:
            win = rw.Window(0, south_cutoff, ds.width, remaining)
            data = np.full((remaining, ds.width), nodata, dtype=np.float32)
            ds.write(data, 1, window=win)
            click.echo(f"  Masked {remaining} polar rows at bottom (<{VIIRS_LAT_SOUTH}°S)")


# ── Source discovery ───────────────────────────────────────────────────────────

def find_source_files(year: int) -> list[Path]:
    """
    Return GeoTIFF paths for the given year from data/raw/{year}/.

    Looks for GEE-named files first (VNL_V22_{year}_average_masked.tif),
    then falls back to any *.tif in the directory.
    """
    raw_dir = DATA_DIR / "raw" / str(year)
    if not raw_dir.exists():
        raise FileNotFoundError(
            f"Raw data directory not found: {raw_dir}\n"
            f"Run download first:  python -m app.pipeline.download --year {year}"
        )

    # GEE-named files
    tifs = sorted(raw_dir.glob(f"VNL_V22_{year}_average_masked.tif"))
    if not tifs:
        # Fallback: any average_masked tif
        tifs = sorted(raw_dir.glob("*average_masked*.tif"))
    if not tifs:
        # Fallback: any tif
        tifs = sorted(raw_dir.glob("*.tif"))
    if not tifs:
        raise FileNotFoundError(
            f"No GeoTIFF files found in {raw_dir}.\n"
            "Run: python -m app.pipeline.download --year {year}"
        )
    return tifs


# ── Streaming mosaic ───────────────────────────────────────────────────────────

def stream_mosaic(tif_paths: list[Path], out_path: Path) -> None:
    """
    Merge GeoTIFF tiles into a single file by writing them one at a time.

    Unlike rasterio.merge this never loads the full global mosaic into memory.
    """
    click.echo(f"  Scanning {len(tif_paths)} tiles for bounds...")

    left = right = bottom = top = None
    crs = nodata = dtype = None

    for p in tif_paths:
        with rasterio.open(p) as ds:
            b = ds.bounds
            if left is None:
                left, bottom, right, top = b.left, b.bottom, b.right, b.top
                crs = ds.crs
                nodata = ds.nodata if ds.nodata is not None else NODATA
                dtype = ds.dtypes[0]
            else:
                left = min(left, b.left)
                bottom = min(bottom, b.bottom)
                right = max(right, b.right)
                top = max(top, b.top)

    with rasterio.open(tif_paths[0]) as ref:
        px_w = ref.transform.a
        px_h = abs(ref.transform.e)

    width = round((right - left) / px_w)      # type: ignore[operator]
    height = round((top - bottom) / px_h)     # type: ignore[operator]
    transform = from_bounds(left, bottom, right, top, width, height)

    profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "count": 1,
        "crs": crs,
        "transform": transform,
        "width": width,
        "height": height,
        "nodata": nodata,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    }

    click.echo(f"  Output: {width}x{height} pixels")

    with rasterio.open(out_path, "w", **profile) as dst:
        for i, p in enumerate(tif_paths, 1):
            click.echo(f"\r  Writing tile {i}/{len(tif_paths)}: {p.name[:50]:<50}", nl=False)
            with rasterio.open(p) as src:
                win = rw.from_bounds(
                    src.bounds.left, src.bounds.bottom,
                    src.bounds.right, src.bounds.top,
                    transform=dst.transform,
                )
                win = win.round_offsets().round_lengths()
                col_off = max(0, int(win.col_off))
                row_off = max(0, int(win.row_off))
                win_width = min(int(win.width), dst.width - col_off)
                win_height = min(int(win.height), dst.height - row_off)
                if win_width <= 0 or win_height <= 0:
                    continue
                clamped = rw.Window(col_off, row_off, win_width, win_height)
                data = src.read(1)
                data = data[:win_height, :win_width]
                dst.write(data, 1, window=clamped)

    click.echo()  # newline after progress line


# ── Overviews + COG ───────────────────────────────────────────────────────────

def build_overviews(path: Path) -> None:
    levels = [2, 4, 8, 16, 32, 64, 128, 256]
    with rasterio.open(path, "r+") as ds:
        ds.build_overviews(levels, Resampling.bilinear)
        ds.update_tags(ns="rio_overview", resampling="bilinear")
    click.echo(f"  Overview levels: {levels}")


def convert_to_cog(src_path: Path, out_path: Path) -> None:
    try:
        from rio_cogeo.cogeo import cog_translate
        from rio_cogeo.profiles import cog_profiles
    except ImportError as exc:
        raise RuntimeError(
            "rio-cogeo is required for COG conversion.\n"
            "Install it:  pip install rio-cogeo"
        ) from exc

    profile = cog_profiles.get("deflate")
    profile.update({"predictor": 3})

    cog_translate(
        str(src_path),
        str(out_path),
        profile,
        nodata=NODATA,
        overview_resampling="bilinear",
        config={
            "GDAL_TIFF_INTERNAL_MASK": True,
            "GDAL_TIFF_OVR_BLOCKSIZE": 512,
        },
        quiet=False,
    )


def validate_cog(path: Path) -> bool:
    try:
        from rio_cogeo.cogeo import cog_validate
        is_valid, errors, warnings = cog_validate(str(path))
        for w in warnings:
            click.echo(f"  Warning: {w}")
        if not is_valid:
            for e in errors:
                click.echo(f"  Error: {e}", err=True)
        return is_valid
    except ImportError:
        click.echo("  (rio-cogeo not available — skipping validation)")
        return True


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--year", default=2023, show_default=True, type=int, help="Year to process")
@click.option("--skip-validate", is_flag=True, default=False, help="Skip COG validation")
def main(year: int, skip_validate: bool) -> None:
    """Process raw GEE VIIRS GeoTIFFs for a year into a Cloud-Optimized GeoTIFF."""
    out_dir = DATA_DIR / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_cog = out_dir / f"{year}_cog.tif"

    # ── Discover source files ──────────────────────────────────────────────────
    click.echo(f"Looking for source files for {year}...")
    try:
        sources = find_source_files(year)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(sources)} GeoTIFF file(s).")
    for t in sources:
        click.echo(f"  {t.name}  ({t.stat().st_size / 1e9:.2f} GB)")

    need_cleanup = False

    if len(sources) == 1:
        click.echo("\nSingle file — skipping mosaic step.")
        work_path = sources[0]

        # Ensure nodata metadata is set (EOG files often lack it)
        with rasterio.open(work_path) as ds:
            if ds.nodata is None:
                click.echo("  Setting nodata metadata on source file...")
                with rasterio.open(work_path, "r+") as rw:
                    rw.nodata = NODATA
    else:
        click.echo(f"\nMosaicking {len(sources)} GeoTIFF tiles...")
        tmp_file = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
        tmp_file.close()
        work_path = Path(tmp_file.name)
        need_cleanup = True
        stream_mosaic(sources, work_path)
        click.echo(f"  Mosaic complete -> {work_path}")

    # ── Mask polar artifacts ──────────────────────────────────────────────────
    click.echo("\nMasking polar latitude artifacts...")
    mask_polar_rows(work_path)

    # ── Build overviews ────────────────────────────────────────────────────────
    click.echo("\nBuilding overviews (may take several minutes on large files)...")
    try:
        build_overviews(work_path)
    except Exception as exc:
        click.echo(f"Error building overviews: {exc}", err=True)
        if need_cleanup:
            work_path.unlink(missing_ok=True)
        sys.exit(1)

    # ── Convert to COG ─────────────────────────────────────────────────────────
    click.echo(f"\nConverting to COG -> {out_cog}")
    try:
        convert_to_cog(work_path, out_cog)
    except Exception as exc:
        click.echo(f"Error during COG conversion: {exc}", err=True)
        if need_cleanup:
            work_path.unlink(missing_ok=True)
        sys.exit(1)
    finally:
        if need_cleanup:
            work_path.unlink(missing_ok=True)

    # ── Validate ───────────────────────────────────────────────────────────────
    if not skip_validate:
        click.echo("\nValidating COG...")
        if validate_cog(out_cog):
            click.echo("  Valid COG.")
        else:
            click.echo("  COG validation failed.", err=True)
            sys.exit(1)

    size_gb = out_cog.stat().st_size / 1e9
    click.echo(f"\nDone. COG saved to {out_cog}  ({size_gb:.2f} GB)")


if __name__ == "__main__":
    main()
