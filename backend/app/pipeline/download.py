"""
Download EOG VIIRS Nighttime Lights (VNL V2) annual composite from
eogdata.mines.edu.

Downloads the global average_masked GeoTIFF for the specified year,
decompresses it, and saves it to data/raw/{year}/ ready for `make process`.

Add credentials to backend/.env:
    EOG_USERNAME=your_username
    EOG_PASSWORD=your_password

Usage:
    python -m app.pipeline.download --year 2023
"""

import gzip
import os
import re
import shutil
import sys
from pathlib import Path

import click
import requests
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)

console = Console()

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ENV_FILE = Path(__file__).parent.parent.parent / ".env"

# EOG OAuth2 endpoint (Keycloak). Client credentials are public for EOG open data.
EOG_TOKEN_URL = "https://eogdata.mines.edu/egog/token"
EOG_CLIENT_ID = "eogdata_eoauth"
EOG_CLIENT_SECRET = "REDACTED"

# Directory listing URL template for VNL V2 annual composites
EOG_DIR_URL = (
    "https://eogdata.mines.edu/products/vnl/v2/"
    "VIIRS_VNL_V2_annual_global_vcm_sl_vcmslcfg/{year}/"
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


def _get_token(username: str, password: str) -> str:
    resp = requests.post(
        EOG_TOKEN_URL,
        data={
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": EOG_CLIENT_ID,
            "client_secret": EOG_CLIENT_SECRET,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Unexpected auth response: {data}")
    return data["access_token"]


def _find_gz_file(session: requests.Session, year: int) -> tuple[str, str]:
    """
    List the EOG directory for `year` and return (url, filename) for the
    average_masked .dat.tif.gz file.
    """
    dir_url = EOG_DIR_URL.format(year=year)
    resp = session.get(dir_url, timeout=30)
    resp.raise_for_status()

    pattern = (
        rf'href="(VNL_npp_{year}_global_vcmslcfg_v2_[^"]*'
        r'\.average_masked\.dat\.tif\.gz)"'
    )
    matches = re.findall(pattern, resp.text)
    if not matches:
        raise FileNotFoundError(
            f"No average_masked .tif.gz found for {year} at {dir_url}\n"
            f"Check that URL in a browser to see what files are available."
        )
    filename = matches[0]
    return f"{dir_url}{filename}", filename


@click.command()
@click.option("--year", required=True, type=int, help="Year to download (e.g. 2023)")
@click.option("--username", default=None, envvar="EOG_USERNAME", help="EOG username")
@click.option("--password", default=None, envvar="EOG_PASSWORD", help="EOG password")
@click.option(
    "--url", default=None,
    help="Direct download URL (overrides auto-discovery)",
)
def main(year: int, username: str | None, password: str | None, url: str | None) -> None:
    """Download EOG VNL V2 annual nighttime lights composite."""
    _load_env()

    username = username or os.environ.get("EOG_USERNAME")
    password = password or os.environ.get("EOG_PASSWORD")

    if not username or not password:
        console.print(
            "[red]EOG credentials required.[/red]\n"
            "Add EOG_USERNAME and EOG_PASSWORD to backend/.env\n"
            "Register at https://eogdata.mines.edu/"
        )
        sys.exit(1)

    console.print("Authenticating with EOG...")
    try:
        token = _get_token(username, password)
    except Exception as exc:
        console.print(f"[red]Authentication failed:[/red] {exc}")
        console.print(
            "If you see a 401 error, double-check your username/password.\n"
            "If you see a 400 error, the client credentials may have changed —\n"
            "check https://eogdata.mines.edu/ for updated API documentation."
        )
        sys.exit(1)
    console.print("  [green]Authenticated.[/green]")

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    out_dir = DATA_DIR / "raw" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    if url:
        gz_filename = url.split("/")[-1]
        file_url = url
        console.print(f"\nUsing provided URL: {gz_filename}")
    else:
        console.print(f"\nSearching for {year} VNL V2 average_masked composite...")
        try:
            file_url, gz_filename = _find_gz_file(session, year)
        except Exception as exc:
            console.print(f"[red]Error finding file:[/red] {exc}")
            sys.exit(1)
        console.print(f"  Found: {gz_filename}")

    # Output: strip .gz only, keeping the original .dat.tif extension
    # mosaic.py globs for *average_masked*.tif which matches .dat.tif
    tif_name = gz_filename.removesuffix(".gz")
    tif_path = out_dir / tif_name
    gz_path = out_dir / gz_filename

    if tif_path.exists():
        size_gb = tif_path.stat().st_size / 1e9
        console.print(
            f"\n[green]Already downloaded:[/green] {tif_name} ({size_gb:.2f} GB)\n"
            f"Run [bold]make process YEAR={year}[/bold] to build the COG."
        )
        return

    # Download .gz
    console.print(f"\nDownloading {gz_filename}...")
    try:
        resp = session.get(file_url, stream=True, timeout=600)
        resp.raise_for_status()
    except Exception as exc:
        console.print(f"[red]Download failed:[/red] {exc}")
        sys.exit(1)

    total_bytes = int(resp.headers.get("content-length", 0)) or None

    try:
        with Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(gz_filename[:55], total=total_bytes)
            with open(gz_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        progress.advance(task, len(chunk))
    except Exception as exc:
        gz_path.unlink(missing_ok=True)
        console.print(f"[red]Download error:[/red] {exc}")
        sys.exit(1)

    # Decompress .gz → .tif
    console.print("\nDecompressing (this may take a few minutes for a global file)...")
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Decompressing {task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            progress.add_task(tif_name[:55])
            with gzip.open(gz_path, "rb") as gz_f, open(tif_path, "wb") as tif_f:
                shutil.copyfileobj(gz_f, tif_f, length=4 * 1024 * 1024)
    except Exception as exc:
        tif_path.unlink(missing_ok=True)
        console.print(f"[red]Decompression error:[/red] {exc}")
        sys.exit(1)
    finally:
        gz_path.unlink(missing_ok=True)

    size_gb = tif_path.stat().st_size / 1e9
    console.print(f"  [green]Done.[/green] {tif_name} ({size_gb:.2f} GB)")
    console.print(
        f"\n[green]Ready.[/green] Run [bold]make process YEAR={year}[/bold] to build the COG."
    )


if __name__ == "__main__":
    main()
