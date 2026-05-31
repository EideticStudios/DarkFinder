"""
Download VIIRS VNP46A4 annual composites from the Earth Observation Group (EOG).

EOG requires a free account and API credentials. See:
  https://eogdata.mines.edu/products/register/

After registering, add your credentials to backend/.env:

    EOG_USERNAME=your@email.com
    EOG_PASSWORD=yourpassword
    EOG_CLIENT_ID=your_client_id
    EOG_CLIENT_SECRET=your_client_secret

Usage:
    python -m app.pipeline.download --year 2023
"""

import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import click
import requests

EOG_BASE = "https://eogdata.mines.edu/nighttime_light/annual/v22/"
TOKEN_URL = "https://eogauth-new.mines.edu/realms/eog/protocol/openid-connect/token"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
ENV_FILE = Path(__file__).parent.parent.parent / ".env"

# Refresh token 60s before the 5-minute expiry
TOKEN_LIFETIME_S = 5 * 60
TOKEN_REFRESH_BUFFER_S = 60


def _load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


class EOGSession:
    """Requests session that transparently refreshes the bearer token before expiry."""

    def __init__(self, username: str, password: str, client_id: str, client_secret: str) -> None:
        self._username = username
        self._password = password
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = requests.Session()
        self._token_fetched_at: float = 0.0
        self._authenticate()

    def _authenticate(self) -> None:
        resp = requests.post(
            TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "username": self._username,
                "password": self._password,
                "grant_type": "password",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            body = resp.json()
            raise RuntimeError(
                f"Authentication failed: {body.get('error_description', resp.text)}\n"
                "Check EOG_USERNAME / EOG_PASSWORD / EOG_CLIENT_ID / EOG_CLIENT_SECRET in backend/.env"
            )
        token = resp.json()["access_token"]
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._token_fetched_at = time.monotonic()

    def _refresh_if_needed(self) -> None:
        age = time.monotonic() - self._token_fetched_at
        if age >= TOKEN_LIFETIME_S - TOKEN_REFRESH_BUFFER_S:
            click.echo("\n  (Refreshing token...)", nl=False)
            self._authenticate()

    def get(self, url: str, **kwargs) -> requests.Response:
        self._refresh_if_needed()
        return self._session.get(url, **kwargs)


def get_download_urls(year: int, session: EOGSession) -> list[str]:
    url = f"{EOG_BASE}{year}/"
    try:
        resp = session.get(url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not fetch directory listing: {exc}") from exc

    matches = re.findall(r'href="([^"]+\.average_masked[^"]*\.tif(?:\.gz)?)"', resp.text)
    if not matches:
        matches = re.findall(r'href="([^"]+\.average[^"]*\.tif(?:\.gz)?)"', resp.text)
    if not matches:
        raise RuntimeError(
            f"No matching GeoTIFFs found for {year}.\n"
            f"Check the listing manually: {url}"
        )
    return [urljoin(url, m) for m in matches]


def download_file(url: str, dest: Path, session: EOGSession) -> None:
    import gzip
    import shutil

    dest.parent.mkdir(parents=True, exist_ok=True)
    existing_bytes = dest.stat().st_size if dest.exists() else 0
    headers = {"Range": f"bytes={existing_bytes}-"} if existing_bytes else {}

    resp = session.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True)

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
            session._refresh_if_needed()
            if total_bytes:
                pct = downloaded / total_bytes * 100
                click.echo(
                    f"\r  {dest.name}: {downloaded/1e9:.2f} / {total_bytes/1e9:.2f} GB  ({pct:.1f}%)",
                    nl=False,
                )

    click.echo()

    if dest.suffix == ".gz":
        click.echo(f"  Decompressing {dest.name}...")
        decompressed = dest.with_suffix("")
        with gzip.open(dest, "rb") as f_in, open(decompressed, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        dest.unlink()
        click.echo(f"  Decompressed → {decompressed.name}")


@click.command()
@click.option("--year", required=True, type=int, help="Year to download (e.g. 2023)")
@click.option("--username", default=None, envvar="EOG_USERNAME")
@click.option("--password", default=None, envvar="EOG_PASSWORD")
@click.option("--client-id", default=None, envvar="EOG_CLIENT_ID")
@click.option("--client-secret", default=None, envvar="EOG_CLIENT_SECRET")
def main(year: int, username: str | None, password: str | None,
         client_id: str | None, client_secret: str | None) -> None:
    """Download VIIRS annual composite GeoTIFFs from EOG for a given year."""
    _load_env()
    username = username or os.environ.get("EOG_USERNAME")
    password = password or os.environ.get("EOG_PASSWORD")
    client_id = client_id or os.environ.get("EOG_CLIENT_ID")
    client_secret = client_secret or os.environ.get("EOG_CLIENT_SECRET")

    missing = [k for k, v in [
        ("EOG_USERNAME", username), ("EOG_PASSWORD", password),
        ("EOG_CLIENT_ID", client_id), ("EOG_CLIENT_SECRET", client_secret),
    ] if not v]

    if missing:
        click.echo(
            f"Missing credentials: {', '.join(missing)}\n"
            "See https://eogdata.mines.edu/products/register/ for setup instructions.\n"
            "Add them to backend/.env and re-run.",
            err=True,
        )
        sys.exit(1)

    click.echo("Authenticating with EOG...")
    try:
        session = EOGSession(username, password, client_id, client_secret)  # type: ignore[arg-type]
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo("  Authenticated.")

    click.echo(f"\nFetching directory listing for {year}...")
    try:
        urls = get_download_urls(year, session)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(urls)} file(s):")
    for url in urls:
        click.echo(f"  {url}")

    raw_dir = DATA_DIR / "raw" / str(year)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for url in urls:
        filename = url.rsplit("/", 1)[-1]
        dest = raw_dir / filename
        if dest.exists():
            click.echo(f"\nResuming {filename} ({dest.stat().st_size / 1e9:.2f} GB already)...")
        else:
            click.echo(f"\nDownloading {filename}...")
        download_file(url, dest, session)
        click.echo(f"  Saved → {dest}")

    click.echo(f"\nDone. Files in {raw_dir}")


if __name__ == "__main__":
    main()
