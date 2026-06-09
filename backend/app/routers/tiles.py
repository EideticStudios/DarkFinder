import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config import PROCESSED_DIR
from app.services.tile_renderer import Layer, render_tile

logger = logging.getLogger(__name__)

router = APIRouter()

_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600"}

_COG_FILENAME: dict[Layer, str] = {
    "emission": "{year}_cog.tif",
    "skyglow": "{year}_skyglow_cog.tif",
}


@router.get("/tiles/{layer}/{year}/{z}/{x}/{y}.png")
def get_layer_tile(layer: Layer, year: int, z: int, x: int, y: int) -> Response:
    cog_name = _COG_FILENAME.get(layer, "").format(year=year)
    cog_path = PROCESSED_DIR / cog_name
    if not cog_path.exists():
        raise HTTPException(status_code=404, detail=f"No {layer} data for year {year}")

    try:
        png_bytes = render_tile(str(cog_path), z, x, y, layer=layer)
    except Exception:
        logger.exception("Tile render error: layer=%s year=%d z=%d x=%d y=%d", layer, year, z, x, y)
        raise HTTPException(status_code=500, detail="Tile render failed")

    if png_bytes is None:
        raise HTTPException(status_code=404, detail="Tile outside data bounds")

    return Response(content=png_bytes, media_type="image/png", headers=_CACHE_HEADERS)


# Legacy route — delegates to emission layer
@router.get("/tiles/{year}/{z}/{x}/{y}.png")
def get_tile(year: int, z: int, x: int, y: int) -> Response:
    return get_layer_tile("emission", year, z, x, y)
