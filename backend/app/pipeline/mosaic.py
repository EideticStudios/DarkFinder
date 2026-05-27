"""
Merge raw VIIRS GeoTIFFs for a year into a Cloud-Optimized GeoTIFF (COG).

If a single global file was downloaded it is converted directly to COG.
If multiple tiles were downloaded they are mosaicked first.

Usage:
    python -m app.pipeline.mosaic --year 2023
"""

import sys
import tempfile
from pathlib import Path

import click
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def find_source_tifs(year: int) -> list[Path]:
    """Return sorted list of source GeoTIFFs for the given year."""
    raw_dir = DATA_DIR / "raw" / str(year)
    if not raw_dir.exists():
        raise FileNotFoundError(
            f"Raw data directory does not exist: {raw_dir}\n"
            f"Run download.py first:  python -m app.pipeline.download --year {year}"
        )

    tifs = sorted(raw_dir.glob("*.average_masked.tif"))
    if not tifs:
        tifs = sorted(raw_dir.glob("*.average.tif"))
    if not tifs:
        raise FileNotFoundError(f"No GeoTIFFs found in {raw_dir}")

    return tifs


def mosaic_tiles(tifs: list[Path], tmp_path: Path) -> None:
    """Merge multiple source GeoTIFFs into a single file at tmp_path."""
    datasets = [rasterio.open(t) for t in tifs]
    try:
        mosaic_data, transform = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(
            {
                "driver": "GTiff",
                "height": mosaic_data.shape[1],
                "width": mosaic_data.shape[2],
                "transform": transform,
                "compress": None,  # uncompressed temp file — COG step handles compression
            }
        )
        with rasterio.open(tmp_path, "w", **profile) as dst:
            dst.write(mosaic_data)
    finally:
        for ds in datasets:
            ds.close()


def build_overviews(path: Path) -> None:
    """Build internal overviews on a GeoTIFF (required before COG conversion)."""
    levels = [2, 4, 8, 16, 32, 64, 128, 256]
    with rasterio.open(path, "r+") as ds:
        ds.build_overviews(levels, Resampling.bilinear)
        ds.update_tags(ns="rio_overview", resampling="bilinear")
    click.echo(f"  Overviews built: {levels}")


def convert_to_cog(src_path: Path, out_path: Path) -> None:
    """Convert src_path to a Cloud-Optimized GeoTIFF at out_path."""
    try:
        from rio_cogeo.cogeo import cog_translate
        from rio_cogeo.profiles import cog_profiles
    except ImportError as exc:
        raise RuntimeError(
            "rio-cogeo is required for COG conversion.\n"
            "Install it:  pip install rio-cogeo"
        ) from exc

    # deflate profile with float predictor for better compression on float32 data
    profile = cog_profiles.get("deflate")
    profile.update({"predictor": 3})

    cog_translate(
        input=str(src_path),
        output=str(out_path),
        profile=profile,
        overview_resampling="bilinear",
        config={
            "GDAL_TIFF_INTERNAL_MASK": True,
            "GDAL_TIFF_OVR_BLOCKSIZE": 512,
        },
        quiet=False,
    )


def validate_cog(path: Path) -> bool:
    """Return True if the file is a valid COG."""
    try:
        from rio_cogeo.cogeo import cog_validate
        is_valid, errors, warnings = cog_validate(str(path))
        if warnings:
            for w in warnings:
                click.echo(f"  Warning: {w}")
        if not is_valid:
            for e in errors:
                click.echo(f"  Error: {e}", err=True)
        return is_valid
    except ImportError:
        click.echo("  (rio-cogeo not available — skipping validation)")
        return True


@click.command()
@click.option("--year", required=True, type=int, help="Year to process (e.g. 2023)")
@click.option(
    "--skip-validate",
    is_flag=True,
    default=False,
    help="Skip COG validation after conversion",
)
def main(year: int, skip_validate: bool) -> None:
    """Process raw VIIRS GeoTIFFs for a year into a Cloud-Optimized GeoTIFF."""
    out_dir = DATA_DIR / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_cog = out_dir / f"{year}_cog.tif"

    # --- Find source files ---
    click.echo(f"Looking for source GeoTIFFs for {year}...")
    try:
        tifs = find_source_tifs(year)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(tifs)} source file(s):")
    for t in tifs:
        size_gb = t.stat().st_size / 1e9
        click.echo(f"  {t.name}  ({size_gb:.2f} GB)")

    # --- Mosaic (or pass through if single file) ---
    if len(tifs) == 1:
        click.echo("\nSingle global file — skipping mosaic step.")
        work_path = tifs[0]
        need_cleanup = False
    else:
        click.echo(f"\nMosaicking {len(tifs)} tiles...")
        tmp_file = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
        tmp_file.close()
        work_path = Path(tmp_file.name)
        need_cleanup = True
        mosaic_tiles(tifs, work_path)
        click.echo(f"  Merged → {work_path}")

    # --- Build overviews ---
    click.echo("\nBuilding overviews (this takes a few minutes on large files)...")
    try:
        build_overviews(work_path)
    except Exception as exc:
        click.echo(f"Error building overviews: {exc}", err=True)
        if need_cleanup:
            work_path.unlink(missing_ok=True)
        sys.exit(1)

    # --- Convert to COG ---
    click.echo(f"\nConverting to COG → {out_cog}")
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

    # --- Validate ---
    if not skip_validate:
        click.echo("\nValidating COG...")
        if validate_cog(out_cog):
            click.echo("  Valid COG.")
        else:
            click.echo("  COG validation failed — check the output file.", err=True)
            sys.exit(1)

    size_gb = out_cog.stat().st_size / 1e9
    click.echo(f"\nDone. COG saved to {out_cog}  ({size_gb:.2f} GB)")


if __name__ == "__main__":
    main()
