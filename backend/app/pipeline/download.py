"""
Download EOG VNL V2.2 annual nighttime lights composite from
Google Earth Engine (NOAA/VIIRS/DNB/ANNUAL_V22).

The EOG VNL V2.2 product (Colorado School of Mines) is available in
GEE's public catalog with no credential wall.

Downloads the average_masked band for the specified year and saves
it to data/raw/{year}/ ready for `make process`.

Requires a one-time GEE authentication:
    earthengine authenticate

Usage:
    python -m app.pipeline.download --year 2023
    python -m app.pipeline.download --year 2023 --bbox -170,5,-40,75
    python -m app.pipeline.download --year 2023 --global
"""

import sys
from pathlib import Path

import click
import rasterio
from rich.console import Console

console = Console()

DATA_DIR = Path(__file__).parent.parent.parent / "data"

GEE_COLLECTION = "NOAA/VIIRS/DNB/ANNUAL_V22"
BAND = "average_masked"
SCALE = 463.83        # native resolution in metres
NODATA = -9999.0


@click.command()
@click.option("--year", required=True, type=int, help="Year to download (e.g. 2023)")
@click.option(
    "--bbox", default="-170,5,-40,75",
    metavar="MIN_LON,MIN_LAT,MAX_LON,MAX_LAT",
    show_default=True,
    help="Bounding box to download",
)
@click.option(
    "--global", "global_coverage", is_flag=True, default=False,
    help="Download global coverage (overrides --bbox)",
)
def main(year: int, bbox: str, global_coverage: bool) -> None:
    """Download EOG VNL V2.2 nighttime lights from Google Earth Engine."""
    try:
        import ee
        import geemap
    except ImportError:
        console.print("[red]earthengine-api and geemap are required.[/red]\n"
                      "Run: pip install earthengine-api geemap")
        sys.exit(1)

    console.print("Initializing Google Earth Engine...")
    try:
        ee.Initialize()
    except Exception as exc:
        console.print(
            f"[red]GEE initialization failed:[/red] {exc}\n"
            "Run [bold]earthengine authenticate[/bold] first."
        )
        sys.exit(1)
    console.print("  [green]Authenticated.[/green]")

    # Build region geometry
    if global_coverage:
        region = ee.Geometry.BBox(-180, -90, 180, 90)
        region_label = "global"
    else:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            min_lon, min_lat, max_lon, max_lat = parts
        except ValueError:
            console.print(
                "[red]Invalid --bbox. Expected: min_lon,min_lat,max_lon,max_lat[/red]"
            )
            sys.exit(1)
        region = ee.Geometry.BBox(min_lon, min_lat, max_lon, max_lat)
        region_label = bbox

    console.print(f"\nSearching GEE for {GEE_COLLECTION} {year}...")
    image = (
        ee.ImageCollection(GEE_COLLECTION)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .first()
    )

    try:
        info = image.getInfo()
    except Exception:
        info = None
    if info is None:
        console.print(
            f"[red]No data found for {year} in {GEE_COLLECTION}.[/red]\n"
            "Check available years at: "
            "https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_ANNUAL_V22"
        )
        sys.exit(1)
    console.print(f"  Found: {info.get('id', 'unknown')}")

    out_dir = DATA_DIR / "raw" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    tif_name = f"VNL_V22_{year}_average_masked.tif"
    tif_path = out_dir / tif_name

    if tif_path.exists():
        size_gb = tif_path.stat().st_size / 1e9
        console.print(
            f"\n[green]Already downloaded:[/green] {tif_name} ({size_gb:.2f} GB)\n"
            f"Run [bold]make process YEAR={year}[/bold] to build the COG."
        )
        return

    # Unmask to explicit nodata value so mosaic.py's warp step handles it correctly
    band_image = image.select(BAND).unmask(NODATA)

    console.print(
        f"\nDownloading {BAND} for {year} ({region_label}) at {SCALE:.0f} m resolution..."
    )
    console.print("  [dim]geemap will tile large regions automatically.[/dim]\n")

    try:
        geemap.download_ee_image(
            band_image,
            filename=str(tif_path),
            region=region,
            scale=SCALE,
            crs="EPSG:4326",
        )
    except Exception as exc:
        tif_path.unlink(missing_ok=True)
        console.print(f"[red]Download failed:[/red] {exc}")
        sys.exit(1)

    if not tif_path.exists():
        console.print("[red]Download produced no output file.[/red]")
        sys.exit(1)

    # geemap doesn't write the nodata tag — fix it in-place via a tmp file
    console.print("\n  Setting nodata metadata...")
    tmp_path = tif_path.with_suffix(".tmp.tif")
    try:
        with rasterio.open(tif_path) as src:
            profile = src.profile.copy()
            profile["nodata"] = NODATA
            data = src.read(1)
        with rasterio.open(tmp_path, "w", **profile) as dst:
            dst.write(data, 1)
        tmp_path.replace(tif_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        console.print(f"[red]Failed to set nodata metadata:[/red] {exc}")
        sys.exit(1)

    size_gb = tif_path.stat().st_size / 1e9
    console.print(f"  [green]Done.[/green] {tif_name} ({size_gb:.2f} GB)")
    console.print(
        f"\n[green]Ready.[/green] Run [bold]make process YEAR={year}[/bold] to build the COG."
    )


if __name__ == "__main__":
    main()
