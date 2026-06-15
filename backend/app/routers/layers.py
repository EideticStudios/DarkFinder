from fastapi import APIRouter
from pydantic import BaseModel

from app.config import latest_emission_cog, latest_skyglow_cog

router = APIRouter()


class LayersResponse(BaseModel):
    emission: bool
    skyglow: bool


@router.get("/layers", response_model=LayersResponse)
def get_layers() -> LayersResponse:
    """Report which data layers have a processed COG available to serve."""
    return LayersResponse(
        emission=latest_emission_cog() is not None,
        skyglow=latest_skyglow_cog() is not None,
    )
