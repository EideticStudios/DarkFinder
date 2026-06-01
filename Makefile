.PHONY: dev-frontend dev-backend install lint typecheck \
        download process pipeline

PYTHON := .venv/bin/python
YEAR   ?= 2023

# ── Dev ────────────────────────────────────────────────────────────────────────

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && ../.venv/bin/uvicorn app.main:app --reload

# ── Setup ──────────────────────────────────────────────────────────────────────

install:
	cd frontend && npm install
	cd backend && uv venv .venv --python 3.12 && uv pip install -r requirements.txt --python .venv/bin/python

# ── Quality ───────────────────────────────────────────────────────────────────

lint:
	cd frontend && npm run lint
	cd backend && .venv/bin/ruff check app/

typecheck:
	cd frontend && npx tsc --noEmit

# ── Data pipeline ─────────────────────────────────────────────────────────────
# Usage:
#   make download YEAR=2023
#   make download YEAR=2023 BBOX="-130,24,-60,50"   # North America only
#   make process  YEAR=2023
#   make pipeline YEAR=2023   (download + process)

# Default to populated North America (CONUS, southern Canada, Mexico, Caribbean).
# Override for a different region: make download YEAR=2023 BBOX="-180,-90,180,90"
BBOX ?= -170,5,-40,75

download:
	cd backend && $(PYTHON) -m app.pipeline.download --year $(YEAR) $(if $(BBOX),--bbox "$(BBOX)",)

process:
	cd backend && $(PYTHON) -m app.pipeline.mosaic --year $(YEAR)

pipeline: download process

validate:
	cd backend && $(PYTHON) -m app.pipeline.validate --year $(YEAR)
