"""
Stream VIIRS VNP46A4 annual composites from NASA Earthdata cloud and extract
the radiance band directly to GeoTIFF — no HDF5 files stored on disk.

Each tile streams ~11 MB of radiance data from the cloud instead of
downloading the full ~100 MB HDF5 file.  Downloads run in parallel.

Requires a free NASA Earthdata account (self-service):
  https://urs.earthdata.nasa.gov/

Add credentials to backend/.env:
    EARTHDATA_USERNAME=your_username
    EARTHDATA_PASSWORD=your_password

Usage:
    python -m app.pipeline.download --year 2023
    python -m app.pipeline.download --year 2023 --bbox -130,24,-60,50  # North America only
"""

import io
import os
import re
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)

console = Console()

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ENV_FILE = Path(__file__).parent.parent.parent / ".env"

PRODUCT_SHORT_NAME = "VNP46A4"
PRODUCT_VERSION = "1"

# HDF5 dataset containing annual average radiance (nW/cm²/sr)
H5_DATASET_PATH = (
    "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/AllAngle_Composite_Snow_Free"
)
H5_SCALE_FACTOR = 0.1
H5_FILL_VALUE = 65535   # uint16 sentinel for missing data
H5_NODATA = -9999.0

# MODIS sinusoidal grid geometry
_EARTH_RADIUS = 6371007.181   # metres
TILE_SIZE_M = _EARTH_RADIUS * np.pi * 2 / 36   # ≈ 1 111 950.52 m
PIXELS_PER_TILE = 2400
MODIS_SINU_PROJ4 = (
    "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 "
    "+a=6371007.181 +b=6371007.181 +units=m +no_defs"
)


def _load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _granule_filename(granule) -> str:
    try:
        links = granule.data_links()
        if links:
            return links[0].split("/")[-1]
    except Exception:
        pass
    return ""


def _extract_granule(
    granule,
    out_dir: Path,
    download_progress: Progress,
    overall_progress: Progress,
    overall_task: TaskID,
) -> tuple[str, str]:
    """
    Download one granule into memory, extract the radiance band, write a GeoTIFF.
    Returns (tif_filename, status_message).
    """
    import earthaccess
    import h5py

    h5_name = _granule_filename(granule)
    tif_name = re.sub(r"\.h5$", ".tif", h5_name)
    tif_path = out_dir / tif_name

    if tif_path.exists():
        overall_progress.advance(overall_task, 1)
        return tif_name, "skipped"

    # Label is the tile id, e.g. "h07v05"
    label = re.search(r"\.(h\d{2}v\d{2})\.", h5_name)
    label = label.group(1) if label else tif_name[:10]

    task = download_progress.add_task(label, total=None)
    try:
        m = re.search(r"\.h(\d{2})v(\d{2})\.", h5_name)
        if not m:
            raise ValueError(f"Cannot parse tile indices from {h5_name}")
        h, v = int(m.group(1)), int(m.group(2))

        left = (h - 18) * TILE_SIZE_M
        top = (9 - v) * TILE_SIZE_M
        right = left + TILE_SIZE_M
        bottom = top - TILE_SIZE_M
        transform = from_bounds(
            left, bottom, right, top, PIXELS_PER_TILE, PIXELS_PER_TILE
        )

        links = granule.data_links()
        if not links:
            raise ValueError("No download URL found")

        session = earthaccess.get_requests_https_session()
        resp = session.get(links[0], stream=True, timeout=300)
        resp.raise_for_status()

        total_bytes = int(resp.headers.get("content-length", 0)) or None
        download_progress.update(task, total=total_bytes)

        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                buf.write(chunk)
                download_progress.advance(task, len(chunk))
        buf.seek(0)

        download_progress.update(task, description=f"[dim]{label} extracting[/dim]")

        with h5py.File(buf, "r") as h5:
            raw = h5[H5_DATASET_PATH][:]

        data = raw.astype("float32")
        data[data >= H5_FILL_VALUE] = H5_NODATA
        data[data != H5_NODATA] *= H5_SCALE_FACTOR

        with rasterio.open(
            tif_path, "w",
            driver="GTiff",
            height=PIXELS_PER_TILE,
            width=PIXELS_PER_TILE,
            count=1,
            dtype="float32",
            crs=MODIS_SINU_PROJ4,
            transform=transform,
            nodata=H5_NODATA,
            compress="deflate",
            predictor=3,
        ) as dst:
            dst.write(data, 1)

        size_mb = tif_path.stat().st_size / 1e6
        download_progress.remove_task(task)
        overall_progress.advance(overall_task, 1)
        return tif_name, f"ok ({size_mb:.1f} MB)"

    except Exception as exc:
        tif_path.unlink(missing_ok=True)
        download_progress.remove_task(task)
        overall_progress.advance(overall_task, 1)
        return tif_name, f"error: {exc}"


@click.command()
@click.option("--year", required=True, type=int, help="Year to download (e.g. 2023)")
@click.option("--username", default=None, envvar="EARTHDATA_USERNAME")
@click.option("--password", default=None, envvar="EARTHDATA_PASSWORD")
@click.option(
    "--threads", default=8, show_default=True,
    help="Parallel extraction threads",
)
@click.option(
    "--bbox", default=None,
    metavar="MIN_LON,MIN_LAT,MAX_LON,MAX_LAT",
    help="Restrict to a bounding box (e.g. -130,24,-60,50 for North America)",
)
def main(
    year: int,
    username: str | None,
    password: str | None,
    threads: int,
    bbox: str | None,
) -> None:
    """Stream VIIRS VNP46A4 tiles from NASA cloud and extract to GeoTIFF."""
    _load_env()
    warnings.filterwarnings("ignore", category=FutureWarning, module="earthaccess")

    username = username or os.environ.get("EARTHDATA_USERNAME")
    password = password or os.environ.get("EARTHDATA_PASSWORD")
    if username:
        os.environ["EARTHDATA_USERNAME"] = username
    if password:
        os.environ["EARTHDATA_PASSWORD"] = password

    try:
        import earthaccess
    except ImportError:
        click.echo("earthaccess not installed. Run: pip install earthaccess", err=True)
        sys.exit(1)

    console.print("Authenticating with NASA Earthdata...")
    try:
        auth = earthaccess.login(
            strategy="environment" if (username and password) else "netrc"
        )
    except Exception as exc:
        console.print(f"[red]Authentication error:[/red] {exc}")
        sys.exit(1)

    if not auth.authenticated:
        console.print(
            "[red]Authentication failed.[/red]\n"
            "Add EARTHDATA_USERNAME and EARTHDATA_PASSWORD to backend/.env\n"
            "or register at https://urs.earthdata.nasa.gov/"
        )
        sys.exit(1)
    console.print("  [green]Authenticated.[/green]")

    # Parse optional bounding box
    bbox_tuple: tuple | None = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox_tuple = tuple(parts)
            console.print(f"  Bounding box: {bbox}")
        except ValueError:
            console.print("[red]Invalid --bbox. Expected: min_lon,min_lat,max_lon,max_lat[/red]")
            sys.exit(1)

    console.print(f"\nSearching for {PRODUCT_SHORT_NAME} v{PRODUCT_VERSION} data for {year}...")
    search_kwargs: dict = dict(
        short_name=PRODUCT_SHORT_NAME,
        version=PRODUCT_VERSION,
        temporal=(f"{year}-01-01", f"{year}-12-31"),
    )
    if bbox_tuple:
        search_kwargs["bounding_box"] = bbox_tuple

    try:
        results = earthaccess.search_data(**search_kwargs)
    except Exception as exc:
        console.print(f"[red]Search failed:[/red] {exc}")
        sys.exit(1)

    if not results:
        console.print(
            f"[red]No data found for {year}.[/red]\n"
            "Check https://lpdaac.usgs.gov/products/vnp46a4v001/ for available years."
        )
        sys.exit(1)

    console.print(f"Found [bold]{len(results)}[/bold] granule(s).")

    out_dir = DATA_DIR / "raw" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    existing_tifs = {f.name for f in out_dir.glob("VNP46A4.*.tif")}
    todo = [
        g for g in results
        if re.sub(r"\.h5$", ".tif", _granule_filename(g)) not in existing_tifs
    ]

    if existing_tifs:
        console.print(
            f"  {len(existing_tifs)} already done, "
            f"[bold]{len(todo)}[/bold] remaining."
        )

    if not todo:
        console.print("[green]All tiles already extracted.[/green]")
    else:
        console.print(f"\nDownloading {len(todo)} tile(s) with {threads} threads...\n")
        failed: list[str] = []

        overall_progress = Progress(
            TextColumn("[bold green]{task.description}[/bold green]"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        )
        download_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description:<16}[/bold cyan]"),
            BarColumn(bar_width=24),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
        )

        with Live(
            Group(overall_progress, download_progress),
            console=console,
            refresh_per_second=10,
        ):
            overall = overall_progress.add_task("Tiles complete", total=len(todo))
            with ThreadPoolExecutor(max_workers=threads) as pool:
                futures = {
                    pool.submit(
                        _extract_granule, g, out_dir,
                        download_progress, overall_progress, overall,
                    ): g
                    for g in todo
                }
                for future in as_completed(futures):
                    name, status = future.result()
                    if status.startswith("error"):
                        failed.append(name)
                        console.print(f"[red]FAILED[/red] {name}: {status}")

        if failed:
            console.print(f"\n[red]{len(failed)} tile(s) failed:[/red]")
            for f in failed:
                console.print(f"  {f}")
            sys.exit(1)

    total_tiles = len(list(out_dir.glob("VNP46A4.*.tif")))
    console.print(f"\n[green]Done.[/green] {total_tiles} GeoTIFF tile(s) in {out_dir}")


if __name__ == "__main__":
    main()
