from pathlib import Path

# Absolute path to backend/data/
DATA_DIR = Path(__file__).parent.parent / "data"

PROCESSED_DIR = DATA_DIR / "processed"

API_PREFIX = "/api/v1"

FRONTEND_ORIGIN = "http://localhost:5173"


def latest_emission_cog() -> Path | None:
    """Newest emission COG in PROCESSED_DIR (by year), or None if none exist."""
    if not PROCESSED_DIR.exists():
        return None
    cogs = [
        p
        for p in PROCESSED_DIR.glob("*_cog.tif")
        if p.stem.replace("_cog", "").isdigit()  # excludes *_skyglow_cog.tif
    ]
    return max(cogs, key=lambda p: int(p.stem.replace("_cog", "")), default=None)


def latest_skyglow_cog() -> Path | None:
    """Newest sky-glow COG in PROCESSED_DIR (by year), or None if none exist."""
    if not PROCESSED_DIR.exists():
        return None
    cogs = [
        p
        for p in PROCESSED_DIR.glob("*_skyglow_cog.tif")
        if p.stem.replace("_skyglow_cog", "").isdigit()
    ]
    return max(cogs, key=lambda p: int(p.stem.replace("_skyglow_cog", "")), default=None)
