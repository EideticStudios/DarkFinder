import math

import rasterio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import PROCESSED_DIR

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
    year: int


@router.get("/radiance", response_model=RadianceResponse)
def get_radiance(lat: float, lng: float, year: int) -> RadianceResponse:
    cog_path = PROCESSED_DIR / f"{year}_cog.tif"
    if not cog_path.exists():
        raise HTTPException(status_code=404, detail=f"No processed data for year {year}")

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise HTTPException(status_code=422, detail="lat/lng out of range")

    try:
        with rasterio.open(cog_path) as ds:
            samples = list(ds.sample([(lng, lat)]))
            raw = float(samples[0][0])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to sample raster: {exc}") from exc

    # Treat nodata / negative values as zero radiance
    radiance = max(raw, 0.0) if not math.isnan(raw) else 0.0

    return RadianceResponse(
        radiance=round(radiance, 4),
        bortle=_radiance_to_bortle(radiance),
        sqm=_radiance_to_sqm(radiance),
        year=year,
    )
