# Production image for the DarkFinder API (serve-only).
# Build context is the backend/ directory (set "Root Directory = backend" on Railway).
FROM python:3.12-slim

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    # GDAL tuning for reading COGs remotely over HTTPS range requests (Strategy B / R2).
    GDAL_CACHEMAX=256 \
    VSI_CACHE=TRUE \
    GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR \
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif \
    GDAL_HTTP_MULTIPLEX=YES

COPY requirements-serve.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Railway injects $PORT and expects the app to bind it; fall back to 8080 locally.
EXPOSE 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
