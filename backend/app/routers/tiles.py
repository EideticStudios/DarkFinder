import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config import PROCESSED_DIR
from app.services.tile_renderer import render_tile

logger = logging.getLogger(__name__)

router = APIRouter()

_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600"}


@router.get("/tiles/{year}/{z}/{x}/{y}.png")
def get_tile(year: int, z: int, x: int, y: int) -> Response:
    cog_path = PROCESSED_DIR / f"{year}_cog.tif"
    if not cog_path.exists():
        raise HTTPException(status_code=404, detail=f"No processed data for year {year}")

    try:
        png_bytes = render_tile(str(cog_path), z, x, y)
    except Exception:
        logger.exception("Tile render error: year=%d z=%d x=%d y=%d", year, z, x, y)
        raise HTTPException(status_code=500, detail="Tile render failed")

    if png_bytes is None:
        raise HTTPException(status_code=404, detail="Tile outside data bounds")

    return Response(content=png_bytes, media_type="image/png", headers=_CACHE_HEADERS)
