.PHONY: dev-frontend dev-backend install lint typecheck \
        download process skyglow pipeline validate

PYTHON := .venv/bin/python
YEAR   ?= 2023

# ── Dev ────────────────────────────────────────────────────────────────────────

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload

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

# ── Data pipeline (GEE) ─────────────────────────────────────────────────────
# Requires: earthengine authenticate  (one-time)
#
# Usage:
#   make download YEAR=2023                           # default bbox (North America)
#   make download YEAR=2023 BBOX="-130,24,-60,50"     # custom bbox
#   make process  YEAR=2023
#   make pipeline YEAR=2023   (download + process)

BBOX ?= -170,5,-40,75

download:
	cd backend && $(PYTHON) -m app.pipeline.download --year $(YEAR) $(if $(BBOX),--bbox "$(BBOX)",)

process:
	cd backend && $(PYTHON) -m app.pipeline.mosaic --year $(YEAR)
	cd backend && $(PYTHON) -m app.pipeline.skyglow --year $(YEAR)

skyglow:
	cd backend && $(PYTHON) -m app.pipeline.skyglow --year $(YEAR)

pipeline: download process

validate:
	cd backend && $(PYTHON) -m app.pipeline.validate --year $(YEAR)
