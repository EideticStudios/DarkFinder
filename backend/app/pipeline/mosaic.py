"""
Merge raw VIIRS GeoTIFFs (or HDF5 tiles from NASA LPDAAC) for a year into a
Cloud-Optimized GeoTIFF (COG).

Handles two input formats:
  - EOG global GeoTIFFs (*.average_masked.tif / *.average.tif)
  - NASA LPDAAC tiled HDF5 files (VNP46A4.*.h5) — extracted then mosaicked

For large tiled datasets the mosaic is written tile-by-tile to avoid loading
the entire global raster (~14 GB at 500m) into memory.

Usage:
    python -m app.pipeline.mosaic --year 2023
"""

import re
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

# ── VNP46A4 HDF5 constants ─────────────────────────────────────────────────────

H5_DATASET_PATH = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/AllAngle_Composite_Snow_Free"
H5_SCALE_FACTOR = 0.1
H5_FILL_VALUE = 65535   # uint16 sentinel
H5_NODATA = -9999.0

# MODIS sinusoidal grid parameters
_EARTH_RADIUS = 6371007.181  # metres
TILE_SIZE_M = _EARTH_RADIUS * np.pi * 2 / 36   # ≈ 1 111 950.52 m per tile
PIXELS_PER_TILE = 2400
PIXEL_SIZE_M = TILE_SIZE_M / PIXELS_PER_TILE

MODIS_SINU_PROJ4 = (
    "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 "
    "+a=6371007.181 +b=6371007.181 +units=m +no_defs"
)


# ── Source discovery ───────────────────────────────────────────────────────────

def find_source_files(year: int) -> tuple[list[Path], str]:
    """
    Return (paths, kind) where kind is 'tif' or 'h5'.

    Preference order:
      1. *.average_masked.tif  (EOG masked composite)
      2. *.average.tif         (EOG unmasked composite)
      3. VNP46A4.*.h5          (NASA LPDAAC tiles)
    """
    raw_dir = DATA_DIR / "raw" / str(year)
    if not raw_dir.exists():
        raise FileNotFoundError(
            f"Raw data directory not found: {raw_dir}\n"
            f"Run download first:  python -m app.pipeline.download --year {year}"
        )

    tifs = sorted(raw_dir.glob("*.average_masked.tif"))
    if not tifs:
        tifs = sorted(raw_dir.glob("*.average.tif"))
    if tifs:
        return tifs, "tif"

    # GeoTIFFs extracted by download.py from LPDAAC granules
    # Filter by year so 2022 tiles in the same directory don't pollute 2023 output
    vnp_tifs = sorted(
        p for p in raw_dir.glob("VNP46A4.*.tif") if f"A{year}" in p.name
    )
    if vnp_tifs:
        return vnp_tifs, "tif"

    # Fallback: raw HDF5 files (old download approach)
    h5s = sorted(raw_dir.glob("VNP46A4.*.h5"))
    if h5s:
        return h5s, "h5"

    raise FileNotFoundError(
        f"No source files found in {raw_dir}.\n"
        "Expected VNP46A4.*.tif (run download first) or *.average_masked.tif (EOG)."
    )


# ── HDF5 → GeoTIFF extraction ─────────────────────────────────────────────────

def _tile_bounds(h5_path: Path) -> tuple[float, float, float, float]:
    """Compute (left, bottom, right, top) sinusoidal bounds from tile filename."""
    m = re.search(r"\.h(\d{2})v(\d{2})\.", h5_path.name)
    if not m:
        raise ValueError(f"Cannot parse tile indices from filename: {h5_path.name}")
    h, v = int(m.group(1)), int(m.group(2))
    left = (h - 18) * TILE_SIZE_M
    top = (9 - v) * TILE_SIZE_M
    right = left + TILE_SIZE_M
    bottom = top - TILE_SIZE_M
    return left, bottom, right, top


def extract_h5_to_tif(h5_path: Path, out_path: Path) -> None:
    """
    Extract annual radiance from a VNP46A4 HDF5 tile and write a float32 GeoTIFF
    in MODIS sinusoidal CRS.
    """
    try:
        import h5py
    except ImportError:
        raise RuntimeError(
            "h5py is required for HDF5 extraction.\n"
            "Install it:  pip install h5py"
        )

    left, bottom, right, top = _tile_bounds(h5_path)
    transform = from_bounds(left, bottom, right, top, PIXELS_PER_TILE, PIXELS_PER_TILE)

    with h5py.File(h5_path, "r") as f:
        raw = f[H5_DATASET_PATH][:]          # (2400, 2400) uint16

    data = raw.astype("float32")
    data[data >= H5_FILL_VALUE] = H5_NODATA
    valid = data != H5_NODATA
    data[valid] *= H5_SCALE_FACTOR           # → nW/cm²/sr

    with rasterio.open(
        out_path, "w",
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


def extract_all_h5(h5_files: list[Path], out_dir: Path) -> list[Path]:
    """Extract all HDF5 tiles to GeoTIFFs; skip files already extracted."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tif_paths: list[Path] = []
    for i, h5 in enumerate(h5_files, 1):
        tif = out_dir / h5.with_suffix(".tif").name
        if not tif.exists():
            click.echo(f"  [{i}/{len(h5_files)}] Extracting {h5.name}...", nl=False)
            extract_h5_to_tif(h5, tif)
            click.echo(" done")
        else:
            click.echo(f"  [{i}/{len(h5_files)}] {h5.name} already extracted")
        tif_paths.append(tif)
    return tif_paths


# ── Streaming mosaic ───────────────────────────────────────────────────────────

def stream_mosaic(tif_paths: list[Path], out_path: Path) -> None:
    """
    Merge GeoTIFF tiles into a single file by writing them one at a time.

    Unlike rasterio.merge this never loads the full global mosaic into memory,
    making it safe for hundreds of tiles at 500m resolution.
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
                nodata = ds.nodata if ds.nodata is not None else H5_NODATA
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

    click.echo(f"  Output: {width}×{height} pixels  ({width * px_w / 1e6:.0f} × {height * px_h / 1e6:.0f} km)")

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
                # Clamp to output extent (handles tiles at the grid boundary)
                col_off = max(0, int(win.col_off))
                row_off = max(0, int(win.row_off))
                win_width = min(int(win.width), dst.width - col_off)
                win_height = min(int(win.height), dst.height - row_off)
                if win_width <= 0 or win_height <= 0:
                    continue
                clamped = rw.Window(col_off, row_off, win_width, win_height)
                data = src.read(1)
                # Trim data to match clamped window if needed
                data = data[:win_height, :win_width]
                dst.write(data, 1, window=clamped)

    click.echo()  # newline after progress line


# ── Sinusoidal → WGS84 reprojection ───────────────────────────────────────────

def warp_to_wgs84(src_path: Path, dst_path: Path) -> None:
    """
    Reproject a sinusoidal GeoTIFF to EPSG:4326.

    Uses file handles so rasterio/GDAL reads the CRS from the embedded file
    metadata rather than parsing a PROJ4 string we specify in code.  This is
    reliable for MODIS sinusoidal whereas passing a PROJ4 string to the
    in-memory reproject API was silently producing all-nodata output.
    """
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:4326", src.width, src.height, *src.bounds
        )
        profile = src.profile.copy()
        profile.update({
            "crs": "EPSG:4326",
            "transform": transform,
            "width": width,
            "height": height,
            "compress": "deflate",
            "predictor": 3,
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
        })
        # Remove bigtiff / other driver-specific keys that may not transfer
        profile.pop("bigtiff", None)

        with rasterio.open(dst_path, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_crs=src.crs,
                dst_crs="EPSG:4326",
                dst_transform=transform,
                resampling=Resampling.bilinear,
                src_nodata=H5_NODATA,
                dst_nodata=H5_NODATA,
            )


# ── EOG multi-tile mosaic (original, in-memory — safe for ≤ a few files) ──────

def mosaic_tiles(tifs: list[Path], tmp_path: Path) -> None:
    """Merge a small number of GeoTIFFs in memory (used for EOG multi-tile input)."""
    from rasterio.merge import merge

    datasets = [rasterio.open(t) for t in tifs]
    try:
        mosaic_data, transform = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(
            driver="GTiff",
            height=mosaic_data.shape[1],
            width=mosaic_data.shape[2],
            transform=transform,
            compress=None,
        )
        with rasterio.open(tmp_path, "w", **profile) as dst:
            dst.write(mosaic_data)
    finally:
        for ds in datasets:
            ds.close()


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
@click.option("--year", required=True, type=int, help="Year to process (e.g. 2023)")
@click.option("--skip-validate", is_flag=True, default=False, help="Skip COG validation")
def main(year: int, skip_validate: bool) -> None:
    """Process raw VIIRS files for a year into a Cloud-Optimized GeoTIFF."""
    out_dir = DATA_DIR / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_cog = out_dir / f"{year}_cog.tif"

    # ── Discover source files ──────────────────────────────────────────────────
    click.echo(f"Looking for source files for {year}...")
    try:
        sources, kind = find_source_files(year)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(sources)} {kind.upper()} file(s).")

    work_path: Path
    need_cleanup = False

    # ── HDF5 path: extract then stream-mosaic ──────────────────────────────────
    if kind == "h5":
        extract_dir = DATA_DIR / "raw" / str(year) / "_extracted"
        click.echo(f"\nExtracting {len(sources)} HDF5 tiles to {extract_dir}...")
        tifs = extract_all_h5(sources, extract_dir)
        click.echo(f"  Extracted {len(tifs)} GeoTIFF(s).")

        tmp_file = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
        tmp_file.close()
        work_path = Path(tmp_file.name)
        need_cleanup = True

        click.echo(f"\nStreaming mosaic → {work_path}...")
        stream_mosaic(tifs, work_path)
        size_gb = work_path.stat().st_size / 1e9
        click.echo(f"  Mosaic complete: {size_gb:.2f} GB")

    # ── GeoTIFF path (EOG): single file pass-through or small in-memory merge ──
    else:
        for t in sources:
            click.echo(f"  {t.name}  ({t.stat().st_size / 1e9:.2f} GB)")

        if len(sources) == 1:
            click.echo("\nSingle global file — skipping mosaic step.")
            work_path = sources[0]
            need_cleanup = False
        else:
            click.echo(f"\nMosaicking {len(sources)} GeoTIFF tiles...")
            tmp_file = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
            tmp_file.close()
            work_path = Path(tmp_file.name)
            need_cleanup = True
            stream_mosaic(sources, work_path)
            click.echo(f"  Mosaic complete → {work_path}")

    # ── Warp sinusoidal mosaic → WGS84 ────────────────────────────────────────
    click.echo("\nWarping sinusoidal mosaic → EPSG:4326 (gdalwarp)...")
    wgs84_tmp = tempfile.NamedTemporaryFile(suffix="_wgs84.tif", delete=False)
    wgs84_tmp.close()
    wgs84_path = Path(wgs84_tmp.name)
    try:
        warp_to_wgs84(work_path, wgs84_path)
        size_gb = wgs84_path.stat().st_size / 1e9
        click.echo(f"  Warp complete: {size_gb:.2f} GB")
    except Exception as exc:
        click.echo(f"Error during warp: {exc}", err=True)
        if need_cleanup:
            work_path.unlink(missing_ok=True)
        wgs84_path.unlink(missing_ok=True)
        sys.exit(1)

    if need_cleanup:
        work_path.unlink(missing_ok=True)
    work_path = wgs84_path
    need_cleanup = True

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
