from fastapi import APIRouter
from pydantic import BaseModel

from app.config import PROCESSED_DIR

router = APIRouter()


class YearsResponse(BaseModel):
    years: list[int]


@router.get("/years", response_model=YearsResponse)
def get_years() -> YearsResponse:
    if not PROCESSED_DIR.exists():
        return YearsResponse(years=[])

    years = sorted(
        int(p.stem.replace("_cog", ""))
        for p in PROCESSED_DIR.glob("*_cog.tif")
    )
    return YearsResponse(years=years)
