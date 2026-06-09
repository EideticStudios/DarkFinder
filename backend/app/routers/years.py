from fastapi import APIRouter
from pydantic import BaseModel

from app.config import PROCESSED_DIR

router = APIRouter()


class YearsResponse(BaseModel):
    years: list[int]
    skyglow_years: list[int]


@router.get("/years", response_model=YearsResponse)
def get_years() -> YearsResponse:
    if not PROCESSED_DIR.exists():
        return YearsResponse(years=[], skyglow_years=[])

    years = sorted(
        int(p.stem.replace("_cog", ""))
        for p in PROCESSED_DIR.glob("*_cog.tif")
        if p.stem.replace("_cog", "").isdigit()
    )
    skyglow_years = sorted(
        int(p.stem.replace("_skyglow_cog", ""))
        for p in PROCESSED_DIR.glob("*_skyglow_cog.tif")
        if p.stem.replace("_skyglow_cog", "").isdigit()
    )
    return YearsResponse(years=years, skyglow_years=skyglow_years)
