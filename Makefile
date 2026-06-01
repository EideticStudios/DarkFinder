.PHONY: dev-frontend dev-backend install lint typecheck \
        download download-nasa process pipeline

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
#   make download YEAR=2023                          # EOG global composite
#   make download YEAR=2023 URL="https://..."        # EOG with explicit URL
#   make download-nasa YEAR=2023                     # NASA VNP46A4 (v2 tiles)
#   make download-nasa YEAR=2023 BBOX="-130,24,-60,50"
#   make process  YEAR=2023
#   make pipeline YEAR=2023   (download + process)

BBOX ?= -170,5,-40,75

download:
	cd backend && $(PYTHON) -m app.pipeline.download --year $(YEAR) $(if $(URL),--url "$(URL)",)

download-nasa:
	cd backend && $(PYTHON) -m app.pipeline.download_nasa --year $(YEAR) $(if $(BBOX),--bbox "$(BBOX)",)

process:
	cd backend && $(PYTHON) -m app.pipeline.mosaic --year $(YEAR)

pipeline: download process

validate:
	cd backend && $(PYTHON) -m app.pipeline.validate --year $(YEAR)
