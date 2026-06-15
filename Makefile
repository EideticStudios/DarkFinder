.PHONY: dev dev-frontend dev-backend install auth setup lint typecheck \
        download process skyglow pipeline validate

PYTHON := .venv/bin/python
YEAR   ?= 2023

# ── Dev ────────────────────────────────────────────────────────────────────────

# Run both servers from the repo root. One Ctrl-C stops both.
dev:
	@trap 'kill 0' INT; \
	(cd backend && .venv/bin/uvicorn app.main:app --reload) & \
	(cd frontend && npm run dev) & \
	wait

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload

# ── Setup ──────────────────────────────────────────────────────────────────────

# One-time bootstrap: deps, Earth Engine auth, then download + process the data.
setup: install auth pipeline

install:
	cd frontend && npm install
	cd backend && uv venv .venv --python 3.12 && uv pip install -r requirements.txt --python .venv/bin/python

# Earth Engine ships its CLI inside the backend venv (not on PATH); run it from there.
auth:
	cd backend && .venv/bin/earthengine authenticate

# ── Quality ───────────────────────────────────────────────────────────────────

lint:
	cd frontend && npm run lint
	cd backend && .venv/bin/ruff check app/

typecheck:
	cd frontend && npx tsc --noEmit

# ── Data pipeline (GEE) ─────────────────────────────────────────────────────
# Requires: earthengine authenticate  (one-time)
#
# Usage:
#   make download YEAR=2023                           # global (default)
#   make download YEAR=2023 BBOX="-130,24,-60,50"     # custom bbox
#   make process  YEAR=2023
#   make pipeline YEAR=2023   (download + process)

download:
	cd backend && $(PYTHON) -m app.pipeline.download --year $(YEAR) $(if $(BBOX),--bbox "$(BBOX)",--global)

process:
	cd backend && $(PYTHON) -m app.pipeline.mosaic --year $(YEAR)
	cd backend && $(PYTHON) -m app.pipeline.skyglow --year $(YEAR)

skyglow:
	cd backend && $(PYTHON) -m app.pipeline.skyglow --year $(YEAR)

pipeline: download process

validate:
	cd backend && $(PYTHON) -m app.pipeline.validate --year $(YEAR)
