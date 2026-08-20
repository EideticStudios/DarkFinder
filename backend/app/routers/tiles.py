import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config import latest_emission_cog, latest_skyglow_cog
from app.services.tile_renderer import Layer, render_tile_cached

logger = logging.getLogger(__name__)

router = APIRouter()

# Tiles are effectively immutable within a deploy (the COG doesn't change, and the
# frontend appends a ?v= cache-buster that changes when the render does), so they can
# be cached hard by browsers and any CDN placed in front of the backend.
_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400, immutable"}


@router.get("/tiles/{layer}/{z}/{x}/{y}.png")
def get_layer_tile(layer: Layer, z: int, x: int, y: int) -> Response:
    cog_path = latest_skyglow_cog() if layer == "skyglow" else latest_emission_cog()
    if cog_path is None:
        raise HTTPException(status_code=404, detail=f"No {layer} data available")

    try:
        png_bytes = render_tile_cached(str(cog_path), z, x, y, layer=layer)
    except Exception:
        logger.exception("Tile render error: layer=%s z=%d x=%d y=%d", layer, z, x, y)
        raise HTTPException(status_code=500, detail="Tile render failed")

    if png_bytes is None:
        raise HTTPException(status_code=404, detail="Tile outside data bounds")

    return Response(content=png_bytes, media_type="image/png", headers=_CACHE_HEADERS)
