import os
from pathlib import Path

# Absolute path to backend/data/
DATA_DIR = Path(__file__).parent.parent / "data"

PROCESSED_DIR = DATA_DIR / "processed"

API_PREFIX = "/api/v1"

# Comma-separated list of allowed CORS origins; defaults to the local dev frontend.
FRONTEND_ORIGINS = [
    o.strip()
    for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

# Any localhost/127.0.0.1 port is allowed in dev: Vite silently picks the next free
# port when 5173 is taken, which would otherwise break CORS. Matched in addition to
# FRONTEND_ORIGINS, so the exact production origin is unaffected.
LOCALHOST_ORIGIN_REGEX = r"http://(localhost|127\.0\.0\.1):\d+"


def latest_emission_cog() -> str | None:
    """Emission COG to serve: an env-provided URL if set (e.g. R2), else the
    newest local file by year. Returns a path or URL string, or None."""
    url = os.environ.get("EMISSION_COG_URL")
    if url:
        return url
    if not PROCESSED_DIR.exists():
        return None
    cogs = [
        p
        for p in PROCESSED_DIR.glob("*_cog.tif")
        if p.stem.replace("_cog", "").isdigit()  # excludes *_skyglow_cog.tif
    ]
    newest = max(cogs, key=lambda p: int(p.stem.replace("_cog", "")), default=None)
    return str(newest) if newest else None


def latest_skyglow_cog() -> str | None:
    """Sky-glow COG to serve: an env-provided URL if set (e.g. R2), else the
    newest local file by year. Returns a path or URL string, or None."""
    url = os.environ.get("SKYGLOW_COG_URL")
    if url:
        return url
    if not PROCESSED_DIR.exists():
        return None
    cogs = [
        p
        for p in PROCESSED_DIR.glob("*_skyglow_cog.tif")
        if p.stem.replace("_skyglow_cog", "").isdigit()
    ]
    newest = max(cogs, key=lambda p: int(p.stem.replace("_skyglow_cog", "")), default=None)
    return str(newest) if newest else None
