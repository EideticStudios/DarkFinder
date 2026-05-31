"""
Download VIIRS VNP46A4 annual composites from NASA Earthdata (LPDAAC).

Requires a free NASA Earthdata account (self-service, no email required):
  https://urs.earthdata.nasa.gov/

After registering, add your credentials to backend/.env:

    EARTHDATA_USERNAME=your_username
    EARTHDATA_PASSWORD=your_password

Usage:
    python -m app.pipeline.download --year 2023
"""

import os
import sys
from pathlib import Path

import click

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ENV_FILE = Path(__file__).parent.parent.parent / ".env"

PRODUCT_SHORT_NAME = "VNP46A4"
PRODUCT_VERSION = "001"


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


@click.command()
@click.option("--year", required=True, type=int, help="Year to download (e.g. 2023)")
@click.option("--username", default=None, envvar="EARTHDATA_USERNAME")
@click.option("--password", default=None, envvar="EARTHDATA_PASSWORD")
def main(year: int, username: str | None, password: str | None) -> None:
    """Download VIIRS VNP46A4 annual composite tiles from NASA Earthdata LPDAAC."""
    _load_env()

    username = username or os.environ.get("EARTHDATA_USERNAME")
    password = password or os.environ.get("EARTHDATA_PASSWORD")

    # earthaccess reads these specific env var names
    if username:
        os.environ["EARTHDATA_USERNAME"] = username
    if password:
        os.environ["EARTHDATA_PASSWORD"] = password

    try:
        import earthaccess
    except ImportError:
        click.echo(
            "earthaccess is not installed.\n"
            "Run: pip install earthaccess",
            err=True,
        )
        sys.exit(1)

    click.echo("Authenticating with NASA Earthdata...")
    try:
        if username and password:
            auth = earthaccess.login(strategy="environment")
        else:
            auth = earthaccess.login(strategy="netrc")
    except Exception as exc:
        click.echo(f"Authentication error: {exc}", err=True)
        sys.exit(1)

    if not auth.authenticated:
        click.echo(
            "Authentication failed.\n"
            "Set EARTHDATA_USERNAME and EARTHDATA_PASSWORD in backend/.env\n"
            "Register at https://urs.earthdata.nasa.gov/",
            err=True,
        )
        sys.exit(1)
    click.echo("  Authenticated.")

    click.echo(f"\nSearching for {PRODUCT_SHORT_NAME} v{PRODUCT_VERSION} data for {year}...")
    try:
        results = earthaccess.search_data(
            short_name=PRODUCT_SHORT_NAME,
            version=PRODUCT_VERSION,
            temporal=(f"{year}-01-01", f"{year}-12-31"),
        )
    except Exception as exc:
        click.echo(f"Search failed: {exc}", err=True)
        sys.exit(1)

    if not results:
        click.echo(
            f"No data found for {year}.\n"
            f"Check available years at https://lpdaac.usgs.gov/products/vnp46a4v001/",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Found {len(results)} granule(s).")

    raw_dir = DATA_DIR / "raw" / str(year)
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Skip already-downloaded files
    existing = {f.name for f in raw_dir.glob("*.h5")}
    to_download = [g for g in results if _granule_filename(g) not in existing]

    if existing:
        click.echo(f"  {len(existing)} file(s) already present, {len(to_download)} remaining.")

    if not to_download:
        click.echo("All files already downloaded.")
    else:
        click.echo(f"\nDownloading {len(to_download)} file(s) to {raw_dir}...")
        try:
            earthaccess.download(to_download, str(raw_dir))
        except Exception as exc:
            click.echo(f"Download error: {exc}", err=True)
            sys.exit(1)

    total = len(list(raw_dir.glob("*.h5")))
    click.echo(f"\nDone. {total} file(s) in {raw_dir}")


if __name__ == "__main__":
    main()
