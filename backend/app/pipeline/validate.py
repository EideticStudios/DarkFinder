"""
Quick data quality check for downloaded VNP46A4 tiles.

Usage:
    python -m app.pipeline.validate --year 2023
"""

import math
import sys
from pathlib import Path

import click
import numpy as np
import rasterio

DATA_DIR = Path(__file__).parent.parent.parent / "data"

R = 6371007.181
TILE_SIZE_M = R * math.pi * 2 / 36
PX = TILE_SIZE_M / 2400

# Key cities and their expected MODIS tile (h, v)
CITIES = [
    ("Los Angeles",  34.05, -118.24),
    ("Denver",       39.74, -104.99),
    ("Minneapolis",  44.98,  -93.27),
    ("Kansas City",  39.10,  -94.58),
    ("Chicago",      41.88,  -87.63),
    ("Atlanta",      33.75,  -84.39),
    ("NYC",          40.71,  -74.01),
    ("Boston",       42.36,  -71.06),
    ("Miami",        25.76,  -80.19),
]


def tile_for_point(lat, lon):
    """Return (h, v) MODIS tile indices for a WGS84 point."""
    y = lat * math.pi / 180 * R
    x = lon * math.pi / 180 * R * math.cos(lat * math.pi / 180)
    h = math.floor(x / TILE_SIZE_M) + 18
    v = 9 - math.ceil(y / TILE_SIZE_M)
    return h, v


def rowcol_in_tile(lat, lon, h, v):
    """Row and column of a WGS84 point within tile (h, v)."""
    tile_left = (h - 18) * TILE_SIZE_M
    tile_top  = (9 - v)  * TILE_SIZE_M
    y = lat * math.pi / 180 * R
    x = lon * math.pi / 180 * R * math.cos(lat * math.pi / 180)
    row = int((tile_top - y) / PX)
    col = int((x - tile_left) / PX)
    return row, col


@click.command()
@click.option("--year", required=True, type=int)
def main(year: int) -> None:
    raw_dir = DATA_DIR / "raw" / str(year)
    tiles = sorted(
        p for p in raw_dir.glob("VNP46A4.*.tif") if f"A{year}" in p.name
    )
    if not tiles:
        click.echo(f"No tiles found in {raw_dir}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(tiles)} tiles for {year}\n")

    # Per-tile summary
    click.echo(f"{'Tile':<12}  {'Nonzero':>8}  {'Max nW':>8}  {'Notes'}")
    click.echo("-" * 50)
    problem_tiles = []
    for p in tiles:
        hv = next(
            (part for part in p.stem.split(".") if part.startswith("h") and "v" in part),
            p.stem
        )
        with rasterio.open(p) as ds:
            d = ds.read(1)
            nodata = ds.nodata
            valid = d[d != nodata]
            nonzero_pct = 100 * (valid > 0).sum() / d.size
            max_val = valid.max() if len(valid) else 0.0

        note = ""
        if nonzero_pct < 1.0:
            note = "WARN: <1% nonzero — possible mask corruption"
            problem_tiles.append(hv)
        elif nonzero_pct < 5.0:
            note = "low"

        click.echo(f"{hv:<12}  {nonzero_pct:7.1f}%  {max_val:8.2f}  {note}")

    # City spot-check
    click.echo(f"\n{'City':<16}  {'Tile':<8}  {'Value':>10}  {'Status'}")
    click.echo("-" * 55)
    for name, lat, lon in CITIES:
        h, v = tile_for_point(lat, lon)
        hv = f"h{h:02d}v{v:02d}"
        pattern = f"VNP46A4.A{year}001.{hv}.*.tif"
        matches = list(raw_dir.glob(pattern))
        if not matches:
            click.echo(f"{name:<16}  {hv:<8}  {'N/A':>10}  tile not downloaded")
            continue

        row, col = rowcol_in_tile(lat, lon, h, v)
        with rasterio.open(matches[0]) as ds:
            d = ds.read(1)
        val = d[row, col] if 0 <= row < 2400 and 0 <= col < 2400 else None

        if val is None:
            status = "out of bounds"
        elif val <= 0:
            status = "WARN: zero radiance at city center"
        elif val < 0.5:
            status = f"low ({val:.4f} nW)"
        else:
            status = f"ok ({val:.3f} nW)"

        click.echo(f"{name:<16}  {hv:<8}  {(val if val is not None else 0):>10.4f}  {status}")

    if problem_tiles:
        click.echo(f"\nProblem tiles ({len(problem_tiles)}): {', '.join(problem_tiles)}")
        click.echo("These tiles have <1% nonzero pixels — land/water mask may be corrupted.")
        click.echo("Consider re-downloading or switching to PRODUCT_VERSION=1 (year <= 2022).")
    else:
        click.echo("\nAll tiles look reasonable.")


if __name__ == "__main__":
    main()
