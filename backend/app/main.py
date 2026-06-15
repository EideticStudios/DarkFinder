from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_PREFIX, FRONTEND_ORIGIN
from app.routers import layers, radiance, tiles

app = FastAPI(title="DarkFinder API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(tiles.router, prefix=API_PREFIX)
app.include_router(radiance.router, prefix=API_PREFIX)
app.include_router(layers.router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
