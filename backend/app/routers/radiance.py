import math

import rasterio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import latest_emission_cog, latest_skyglow_cog

router = APIRouter()

# Radiance breakpoints matching the Bortle color ramp in tile_renderer.py
_BREAKPOINTS = [0.0, 0.2, 0.4, 1.0, 3.0, 6.0, 12.0, 30.0, 60.0]


def _radiance_to_bortle(radiance: float) -> int:
    for i, threshold in enumerate(_BREAKPOINTS[1:], start=1):
        if radiance < threshold:
            return i
    return 9


def _radiance_to_sqm(radiance: float) -> float:
    """Approximate sky quality meter value from satellite radiance."""
    if radiance <= 0:
        return 22.0
    return round(22.0 - 2.5 * math.log10(radiance / 0.171 + 1), 2)


class RadianceResponse(BaseModel):
    radiance: float
    bortle: int
    sqm: float
    skyglow: float | None = None


@router.get("/radiance", response_model=RadianceResponse)
def get_radiance(lat: float, lng: float) -> RadianceResponse:
    cog_path = latest_emission_cog()
    if cog_path is None or not cog_path.exists():
        raise HTTPException(status_code=404, detail="No processed data available")

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise HTTPException(status_code=422, detail="lat/lng out of range")

    try:
        from rasterio.warp import transform as rio_transform
        with rasterio.open(cog_path) as ds:
            xs, ys = rio_transform("EPSG:4326", ds.crs, [lng], [lat])
            samples = list(ds.sample([(xs[0], ys[0])]))
            raw = float(samples[0][0])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to sample raster: {exc}") from exc

    # Treat nodata / negative values as zero radiance
    radiance = max(raw, 0.0) if not math.isnan(raw) else 0.0

    # Sample sky-glow COG if available
    skyglow_val: float | None = None
    skyglow_path = latest_skyglow_cog()
    if skyglow_path is not None and skyglow_path.exists():
        try:
            from rasterio.warp import transform as rio_transform
            with rasterio.open(skyglow_path) as ds:
                xs, ys = rio_transform("EPSG:4326", ds.crs, [lng], [lat])
                samples = list(ds.sample([(xs[0], ys[0])]))
                raw_sg = float(samples[0][0])
                skyglow_val = round(max(raw_sg, 0.0) if not math.isnan(raw_sg) else 0.0, 4)
        except Exception:
            pass  # skyglow sampling failure is non-fatal

    # Use skyglow for SQM when available (better proxy than point emission)
    sqm_source = skyglow_val if skyglow_val is not None else radiance

    return RadianceResponse(
        radiance=round(radiance, 4),
        bortle=_radiance_to_bortle(radiance),
        sqm=_radiance_to_sqm(sqm_source),
        skyglow=skyglow_val,
    )
