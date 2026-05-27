"""
Download VIIRS VNP46A4 annual composites from the Earth Observation Group (EOG).

Usage:
    python -m app.pipeline.download --year 2023
"""

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import click
import requests

EOG_BASE = "https://eogdata.mines.edu/nighttime_light/annual/v22/"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def get_download_urls(year: int) -> list[str]:
    """Scrape the EOG directory listing and return URLs for average_masked GeoTIFFs."""
    url = f"{EOG_BASE}{year}/"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not fetch directory listing from {url}: {exc}") from exc

    # Match href links ending in .average_masked.tif
    matches = re.findall(r'href="([^"]+\.average_masked\.tif)"', resp.text)

    # Also accept .average.tif if no masked variant is found
    if not matches:
        matches = re.findall(r'href="([^"]+\.average\.tif)"', resp.text)

    if not matches:
        raise RuntimeError(
            f"No matching GeoTIFFs found in the EOG directory for {year}.\n"
            f"Check the listing manually: {url}"
        )

    return [urljoin(url, m) for m in matches]


def download_file(url: str, dest: Path) -> None:
    """Download a file to dest with resume support (HTTP Range requests)."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    existing_bytes = dest.stat().st_size if dest.exists() else 0
    headers = {"Range": f"bytes={existing_bytes}-"} if existing_bytes else {}

    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=60)
    except requests.RequestException as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc

    if resp.status_code == 416:
        # 416 Range Not Satisfiable — file is already fully downloaded
        click.echo(f"  Already complete: {dest.name}")
        return

    resp.raise_for_status()

    content_length = int(resp.headers.get("content-length", 0))
    total_bytes = existing_bytes + content_length
    downloaded = existing_bytes
    mode = "ab" if existing_bytes else "wb"

    with open(dest, mode) as fh:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1 MB chunks
            if not chunk:
                continue
            fh.write(chunk)
            downloaded += len(chunk)
            if total_bytes:
                pct = downloaded / total_bytes * 100
                gb_done = downloaded / 1e9
                gb_total = total_bytes / 1e9
                click.echo(
                    f"\r  {dest.name}: {gb_done:.2f} / {gb_total:.2f} GB  ({pct:.1f}%)",
                    nl=False,
                )

    click.echo()  # newline after progress line


@click.command()
@click.option("--year", required=True, type=int, help="Year to download (e.g. 2023)")
def main(year: int) -> None:
    """Download VIIRS annual composite GeoTIFFs from EOG for a given year."""
    raw_dir = DATA_DIR / "raw" / str(year)
    raw_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Fetching EOG directory listing for {year}...")
    try:
        urls = get_download_urls(year)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(urls)} file(s) to download:")
    for url in urls:
        click.echo(f"  {url}")

    for url in urls:
        filename = url.rsplit("/", 1)[-1]
        dest = raw_dir / filename

        if dest.exists():
            size_gb = dest.stat().st_size / 1e9
            click.echo(f"\nResuming {filename} (already have {size_gb:.2f} GB)...")
        else:
            click.echo(f"\nDownloading {filename}...")

        try:
            download_file(url, dest)
        except RuntimeError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)

        click.echo(f"  Saved → {dest}")

    click.echo(f"\nDone. Files in {raw_dir}")


if __name__ == "__main__":
    main()
