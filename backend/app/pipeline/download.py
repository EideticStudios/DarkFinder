"""
Download VIIRS VNP46A4 annual composites from the Earth Observation Group (EOG).

EOG requires a free account. Create one at https://eogdata.mines.edu/
Then set credentials in backend/.env:

    EOG_USERNAME=your@email.com
    EOG_PASSWORD=yourpassword

Usage:
    python -m app.pipeline.download --year 2023
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import click
import requests

EOG_BASE = "https://eogdata.mines.edu/nighttime_light/annual/v22/"
TOKEN_URL = "https://eogauth.mines.edu/realms/eog/protocol/openid-connect/token"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
ENV_FILE = Path(__file__).parent.parent.parent / ".env"


def _load_env() -> None:
    """Load KEY=VALUE pairs from backend/.env into os.environ (if not already set)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def get_bearer_token(username: str, password: str) -> str:
    """Obtain a bearer token from the EOG Keycloak instance."""
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": "admin-cli",
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        body = resp.json()
        raise RuntimeError(
            f"Authentication failed: {body.get('error_description', resp.text)}\n"
            "Check your EOG_USERNAME / EOG_PASSWORD in backend/.env"
        )
    return resp.json()["access_token"]


def get_download_urls(year: int, session: requests.Session) -> list[str]:
    """Scrape the EOG directory listing and return URLs for average_masked GeoTIFFs."""
    url = f"{EOG_BASE}{year}/"
    try:
        resp = session.get(url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not fetch directory listing from {url}: {exc}") from exc

    matches = re.findall(r'href="([^"]+\.average_masked\.tif)"', resp.text)
    if not matches:
        matches = re.findall(r'href="([^"]+\.average\.tif)"', resp.text)
    if not matches:
        raise RuntimeError(
            f"No matching GeoTIFFs found in the EOG directory for {year}.\n"
            f"Check the listing manually: {url}"
        )

    return [urljoin(url, m) for m in matches]


def download_file(url: str, dest: Path, session: requests.Session) -> None:
    """Download a file to dest with resume support (HTTP Range requests)."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    existing_bytes = dest.stat().st_size if dest.exists() else 0
    headers = {"Range": f"bytes={existing_bytes}-"} if existing_bytes else {}

    try:
        resp = session.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True)
    except requests.RequestException as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc

    if resp.status_code == 416:
        click.echo(f"  Already complete: {dest.name}")
        return

    resp.raise_for_status()

    content_length = int(resp.headers.get("content-length", 0))
    total_bytes = existing_bytes + content_length
    downloaded = existing_bytes
    mode = "ab" if existing_bytes else "wb"

    with open(dest, mode) as fh:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
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

    click.echo()


@click.command()
@click.option("--year", required=True, type=int, help="Year to download (e.g. 2023)")
@click.option("--username", default=None, envvar="EOG_USERNAME", help="EOG account email")
@click.option("--password", default=None, envvar="EOG_PASSWORD", help="EOG account password")
def main(year: int, username: str | None, password: str | None) -> None:
    """Download VIIRS annual composite GeoTIFFs from EOG for a given year."""
    _load_env()

    # Re-read from env in case _load_env() just populated them
    username = username or os.environ.get("EOG_USERNAME")
    password = password or os.environ.get("EOG_PASSWORD")

    if not username or not password:
        click.echo(
            "EOG credentials required.\n"
            "1. Register free at https://eogdata.mines.edu/\n"
            "2. Add to backend/.env:\n"
            "     EOG_USERNAME=your@email.com\n"
            "     EOG_PASSWORD=yourpassword\n"
            "3. Re-run: make download YEAR={year}",
            err=True,
        )
        sys.exit(1)

    click.echo("Authenticating with EOG...")
    try:
        token = get_bearer_token(username, password)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo("  Authenticated.")

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    raw_dir = DATA_DIR / "raw" / str(year)
    raw_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"\nFetching EOG directory listing for {year}...")
    try:
        urls = get_download_urls(year, session)
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
            click.echo(f"\nResuming {filename} ({dest.stat().st_size / 1e9:.2f} GB already)...")
        else:
            click.echo(f"\nDownloading {filename}...")

        try:
            download_file(url, dest, session)
        except RuntimeError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)

        click.echo(f"  Saved → {dest}")

    click.echo(f"\nDone. Files in {raw_dir}")


if __name__ == "__main__":
    main()
